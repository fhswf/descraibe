from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from .persons.appearances import TrackIntervalAccumulator
from .persons.clustering import run_clustering
from .persons.config import ANALYSIS_INTERVAL_SECONDS
from .persons.detection import RFDETRPersonDetector
from .persons.face_detection import RetinaFaceDetector
from .persons.face_observations import FaceObservationWriter
from .persons.face_quality import check_face_quality
from .persons.face_recognition import FaceMoERecognizer
from .persons.person_crops import PersonCropWriter
from .persons.tracking import BytePersonTracker, detect_scene_change_frames


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


def _analyze_video(
    video_path: str | Path,
    job_dir: str | Path | None = None,
    progress_cb=None,
) -> dict:
    """Führt die eigentliche automatische Personenanalyse auf dem Video aus."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video nicht gefunden:\n{video_path}")

    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        raise RuntimeError(f"Video konnte nicht geöffnet werden:\n{video_path}")

    fps = float(video.get(cv2.CAP_PROP_FPS))
    frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        video.release()
        raise RuntimeError("Ungültige Framerate.")

    analysis_interval_frames = max(1, int(round(fps * ANALYSIS_INTERVAL_SECONDS)))
    base_dir = Path(job_dir) if job_dir else video_path.parent
    analysis_output_dir = base_dir / "person_analysis"
    analysis_output_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("PERSONENANALYSE")
    print("================")
    print(f"Video: {video_path}")
    print(f"FPS: {fps:.3f}")
    print(f"Frames: {frame_count}")
    print(f"Gesichtsanalyse alle {ANALYSIS_INTERVAL_SECONDS:.2f} s ({analysis_interval_frames} Frames)")
    print("FaceMoE-Embeddings: nur im RAM")
    print("Tracks ohne FaceMoE: bleiben unassigned")
    print(f"Ausgabe: {analysis_output_dir}")
    print()

    if progress_cb:
        progress_cb("Szenenwechsel werden erkannt ...", 0, frame_count)

    scene_change_frames = detect_scene_change_frames(video_path)
    print(f"Szenenwechsel erkannt: {len(scene_change_frames)}")

    person_detector = RFDETRPersonDetector()
    person_tracker = BytePersonTracker(frame_rate=fps)
    face_detector = RetinaFaceDetector(model_cache_dir=MODEL_ROOT / "retinaface")
    face_recognizer = FaceMoERecognizer(model_root=MODEL_ROOT / "facemoe")

    track_accumulator = TrackIntervalAccumulator(fps=fps)
    person_crop_writer = PersonCropWriter(
        output_dir=analysis_output_dir,
        fps=fps,
        jpeg_quality=90,
        clear_existing=True,
    )
    face_observation_writer = FaceObservationWriter(
        output_dir=analysis_output_dir,
        fps=fps,
        clear_existing=True,
    )

    face_stats: dict[int, dict] = {}
    total_faces_detected = 0
    total_faces_assigned = 0
    total_faces_usable = 0
    total_alignment_failures = 0
    total_embeddings_created = 0
    total_embedding_errors = 0

    # Embeddings existieren ausschließlich während dieses Laufs im RAM.
    face_embedding_records: list[dict] = []
    rejected_track_ids: list[int] = []
    rejected_frame_numbers: list[int] = []

    frame_number = 0

    try:
        while True:
            success, frame_bgr = video.read()
            if not success:
                break

            frame_number += 1

            # 1. Personenerkennung
            persons = person_detector.detect(frame_bgr)

            # 2. Tracking
            tracked_persons = person_tracker.update(
                persons,
                scene_change=frame_number in scene_change_frames,
            )

            # 3. Track-Zeiten und Personencrops
            current_crop_paths: dict[int, Path] = {}

            for person in tracked_persons:
                track_id = int(person["track_id"])
                scene_id = int(person["scene_id"])

                track_accumulator.observe(
                    track_id=track_id,
                    scene_id=scene_id,
                    frame_number=frame_number,
                )

                crop_path = person_crop_writer.save(
                    frame_bgr=frame_bgr,
                    track_id=track_id,
                    scene_id=scene_id,
                    frame_number=frame_number,
                    bbox=person["bbox"],
                    confidence=person.get("confidence"),
                )

                if crop_path is not None:
                    current_crop_paths[track_id] = crop_path

            # 4. Gesichtsanalyse alle 0,5 Sekunden
            analyze_frame = (frame_number - 1) % analysis_interval_frames == 0

            if analyze_frame and tracked_persons:
                faces = face_detector.detect(frame_bgr)
                total_faces_detected += len(faces)
                assignments = assign_faces_to_tracks(faces, tracked_persons)

                for face_index, person in assignments.items():
                    face = faces[face_index]
                    track_id = int(person["track_id"])
                    scene_id = int(person["scene_id"])
                    total_faces_assigned += 1

                    stats = face_stats.setdefault(
                        track_id,
                        {
                            "faces_assigned": 0,
                            "faces_usable": 0,
                            "alignment_failures": 0,
                            "embeddings_created": 0,
                            "embedding_errors": 0,
                        },
                    )
                    stats["faces_assigned"] += 1

                    # 5. Face Quality
                    face_crop = face["crop"]
                    face_confidence = float(face["confidence"])
                    is_usable, quality_info = check_face_quality(face_crop, face_confidence)
                    blur_score = quality_info.get("blur_score")

                    aligned_crop = face["aligned_crop"]
                    alignment_ok = aligned_crop is not None

                    # 6. Face-Metadaten speichern
                    person_crop_path = current_crop_paths.get(track_id)
                    face_id = None

                    if person_crop_path is not None:
                        frame_height, frame_width = frame_bgr.shape[:2]
                        face_id = face_observation_writer.save(
                            track_id=track_id,
                            scene_id=scene_id,
                            frame_number=frame_number,
                            person_bbox=person["bbox"],
                            face_bbox=face["bbox"],
                            person_crop_path=person_crop_path,
                            frame_width=frame_width,
                            frame_height=frame_height,
                            face_confidence=face_confidence,
                            face_usable=is_usable,
                            blur_score=blur_score,
                            alignment_ok=alignment_ok,
                        )

                    if is_usable:
                        stats["faces_usable"] += 1
                        total_faces_usable += 1

                        if not alignment_ok:
                            stats["alignment_failures"] += 1
                            total_alignment_failures += 1

                    # 7. FaceMoE
                    embedding_created = False

                    if is_usable and alignment_ok:
                        try:
                            embedding = face_recognizer.extract_embedding(aligned_crop)
                        except Exception as error:
                            stats["embedding_errors"] += 1
                            total_embedding_errors += 1
                            print(
                                f"FaceMoE-Fehler | Track {track_id} | Frame {frame_number} | "
                                f"{type(error).__name__}: {error}"
                            )
                        else:
                            face_embedding_records.append(
                                {
                                    "face_id": face_id,
                                    "track_id": track_id,
                                    "scene_id": scene_id,
                                    "frame_number": frame_number,
                                    "timestamp_s": (frame_number - 1) / fps,
                                    "embedding": embedding,
                                }
                            )
                            stats["embeddings_created"] += 1
                            total_embeddings_created += 1
                            embedding_created = True

                    # Für Same-Frame-Cannot-Link berücksichtigen.
                    if not embedding_created:
                        rejected_track_ids.append(track_id)
                        rejected_frame_numbers.append(frame_number)

            if progress_cb and (
                frame_number % max(1, int(round(fps))) == 0
                or frame_number == frame_count
            ):
                progress_cb(
                    f"Personenanalyse: Frame {frame_number}/{frame_count}",
                    frame_number,
                    frame_count,
                )

            if frame_number % 500 == 0:
                print(f"Frame {frame_number}/{frame_count}")

    finally:
        video.release()
        person_crop_writer.close()
        face_observation_writer.close()
        face_recognizer.close()

    tracks = track_accumulator.result()

    default_stats = {
        "faces_assigned": 0,
        "faces_usable": 0,
        "alignment_failures": 0,
        "embeddings_created": 0,
        "embedding_errors": 0,
    }

    for track in tracks:
        track.update(face_stats.get(int(track["track_id"]), default_stats.copy()))

    # Embeddings für das Clustering vorbereiten.
    if face_embedding_records:
        embeddings = np.stack(
            [record["embedding"] for record in face_embedding_records]
        ).astype(np.float32)

        embedding_frame_numbers = np.asarray(
            [record["frame_number"] for record in face_embedding_records],
            dtype=np.int32,
        )
        embedding_track_ids = np.asarray(
            [record["track_id"] for record in face_embedding_records],
            dtype=np.int32,
        )
    else:
        embeddings = np.empty((0, 512), dtype=np.float32)
        embedding_frame_numbers = np.empty(0, dtype=np.int32)
        embedding_track_ids = np.empty(0, dtype=np.int32)

    clustered_mapping = run_clustering(
        embeddings=embeddings,
        frame_numbers=embedding_frame_numbers,
        track_ids=embedding_track_ids,
        rejected_track_ids=np.asarray(rejected_track_ids, dtype=np.int32),
        rejected_frame_numbers=np.asarray(rejected_frame_numbers, dtype=np.int32),
    )

    clustered_track_ids = set(clustered_mapping)
    unassigned_tracks = [
        track
        for track in tracks
        if int(track["track_id"]) not in clustered_track_ids
    ]

    track_to_person = dict(clustered_mapping)
    clustered_tracks = [
        track
        for track in tracks
        if int(track["track_id"]) in clustered_track_ids
    ]
    persons = build_persons(clustered_tracks, track_to_person)

    track_identity_path = analysis_output_dir / "track_identities.csv"
    persons_path = analysis_output_dir / "persons.json"

    save_track_identities(track_identity_path, tracks, track_to_person)
    save_persons(
        persons_path,
        video_path,
        tracks,
        persons,
        unassigned_tracks,
    )

    # Embeddings nicht persistieren und nach dem Clustering freigeben.
    face_embedding_records.clear()
    del embeddings
    del embedding_frame_numbers
    del embedding_track_ids

    print()
    print("GESICHTSANALYSE")
    print("================")
    print(f"Gesichter erkannt: {total_faces_detected}")
    print(f"Gesichtern Tracks zugeordnet: {total_faces_assigned}")
    print(f"Qualitativ verwendbar: {total_faces_usable}")
    print(f"Alignment fehlgeschlagen: {total_alignment_failures}")

    print()
    print("FACEMOE")
    print("=======")
    print(f"Embeddings erzeugt: {total_embeddings_created}")
    print(f"Embedding-Fehler: {total_embedding_errors}")
    print("Embeddings gespeichert: NEIN")

    print()
    print("AUTOMATISCHE PERSONEN")
    print("=====================")
    print(f"Tracks insgesamt: {len(tracks)}")
    print(f"Tracks mit FaceMoE-Embedding: {len(clustered_track_ids)}")
    print(f"Nicht zugeordnete Tracks: {len(unassigned_tracks)}")
    print(f"Automatisch erkannte Personen: {len(persons)}")
    print(f"Track-Zuordnungen: {track_identity_path}")
    print(f"Personenergebnis: {persons_path}")

    print()
    print("PERSONENCROPS")
    print("=============")
    print(f"Gespeicherte Personencrops: {person_crop_writer.crop_count}")
    print(f"Crop-Verzeichnis: {person_crop_writer.crops_dir}")
    print(f"Manifest: {person_crop_writer.manifest_path}")

    print()
    print("FACE-METADATEN")
    print("==============")
    print(f"Gespeicherte Face-Beobachtungen: {face_observation_writer.face_count}")
    print(f"Manifest: {face_observation_writer.manifest_path}")

    return {
        "video_path": str(video_path),
        "tracks": tracks,
        "persons": persons,
        "unassigned_tracks": unassigned_tracks,
        "track_to_person": track_to_person,
        "output_dir": str(analysis_output_dir),
        "persons_path": str(persons_path),
        "track_identities_path": str(track_identity_path),
    }


def _parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "ja"}


def _build_web_result(result: dict) -> tuple[pd.DataFrame, list[dict]]:
    """
    Wandelt das neue Personenergebnis in das Format um,
    das die bestehende descraibe-Web-App aktuell erwartet.
    """
    persons = result["persons"]
    track_to_person = result["track_to_person"]
    analysis_output_dir = Path(result["output_dir"])
    face_manifest_path = analysis_output_dir / "face_observations.csv"

    faces: list[dict] = []

    if face_manifest_path.is_file():
        with face_manifest_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file, delimiter=";")

            for row in reader:
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