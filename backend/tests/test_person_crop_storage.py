"""Real JPEG persistence; no every-frame crops or write-then-delete strategy."""
import sys
import cv2
import numpy as np
from backend.pipeline.persons.person_crops import FallbackCropCollector
from backend.pipeline.persons import review_artifacts, stage_state
from backend.pipeline.persons.tracking_stage import run_tracking
from backend.pipeline.persons.identity_stage import run_identities
from test_person_stages import staged_job  # noqa: F401 - shared deterministic fixture


def test_fallback_keeps_coordinates_and_removes_successful_tracks():
    collector = FallbackCropCollector()
    for frame in range(1, 1001):
        for tid in (1, 2):
            collector.observe({"track_id": tid, "scene_id": 1, "bbox": np.array([0, 0, 10, 20])}, frame)
        if frame == 3:
            collector.face_succeeded(1)
    assert set(collector.observations) == {2}
    selected = collector.selected()
    assert sorted(selected) == [1, 251, 500, 750, 1000]
    assert all(isinstance(row[2], tuple) for row in collector.observations[2])
    gaps = FallbackCropCollector()
    for frame in [1, 2, 3, 4, 1000]:
        gaps.observe({"track_id": 1, "scene_id": 1, "bbox": (0, 0, 10, 20)}, frame)
    assert len(gaps.selected()) == 5


def test_only_selected_full_person_crops_are_encoded(staged_job, monkeypatch):
    job, video, calls = staged_job
    writes = []
    actual = cv2.imencode
    def encode(extension, image, options):
        writes.append(image.shape)
        return actual(extension, image, options)
    monkeypatch.setattr(cv2, "imencode", encode)
    run_tracking(video, job)
    run_identities(video, job)
    assert calls["detection"] == calls["tracking"] == 61
    assert len(list((job / "person_analysis").rglob("*.jpg"))) == len(writes) == 25
    assert all(shape == (100, 40, 3) for shape in writes)
    data = review_artifacts.load(job)
    assert len(data.review_crops(1)) == 4
    assert all(data.crop_file(cid).is_file() for cid in data.crops)


def test_no_faces_keeps_all_tracks_and_fallbacks(staged_job, monkeypatch):
    job, video, calls = staged_job
    faces = sys.modules["backend.pipeline.persons.face_detection"].RetinaFaceDetector
    monkeypatch.setattr(faces, "detect", lambda self, frame: [])
    run_tracking(video, job)
    result = run_identities(video, job)
    assert result["persons"] == [] and len(result["unassigned_tracks"]) == 5
    assert calls["detection"] == calls["tracking"] == 61
    assert calls["recognition"] == []
    assert len(list((job / "person_analysis").rglob("*.jpg"))) == 25
    data = review_artifacts.load(job)
    assert all(len(data.review_crops(tid)) == 5 for tid in data.tracks)
    assert stage_state.status(job)["identities_ready"] is True
