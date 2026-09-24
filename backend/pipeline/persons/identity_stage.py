"""Stage 2: FaceMoE im RAM und Clustering der aktuellen logischen Tracks."""
from __future__ import annotations

import json
from pathlib import Path

from . import stage_state, track_segments
from .review_artifacts import ReviewError
from .config import SIMILARITY_THRESHOLD, validate_parameter


def _true(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _next_revisions(base: Path) -> tuple[int, int]:
    path = base / "persons.json"
    if not path.is_file():
        return 1, 1
    previous = stage_state.read_json(path)
    return int(previous.get("revision", 0)) + 1, int(previous.get("assignment_revision", 0)) + 1


def _persons(mapping: dict[int, int], tracking_revision: int, revision: int, assignment_revision: int) -> dict:
    grouped = {}
    for track_id, person_id in mapping.items():
        grouped.setdefault(int(person_id), []).append(int(track_id))
    return {
        "schema_version": 1, "revision": revision, "assignment_revision": assignment_revision,
        "tracking_revision": tracking_revision,
        "persons": [{
            "person_id": person_id, "name": f"Person {person_id}", "function": "",
            "track_ids": sorted(track_ids),
        } for person_id, track_ids in sorted(grouped.items())],
    }


def run_identities(video_path, job_dir, progress_cb=None, *, similarity_threshold=SIMILARITY_THRESHOLD):
    validate_parameter("similarity_threshold", similarity_threshold)
    import cv2
    import numpy as np

    from .clustering import run_clustering
    from .face_detection import align_face
    from .face_recognition import FaceMoERecognizer
    from .person_crops import refresh_identity_fallbacks

    video_path = Path(video_path)
    base = stage_state.root(job_dir)
    if not (base / "tracks.json").is_file():
        raise ReviewError("Bitte zuerst Tracking ausführen.", 409)
    metadata = stage_state.read_json(base / "tracks.json")
    tracking_revision = int(metadata["revision"])
    if stage_state.video_digest(video_path) != metadata.get("video_sha256"):
        raise ReviewError("Das Originalvideo hat sich geändert. Tracking erneut ausführen.", 409)

    track_segments.timeline.cache_clear()
    tracks = track_segments.current_tracks(metadata, base)
    track_by_id = {track["track_id"]: track for track in tracks}
    face_rows, face_fields = stage_state.read_csv(base / "face_observations.csv")
    for field in ("alignment_ok", "embedding_created"):
        if field not in face_fields:
            face_fields.append(field)
    for row in face_rows:
        row["alignment_ok"], row["embedding_created"] = "", "False"

    selected, rejected_tracks, rejected_frames = {}, [], []
    source_has_usable_face, logical_has_face = set(), set()
    for row in face_rows:
        source, frame = int(row["source_track_id"]), int(row["frame_number"])
        track_id = track_segments.resolve_track(source, frame, metadata)
        if track_by_id[track_id]["excluded"]:
            continue
        usable = _true(row.get("face_usable"))
        if usable:
            source_has_usable_face.add(source)
        if usable and not _true(row.get("excluded")):
            logical_has_face.add(track_id)
            selected.setdefault(frame, []).append((row, track_id))
        else:
            rejected_tracks.append(track_id)
            rejected_frames.append(frame)

    records = []
    capture = recognizer = None
    try:
        if selected:
            capture = cv2.VideoCapture(str(video_path))
            if not capture.isOpened():
                raise RuntimeError("Originalvideo nicht verfügbar.")
            recognizer = FaceMoERecognizer(model_root=Path(__file__).resolve().parents[3] / "models" / "facemoe")
            last = max(selected)
            for frame_number in range(1, last + 1):
                if not capture.grab():
                    raise RuntimeError(f"Originalframe {frame_number} nicht verfügbar.")
                if frame_number in selected:
                    ok, frame = capture.retrieve()
                    if not ok:
                        raise RuntimeError(f"Originalframe {frame_number} konnte nicht dekodiert werden.")
                    for row, track_id in selected[frame_number]:
                        face_id = int(row["face_id"])
                        try:
                            x1, y1, x2, y2 = json.loads(row["face_crop_box"])
                            points = np.asarray(json.loads(row["landmarks"]), dtype=np.float32)
                            points -= np.asarray([x1, y1], dtype=np.float32)
                            aligned = align_face(frame[y1:y2, x1:x2].copy(), points)
                        except Exception:
                            aligned = None
                        if aligned is None:
                            row["alignment_ok"] = "False"
                            rejected_tracks.append(track_id); rejected_frames.append(frame_number)
                            continue
                        row["alignment_ok"] = "True"
                        try:
                            embedding = recognizer.extract_embedding(aligned)
                        except Exception as exc:
                            print(f"FaceMoE-Fehler | Track {track_id} | Frame {frame_number} | {type(exc).__name__}: {exc}")
                            rejected_tracks.append(track_id); rejected_frames.append(frame_number)
                            continue
                        row["embedding_created"] = "True"
                        records.append((face_id, track_id, frame_number, embedding))
                if progress_cb and (frame_number % 30 == 0 or frame_number == last):
                    progress_cb(f"Personenzuordnung: Frame {frame_number}/{last}", frame_number, last)

        vectors = np.stack([row[3] for row in records]).astype(np.float32) if records else np.empty((0, 512), np.float32)
        mapping = run_clustering(
            embeddings=vectors, frame_numbers=np.asarray([row[2] for row in records], np.int32),
            track_ids=np.asarray([row[1] for row in records], np.int32),
            rejected_track_ids=np.asarray(rejected_tracks, np.int32),
            rejected_frame_numbers=np.asarray(rejected_frames, np.int32),
            similarity_threshold=similarity_threshold,
        )
    finally:
        records.clear()
        if capture is not None:
            capture.release()
        if recognizer is not None:
            recognizer.close()

    current = stage_state.read_json(base / "tracks.json")
    if current.get("revision") != tracking_revision or current.get("video_sha256") != metadata.get("video_sha256"):
        raise ReviewError("Tracking oder Review wurde während des Clusterlaufs geändert. Bitte erneut ausführen.", 409)

    needs_fallback = {
        track["track_id"] for track in tracks
        if not track["excluded"] and track["track_id"] not in logical_has_face
        and (track["is_split"] or track["source_track_id"] in source_has_usable_face)
    }
    refresh_identity_fallbacks(video_path, base, tracks, needs_fallback, float(metadata["fps"]), progress_cb)
    stage_state.write_csv(base / "face_observations.csv", face_rows, face_fields)
    revision, assignment_revision = _next_revisions(base)
    stage_state.atomic_write(base / "persons.json", {
        **_persons(mapping, tracking_revision, revision, assignment_revision),
        "similarity_threshold": similarity_threshold,
    })
    (base / "attributes.json").unlink(missing_ok=True)

    from .review_state import current as current_review
    return current_review(job_dir)
