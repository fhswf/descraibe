"""ad_slots.py – convert pauses → AD slots + quality assessment (Steps 04b-04d)."""
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
    whisper_overlap_threshold: float = 0.5,
) -> pd.DataFrame:
    """Convert pause DataFrames into AD slots.

    Applies padding and minimum duration filter.  When `speech_df` is provided
    slots that overlap significantly with detected speech are flagged and removed.

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
    slots.insert(0, "slot", range(len(slots)))

    # Filter using whisper speech segments if provided
    if speech_df is not None and not speech_df.empty and not slots.empty:
        keep = []
        for _, s_row in slots.iterrows():
            overlap = _total_overlap(s_row["start_s"], s_row["end_s"], speech_df)
            ratio = overlap / max(s_row["dur_s"], 1e-9)
            keep.append(ratio < whisper_overlap_threshold)
        slots = slots[keep].reset_index(drop=True)
        slots["slot"] = range(len(slots))

    return slots


def _total_overlap(start: float, end: float, speech_df: pd.DataFrame) -> float:
    total = 0.0
    for _, row in speech_df.iterrows():
        overlap = max(0.0, min(end, row["end_s"]) - max(start, row["start_s"]))
        total += overlap
    return total


def quality_report(
    pauses_df: pd.DataFrame,
    speech_df: pd.DataFrame,
    slots_df: pd.DataFrame,
) -> dict:
    """Generate a quality report comparing pauses with whisper speech.

    Returns dict with:
        - total_pauses, total_slots
        - green_count / yellow_count / red_count
        - rows: list of dicts per pause with traffic-light status
    """
    rows = []
    for _, p in pauses_df.iterrows():
        overlap = _total_overlap(p["start_s"], p["end_s"], speech_df)
        ratio = overlap / max(p["dur_s"], 1e-9)

        if ratio < 0.1:
            status = "green"
        elif ratio < 0.4:
            status = "yellow"
        else:
            status = "red"

        rows.append({
            "start_s": p["start_s"],
            "end_s": p["end_s"],
            "dur_s": p["dur_s"],
            "speech_overlap_s": round(overlap, 3),
            "overlap_ratio": round(ratio, 3),
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
