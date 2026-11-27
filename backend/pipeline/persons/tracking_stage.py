"""Stage 1: scene-parallel RF-DETR, ByteTrack, RetinaFace and face quality."""
from __future__ import annotations

import os
import queue
import shutil
import tempfile
import threading
import time
from pathlib import Path

from . import stage_state
from .config import TRACKING_INTERVAL_SECONDS, validate_parameter
from .tracking_telemetry import TrackingTelemetry
from .work_pool import RFDETR_BATCH_SIZE, map_bounded, model_slot, report_progress, worker_count


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
    stride: int, detector, detector_lock, faces, faces_lock, progress_task, telemetry,
    batch_size=RFDETR_BATCH_SIZE, cancel_token=None,
):
    from . import track_segments
    from .appearances import TrackIntervalAccumulator
    from .face_assignment import assign_faces_to_tracks
    from .face_observations import FaceObservationWriter
    from .face_quality import check_face_quality
    from .face_samples import TrackingFaceSampleCollector
    from .person_crops import FallbackCropCollector, PersonCropWriter, read_manifest
    from .tracking import BytePersonTracker

    scene_dir.mkdir(parents=True, exist_ok=True)
    crop_writer = face_writer = timeline_writer = None
    reader_stop = threading.Event()
    supports_batch = callable(getattr(detector, "detect_batch", None)) or (
        callable(getattr(detector, "prepare_batch", None))
        and callable(getattr(detector, "detect_prepared_batch", None))
    )
    if not supports_batch:
        # Simple detector adapters keep the historical detect/update interleave.
        # Production RF-DETR exposes native batching and takes the batch path.
        batch_size = 1
    # Bound each scene to one prefetched batch to keep high-resolution videos
    # from multiplying memory use across all active scene workers.
    frame_queue = queue.Queue(maxsize=max(1, batch_size))
    reader_error = []
    end_of_scene = object()

    def put_frame(item):
        while not reader_stop.is_set():
            try:
                frame_queue.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def read_scene_frames():
        capture = None
        try:
            capture, last_grabbed = _open_at_frame(cv2, video_path, spec["first_sample"])
            frame_number = spec["first_sample"]
            while frame_number <= spec["end_frame"]:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                decode_started = time.perf_counter()
                while last_grabbed < frame_number:
                    if not capture.grab():
                        raise RuntimeError(f"Tracking-Frame {frame_number} konnte nicht gelesen werden.")
                    last_grabbed += 1
                ok, frame = capture.retrieve()
                if not ok:
                    raise RuntimeError(f"Tracking-Frame {frame_number} konnte nicht dekodiert werden.")
                telemetry.record_decoded_frame(time.perf_counter() - decode_started)
                telemetry.frame_enqueued()
                if not put_frame((frame_number, frame)):
                    telemetry.frame_dequeued()
                    return
                frame_number += stride
        except BaseException as exc:
            reader_error.append(exc)
        finally:
            if capture is not None:
                capture.release()
            put_frame(end_of_scene)

    reader = threading.Thread(target=read_scene_frames, name=f"tracking-reader-{spec['scene_id']}", daemon=True)
    try:
        tracker = BytePersonTracker(frame_rate=fps / stride)
        accumulator, fallback = TrackIntervalAccumulator(fps), FallbackCropCollector()
        face_sample_collector = TrackingFaceSampleCollector()
        crop_writer = PersonCropWriter(scene_dir, fps)
        face_writer = FaceObservationWriter(scene_dir, fps)
        timeline_writer = track_segments.TimelineWriter(scene_dir)
        counts = {
            "tracking_frames": 0, "faces_detected": 0,
            "faces_assigned": 0, "faces_usable": 0,
        }
        reader.start()
        scene_finished = False
        while not scene_finished:
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            frame_batch = []
            while len(frame_batch) < batch_size:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                item = frame_queue.get()
                if item is end_of_scene:
                    scene_finished = True
                    break
                telemetry.frame_dequeued()
                frame_batch.append(item)

            if frame_batch:
                frames = [frame for _frame_number, frame in frame_batch]
                prepare_batch = getattr(detector, "prepare_batch", None)
                detect_prepared_batch = getattr(detector, "detect_prepared_batch", None)
                if callable(prepare_batch) and callable(detect_prepared_batch):
                    preprocess_started = time.perf_counter()
                    prepared_frames = prepare_batch(frames)
                    telemetry.record_detector_preprocess(time.perf_counter() - preprocess_started)
                    batch_detections = telemetry.run_inference(
                        "rfdetr", detector_lock, len(frames),
                        lambda: detect_prepared_batch(prepared_frames), cancel_token,
                    )
                elif callable(getattr(detector, "detect_batch", None)):
                    batch_detections = telemetry.run_inference(
                        "rfdetr", detector_lock, len(frames),
                        lambda: detector.detect_batch(frames), cancel_token,
                    )
                else:
                    # Keep compatibility with simple detector adapters while
                    # production RF-DETR uses its native list/batch API.
                    batch_detections = telemetry.run_inference(
                        "rfdetr", detector_lock, len(frames),
                        lambda: [detector.detect(frame) for frame in frames], cancel_token,
                    )
                if len(batch_detections) != len(frame_batch):
                    raise RuntimeError("RF-DETR gab nicht für jedes Batch-Bild Detektionen zurück.")

                # Detection is batched; ByteTrack still receives every result
                # in its original scene order to preserve association state.
                for (frame_number, frame), detections in zip(frame_batch, batch_detections):
                    if cancel_token is not None:
                        cancel_token.raise_if_cancelled()
                    tracker_started = time.perf_counter()
                    tracked = [
                        {**person, "scene_id": spec["scene_id"]}
                        for person in tracker.update(detections)
                    ]
                    telemetry.record_tracker_update(time.perf_counter() - tracker_started)
                    counts["tracking_frames"] += 1
                    for person in tracked:
                        timeline_writer.observe(person, frame_number, frame.shape[1], frame.shape[0])
                        accumulator.observe(person["track_id"], spec["scene_id"], frame_number)
                        fallback.observe(person, frame_number)

                    # Preserve the global cadence even when a scene starts
                    # between sampled frames.
                    tracking_ordinal = (frame_number - 1) // stride
                    if tracking_ordinal % 2 == 0 and tracked:
                        detected_faces = telemetry.run_inference(
                            "retinaface", faces_lock, 1, lambda: faces.detect(frame), cancel_token,
                        )
                        counts["faces_detected"] += len(detected_faces)
                        for index, person in assign_faces_to_tracks(detected_faces, tracked).items():
                            if cancel_token is not None:
                                cancel_token.raise_if_cancelled()
                            face = detected_faces[index]
                            usable, quality = check_face_quality(face["crop"], float(face["confidence"]))
                            counts["faces_assigned"] += 1
                            counts["faces_usable"] += int(usable)
                            crop_path = None
                            if usable:
                                crop_started = time.perf_counter()
                                crop_path = crop_writer.save(
                                    frame, person["track_id"], spec["scene_id"], frame_number,
                                    person["bbox"], person.get("confidence"), "face_evidence",
                                )
                                telemetry.record_crop_write(time.perf_counter() - crop_started)
                                if crop_path is None:
                                    raise RuntimeError("Personencrop einer verwendbaren Beobachtung fehlt.")
                                fallback.face_succeeded(person["track_id"])
                            face_id = face_writer.save(
                                source_track_id=person["track_id"], scene_id=spec["scene_id"], frame_number=frame_number,
                                person_bbox=person["bbox"], face_bbox=face["bbox"], person_crop_path=crop_path,
                                frame_width=frame.shape[1], frame_height=frame.shape[0], face_confidence=face["confidence"],
                                face_usable=usable, blur_score=quality.get("blur_score"), landmarks=face["landmarks"],
                                face_crop_box=face["face_crop_box"],
                            )
                            if usable:
                                face_sample_collector.observe(person["track_id"], frame_number, face_id, face["crop"])

                    progress_task(spec, counts["tracking_frames"], frame_number, total_frames)

            if scene_finished and reader_error:
                raise reader_error[0]

        for writer in (crop_writer, face_writer, timeline_writer):
            writer.close()
        crop_writer = face_writer = timeline_writer = None
        timeline_rows, _ = stage_state.read_csv(scene_dir / track_segments.TIMELINE)
        face_rows, _ = stage_state.read_csv(scene_dir / "face_observations.csv")
        face_sample_paths = face_sample_collector.save(scene_dir)
        for row in face_rows:
            row["face_sample_path"] = face_sample_paths.get(int(row["face_id"]), "")
        crop_rows = read_manifest(scene_dir)
        return {
            **spec,
            "counts": counts,
            "tracks": accumulator.result(),
            "fallback": fallback,
            "timeline_rows": timeline_rows,
            "face_rows": face_rows,
            "crop_rows": crop_rows,
            "scene_dir": scene_dir,
            "crop_dir": scene_dir / "person_crops",
        }
    finally:
        reader_stop.set()
        if reader.is_alive():
            reader.join()
        for writer in (crop_writer, face_writer, timeline_writer):
            if writer is not None:
                writer.close()


