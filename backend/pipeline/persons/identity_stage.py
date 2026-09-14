"""Stage 2: original pixels + saved landmarks, RAM-only FaceMoE, unchanged clustering."""
import csv
import json
from pathlib import Path

from . import stage_state
from .review_artifacts import ReviewError


def run_identities(video_path, job_dir, progress_cb=None):
    import cv2
    import numpy as np
    from ..person_analysis import build_persons, save_persons, save_track_identities
    from .face_detection import align_face
    from .face_recognition import FaceMoERecognizer
    from .clustering import run_clustering
    from .person_crops import PersonCropWriter, FallbackCropCollector
    from . import review_artifacts
    from . import track_segments

    pointer = stage_state.active(job_dir)
    if pointer is None:
        raise ReviewError("Bitte zuerst Tracking & Gesichter ausführen.", 409)
    tracking_id = pointer["tracking_run"]
    source = stage_state.run_path(job_dir, tracking_id, "tracking")
    metadata = stage_state.read_json(source / "tracks.json")
    if stage_state.video_digest(video_path) != metadata["video_sha256"]:
        raise ReviewError("Das Originalvideo hat sich geändert. Tracking erneut ausführen.", 409)
    face_review = stage_state.face_state(job_dir, tracking_id)
    face_version = stage_state.face_version(tracking_id, face_review)
    excluded = set(face_review["excluded_face_observations"])
    tracks = track_segments.effective_tracks(metadata, face_review, source)
    with (source / "face_observations.csv").open(encoding="utf-8-sig", newline="") as f:
        observations = list(csv.DictReader(f, delimiter=";"))
    selected = {}
    rejected_tracks, rejected_frames, results = [], [], []
    for row in observations:
        fid, number = int(row["face_id"]), int(row["frame_number"])
        tid = track_segments.resolve_track(int(row["track_id"]), number, face_review)
        row["track_id"] = str(tid)
        if row["face_usable"].lower() != "true" or fid in excluded:
            rejected_tracks.append(tid)
            rejected_frames.append(number)
            results.append({"face_id": fid, "status": "excluded" if fid in excluded else "quality_rejected"})
        else:
            selected.setdefault(number, []).append(row)
    records = []
    recognizer = capture = None
    try:
        if selected:
            capture = cv2.VideoCapture(str(video_path))
            if not capture.isOpened():
                raise RuntimeError("Originalvideo nicht verfügbar.")
            recognizer = FaceMoERecognizer(model_root=Path(__file__).resolve().parents[3] / "models" / "facemoe")
            last = max(selected)
            for number in range(1, last + 1):
                if not capture.grab():
                    raise RuntimeError(f"Originalframe {number} nicht verfügbar.")
                if number in selected:
                    ok, frame = capture.retrieve()
                    if not ok:
                        raise RuntimeError(f"Originalframe {number} konnte nicht dekodiert werden.")
                    for row in selected[number]:
                        fid, tid = int(row["face_id"]), int(row["track_id"])
                        x1, y1, x2, y2 = json.loads(row["face_crop_box"])
                        points = np.asarray(json.loads(row["landmarks"]), dtype=np.float32)
                        points = points - np.asarray([x1, y1], dtype=np.float32)
                        aligned = align_face(frame[y1:y2, x1:x2].copy(), points)
                        outcome = "alignment_failed"
                        if aligned is not None:
                            try:
                                embedding = recognizer.extract_embedding(aligned)
                            except Exception as exc:
                                outcome = "embedding_failed"
                                print(f"FaceMoE-Fehler | Track {tid} | Frame {number} | {type(exc).__name__}: {exc}")
                            else:
                                records.append((fid, tid, number, embedding))
                                outcome = "success"
                        results.append({"face_id": fid, "status": outcome})
                        if outcome != "success":
                            rejected_tracks.append(tid)
                            rejected_frames.append(number)
                if progress_cb and (number % 30 == 0 or number == last):
                    progress_cb(f"Personen & Cluster: Frame {number}/{last}", number, last)
        vectors = np.stack([r[3] for r in records]).astype(np.float32) if records else np.empty((0, 512), np.float32)
        mapping = run_clustering(embeddings=vectors,
            frame_numbers=np.asarray([r[2] for r in records], np.int32), track_ids=np.asarray([r[1] for r in records], np.int32),
            rejected_track_ids=np.asarray(rejected_tracks, np.int32), rejected_frame_numbers=np.asarray(rejected_frames, np.int32))
        del vectors
    finally:
        records.clear()
        if capture is not None:
            capture.release()
        if recognizer is not None:
            recognizer.close()
    run_id, output = stage_state.new_run(job_dir, "identities")
    persons = build_persons(tracks, mapping)
    save_persons(output / "persons.json", Path(video_path), tracks, persons, [t for t in tracks if t["track_id"] not in mapping])
    save_track_identities(output / "track_identities.csv", tracks, mapping)
    data = review_artifacts.load_tracking(job_dir)
    evidence_tracks = {track_segments.resolve_track(source_id, c["frame_number"], face_review)
                       for source_id, rows in data.evidence_by_track.items() for c in rows if c["face_id"] not in excluded}
    without_evidence = {t["track_id"] for t in tracks if t["track_id"] not in evidence_tracks and
                        (t["is_split"] or data.evidence_by_track[t["source_track_id"]])}
    fallback = FallbackCropCollector()
    candidates = metadata["fallback_candidates"]
    if (source / track_segments.TIMELINE).is_file() and without_evidence:
        candidates = [c for rows in track_segments.timeline(str(source)).values() for c in rows]
    for c in sorted(candidates, key=lambda c: c["frame_number"]):
        tid = track_segments.resolve_track(c["track_id"], c["frame_number"], face_review)
        if tid in without_evidence:
            fallback.observe({**c, "track_id": tid}, c["frame_number"])
    with_writer = PersonCropWriter(output, metadata["fps"], clear_existing=False, start_id=max(data.crops, default=0))
    try:
        fallback.save(Path(video_path), with_writer, progress_cb)
    finally:
        with_writer.close()
    stage_state.atomic_write(output / "identity_result.json", {"tracking_run": tracking_id,
        "track_splits": face_review.get("track_splits", {}), "tracks": tracks,
        "face_review_version": face_version, "excluded_face_observations": sorted(excluded),
        "observations": sorted(results, key=lambda r: r["face_id"])})
    # No publication of a result computed against a concurrently changed source.
    if stage_state.active(job_dir)["tracking_run"] != tracking_id or stage_state.face_version(tracking_id, stage_state.face_state(job_dir, tracking_id)) != face_version:
        raise ReviewError("Eingangsdaten wurden während des Clusterlaufs geändert; Ergebnis nicht aktiviert.", 409)
    stage_state.publish(job_dir, tracking_id, run_id)
    from .review_state import current
    return current(job_dir)
