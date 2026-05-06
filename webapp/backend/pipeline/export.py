"""export.py – write AD output files from result records (Step 08/09)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional


def _srt_time(seconds: float) -> str:
    s = max(0.0, float(seconds))
    ms = int(round(s * 1000))
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1_000)
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"


def _frame_time(seconds: float, fps: int = 25) -> str:
    s = max(0.0, float(seconds))
    total_frames = int(round(s * fps))
    hh, rem = divmod(total_frames, 3600 * fps)
    mm, rem = divmod(rem, 60 * fps)
    ss, ff = divmod(rem, fps)
    return f"{hh:02}:{mm:02}:{ss:02},{ff:02}"


def _clean_line(txt: str) -> str:
    return " ".join((txt or "").split())


def _record_note(rec: Dict[str, Any]) -> str:
    error = rec.get("error")
    if isinstance(error, dict):
        return _clean_line(error.get("message", ""))
    return _clean_line(rec.get("reason", ""))


def write_outputs(
    run_folder: Path,
    records: List[Dict[str, Any]],
    cut: str,
) -> Dict[str, str]:
    """Write output files for one cut (broadcast or directors).

    Returns a dict mapping file label → absolute path string.
    """
    run_folder = Path(run_folder)
    run_folder.mkdir(parents=True, exist_ok=True)

    paths: Dict[str, str] = {}

    if cut == "broadcast":
        # 1) GESAMT text
        gesamt_path = run_folder / "AD_GESAMT_Broadcast.txt"
        _write_gesamt(gesamt_path, records)
        paths["gesamt_txt"] = str(gesamt_path)

        # 2) Qualitätsdatei
        quality_path = run_folder / "Qualitätsdatei_Broadcast.txt"
        _write_quality(quality_path, records)
        paths["quality_txt"] = str(quality_path)

        # 3) Frazier CSV
        frazier_path = run_folder / "audio_description_frazier.csv"
        _write_frazier(frazier_path, records)
        paths["frazier_csv"] = str(frazier_path)

    else:  # directors
        gesamt_path = run_folder / "AD_GESAMT_DirectorsCut.txt"
        _write_gesamt(gesamt_path, records)
        paths["gesamt_txt"] = str(gesamt_path)

        quality_path = run_folder / "Qualitätsdatei_DirectorsCut.txt"
        _write_quality(quality_path, records)
        paths["quality_txt"] = str(quality_path)

        tsv_path = run_folder / "audio_description_directors_cut.tsv"
        _write_tsv(tsv_path, records)
        paths["directors_tsv"] = str(tsv_path)

    return paths


# ── Writers ────────────────────────────────────────────────────────────────────

def _write_gesamt(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            if rec.get("skipped") or not rec.get("ok"):
                continue
            s = _srt_time(rec["start_s"])
            e = _srt_time(rec["end_s"])
            txt = _clean_line(rec.get("text", ""))
            f.write(f"{s} --> {e}\n{txt}\n\n")


def _write_quality(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write("Slot\tStart\tEnde\tDauer\tStatus\tText\tHinweis\n")
        for rec in records:
            status = "OK" if rec.get("ok") and not rec.get("skipped") else \
                     ("SKIP" if rec.get("skipped") else "ERROR")
            text = _clean_line(rec.get("text", "")) if status == "OK" else ""
            f.write(
                f"{rec['slot']}\t"
                f"{_srt_time(rec['start_s'])}\t"
                f"{_srt_time(rec['end_s'])}\t"
                f"{rec['duration_s']:.3f}\t"
                f"{status}\t"
                f"{text}\t"
                f"{_record_note(rec)}\n"
            )


def _write_frazier(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Slot", "Startzeit", "Endzeit", "Dauer_s", "Audiodeskription"])
        for rec in records:
            if rec.get("skipped") or not rec.get("ok"):
                continue
            writer.writerow([
                rec["slot"],
                _frame_time(rec["start_s"]),
                _frame_time(rec["end_s"]),
                rec["duration_s"],
                _clean_line(rec.get("text", "")),
            ])


def _write_tsv(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write("start\tende\ttext\n")
        for rec in records:
            if rec.get("skipped") or not rec.get("ok"):
                continue
            txt = _clean_line(rec.get("text", ""))
            f.write(f"{_srt_time(rec['start_s'])}\t{_srt_time(rec['end_s'])}\t{txt}\n")
