from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def assign_faces_to_tracks(faces: list[dict], tracked_persons: list[dict]) -> dict[int, dict]:
    """Ordnet pro Analyseframe höchstens ein Gesicht einem Track zu."""
    candidates = []

    for face_index, face in enumerate(faces):
        fx1, fy1, fx2, fy2 = face["bbox"]
        face_cx = (fx1 + fx2) / 2.0
        face_cy = (fy1 + fy2) / 2.0

        for person in tracked_persons:
            x1, y1, x2, y2 = person["bbox"]
            if not (x1 <= face_cx <= x2 and y1 <= face_cy <= y2):
                continue

            person_width = max(1.0, float(x2 - x1))
            person_height = max(1.0, float(y2 - y1))
            expected_head_x = (x1 + x2) / 2.0
            expected_head_y = y1 + 0.20 * person_height

            score = (
                ((face_cx - expected_head_x) / person_width) ** 2
                + ((face_cy - expected_head_y) / person_height) ** 2
            )
            candidates.append((score, face_index, person))

    candidates.sort(key=lambda item: item[0])

    assignments: dict[int, dict] = {}
    used_tracks: set[int] = set()

    for _, face_index, person in candidates:
        track_id = int(person["track_id"])
        if face_index in assignments or track_id in used_tracks:
            continue
        assignments[face_index] = person
        used_tracks.add(track_id)

    return assignments


def _analyze_video(video_path, job_dir=None, progress_cb=None) -> dict:
    """Compatibility entry point: run both optional-review stages automatically."""
    from .persons.tracking_stage import run_tracking
    from .persons.identity_stage import run_identities
    from .persons import stage_state
    base = Path(job_dir) if job_dir else Path(video_path).parent
    run_tracking(video_path, base, progress_cb)
    snapshot = run_identities(video_path, base, progress_cb)
    output = stage_state.root(base)
    return {"video_path": str(video_path), "output_dir": str(output),
            "persons": snapshot["persons"], "tracks": snapshot["tracks"],
            "unassigned_tracks": snapshot["unassigned_tracks"],
            "track_to_person": {t["track_id"]: t["person_id"] for t in snapshot["tracks"] if t["person_id"] is not None},
            "review_snapshot": snapshot}


def _build_web_result(result: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Wandelt den aktuellen Review-Stand in das bestehende Web-App-Format um."""
    snapshot = result["review_snapshot"]
    rows = []
    for person in snapshot["persons"]:
        row = dict(person)
        for field in ("track_ids", "segments", "appearances", "attributes", "face_ids", "valid_identity_crop_ids", "fallback_crop_ids"):
            row[field] = json.dumps(row[field], ensure_ascii=False)
        rows.append(row)
    return pd.DataFrame(rows), snapshot["faces"]


def analyze_persons(
    video_path: str | Path,
    job_dir: str | None = None,
    progress_cb=None,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Öffentliche Schnittstelle für backend/app.py.

    Rückgabe bleibt kompatibel zur bisherigen Web-App:
        persons_df, faces
    """
    result = _analyze_video(
        video_path=video_path,
        job_dir=job_dir,
        progress_cb=progress_cb,
    )

    persons_df, faces = _build_web_result(result)

    if progress_cb:
        progress_cb(
            f"Personenanalyse abgeschlossen: {len(persons_df)} Personen",
            100,
            100,
        )

    return persons_df, faces


def print_person_summary(result: dict) -> None:
    print()
    print("PERSONEN")
    print("========")

    for person in result["persons"]:
        track_text = ", ".join(str(track_id) for track_id in person["track_ids"])
        appearance_text = ", ".join(
            f"{appearance['start_s']:.2f}–{appearance['end_s']:.2f}"
            for appearance in person["appearances"]
        )
        print(
            f"Person {person['person_id']:03d} | "
            f"Tracks: {track_text} | Zeiten: {appearance_text}"
        )

    print()
    print("NICHT ZUGEORDNETE TRACKS")
    print("========================")

    for track in result["unassigned_tracks"]:
        print(
            f"Track {int(track['track_id']):03d} | "
            f"Szene {int(track['scene_id'])} | "
            f"{float(track['start_s']):.2f}–{float(track['end_s']):.2f} s | "
            f"Faces {int(track.get('faces_usable', 0))}/{int(track.get('faces_assigned', 0))}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="descraibe-Personenanalyse")
    parser.add_argument("video", type=Path, help="Pfad zur Videodatei")
    args = parser.parse_args()

    result = _analyze_video(args.video)
    print_person_summary(result)


if __name__ == "__main__":
    main()