def _merge_scenes(scene_results: list[dict], staged: Path, video_path: Path, fps: float, progress_cb,
                  total_frames: int, cancel_token=None):
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
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            scene_id = result["scene_id"]
            for local_track in result["tracks"]:
                global_id = track_ids[(scene_id, int(local_track["track_id"]))]
                tracks.append({**local_track, "track_id": global_id, "scene_id": scene_id})

            for row in result["timeline_rows"]:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                copied = dict(row)
                local_id = int(copied["source_track_id"])
                copied["source_track_id"] = track_ids[(scene_id, local_id)]
                copied["scene_id"] = scene_id
                timeline_rows.append(copied)

            for row in result["crop_rows"]:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
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
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                copied = dict(row)
                local_id = int(copied["source_track_id"])
                old_face_crop = str(copied.get("person_crop_path", ""))
                copied.update({
                    "face_id": next_face_id,
                    "source_track_id": track_ids[(scene_id, local_id)],
                    "scene_id": scene_id,
                })
                old_sample_path = str(copied.get("face_sample_path") or "").replace("\\", "/")
                if old_sample_path:
                    scene_root = Path(result["scene_dir"]).resolve()
                    source_sample = (scene_root / old_sample_path).resolve()
                    if not source_sample.is_relative_to((scene_root / "person_crops" / ".face_samples").resolve()):
                        raise RuntimeError("Ungültiger Pfad für gespeicherte Gesichtsprobe.")
                    global_id = track_ids[(scene_id, local_id)]
                    sample_relative = Path("person_crops") / ".face_samples" / f"track_{global_id:04d}" / source_sample.name
                    sample_target = staged / sample_relative
                    sample_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_sample, sample_target)
                    copied["face_sample_path"] = sample_relative.as_posix()
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
            cancel_token=cancel_token,
        )
        staged_crops.close()
        staged_crops = None
        fallback_rows = read_manifest(staged)
        for index, row in enumerate(fallback_rows, start=len(crop_rows) + 1):
            row["crop_id"] = index
        evidence_count = len(crop_rows)
        write_manifest(staged, crop_rows + fallback_rows)
        face_sample_count = sum(bool(row.get("face_sample_path")) for row in face_rows)
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
        "face_samples": face_sample_count,
    }
    return tracks, stats


