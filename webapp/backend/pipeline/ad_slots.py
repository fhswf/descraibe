"""ad_slots.py – convert pauses → AD slots + quality assessment (Steps 04b-04d).

Fidelity note (aligned with FINAL notebook step 04b):
- Whisper overlap filter uses a fixed absolute epsilon (default 0.05 s) matching
  the notebook's WHISPER_OVERLAP_EPS = 0.05 constant, NOT a slot-duration ratio.
- Quality report uses absolute overlap thresholds: red >= 0.20 s, yellow >= 0.05 s.
"""
from __future__ import annotations

from typing import Optional
import pandas as pd


def pauses_to_slots(
    pauses_df: pd.DataFrame,
    *,
    min_slot_s: float = 1.0,
    pad_in_s: float = 0.0,
    pad_out_s: float = 0.0,
    speech_df: Optional[pd.DataFrame] = None,
    whisper_overlap_eps_s: float = 0.05,  # absolute epsilon, not ratio
) -> pd.DataFrame:
    """Convert pause DataFrames into AD slots.

    Applies padding and minimum duration filter.  When `speech_df` is provided,
    slots that overlap with any speech segment by more than `whisper_overlap_eps_s`
    seconds are removed (absolute epsilon matching the notebook's logic).

    Returns: DataFrame(slot, start_s, end_s, dur_s)
    """
    rows = []
    for _, row in pauses_df.iterrows():
        start = float(row["start_s"]) + pad_in_s
        end = float(row["end_s"]) - pad_out_s
        dur = end - start
        if dur >= min_slot_s:
            rows.append({"start_s": round(start, 3),
                         "end_s": round(end, 3),
                         "dur_s": round(dur, 3)})

    slots = pd.DataFrame(rows if rows else [], columns=["start_s", "end_s", "dur_s"])
    slots.insert(0, "slot", range(1, len(slots) + 1))

    # Filter using whisper speech segments if provided
    if speech_df is not None and not speech_df.empty and not slots.empty:
        keep = []
        for _, s_row in slots.iterrows():
            has_speech = _any_overlap_exceeds(
                s_row["start_s"], s_row["end_s"], speech_df, whisper_overlap_eps_s
            )
            keep.append(not has_speech)
        slots = slots[keep].reset_index(drop=True)
        slots["slot"] = range(1, len(slots) + 1)

    return slots


def _any_overlap_exceeds(
    start: float, end: float, speech_df: pd.DataFrame, eps_s: float
) -> bool:
    """Return True if any speech segment overlaps [start, end] by more than eps_s."""
    for _, row in speech_df.iterrows():
        overlap = max(0.0, min(end, float(row["end_s"])) - max(start, float(row["start_s"])))
        if overlap > eps_s:
            return True
    return False


def _total_overlap(start: float, end: float, speech_df: pd.DataFrame) -> float:
    """Return total seconds of overlap between [start, end] and all speech segments."""
    total = 0.0
    for _, row in speech_df.iterrows():
        overlap = max(0.0, min(end, float(row["end_s"])) - max(start, float(row["start_s"])))
        total += overlap
    return total


def quality_report(
    pauses_df: pd.DataFrame,
    speech_df: pd.DataFrame,
    slots_df: pd.DataFrame,
) -> dict:
    """Generate a quality report comparing pauses with silero/whisper speech.

    Traffic-light thresholds (absolute overlap, aligning with notebook step 04d):
      GREEN  : max speech overlap < 0.05 s
      YELLOW : max speech overlap 0.05 – 0.20 s
      RED    : max speech overlap >= 0.20 s

    Returns dict with:
        - total_pauses, total_slots
        - green_count / yellow_count / red_count
        - rows: list of dicts per pause with traffic-light status
    """
    RED_S = 0.20
    YELLOW_S = 0.05

    rows = []
    for _, p in pauses_df.iterrows():
        # Compute max single-segment overlap (notebook uses max, not total)
        max_ov = 0.0
        for _, sp in speech_df.iterrows():
            ov = max(0.0, min(float(p["end_s"]), float(sp["end_s"])) -
                         max(float(p["start_s"]), float(sp["start_s"])))
            if ov > max_ov:
                max_ov = ov

        if max_ov >= RED_S:
            status = "red"
        elif max_ov >= YELLOW_S:
            status = "yellow"
        else:
            status = "green"

        rows.append({
            "start_s": p["start_s"],
            "end_s": p["end_s"],
            "dur_s": p["dur_s"],
            "speech_overlap_max_s": round(max_ov, 3),
            "status": status,
        })

    green = sum(1 for r in rows if r["status"] == "green")
    yellow = sum(1 for r in rows if r["status"] == "yellow")
    red = sum(1 for r in rows if r["status"] == "red")

    return {
        "total_pauses": len(rows),
        "total_slots": len(slots_df),
        "green_count": green,
        "yellow_count": yellow,
        "red_count": red,
        "rows": rows,
    }
