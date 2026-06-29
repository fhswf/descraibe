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


class GPTGenerationAborted(RuntimeError):
    """Raised when generation should stop instead of failing every remaining slot."""


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


def _abort_message(consecutive_errors: int, last_error: Exception) -> str:
    return (
        f"GPT generation aborted after {consecutive_errors} consecutive OpenAI connection/API failures. "
        "This usually points to staging egress, DNS, proxy, TLS, or OpenAI API reachability problems. "
        f"Last error: {_error_message(last_error)}"
    )


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


def _append_with_limit(lines: List[str], line: str, current_chars: int, max_chars: int) -> int:
    """Append line while respecting a soft character budget."""
    if not line:
        return current_chars
    extra = len(line) + (1 if lines else 0)
    if current_chars + extra > max_chars:
        return current_chars
    lines.append(line)
    return current_chars + extra


def _format_transcript_context(
    transcript_df: Optional[pd.DataFrame],
    slot_start_s: float,
    slot_end_s: float,
    *,
    window_before_s: float,
    window_after_s: float,
    max_chars: int,
) -> str:
    """Return nearby transcript lines for context, bounded for prompt size."""
    if transcript_df is None or transcript_df.empty or max_chars <= 0:
        return ""

    required = {"start_s", "end_s", "text"}
    if not required.issubset(set(transcript_df.columns)):
        return ""

    ctx_start = slot_start_s - max(0.0, window_before_s)
    ctx_end = slot_end_s + max(0.0, window_after_s)
    df = transcript_df.copy()
    df = df[(df["end_s"] >= ctx_start) & (df["start_s"] <= ctx_end)]
    if df.empty:
        return ""

    lines: List[str] = []
    current_chars = 0
    for _, r in df.sort_values("start_s").iterrows():
        text = " ".join(str(r.get("text", "")).split())
        if not text:
            continue
        line = f"[{float(r['start_s']):.1f}-{float(r['end_s']):.1f}s] {text}"
        new_count = _append_with_limit(lines, line, current_chars, max_chars)
        if new_count == current_chars:
            break
        current_chars = new_count

    return "\n".join(lines)


def _format_previous_descriptions_context(
    previous_records: List[Dict[str, Any]],
    *,
    max_chars: int,
) -> str:
    """Return previous successful AD texts, prioritising the most recent ones."""
    if not previous_records or max_chars <= 0:
        return ""

    selected_reversed: List[str] = []
    current_chars = 0
    for rec in reversed(previous_records):
        if not rec.get("ok") or rec.get("skipped"):
            continue
        text = " ".join(str(rec.get("text") or "").split())
        if not text:
            continue
        line = (
            f"Slot {rec.get('slot')} "
            f"({float(rec.get('start_s', 0.0)):.1f}-{float(rec.get('end_s', 0.0)):.1f}s): "
            f"{text}"
        )
        extra = len(line) + (1 if selected_reversed else 0)
        if current_chars + extra > max_chars:
            break
        selected_reversed.append(line)
        current_chars += extra

    return "\n".join(reversed(selected_reversed))


def _build_context_block(
    transcript_df: Optional[pd.DataFrame],
    previous_records: List[Dict[str, Any]],
    slot_start_s: float,
    slot_end_s: float,
    *,
    transcript_window_before_s: float,
    transcript_window_after_s: float,
    transcript_context_max_chars: int,
    previous_context_max_chars: int,
) -> str:
    transcript_context = _format_transcript_context(
        transcript_df,
        slot_start_s,
        slot_end_s,
        window_before_s=transcript_window_before_s,
        window_after_s=transcript_window_after_s,
        max_chars=transcript_context_max_chars,
    )
    previous_context = _format_previous_descriptions_context(
        previous_records,
        max_chars=previous_context_max_chars,
    )
    if not transcript_context and not previous_context:
        return ""

    parts = [
        "## Kontext",
        "Nutze diesen Kontext, um Wiederholungen zu vermeiden.",
        "Wiederhole keine Informationen, die im Audio-Transkript bereits genannt werden.",
        "Wiederhole keine visuellen Details aus vorherigen AD-Slots, außer sie haben sich sichtbar verändert oder sind für das Verständnis zwingend nötig.",
    ]
    if transcript_context:
        parts.extend(["", "### Audio-Transkript im Umfeld des Slots", transcript_context])
    if previous_context:
        parts.extend(["", "### Vorherige AD-Slots", previous_context])
    return "\n".join(parts)


