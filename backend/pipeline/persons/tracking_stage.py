"""Stage 1: scene-parallel RF-DETR, ByteTrack, RetinaFace and face quality."""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from . import stage_state
from .config import TRACKING_INTERVAL_SECONDS, validate_parameter
from .work_pool import map_bounded, model_slot, report_progress


TIMELINE_FIELDS = ["source_track_id", "frame_number", "scene_id", "x1", "y1", "x2", "y2", "confidence"]


def _publish(staged: Path, target: Path) -> None:
    backup = target.with_name(f".{target.name}_old")
    shutil.rmtree(backup, ignore_errors=True)
    if target.exists():
        os.replace(target, backup)
    try:
        os.replace(staged, target)
    except Exception:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _scene_specs(total_frames: int, cuts: list[int], stride: int) -> list[dict]:
    """Return non-empty scene tasks while retaining IDs for scenes with no sampled frame."""
    specs = []
    start = 1
    boundaries = [*cuts, total_frames + 1]
    for scene_id, end_exclusive in enumerate(boundaries, start=1):
        end = min(total_frames, end_exclusive - 1)
        first = start + ((1 - start) % stride)
        if first <= end:
            specs.append({
                "scene_id": scene_id,
                "start_frame": start,
                "end_frame": end,
                "first_sample": first,
                "sample_count": ((end - first) // stride) + 1,
            })
        start = end_exclusive
        if start > total_frames:
            break
    return specs


def _open_at_frame(cv2, video_path: Path, first_frame: int):
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("Video konnte nicht geöffnet werden.")
    last_grabbed = 0
    if first_frame > 1:
        positioned = capture.set(cv2.CAP_PROP_POS_FRAMES, first_frame - 1)
        position = capture.get(cv2.CAP_PROP_POS_FRAMES) if positioned else -1
        if positioned and abs(float(position) - (first_frame - 1)) < 0.5:
            # Treat the frames before the target as consumed. The caller's
            # next grab advances the decoder onto the requested frame.
            last_grabbed = first_frame - 1
        else:
            # Some codecs do not support exact frame seeking. Reopen and decode
            # the prefix so frame numbers still match the serial implementation.
            capture.release()
            capture = cv2.VideoCapture(str(video_path))
            if not capture.isOpened():
                capture.release()
                raise RuntimeError("Video konnte nicht geöffnet werden.")
            for frame_number in range(1, first_frame):
                if not capture.grab():
                    capture.release()
                    raise RuntimeError(f"Frame {frame_number} konnte nicht gelesen werden.")
            last_grabbed = first_frame - 1
    return capture, last_grabbed


def _process_scene(
    *, cv2, video_path: Path, scene_dir: Path, spec: dict, fps: float, total_frames: int,
    stride: int, detector, detector_lock, faces, faces_lock, progress_task,
):
    from . import track_segments
    from .appearances import TrackIntervalAccumulator
    from .face_assignment import assign_faces_to_tracks
    from .face_observations import FaceObservationWriter
    from .face_quality import check_face_quality
    from .person_crops import FallbackCropCollector, PersonCropWriter, read_manifest
    from .tracking import BytePersonTracker

    scene_dir.mkdir(parents=True, exist_ok=True)
    capture, last_grabbed = _open_at_frame(cv2, video_path, spec["first_sample"])
    crop_writer = face_writer = timeline_writer = None
    try:
        tracker = BytePersonTracker(frame_rate=fps / stride)
        accumulator, fallback = TrackIntervalAccumulator(fps), FallbackCropCollector()
        crop_writer = PersonCropWriter(scene_dir, fps)
        face_writer = FaceObservationWriter(scene_dir, fps)
        timeline_writer = track_segments.TimelineWriter(scene_dir)
        counts = {
            "tracking_frames": 0, "faces_detected": 0,
            "faces_assigned": 0, "faces_usable": 0,
        }
        frame_number = spec["first_sample"]
        while frame_number <= spec["end_frame"]:
            while last_grabbed < frame_number:
                if not capture.grab():
                    raise RuntimeError(f"Tracking-Frame {frame_number} konnte nicht gelesen werden.")
                last_grabbed += 1
            ok, frame = capture.retrieve()
            if not ok:
                raise RuntimeError(f"Tracking-Frame {frame_number} konnte nicht dekodiert werden.")

            with detector_lock:
                detections = detector.detect(frame)
            tracked = [
                {**person, "scene_id": spec["scene_id"]}
                for person in tracker.update(detections)
            ]
            counts["tracking_frames"] += 1
            for person in tracked:
                timeline_writer.observe(person, frame_number, frame.shape[1], frame.shape[0])
                accumulator.observe(person["track_id"], spec["scene_id"], frame_number)
                fallback.observe(person, frame_number)

            # Keep the historical global cadence: every second sampled frame,
            # including when a scene begins between those frames.
            tracking_ordinal = (frame_number - 1) // stride
            if tracking_ordinal % 2 == 0 and tracked:
                with faces_lock:
                    detected_faces = faces.detect(frame)
                counts["faces_detected"] += len(detected_faces)
                for index, person in assign_faces_to_tracks(detected_faces, tracked).items():
                    face = detected_faces[index]
                    usable, quality = check_face_quality(face["crop"], float(face["confidence"]))
                    counts["faces_assigned"] += 1
                    counts["faces_usable"] += int(usable)
                    crop_path = None
                    if usable:
                        crop_path = crop_writer.save(
                            frame, person["track_id"], spec["scene_id"], frame_number,
                            person["bbox"], person.get("confidence"), "face_evidence",
                        )
                        if crop_path is None:
                            raise RuntimeError("Personencrop einer verwendbaren Beobachtung fehlt.")
                        fallback.face_succeeded(person["track_id"])
                    face_writer.save(
                        source_track_id=person["track_id"], scene_id=spec["scene_id"], frame_number=frame_number,
                        person_bbox=person["bbox"], face_bbox=face["bbox"], person_crop_path=crop_path,
                        frame_width=frame.shape[1], frame_height=frame.shape[0], face_confidence=face["confidence"],
                        face_usable=usable, blur_score=quality.get("blur_score"), landmarks=face["landmarks"],
                        face_crop_box=face["face_crop_box"],
                    )

            progress_task(spec, counts["tracking_frames"], frame_number, total_frames)
            frame_number += stride

        for writer in (crop_writer, face_writer, timeline_writer):
            writer.close()
        crop_writer = face_writer = timeline_writer = None
        timeline_rows, _ = stage_state.read_csv(scene_dir / track_segments.TIMELINE)
        face_rows, _ = stage_state.read_csv(scene_dir / "face_observations.csv")
        crop_rows = read_manifest(scene_dir)
        return {
            **spec,
            "counts": counts,
            "tracks": accumulator.result(),
            "fallback": fallback,
            "timeline_rows": timeline_rows,
            "face_rows": face_rows,
            "crop_rows": crop_rows,
            "crop_dir": scene_dir / "person_crops",
        }
    finally:
        capture.release()
        for writer in (crop_writer, face_writer, timeline_writer):
            if writer is not None:
                writer.close()


def _merge_scenes(scene_results: list[dict], staged: Path, video_path: Path, fps: float, progress_cb, total_frames: int):
    from .face_observations import FaceObservationWriter
    from .person_crops import FallbackCropCollector, PersonCropWriter, read_manifest, write_manifest
    from .track_segments import TIMELINE, initial_state

    track_ids: dict[tuple[int, int], int] = {}
    next_track_id = 1
    for result in scene_results:
        for track in result["tracks"]:
            key = (result["scene_id"], int(track["track_id"]))
            if key not in track_ids:
                track_ids[key] = next_track_id
                next_track_id += 1

    timeline_rows, face_rows, crop_rows, tracks = [], [], [], []
    fallback = FallbackCropCollector()
    next_face_id = 1
    crop_path_map: dict[tuple[int, str], str] = {}
    staged_crops = PersonCropWriter(staged, fps)
    evidence_count = 0
    fallback_count = 0
    try:
        for result in scene_results:
            scene_id = result["scene_id"]
            for local_track in result["tracks"]:
                global_id = track_ids[(scene_id, int(local_track["track_id"]))]
                tracks.append({**local_track, "track_id": global_id, "scene_id": scene_id})

            for row in result["timeline_rows"]:
                copied = dict(row)
                local_id = int(copied["source_track_id"])
                copied["source_track_id"] = track_ids[(scene_id, local_id)]
                copied["scene_id"] = scene_id
                timeline_rows.append(copied)

            for row in result["crop_rows"]:
                copied = dict(row)
                local_id = int(copied["source_track_id"])
                global_id = track_ids[(scene_id, local_id)]
                old_path = str(copied["crop_path"])
                new_path = (Path("person_crops") / f"track_{global_id:04d}" / Path(old_path).name).as_posix()
                source = result["crop_dir"].parent / old_path
                target = staged / new_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                crop_path_map[(scene_id, old_path)] = new_path
                copied.update({
                    "crop_id": len(crop_rows) + 1,
                    "source_track_id": global_id, "scene_id": scene_id,
                    "crop_path": new_path,
                })
                crop_rows.append(copied)

            for row in result["face_rows"]:
                copied = dict(row)
                local_id = int(copied["source_track_id"])
                old_face_crop = str(copied.get("person_crop_path", ""))
                copied.update({
                    "face_id": next_face_id,
                    "source_track_id": track_ids[(scene_id, local_id)],
                    "scene_id": scene_id,
                })
                if old_face_crop:
                    copied["person_crop_path"] = crop_path_map[(scene_id, old_face_crop)]
                face_rows.append(copied)
                next_face_id += 1

            for local_id, observations in result["fallback"].observations.items():
                global_id = track_ids[(scene_id, int(local_id))]
                fallback.observations[global_id].extend(
                    (frame, scene_id, bbox, confidence)
                    for frame, _old_scene_id, bbox, confidence in observations
                )
            for local_id in result["fallback"].with_faces:
                fallback.with_faces.add(track_ids[(scene_id, int(local_id))])

        report_progress(progress_cb, "Fallback-Crops werden gespeichert …", 0, total_frames,
                        {"phase": "fallback", "unit": "frames"})
        fallback_count = fallback.save(
            video_path, staged_crops,
            lambda message, current, total: report_progress(
                progress_cb, message, current, total,
                {"phase": "fallback", "unit": "frames"},
            ),
        )
        staged_crops.close()
        staged_crops = None
        fallback_rows = read_manifest(staged)
        for index, row in enumerate(fallback_rows, start=len(crop_rows) + 1):
            row["crop_id"] = index
        evidence_count = len(crop_rows)
        write_manifest(staged, crop_rows + fallback_rows)
    finally:
        if staged_crops is not None:
            staged_crops.close()

    stage_state.write_csv(staged / TIMELINE, timeline_rows, TIMELINE_FIELDS)
    stage_state.write_csv(staged / "face_observations.csv", face_rows, FaceObservationWriter.FIELDS)
    stats = {
        "frames": total_frames,
        "tracking_frames": sum(result["counts"]["tracking_frames"] for result in scene_results),
        "faces_detected": sum(result["counts"]["faces_detected"] for result in scene_results),
        "faces_assigned": sum(result["counts"]["faces_assigned"] for result in scene_results),
        "faces_usable": sum(result["counts"]["faces_usable"] for result in scene_results),
        "person_crops": evidence_count + fallback_count,
        "fallback_crops": fallback_count,
    }
    return tracks, stats


def run_tracking(video_path, job_dir, progress_cb=None, *, tracking_interval_seconds=TRACKING_INTERVAL_SECONDS):
    validate_parameter("tracking_interval_seconds", tracking_interval_seconds)
    cuts = stage_state.scene_cuts(job_dir)
    import cv2

    from .detection import RFDETRPersonDetector
    from .face_detection import RetinaFaceDetector
    from .track_segments import initial_state, timeline

    video_path, job_dir = Path(video_path), Path(job_dir)
    target = stage_state.root(job_dir)
    old_tracks = target / "tracks.json"
    next_revision = int(stage_state.read_json(old_tracks).get("revision", 0)) + 1 if old_tracks.is_file() else 1
    staged = Path(tempfile.mkdtemp(prefix=".person_analysis_new_", dir=job_dir))
    scene_root = staged / "scenes"
    scene_root.mkdir()
    probe = cv2.VideoCapture(str(video_path))
    detector = faces = None
    try:
        if not probe.isOpened():
            raise RuntimeError("Video konnte nicht geöffnet werden.")
        fps = float(probe.get(cv2.CAP_PROP_FPS))
        total_frames = int(probe.get(cv2.CAP_PROP_FRAME_COUNT))
        probe.release()
        if fps <= 0 or total_frames <= 0:
            raise RuntimeError("Ungültige Framerate oder Videolänge.")
        stride = max(1, round(fps * tracking_interval_seconds))
        specs = _scene_specs(total_frames, cuts, stride)
        total_samples = sum(spec["sample_count"] for spec in specs)
        if not specs:
            raise RuntimeError("Das Video enthält keine auswertbaren Trackingframes.")

        report_progress(progress_cb, "Tracking-Modelle werden geladen …", 0, max(1, total_samples), {
            "phase": "models", "completed": 0, "total": max(1, total_samples), "unit": "tracking_frames",
            "workers": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
        })

        task_lock = threading.Lock()
        state = {
            "queued": 0, "running": 0, "completed": 0, "failed": 0,
            "frames": {spec["scene_id"]: 0 for spec in specs},
            "current_task": None,
            "last_emit": 0.0,
        }
        started = time.monotonic()

        def publish_progress(force=False):
            now = time.monotonic()
            with task_lock:
                if not force and now - state["last_emit"] < 0.25:
                    return
                state["last_emit"] = now
                completed_frames = sum(state["frames"].values())
                workers = {key: state[key] for key in ("queued", "running", "completed", "failed")}
                current_task = state["current_task"]
            report_progress(
                progress_cb,
                f"Tracking: {completed_frames}/{total_samples} ausgewertete Frames",
                completed_frames, total_samples,
                {
                    "phase": "scenes", "completed": completed_frames, "total": total_samples,
                    "unit": "tracking_frames", "workers": workers, "current_task": current_task,
                    "elapsed_seconds": round(now - started, 1),
                },
            )

        def task_event(event, spec):
            with task_lock:
                if event == "queued":
                    state["queued"] += 1
                elif event == "started":
                    state["queued"] = max(0, state["queued"] - 1)
                    state["running"] += 1
                    state["current_task"] = {"id": f"scene-{spec['scene_id']}", "unit": "tracking_frames"}
                elif event == "cancelled":
                    state["queued"] = max(0, state["queued"] - 1)
                elif event in {"completed", "failed"}:
                    state["running"] = max(0, state["running"] - 1)
                    state[event] += 1
                    state["current_task"] = {"id": f"scene-{spec['scene_id']}", "status": event}
            publish_progress(force=event in {"completed", "failed"})

        def task_progress(spec, completed, frame_number, _total_frames):
            with task_lock:
                state["frames"][spec["scene_id"]] = completed
                state["current_task"] = {
                    "id": f"scene-{spec['scene_id']}", "current": completed,
                    "total": spec["sample_count"], "unit": "tracking_frames",
                    "frame_number": frame_number,
                }
            publish_progress()

        with model_slot():
            detector = RFDETRPersonDetector()
            faces = RetinaFaceDetector(model_cache_dir=Path(__file__).resolve().parents[3] / "models" / "retinaface")
            detector_lock, faces_lock = threading.Lock(), threading.Lock()
            scene_results = map_bounded(
                specs,
                lambda spec: _process_scene(
                    cv2=cv2, video_path=video_path,
                    scene_dir=scene_root / f"scene_{spec['scene_id']:04d}",
                    spec=spec, fps=fps, total_frames=total_frames, stride=stride,
                    detector=detector, detector_lock=detector_lock,
                    faces=faces, faces_lock=faces_lock, progress_task=task_progress,
                ),
                on_task_event=task_event,
            )

            report_progress(progress_cb, "Tracking-Ergebnisse werden zusammengeführt …", 0, 1, {
                "phase": "merge", "completed": len(scene_results), "total": len(scene_results),
                "unit": "scenes", "workers": {"queued": 0, "running": 0,
                                                  "completed": len(scene_results), "failed": 0},
            })
            tracks, stats = _merge_scenes(scene_results, staged, video_path, fps, progress_cb, total_frames)
            stats.update({"tracking_stride": stride})
            state = initial_state(tracks, fps, stage_state.video_digest(video_path), stats)
            state["revision"] = next_revision
            state["tracking_interval_seconds"] = tracking_interval_seconds
            stage_state.atomic_write(staged / "tracks.json", state)
            shutil.rmtree(scene_root, ignore_errors=True)
            report_progress(progress_cb, "Tracking-Ergebnisse werden veröffentlicht …", 0, 1, {
                "phase": "publishing", "completed": 0, "total": 1, "unit": "publish",
            })
            _publish(staged, target)
            timeline.cache_clear()

        report_progress(progress_cb, "Tracking abgeschlossen", 1, 1, {
            "phase": "complete", "completed": 1, "total": 1, "unit": "publish",
            "elapsed_seconds": round(time.monotonic() - started, 1),
        })
        return stage_state.face_snapshot(job_dir)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    finally:
        probe.release()
