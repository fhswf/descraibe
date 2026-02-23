"""gpt_description.py – OpenAI vision API GPT calls for AD generation (Step 08)."""
from __future__ import annotations

import base64
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd


# ── Image helpers ──────────────────────────────────────────────────────────────

def _img_to_data_url(image_path: str) -> str:
    p = Path(image_path)
    b = p.read_bytes()
    mime = "image/jpeg"
    if p.suffix.lower() == ".png":
        mime = "image/png"
    elif p.suffix.lower() == ".webp":
        mime = "image/webp"
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


def _build_messages(system_text: str, user_text: str, image_paths: List[str], detail: str = "low") -> List[dict]:
    content: List[dict] = []
    if user_text.strip():
        content.append({"type": "text", "text": user_text})
    for ip in image_paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": _img_to_data_url(ip), "detail": detail}
        })
    msgs: List[dict] = []
    if system_text.strip():
        msgs.append({"role": "system", "content": system_text})
    msgs.append({"role": "user", "content": content})
    return msgs


# ── Syllable helpers (optional pyphen) ────────────────────────────────────────

def _count_syllables(text: str) -> int:
    try:
        import pyphen
        dic = pyphen.Pyphen(lang="de_DE")
        return sum(len(dic.inserted(w).split("-")) for w in re.findall(r"\w+", text))
    except Exception:
        return -1


# ── Main function ──────────────────────────────────────────────────────────────

def describe_slots(
    slots_df: pd.DataFrame,
    slot_map_df: pd.DataFrame,
    system_prompt: str,
    user_prompt_base: str,
    *,
    api_key: str,
    model: str = "gpt-4o",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    detail: str = "low",
    cut: str = "broadcast",
    syllables_per_second: float = 12.0,
    syl_safety_factor: float = 0.85,
    max_rewrite_attempts: int = 2,
    min_slot_s: float = 0.5,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
) -> List[Dict[str, Any]]:
    """Call OpenAI vision API for each AD slot and return result records.

    Args:
        slots_df       – DataFrame with slot/start_s/end_s columns
        slot_map_df    – DataFrame mapping slot → image_path
        system_prompt  – combined system + AD rules text
        user_prompt_base – base user instruction text
        api_key        – OpenAI API key
        cut            – "broadcast" or "directors"
        progress_cb    – called with (message, current_slot_index, total_slots)

    Returns: list of record dicts (slot, start_s, end_s, duration_s, text, ok, skipped, reason)
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    # Build a slot_id → image_path index
    img_index: Dict[int, List[str]] = {}
    if slot_map_df is not None and not slot_map_df.empty:
        for _, r in slot_map_df.iterrows():
            sid = int(r["slot"])
            ip = str(r.get("image_path", ""))
            if ip and Path(ip).exists():
                img_index.setdefault(sid, []).append(ip)

    # Normalise column names
    col_slot  = "slot"  if "slot"  in slots_df.columns else "Slot"
    col_start = "start_s" if "start_s" in slots_df.columns else "start"
    col_end   = "end_s"   if "end_s"   in slots_df.columns else "end"

    records: List[Dict[str, Any]] = []
    total = len(slots_df)

    for idx, (_, row) in enumerate(slots_df.iterrows()):
        slot_id = int(row[col_slot])
        s = float(row[col_start])
        e = float(row[col_end])
        dur = max(0.0, e - s)

        rec: Dict[str, Any] = {
            "cut": cut,
            "slot": slot_id,
            "start_s": round(s, 3),
            "end_s": round(e, 3),
            "duration_s": round(dur, 3),
            "ok": False,
            "skipped": False,
            "reason": "",
            "num_images": 0,
            "text": "",
        }

        if progress_cb:
            progress_cb(f"Slot {idx+1}/{total}: {s:.1f}s–{e:.1f}s", idx, total)

        if dur < min_slot_s:
            rec.update({"ok": True, "skipped": True, "reason": "slot_too_short",
                        "text": "[SKIP:slot_too_short]"})
            records.append(rec)
            continue

        imgs = img_index.get(slot_id, [])
        rec["num_images"] = len(imgs)

        if not imgs:
            rec.update({"ok": True, "skipped": True, "reason": "no_images",
                        "text": "[SKIP:no_images]"})
            records.append(rec)
            continue

        # Build syllable limit (broadcast only)
        syll_limit: Optional[int] = None
        if cut == "broadcast":
            cap = dur * syllables_per_second
            syll_limit = max(1, int(cap * syl_safety_factor))

        # Build user prompt
        if cut == "broadcast":
            user_text = (
                user_prompt_base.strip()
                + f"\n\n## Slot-Information\nStart={s:.3f}\nEnde={e:.3f}\nSprechpause={dur:.3f}\n"
                + (f"MaxSilben={syll_limit}\n" if syll_limit else "")
            )
        else:
            user_text = (
                user_prompt_base.strip()
                + "\n\n## Director's Cut\nErstelle eine ausführliche Audiodeskription.\n"
                + f"Start={s:.3f}\nEnde={e:.3f}\nSlotDauer={dur:.3f}\n"
            )

        try:
            messages = _build_messages(system_prompt, user_text, imgs, detail=detail)
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=float(temperature),
                max_completion_tokens=int(max_tokens),
            )
            txt_final = (resp.choices[0].message.content or "").strip()

            # Syllable rewrite loop (broadcast only)
            if cut == "broadcast" and syll_limit is not None:
                attempts = 0
                sylls = _count_syllables(txt_final)
                while attempts < max_rewrite_attempts and sylls > syll_limit and sylls > 0:
                    attempts += 1
                    rewrite = (
                        f"KÜRZEN: Maximal {syll_limit} Silben, passt in {dur:.2f}s. "
                        "Nur den finalen AD-Text zurückgeben.\n\n"
                        f"TEXT:\n{txt_final}"
                    )
                    rr = client.chat.completions.create(
                        model=model,
                        messages=_build_messages(system_prompt, rewrite, [], detail="low"),
                        temperature=float(temperature),
                        max_completion_tokens=int(max_tokens),
                    )
                    txt_final = (rr.choices[0].message.content or "").strip()
                    sylls = _count_syllables(txt_final)

            rec.update({"ok": True, "skipped": False, "text": txt_final})

        except Exception as exc:
            rec.update({"ok": False, "reason": f"gpt_error:{exc}", "text": f"[ERROR:{exc}]"})

        records.append(rec)

    if progress_cb:
        progress_cb("Done", total, total)

    return records
