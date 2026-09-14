from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd



PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = PROJECT_ROOT / "models"


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


def build_persons(tracks: list[dict], track_to_person: dict[int, int]) -> list[dict]:
    """Baut Personen nur aus Tracks mit FaceMoE-basierter Identitätszuordnung."""
    grouped_tracks: dict[int, list[dict]] = {}

    for track in tracks:
        track_id = int(track["track_id"])
        if track_id not in track_to_person:
            continue
        person_id = int(track_to_person[track_id])
        grouped_tracks.setdefault(person_id, []).append(track)

    persons = []

    for person_id in sorted(grouped_tracks):
        person_tracks = sorted(
            grouped_tracks[person_id],
            key=lambda item: (float(item["start_s"]), int(item["track_id"])),
        )

        segments = [
            {
                "track_id": int(track["track_id"]),
                "scene_id": int(track["scene_id"]),
                "start_s": float(track["start_s"]),
                "end_s": float(track["end_s"]),
                "start_frame": track.get("start_frame"),
                "end_frame": track.get("end_frame"),
            }
            for track in person_tracks
        ]

        appearances = [
            {"start_s": float(track["start_s"]), "end_s": float(track["end_s"])}
            for track in person_tracks
        ]

        persons.append(
            {
                "person_id": person_id,
                "name": f"Person {person_id}",
                "function": "",
                "track_ids": [int(track["track_id"]) for track in person_tracks],
                "segments": segments,
                "appearances": appearances,
                "first_seen_ts": min(item["start_s"] for item in appearances),
                "last_seen_ts": max(item["end_s"] for item in appearances),
                "attributes": {},
            }
        )

    return persons


def save_track_identities(
    output_path: Path,
    tracks: list[dict],
    track_to_person: dict[int, int],
) -> None:
    """Speichert Track-Zuordnungen, jedoch keine Embeddings."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerow(["person_id", "track_id", "assignment_source"])

        for track in sorted(tracks, key=lambda item: int(item["track_id"])):
            track_id = int(track["track_id"])
            if track_id in track_to_person:
                writer.writerow([int(track_to_person[track_id]), track_id, "facemoe_cluster"])
            else:
                writer.writerow(["", track_id, "unassigned_no_embedding"])


def save_persons(
    output_path: Path,
    video_path: Path,
    tracks: list[dict],
    persons: list[dict],
    unassigned_tracks: list[dict],
) -> None:
    """Speichert Personen und nicht zugeordnete Tracks getrennt."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    unassigned_data = []
    for track in sorted(unassigned_tracks, key=lambda item: int(item["track_id"])):
        unassigned_data.append(
            {
                "track_id": int(track["track_id"]),
                "scene_id": int(track["scene_id"]),
                "start_s": float(track["start_s"]),
                "end_s": float(track["end_s"]),
                "faces_assigned": int(track.get("faces_assigned", 0)),
                "start_frame": track.get("start_frame"),
                "end_frame": track.get("end_frame"),
                "faces_usable": int(track.get("faces_usable", 0)),
                "alignment_failures": int(track.get("alignment_failures", 0)),
                "embeddings_created": int(track.get("embeddings_created", 0)),
                "embedding_errors": int(track.get("embedding_errors", 0)),
            }
        )

    payload = {
        "video": video_path.name,
        "track_count": len(tracks),
        "person_count": len(persons),
        "unassigned_track_count": len(unassigned_data),
        "persons": persons,
        "unassigned_tracks": unassigned_data,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _analyze_video(video_path, job_dir=None, progress_cb=None) -> dict:
    """Compatibility entry point: run both optional-review stages automatically."""
    from .persons.tracking_stage import run_tracking
    from .persons.identity_stage import run_identities
    from .persons import stage_state
    base = Path(job_dir) if job_dir else Path(video_path).parent
    run_tracking(video_path, base, progress_cb)
    snapshot = run_identities(video_path, base, progress_cb)
    pointer = stage_state.active(base)
    output = stage_state.run_path(base, pointer["identity_run"], "identities")
    return {"video_path": str(video_path), "output_dir": str(output),
            "persons": snapshot["persons"], "tracks": snapshot["tracks"],
            "unassigned_tracks": snapshot["unassigned_tracks"],
            "track_to_person": {t["track_id"]: t["person_id"] for t in snapshot["tracks"] if t["person_id"] is not None},
            "review_snapshot": snapshot}


def _parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "ja"}


