"""Stage 2: FaceMoE im RAM und Clustering der aktuellen logischen Tracks."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import embedding_store, stage_state, track_segments
from .review_artifacts import ReviewError
from .config import SIMILARITY_THRESHOLD, validate_parameter
from .work_pool import CancellationToken, map_bounded, model_slot, report_progress, worker_count


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


def run_identities(video_path, job_dir, progress_cb=None, *, similarity_threshold=SIMILARITY_THRESHOLD,
                   cancel_token: CancellationToken | None = None):
    validate_parameter("similarity_threshold", similarity_threshold)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    import numpy as np

    from .clustering import run_clustering
    from .face_samples import MAX_FACE_SAMPLES_PER_TRACK, load_aligned_face, select_temporal_observations
    from .face_recognition import FaceMoERecognizer
    from .person_crops import refresh_identity_fallbacks

    video_path = Path(video_path)
    base = stage_state.root(job_dir)
    if not (base / "tracks.json").is_file():
        raise ReviewError("Bitte zuerst Tracking ausführen.", 409)
    metadata = stage_state.read_json(base / "tracks.json")
    tracking_revision = int(metadata["revision"])
    if not stage_state.video_matches(video_path, metadata):
        raise ReviewError("Das Originalvideo hat sich geändert. Tracking erneut ausführen.", 409)

    track_segments.timeline.cache_clear()
    tracks = track_segments.current_tracks(metadata, base)
    track_by_id = {track["track_id"]: track for track in tracks}
    face_rows, face_fields = stage_state.read_csv(base / "face_observations.csv")
    for field in ("alignment_ok", "embedding_created", "face_sample_path"):
        if field not in face_fields:
            face_fields.append(field)
    for row in face_rows:
        row["alignment_ok"], row["embedding_created"] = "", "False"

    usable_by_track = {}
    rejected_tracks, rejected_frames = [], []
    source_has_usable_face, logical_has_face = set(), set()
    for row in face_rows:
        source, frame = int(row["source_track_id"]), int(row["frame_number"])
        track_id = track_segments.resolve_track(source, frame, metadata)
        if track_by_id[track_id]["excluded"]:
            continue
        usable = _true(row.get("face_usable"))
        if usable:
            source_has_usable_face.add(source)
        if _true(row.get("excluded")):
            continue
        if usable:
            logical_has_face.add(track_id)
            usable_by_track.setdefault(track_id, []).append(row)
        else:
            rejected_tracks.append(track_id)
            rejected_frames.append(frame)

    selected = {}
    for track_id, observations in usable_by_track.items():
        # Tracking persists a bounded reservoir of lossless face crops per
        # source track. Use those directly when available; older artifacts
        # still select temporal samples from their saved person crops.
        cached = [row for row in observations if row.get("face_sample_path")]
        chosen = cached[:MAX_FACE_SAMPLES_PER_TRACK] if cached else select_temporal_observations(
            observations, MAX_FACE_SAMPLES_PER_TRACK,
        )
        chosen_face_ids = {int(row["face_id"]) for row in chosen}
        for row in chosen:
            frame = int(row["frame_number"])
            selected.setdefault(frame, []).append((row, track_id))
        for row in observations:
            if int(row["face_id"]) not in chosen_face_ids:
                rejected_tracks.append(track_id)
                rejected_frames.append(int(row["frame_number"]))

    crop_rows, _ = stage_state.read_csv(base / "person_crops.csv")
    crop_by_path = {str(row["crop_path"]).replace("\\", "/"): row for row in crop_rows}

    records = []
    if selected:
        recognizer = None
        recognition_lock = threading.Lock()
        total_faces = sum(len(rows) for rows in selected.values())
        state_lock = threading.Lock()
        state = {"queued": 0, "running": 0, "completed": 0, "failed": 0,
                 "completed_faces": 0, "current_task": None, "last_emit": 0.0}
        started = time.monotonic()
        rows_by_id = {int(row["face_id"]): row for row in face_rows}
        rejected_records = []

        def publish(force=False):
            now = time.monotonic()
            with state_lock:
                if not force and now - state["last_emit"] < 0.25:
                    return
                state["last_emit"] = now
                current = state["completed_faces"]
                workers = {key: state[key] for key in ("queued", "running", "completed", "failed")}
                workers["limit"] = worker_count()
                current_task = state["current_task"]
            report_progress(progress_cb, f"Gesichter verarbeitet: {current}/{total_faces}", current, total_faces, {
                "phase": "embeddings", "completed": current, "total": total_faces, "unit": "faces",
                "workers": workers, "current_task": current_task,
                "elapsed_seconds": round(now - started, 1),
            })

        def task_event(event, item):
            frame_number = item[0]
            with state_lock:
                if event == "queued":
                    state["queued"] += 1
                elif event == "started":
                    state["queued"] = max(0, state["queued"] - 1)
                    state["running"] += 1
                    state["current_task"] = {"id": f"frame-{frame_number}", "frame_number": frame_number}
                elif event == "cancelled":
                    state["queued"] = max(0, state["queued"] - 1)
                elif event == "cancelled_running":
                    state["running"] = max(0, state["running"] - 1)
                    state["current_task"] = {"id": f"frame-{frame_number}", "status": "cancelled"}
                elif event in {"completed", "failed"}:
                    state["running"] = max(0, state["running"] - 1)
                    state[event] += 1
                    state["current_task"] = {"id": f"frame-{frame_number}", "status": event}
            publish(force=event in {"completed", "failed", "cancelled_running"})

        def on_result(item, result):
            for face_id, track_id, frame_number, alignment_ok, embedding_created, embedding in result:
                row = rows_by_id[face_id]
                row["alignment_ok"] = str(bool(alignment_ok))
                row["embedding_created"] = str(bool(embedding_created))
                if embedding_created:
                    records.append((face_id, track_id, frame_number, embedding))
                else:
                    rejected_records.append((face_id, track_id, frame_number))
            with state_lock:
                state["completed_faces"] += len(result)
                completed_faces = state["completed_faces"]
            publish(force=completed_faces >= total_faces)

        def frame_batches():
            frame_numbers = sorted(selected)
            for index, frame_number in enumerate(frame_numbers, start=1):
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                yield (frame_number, selected[frame_number])
                if index % 30 == 0 or index == len(frame_numbers):
                    report_progress(progress_cb, f"Gesichtsproben geladen: {index}/{len(frame_numbers)}", index,
                                    len(frame_numbers), {
                        "phase": "decode", "unit": "face_sample_frames",
                        "workers": {**{key: state[key] for key in ("queued", "running", "completed", "failed")},
                                    "limit": worker_count()},
                    })

        def process_frame(item):
            frame_number, observations = item
            results = []
            for row, track_id in observations:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                face_id = int(row["face_id"])
                aligned = load_aligned_face(base, row, crop_by_path)
                if aligned is None:
                    results.append((face_id, track_id, frame_number, False, False, None))
                    continue
                try:
                    with recognition_lock:
                        if cancel_token is not None:
                            cancel_token.raise_if_cancelled()
                        embedding = recognizer.extract_embedding(aligned)
                except Exception as exc:
                    print(f"FaceMoE-Fehler | Track {track_id} | Frame {frame_number} | {type(exc).__name__}: {exc}")
                    results.append((face_id, track_id, frame_number, True, False, None))
                    continue
                results.append((face_id, track_id, frame_number, True, True, embedding))
            return results

        try:
            with model_slot(cancel_token):
                recognizer = FaceMoERecognizer(model_root=Path(__file__).resolve().parents[3] / "models" / "facemoe")
                map_bounded(
                    frame_batches(), process_frame,
                    on_task_event=task_event, on_result=on_result,
                    collect_results=False,
                    cancel_token=cancel_token,
                )
        finally:
            if recognizer is not None:
                recognizer.close()

        records.sort(key=lambda record: record[0])
        rejected_records.sort(key=lambda record: record[0])
        rejected_tracks.extend(track_id for _face_id, track_id, _frame_number in rejected_records)
        rejected_frames.extend(frame_number for _face_id, _track_id, frame_number in rejected_records)

    vectors = np.stack([row[3] for row in records]).astype(np.float32) if records else np.empty((0, 512), np.float32)
    reference_state = {"track_references": None, "track_ids": None, "distance_matrix": None}

    def retain_track_references(track_references, track_ids, distance_matrix):
        reference_state["track_references"] = track_references
        reference_state["track_ids"] = track_ids
        reference_state["distance_matrix"] = distance_matrix

    try:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        report_progress(progress_cb, "Personen werden global geclustert …", 0, 1, {
            "phase": "clustering", "completed": 0, "total": 1, "unit": "clustering",
        })
        mapping = run_clustering(
            embeddings=vectors, frame_numbers=np.asarray([row[2] for row in records], np.int32),
            track_ids=np.asarray([row[1] for row in records], np.int32),
            rejected_track_ids=np.asarray(rejected_tracks, np.int32),
            rejected_frame_numbers=np.asarray(rejected_frames, np.int32),
            similarity_threshold=similarity_threshold, progress_cb=progress_cb,
            cancel_token=cancel_token, track_references_cb=retain_track_references,
        )
    finally:
        records.clear()

    current = stage_state.read_json(base / "tracks.json")
    if current.get("revision") != tracking_revision or current.get("video_sha256") != metadata.get("video_sha256"):
        raise ReviewError("Tracking oder Review wurde während des Clusterlaufs geändert. Bitte erneut ausführen.", 409)

    needs_fallback = {
        track["track_id"] for track in tracks
        if not track["excluded"] and track["track_id"] not in logical_has_face
        and track["source_track_id"] in source_has_usable_face
    }
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    refresh_identity_fallbacks(
        video_path, base, tracks, needs_fallback, float(metadata["fps"]),
        lambda message, current, total: report_progress(
            progress_cb, message, current, total, {"phase": "fallback", "unit": "frames"},
        ),
        cancel_token=cancel_token,
        commit_cb=lambda: report_progress(progress_cb, "Identity-Fallback-Crops werden veröffentlicht …", 0, 1, {
            "phase": "publishing", "completed": 0, "total": 1, "unit": "publish",
        }),
    )
    report_progress(progress_cb, "Personenzuordnung wird gespeichert …", 0, 1, {
        "phase": "publishing", "completed": 0, "total": 1, "unit": "publish",
    })
    if cancel_token is not None:
        cancel_token.begin_commit()
    stage_state.write_csv(base / "face_observations.csv", face_rows, face_fields)
    embedding_store.write(base / "track_references.f16", reference_state["track_references"] or {})
    (base / "track_distances.csv").unlink(missing_ok=True)
    revision, assignment_revision = _next_revisions(base)
    stage_state.atomic_write(base / "persons.json", {
        **_persons(mapping, tracking_revision, revision, assignment_revision),
        "similarity_threshold": similarity_threshold,
    })
    (base / "attributes.json").unlink(missing_ok=True)
    report_progress(progress_cb, "Personenzuordnung abgeschlossen", 1, 1, {
        "phase": "complete", "completed": 1, "total": 1, "unit": "publish",
    })

    from .review_state import current as current_review
    distance_data = None
    if reference_state["track_ids"] is not None:
        distance_data = (reference_state["track_ids"], reference_state["distance_matrix"])
    return current_review(job_dir, distance_data=distance_data)
