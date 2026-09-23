"""Image extraction is the single source of full-video tracking cuts."""
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.pipeline.persons import stage_state, review_artifacts
from backend.pipeline.persons.tracking_stage import run_tracking
from backend.tests.test_person_stages import staged_job
from backend.tests.test_image_extraction_progress import _FakeSceneManager, _FakeContentDetector


def test_real_scene_detection_keeps_exact_cuts_outside_image_window(tmp_path):
    import cv2
    import numpy as np
    from backend.pipeline.image_extraction import MidframeExtractor
    video = tmp_path / 'cuts.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 30, (64, 64))
    assert writer.isOpened()
    try:
        for value in (0, 255, 0):
            for _ in range(30):
                writer.write(np.full((64, 64, 3), value, dtype=np.uint8))
    finally:
        writer.release()
    extractor = MidframeExtractor(output_dir=str(tmp_path / 'frames'), min_bytes=100)
    _, scenes = extractor.process_video(str(video), window_start_s=1.2, window_end_s=1.8)
    assert scenes == [(1.2, 1.8)]
    assert extractor.scene_cut_frames == [31, 61]


def test_image_window_keeps_full_video_cuts(monkeypatch, tmp_path):
    import scenedetect
    import scenedetect.detectors
    from backend.pipeline import image_extraction as images
    monkeypatch.setattr(images, '_video_frame_count', lambda _: 225)
    monkeypatch.setattr(scenedetect, 'open_video', lambda _: object())
    monkeypatch.setattr(scenedetect, 'SceneManager', _FakeSceneManager)
    monkeypatch.setattr(scenedetect.detectors, 'ContentDetector', _FakeContentDetector)
    extractor = images.MidframeExtractor(output_dir=str(tmp_path))
    seen = []
    monkeypatch.setattr(extractor, 'extract_frames', lambda video, scenes, **kw: seen.extend(scenes) or [])
    extractor.process_video('video', window_start_s=4, window_end_s=6)
    assert seen == [(4, 6)]
    assert extractor.scene_cut_frames == [91]  # Cut at 3s survives window clipping.
    monkeypatch.setattr(_FakeSceneManager, 'get_scene_list', lambda self: [])
    extractor.process_video('video')
    assert extractor.scene_cut_frames == []  # Completed detection without cuts is valid.


@pytest.mark.parametrize('cuts', [None, [0], [3, 2], [3, 3], [2.5]])
def test_missing_or_invalid_cuts_fail_before_tracking(staged_job, cuts):
    job, video, calls = staged_job
    payload = json.loads((job / 'job.json').read_text())
    payload['scene_cut_frames'] = cuts
    (job / 'job.json').write_text(json.dumps(payload))
    with pytest.raises(review_artifacts.ReviewError, match='Bilder extrahieren'):
        run_tracking(video, job)
    assert calls['detection'] == 0
    assert not (job / 'person_analysis').exists()


def test_no_cuts_means_one_continuous_tracking_pass(staged_job):
    job, video, calls = staged_job
    payload = json.loads((job / 'job.json').read_text())
    payload['scene_cut_frames'] = []
    (job / 'job.json').write_text(json.dumps(payload))
    run_tracking(video, job)
    assert calls['tracking'] > 0
    assert calls['resets'] == []


def test_saved_cuts_and_invalidation_survive_restart(staged_job, monkeypatch):
    from backend import session_manager as sm
    job, video, _ = staged_job
    run_tracking(video, job)
    monkeypatch.setattr(sm, '_BASE_DIR', job.parent)
    monkeypatch.setattr(sm, '_STORE', {})
    sm.get_job('job')
    root = job / 'person_analysis'
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    sm.update_job('job', scene_cut_frames=[31])
    assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    # Also invalidate any dependent current results and legacy projection.
    (root / 'persons.json').write_text('{}')
    (root / 'attributes.json').write_text('{}')
    (job / 'persons_df.parquet').write_bytes(b'old projection')
    sm.update_job('job', scene_cut_frames=[15, 31])
    assert not root.exists()
    assert not (job / 'persons_df.parquet').exists()
    sm._STORE.clear()
    restored = sm.get_job('job')
    assert restored['scene_cut_frames'] == [15, 31]
    assert restored['persons_df'] is None
    assert not stage_state.status(job)['tracking_ready']
    assert stage_state.scene_cuts(job) == [15, 31]


def test_changed_cuts_cannot_replace_a_running_person_stage(staged_job, monkeypatch):
    from backend import session_manager as sm
    job, video, _ = staged_job
    run_tracking(video, job)
    monkeypatch.setattr(sm, '_BASE_DIR', job.parent)
    monkeypatch.setattr(sm, '_STORE', {})
    sm.get_job('job')
    sm.begin_person_stage('job', 'tracking')
    with pytest.raises(review_artifacts.ReviewError, match='abwarten'):
        sm.update_job('job', scene_cut_frames=[15])
    assert stage_state.scene_cuts(job) == [31]
    assert (job / 'person_analysis' / 'tracks.json').exists()


def test_api_reserves_images_and_publishes_cuts(staged_job, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    from pipeline import image_extraction as images
    job, video, _ = staged_job
    monkeypatch.setattr(sm, '_BASE_DIR', job.parent)
    monkeypatch.setattr(sm, '_STORE', {})
    monkeypatch.setattr(app, '_DATASTORE', SimpleNamespace(enabled=False))
    sm.get_job('job')
    sm.update_job('job', slots_df=pd.DataFrame([{'slot': 1, 'start_s': 0, 'end_s': 1}]))
    queued = []
    monkeypatch.setattr(app, '_start_worker', lambda *args: queued.append(args))
    class Extractor:
        def __init__(self, **kw): pass
        def process_video(self, *args, **kw):
            self.scene_cut_frames = [20]
            return [], []
    monkeypatch.setattr(images, 'MidframeExtractor', Extractor)
    monkeypatch.setattr(images, 'gapfill_images_for_ad_slots', lambda **kw: ([], pd.DataFrame()))
    client = TestClient(app.app)
    assert client.post('/api/jobs/job/images', json={}).status_code == 200
    assert client.post('/api/jobs/job/person-analysis/tracking').status_code == 409
    assert client.post('/api/jobs/job/images', json={}).status_code == 409
    queued[0][-1]()
    assert stage_state.scene_cuts(job) == [20]
    assert client.post('/api/jobs/job/person-analysis/tracking').status_code == 200
    assert client.post('/api/jobs/job/images', json={}).status_code == 409


def test_api_missing_cuts_explains_prerequisite(staged_job, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    job, _, _ = staged_job
    payload = json.loads((job / 'job.json').read_text())
    payload.pop('scene_cut_frames')
    (job / 'job.json').write_text(json.dumps(payload))
    monkeypatch.setattr(sm, '_BASE_DIR', job.parent)
    monkeypatch.setattr(sm, '_STORE', {})
    monkeypatch.setattr(app, '_DATASTORE', SimpleNamespace(enabled=False))
    client = TestClient(app.app)
    response = client.post('/api/jobs/job/person-analysis/tracking')
    assert response.status_code == 409
    assert 'Bilder extrahieren' in response.json()['error']