def _build_web_result(result: dict) -> tuple[pd.DataFrame, list[dict]]:
    """
    Wandelt das neue Personenergebnis in das Format um,
    das die bestehende descraibe-Web-App aktuell erwartet.
    """
    if "review_snapshot" in result:
        snapshot = result["review_snapshot"]
        rows = []
        for person in snapshot["persons"]:
            row = dict(person)
            for field in ("track_ids", "segments", "appearances", "attributes", "face_ids", "valid_identity_crop_ids", "fallback_crop_ids"):
                row[field] = json.dumps(row[field], ensure_ascii=False)
            rows.append(row)
        return pd.DataFrame(rows), snapshot["faces"]
    persons = result["persons"]
    track_to_person = result["track_to_person"]
    analysis_output_dir = Path(result["output_dir"])
    face_manifest_path = analysis_output_dir / "face_observations.csv"

    faces: list[dict] = []

    if face_manifest_path.is_file():
        with face_manifest_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=";")

            for row in reader:
                if not row.get("person_crop_path"):
                    continue
                face_id = int(row["face_id"])
                track_id = int(row["track_id"])
                person_id = track_to_person.get(track_id)

                relative_crop = str(row.get("person_crop_path", "")).replace("\\", "/")
                crop_path = (Path("person_analysis") / relative_crop).as_posix()

                face_bbox = [
                    int(float(row["face_x1"])),
                    int(float(row["face_y1"])),
                    int(float(row["face_x2"])),
                    int(float(row["face_y2"])),
                ]

                faces.append(
                    {
                        "face_id": face_id,
                        "track_id": track_id,
                        "person_id": int(person_id) if person_id is not None else None,
                        "scene_id": int(row["scene_id"]),
                        "frame_number": int(row["frame_number"]),
                        "timestamp_s": float(row["timestamp_s"]),
                        "crop_path": crop_path,
                        "person_crop_path": crop_path,
                        "bbox": face_bbox,
                        "face_bbox": face_bbox,
                        "confidence": float(row["face_confidence"]),
                        "usable": _parse_bool(row["face_usable"]),
                        "alignment_ok": _parse_bool(row["alignment_ok"]),
                        "embedding_created": _parse_bool(row.get("embedding_created", False)),
                    }
                )

    face_ids_by_person: dict[int, list[int]] = defaultdict(list)
    faces_by_person: dict[int, list[dict]] = defaultdict(list)

    for face in faces:
        person_id = face.get("person_id")
        if person_id is None:
            continue
        face_ids_by_person[int(person_id)].append(int(face["face_id"]))
        faces_by_person[int(person_id)].append(face)

    rows = []

    for person in persons:
        person_id = int(person["person_id"])
        person_faces = faces_by_person.get(person_id, [])
        representative_crop = person_faces[0]["crop_path"] if person_faces else None

        rows.append(
            {
                "person_id": person_id,
                "name": person.get("name", f"Person {person_id}"),
                "function": person.get("function", ""),
                "first_seen_ts": float(person["first_seen_ts"]),
                "last_seen_ts": float(person["last_seen_ts"]),
                "appearances_count": len(person.get("appearances", [])),
                "face_ids": json.dumps(face_ids_by_person.get(person_id, [])),
                "attributes": json.dumps(person.get("attributes", {}), ensure_ascii=False),
                "description": "",
                "representative_image": None,
                "representative_crop": representative_crop,
                "track_ids": json.dumps(person.get("track_ids", [])),
                "segments": json.dumps(person.get("segments", [])),
                "appearances": json.dumps(person.get("appearances", [])),
            }
        )

    persons_df = pd.DataFrame(rows)

    if not persons_df.empty:
        persons_df = persons_df.sort_values("first_seen_ts").reset_index(drop=True)

    return persons_df, faces


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
