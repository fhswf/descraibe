"""gpt_description.py – OpenAI vision API GPT calls for AD generation (Step 08)."""
from __future__ import annotations

import base64
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import logging
import pandas as pd


# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


def _is_retryable_openai_error(exc: Exception) -> bool:
    """Return True for transient OpenAI/client failures worth retrying."""
    name = exc.__class__.__name__
    if name in {
        "APIConnectionError",
        "APITimeoutError",
        "RateLimitError",
        "InternalServerError",
    }:
        return True

    status_code = getattr(exc, "status_code", None)
    return status_code == 429 or (isinstance(status_code, int) and status_code >= 500)


def _error_message(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    return " ".join(msg.split())


def _completion_with_retries(client: Any, *, max_attempts: int = 3, **kwargs: Any) -> Any:
    """Call OpenAI chat completions and retry transient API/client failures."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts or not _is_retryable_openai_error(exc):
                raise

            wait_s = min(2 ** (attempt - 1), 8)
            logger.warning(
                "OpenAI completion failed on attempt %s/%s; retrying in %ss: %s",
                attempt,
                max_attempts,
                wait_s,
                _error_message(exc),
            )
            time.sleep(wait_s)

    if last_exc:
        raise last_exc
    raise RuntimeError("OpenAI completion failed without an exception")


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
    model: str = "gpt-5-mini-2025-08-07",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    detail: str = "low",
    cut: str = "broadcast",
    syllables_per_second: float = 6.0,
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
            ip = str(r.get("img_path", ""))
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
            "original_text": "",
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
            resp = _completion_with_retries(
                client,
                model=model,
                messages=messages,
                temperature=float(temperature),
                max_completion_tokens=int(max_tokens),
                store=True,
            )
            txt_original = (resp.choices[0].message.content or "").strip()
            txt_final = txt_original
            logger.info(f"Slot {slot_id}: Initial GPT response: '{txt_original[:50]}...' ({len(txt_original)} chars)")

            # Syllable rewrite loop (broadcast only)
            sylls_original: Optional[int] = None
            sylls_final: Optional[int] = None
            attempts = 0
            if cut == "broadcast" and syll_limit is not None:
                sylls = _count_syllables(txt_final)
                sylls_original = sylls
                logger.info(f"Slot {slot_id}: Initial syllables: {sylls}, limit: {syll_limit}")
                while attempts < max_rewrite_attempts and sylls > syll_limit and sylls > 0:
                    attempts += 1
                    logger.info(f"Slot {slot_id}: Rewrite attempt {attempts}/{max_rewrite_attempts} (syllables: {sylls} > {syll_limit})")
                    rewrite = (
                        f"KÜRZEN: Maximal {syll_limit} Silben, passt in {dur:.2f}s. "
                        "Nur den finalen AD-Text zurückgeben.\n\n"
                        f"TEXT:\n{txt_final}"
                    )
                    rr = _completion_with_retries(
                        client,
                        model=model,
                        messages=_build_messages(system_prompt, rewrite, [], detail="low"),
                        temperature=float(temperature),
                        max_completion_tokens=int(max_tokens),
                        store=True,
                    )
                    txt_final = (rr.choices[0].message.content or "").strip()
                    sylls = _count_syllables(txt_final)
                    logger.info(f"Slot {slot_id}: Attempt {attempts} result: {sylls} syllables")

                sylls_final = sylls
                if sylls > syll_limit:
                    logger.warning(f"Slot {slot_id}: Could not meet syllable limit ({sylls} > {syll_limit}) after {attempts} attempts")
                elif sylls > 0:
                    logger.info(f"Slot {slot_id}: Syllable limit met: {sylls} <= {syll_limit}")

            rec.update({
                "ok": True,
                "skipped": False,
                "text": txt_final,
                "original_text": txt_original,
                "rewrite_attempts": attempts,
                "syllable_limit": syll_limit,
                "syllables_original": sylls_original,
                "syllables_final": sylls_final,
            })

        except Exception as exc:
            msg = _error_message(exc)
            logger.error("Slot %s: GPT error: %s", slot_id, msg)
            rec.update({
                "ok": False,
                "reason": "gpt_error",
                "error": {
                    "type": exc.__class__.__name__,
                    "message": msg,
                },
                "text": "",
            })

        records.append(rec)

    if progress_cb:
        progress_cb("Done", total, total)

    return records
