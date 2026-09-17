"""Stage 1: RF-DETR, ByteTrack, RetinaFace und Face-Quality."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import stage_state


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


def run_tracking(video_path, job_dir, progress_cb=None):
    import cv2

    from ..person_analysis import assign_faces_to_tracks
    from .appearances import TrackIntervalAccumulator
    from .config import TRACKING_INTERVAL_SECONDS
    from .detection import RFDETRPersonDetector
    from .face_detection import RetinaFaceDetector
    from .face_observations import FaceObservationWriter
    from .face_quality import check_face_quality
    from .person_crops import FallbackCropCollector, PersonCropWriter
    from .track_segments import TimelineWriter, initial_state, timeline
    from .tracking import BytePersonTracker, detect_scene_change_frames

    video_path, job_dir = Path(video_path), Path(job_dir)
    target = stage_state.root(job_dir)
    old_tracks = target / "tracks.json"
    next_revision = int(stage_state.read_json(old_tracks).get("revision", 0)) + 1 if old_tracks.is_file() else 1
    staged = Path(tempfile.mkdtemp(prefix=".person_analysis_new_", dir=job_dir))
    capture = cv2.VideoCapture(str(video_path))
    crop_writer = face_writer = timeline_writer = None
    try:
        if not capture.isOpened():
            raise RuntimeError("Video konnte nicht geöffnet werden.")
        fps, total = float(capture.get(cv2.CAP_PROP_FPS)), int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0:
            raise RuntimeError("Ungültige Framerate.")
        stride = max(1, round(fps * TRACKING_INTERVAL_SECONDS))
        if progress_cb:
            progress_cb("Szenenwechsel werden erkannt ...", 0, total)

        cuts = iter(sorted(detect_scene_change_frames(video_path)))
        next_cut = next(cuts, None)
        detector, tracker = RFDETRPersonDetector(), BytePersonTracker(frame_rate=fps / stride)
        faces = RetinaFaceDetector(model_cache_dir=Path(__file__).resolve().parents[3] / "models" / "retinaface")
        accumulator, fallback = TrackIntervalAccumulator(fps), FallbackCropCollector()
        crop_writer, face_writer, timeline_writer = PersonCropWriter(staged, fps), FaceObservationWriter(staged, fps), TimelineWriter(staged)
        counts = {"frames": 0, "tracking_frames": 0, "tracking_stride": stride, "faces_detected": 0, "faces_assigned": 0, "faces_usable": 0}

        while True:
            if not capture.grab():
                break
            counts["frames"] += 1
            number = counts["frames"]
            if progress_cb and (number % max(1, round(fps)) == 0 or number == total):
                progress_cb(f"Tracking & Gesichter: Frame {number}/{total}", number, total)
            if (number - 1) % stride != 0:
                continue
            ok, frame = capture.retrieve()
            if not ok:
                raise RuntimeError(f"Tracking-Frame {number} konnte nicht gelesen werden.")
            # Apply every crossed cut, including cuts on skipped frames.
            while next_cut is not None and next_cut <= number:
                tracker.start_new_scene()
                next_cut = next(cuts, None)
            tracked = tracker.update(detector.detect(frame))
            counts["tracking_frames"] += 1
            for person in tracked:
                timeline_writer.observe(person, number, frame.shape[1], frame.shape[0])
                accumulator.observe(person["track_id"], person["scene_id"], number)
                fallback.observe(person, number)

            if (counts["tracking_frames"] - 1) % 2 == 0 and tracked:
                detected = faces.detect(frame)
                counts["faces_detected"] += len(detected)
                for index, person in assign_faces_to_tracks(detected, tracked).items():
                    face = detected[index]
                    usable, quality = check_face_quality(face["crop"], float(face["confidence"]))
                    counts["faces_assigned"] += 1
                    counts["faces_usable"] += int(usable)
                    crop_path = None
                    if usable:
                        crop_path = crop_writer.save(frame, person["track_id"], person["scene_id"], number,
                                                     person["bbox"], person.get("confidence"), "face_evidence")
                        if crop_path is None:
                            raise RuntimeError("Personencrop einer verwendbaren Beobachtung fehlt.")
                        fallback.face_succeeded(person["track_id"])
                    face_writer.save(
                        source_track_id=person["track_id"], scene_id=person["scene_id"], frame_number=number,
                        person_bbox=person["bbox"], face_bbox=face["bbox"], person_crop_path=crop_path,
                        frame_width=frame.shape[1], frame_height=frame.shape[0], face_confidence=face["confidence"],
                        face_usable=usable, blur_score=quality.get("blur_score"), landmarks=face["landmarks"],
                        face_crop_box=face["face_crop_box"],
                    )

        fallback_count = fallback.save(video_path, crop_writer, progress_cb)
        stats = {**counts, "person_crops": crop_writer.crop_count, "fallback_crops": fallback_count}
        state = initial_state(accumulator.result(), fps, stage_state.video_digest(video_path), stats)
        state["revision"] = next_revision
        stage_state.atomic_write(staged / "tracks.json", state)
        crop_writer.close(); face_writer.close(); timeline_writer.close()
        crop_writer = face_writer = timeline_writer = None
        _publish(staged, target)
        timeline.cache_clear()
        return stage_state.face_snapshot(job_dir)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    finally:
        capture.release()
        for writer in (crop_writer, face_writer, timeline_writer):
            if writer is not None:
                writer.close()
