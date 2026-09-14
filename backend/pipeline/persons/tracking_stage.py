"""Stage 1: every-frame tracking and sampled RetinaFace/quality. No recognition."""
from pathlib import Path

from . import stage_state


def run_tracking(video_path, job_dir, progress_cb=None):
    import cv2
    from ..person_analysis import assign_faces_to_tracks
    from .appearances import TrackIntervalAccumulator
    from .config import ANALYSIS_INTERVAL_SECONDS
    from .detection import RFDETRPersonDetector
    from .tracking import BytePersonTracker, detect_scene_change_frames
    from .face_detection import RetinaFaceDetector
    from .face_quality import check_face_quality
    from .person_crops import PersonCropWriter, FallbackCropCollector
    from .face_observations import FaceObservationWriter
    from .track_segments import TimelineWriter

    video_path = Path(video_path)
    digest = stage_state.video_digest(video_path)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError("Video konnte nicht geöffnet werden.")
    crop_writer = face_writer = timeline_writer = None
    try:
        fps, total = float(capture.get(cv2.CAP_PROP_FPS)), int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0:
            raise RuntimeError("Ungültige Framerate.")
        interval = max(1, int(round(fps * ANALYSIS_INTERVAL_SECONDS)))
        run_id, output = stage_state.new_run(job_dir, "tracking")
        if progress_cb:
            progress_cb("Szenenwechsel werden erkannt ...", 0, total)
        cuts = detect_scene_change_frames(video_path)
        detector, tracker = RFDETRPersonDetector(), BytePersonTracker(frame_rate=fps)
        faces = RetinaFaceDetector(model_cache_dir=Path(__file__).resolve().parents[3] / "models" / "retinaface")
        accumulator = TrackIntervalAccumulator(fps)
        crop_writer = PersonCropWriter(output, fps, clear_existing=False)
        face_writer = FaceObservationWriter(output, fps, clear_existing=False)
        timeline_writer = TimelineWriter(output)
        fallback, all_coordinates = FallbackCropCollector(), FallbackCropCollector()
        counts = {"frames": 0, "faces_detected": 0, "faces_assigned": 0, "faces_usable": 0}
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            counts["frames"] += 1
            number = counts["frames"]
            tracked = tracker.update(detector.detect(frame), scene_change=number in cuts)
            for person in tracked:
                timeline_writer.observe(person, number, frame.shape[1], frame.shape[0])
                accumulator.observe(person["track_id"], person["scene_id"], number)
                fallback.observe(person, number)
                all_coordinates.observe(person, number)
            if (number - 1) % interval == 0 and tracked:
                detected = faces.detect(frame)
                counts["faces_detected"] += len(detected)
                for index, person in assign_faces_to_tracks(detected, tracked).items():
                    face = detected[index]
                    usable, quality = check_face_quality(face["crop"], float(face["confidence"]))
                    counts["faces_assigned"] += 1
                    counts["faces_usable"] += int(usable)
                    crop_path = None
                    if usable:
                        crop_path = crop_writer.save(frame, person["track_id"], person["scene_id"], number, person["bbox"], person.get("confidence"))
                        if crop_path is None:
                            raise RuntimeError("Personencrop einer verwendbaren Beobachtung fehlt.")
                        fallback.face_succeeded(int(person["track_id"]))
                    face_writer.save(
                        track_id=person["track_id"], scene_id=person["scene_id"], frame_number=number,
                        person_bbox=person["bbox"], face_bbox=face["bbox"], person_crop_path=crop_path,
                        frame_width=frame.shape[1], frame_height=frame.shape[0],
                        face_confidence=face["confidence"], face_usable=usable, blur_score=quality.get("blur_score"),
                        landmarks=face["landmarks"], face_crop_box=face["face_crop_box"],
                    )
            if progress_cb and (number % max(1, round(fps)) == 0 or number == total):
                progress_cb(f"Tracking & Gesichter: Frame {number}/{total}", number, total)
        capture.release()
        fallback_count = fallback.save(video_path, crop_writer, progress_cb)
        tracks = accumulator.result()
        # Five numeric coordinate records per track allow body fallbacks after all
        # faces of a track are manually excluded. No frame arrays are retained.
        candidates = [{"frame_number": number, "track_id": tid, "scene_id": scene, "bbox": bbox,
                       "confidence": float(confidence) if confidence is not None else None}
                      for number, rows in all_coordinates.selected().items() for tid, scene, bbox, confidence in rows]
        stage_state.atomic_write(output / "tracks.json", {"tracks": tracks, "fps": fps,
            "video_sha256": digest, "stats": {**counts, "person_crops": crop_writer.crop_count, "fallback_crops": fallback_count},
            "fallback_candidates": candidates})
    finally:
        capture.release()
        if crop_writer:
            crop_writer.close()
        if face_writer:
            face_writer.close()
        if timeline_writer:
            timeline_writer.close()
    stage_state.publish(job_dir, run_id)
    return stage_state.face_snapshot(job_dir)