def _build_persons_context(
    persons_df: Optional[pd.DataFrame],
    slot_start_s: float,
    slot_end_s: float,
) -> str:
    """Build a context block with person information for a specific slot.

    Identifies persons appearing in the given time window and provides
    their names and visual descriptions. Also indicates first mentions
    (Erstnennung) vs subsequent mentions (Folgebenennung).

    Args:
        persons_df: DataFrame with person data from person_analysis
        slot_start_s: Start time of the current AD slot
        slot_end_s: End time of the current AD slot

    Returns:
        Formatted context string with person information
    """
    if persons_df is None or persons_df.empty:
        return ""

    # Find persons that appear in this time window
    persons_in_slot = persons_df[
        (persons_df["first_seen_ts"] <= slot_end_s) &
        (persons_df["last_seen_ts"] >= slot_start_s)
    ]

    if persons_in_slot.empty:
        return ""

    parts = ["", "### Personen im Slot"]

    for _, person in persons_in_slot.iterrows():
        name = str(person.get("name") or f"Person {person.get('person_id', '?')}")
        description = str(person.get("description") or "")

        # Determine if this is a first mention (Erstnennung)
        # ERSTNENNUNG = person's first appearance falls WITHIN this slot
        # FOLGEBENENNUNG = person was already visible in earlier slots
        first_seen = float(person.get("first_seen_ts", float("inf")))
        is_first_mention = slot_start_s <= first_seen <= slot_end_s

        mention_type = "ERSTNENNUNG" if is_first_mention else "FOLGEBENENNUNG"

        # Build person entry
        entry = f"- **{name}** [{mention_type}]"
        if description and description != name:
            entry += f": {description}"

        parts.append(entry)

    return "\n".join(parts)


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
    transcript_df: Optional[pd.DataFrame] = None,
    persons_df: Optional[pd.DataFrame] = None,
    model: str = "gpt-5-mini-2025-08-07",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    detail: str = "low",
    cut: str = "broadcast",
    syllables_per_second: float = 6.0,
    syl_safety_factor: float = 0.85,
    max_rewrite_attempts: int = 2,
    max_consecutive_gpt_errors: int = 3,
    min_slot_s: float = 0.5,
    transcript_window_before_s: float = 20.0,
    transcript_window_after_s: float = 5.0,
    transcript_context_max_chars: int = 2000,
    previous_context_max_chars: int = 3000,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
) -> List[Dict[str, Any]]:
    """Call OpenAI vision API for each AD slot and return result records.

    Args:
        slots_df       – DataFrame with slot/start_s/end_s columns
        slot_map_df    – DataFrame mapping slot → image_path
        system_prompt  – combined system + AD rules text
        user_prompt_base – base user instruction text
        transcript_df   – optional transcript segments with start_s/end_s/text columns
        api_key        – OpenAI API key
        cut            – "broadcast" or "directors"
        progress_cb    – called with (message, current_slot_index, total_slots)

    Returns: list of record dicts (slot, start_s, end_s, duration_s, text, ok, skipped, reason)
    """
    import os
    from openai import OpenAI

    # OPENAI_BASE_URL allows routing to any OpenAI-compatible endpoint
    # (e.g. https://hub.ki.fh-swf.de/v1). Injected via k8s Secret (envFrom).
    # Falls back to the standard OpenAI API if not set.
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None

    # Allow per-request api_key override (e.g. from the UI), otherwise the
    # OpenAI client picks up OPENAI_API_KEY from the environment automatically.
    effective_api_key = str(api_key).strip() if api_key and str(api_key).strip() else None

    client = OpenAI(
        **({"api_key": effective_api_key} if effective_api_key else {}),
        **({"base_url": base_url} if base_url else {}),
    )

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
    consecutive_gpt_errors = 0

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

        context_block = _build_context_block(
            transcript_df,
            records,
            s,
            e,
            transcript_window_before_s=transcript_window_before_s,
            transcript_window_after_s=transcript_window_after_s,
            transcript_context_max_chars=transcript_context_max_chars,
            previous_context_max_chars=previous_context_max_chars,
        )
        if context_block:
            user_text += "\n\n" + context_block

        # Inject person context with Erstnennung/Folgebenennung flags
        persons_context = _build_persons_context(persons_df, s, e)
        if persons_context:
            user_text += "\n\n" + persons_context

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
            consecutive_gpt_errors = 0

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
            if _is_retryable_openai_error(exc):
                consecutive_gpt_errors += 1
                if max_consecutive_gpt_errors > 0 and consecutive_gpt_errors >= max_consecutive_gpt_errors:
                    records.append(rec)
                    raise GPTGenerationAborted(_abort_message(consecutive_gpt_errors, exc)) from exc
            else:
                consecutive_gpt_errors = 0

        records.append(rec)

    if progress_cb:
        progress_cb("Done", total, total)

    return records