def run_tracking(video_path, job_dir, progress_cb=None, *, tracking_interval_seconds=TRACKING_INTERVAL_SECONDS,
                 cancel_token=None):
    validate_parameter("tracking_interval_seconds", tracking_interval_seconds)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
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
    telemetry = TrackingTelemetry()
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
                    "elapsed_seconds": round(now - started, 1), "pipeline": telemetry.snapshot(),
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
                elif event == "cancelled_running":
                    state["running"] = max(0, state["running"] - 1)
                    state["current_task"] = {"id": f"scene-{spec['scene_id']}", "status": "cancelled"}
                elif event in {"completed", "failed"}:
                    state["running"] = max(0, state["running"] - 1)
                    state[event] += 1
                    state["current_task"] = {"id": f"scene-{spec['scene_id']}", "status": event}
            publish_progress(force=event in {"completed", "failed", "cancelled_running"})

        def task_progress(spec, completed, frame_number, _total_frames):
            with task_lock:
                state["frames"][spec["scene_id"]] = completed
                state["current_task"] = {
                    "id": f"scene-{spec['scene_id']}", "current": completed,
                    "total": spec["sample_count"], "unit": "tracking_frames",
                    "frame_number": frame_number,
                }
            publish_progress()

        with model_slot(cancel_token):
            detector = RFDETRPersonDetector()
            faces = RetinaFaceDetector(model_cache_dir=Path(__file__).resolve().parents[3] / "models" / "retinaface")
            detector_lock, faces_lock = threading.Lock(), threading.Lock()
            telemetry.start_gpu_sampling(getattr(detector, "device", None) == "cuda")
            try:
                scene_results = map_bounded(
                    specs,
                    lambda spec: _process_scene(
                        cv2=cv2, video_path=video_path,
                        scene_dir=scene_root / f"scene_{spec['scene_id']:04d}",
                        spec=spec, fps=fps, total_frames=total_frames, stride=stride,
                        detector=detector, detector_lock=detector_lock,
                        faces=faces, faces_lock=faces_lock, progress_task=task_progress,
                        telemetry=telemetry, batch_size=RFDETR_BATCH_SIZE,
                        cancel_token=cancel_token,
                    ),
                    on_task_event=task_event,
                    cancel_token=cancel_token,
                )
            finally:
                telemetry.stop_gpu_sampling()

            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            report_progress(progress_cb, "Tracking-Ergebnisse werden zusammengeführt …", 0, 1, {
                "phase": "merge", "completed": len(scene_results), "total": len(scene_results),
                "unit": "scenes", "workers": {"queued": 0, "running": 0,
                                                  "completed": len(scene_results), "failed": 0},
            })
            tracks, stats = _merge_scenes(
                scene_results, staged, video_path, fps, progress_cb, total_frames, cancel_token,
            )
            stats.update({
                "tracking_stride": stride,
                "cpu_workers": worker_count(),
                "rfdetr_batch_size": RFDETR_BATCH_SIZE,
                "tracking_pipeline": telemetry.snapshot(),
            })
            video_sha256 = stage_state.video_digest(video_path)
            video_file_signature = stage_state.video_signature(video_path)
            state = initial_state(tracks, fps, video_sha256, stats)
            state["video_signature"] = video_file_signature
            state["revision"] = next_revision
            state["tracking_interval_seconds"] = tracking_interval_seconds
            stage_state.atomic_write(staged / "tracks.json", state)
            shutil.rmtree(scene_root, ignore_errors=True)
            report_progress(progress_cb, "Tracking-Ergebnisse werden veröffentlicht …", 0, 1, {
                "phase": "publishing", "completed": 0, "total": 1, "unit": "publish",
            })
            if cancel_token is not None:
                cancel_token.begin_commit()
            _publish(staged, target)
            timeline.cache_clear()

        report_progress(progress_cb, "Tracking abgeschlossen", 1, 1, {
            "phase": "complete", "completed": 1, "total": 1, "unit": "publish",
            "elapsed_seconds": round(time.monotonic() - started, 1), "pipeline": telemetry.snapshot(),
        })
        return stage_state.face_snapshot(job_dir)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    finally:
        probe.release()
