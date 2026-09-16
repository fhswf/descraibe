"""Attribute integration with real saved crops and an isolated Qwen double."""
import json
import subprocess
import sys
from types import SimpleNamespace
import pytest

from test_person_stages import staged_job, run_tracking, run_identities
from backend.pipeline.persons import attribute_stage, attribute_state, attribute_selection, review_state, stage_state
from backend.pipeline.persons.qwen_attributes import FIELDS, parse_json
from backend.pipeline.persons.review_artifacts import ReviewError


@pytest.fixture
def attribute_job(staged_job, monkeypatch):
    job, video, _ = staged_job
    run_tracking(video, job)
    run_identities(video, job)
    calls = []
    class Model:
        def __enter__(self):
            calls.append('load')
            return self
        def __exit__(self, *args):
            calls.append('close')
        def predict(self, pid, paths):
            calls.append((pid, paths))
            return json.dumps({field: 'automatic' for field in FIELDS})
    monkeypatch.setattr(attribute_stage, 'QwenAttributes', Model)
    return job, video, calls


def test_run_overrides_reload_reset_and_stale(attribute_job):
    job, video, calls = attribute_job
    result = attribute_stage.run_attributes(video, job)
    assert calls[0] == 'load' and calls[-1] == 'close' and len(calls) == 3
    assert len(result['persons'][0]['images']) == 1
    assert len(result['persons'][0]['automatic']) == 12
    output = attribute_state.run_root(job, result['run_id']) / 'attributes.json'
    original = output.read_bytes()
    field = FIELDS[0]
    saved = attribute_state.save_review(job, {'version': result['version'], 'changes': [
        {'person_id': 1, 'field': field, 'value': 'manual'}]})
    assert attribute_state.snapshot(job)['persons'][0]['effective'][field] == 'manual'
    assert saved['persons'][0]['automatic'][field] == 'automatic'
    assert output.read_bytes() == original
    with pytest.raises(ReviewError):
        attribute_state.save_review(job, {'version': result['version'], 'changes': []})
    reset = attribute_state.save_review(job, {'version': saved['version'], 'changes': [
        {'person_id': 1, 'field': field, 'value': None}]})
    assert reset['persons'][0]['effective'][field] == 'automatic'
    current = review_state.current(job)
    review_state.mutate(job, current['version'], 'assign', {'changes': [
        {'track_id': 2, 'action': 'assign', 'person_id': 1}]})
    assert attribute_state.status(job)['stale']
    with pytest.raises(ReviewError):
        attribute_state.save_review(job, {'version': reset['version'], 'changes': []})
    again = attribute_stage.run_attributes(video, job)
    assert not again['stale'] and again['run_id'] != result['run_id']
    assert len(again['persons'][0]['images']) == 2  # existing fallback track
    assert again['persons'][0]['overrides'] == {}
    assert output.read_bytes() == original


def test_no_eligible_images_does_not_load_model(attribute_job, monkeypatch):
    job, video, calls = attribute_job
    original = attribute_selection.select_existing
    monkeypatch.setattr(attribute_stage, 'select_existing', lambda data, state, w, h: original(data, state, w, h*10))
    result = attribute_stage.run_attributes(video, job)
    assert calls == []
    assert result['persons'][0]['status'] == 'no_eligible_images'
    assert result['persons'][0]['images'] == []


def test_face_exclusion_retains_crop_but_invalidates_run(attribute_job):
    job, video, _ = attribute_job
    data, state, _ = attribute_state.source(job)
    before = attribute_selection.select_existing(data, state, 200, 100)
    faces = stage_state.face_snapshot(job)
    stage_state.save_faces(job, {'version': faces['version'], 'face_exclusions': [
        {'face_id': faces['tracks'][0]['observations'][0]['face_id'], 'excluded': True}]})
    after_data, after_state = review_state.read(job)
    assert attribute_selection.select_existing(after_data, after_state, 200, 100) == before
    with pytest.raises(ReviewError):
        attribute_stage.run_attributes(video, job)


def test_reference_scoring_and_five_chronological_representatives():
    candidates = {tid: [dict(track_id=tid, frame_number=10-tid, person_blur_score=0,
                            height_ratio=.25, near_frame_border=False)] for tid in range(1, 8)}
    selected = attribute_selection.select_images(candidates, 5)
    assert len(selected) == 5
    assert len({c['track_id'] for c in selected}) == 5
    assert [c['frame_number'] for c in selected] == sorted(c['frame_number'] for c in selected)
    assert all(c['selection_score'] == .75 for c in selected)


def test_person_error_does_not_stop_remaining_people(attribute_job, monkeypatch):
    job, video, _ = attribute_job
    current = review_state.current(job)
    review_state.mutate(job, current['version'], 'assign', {'changes': [
        {'track_id': 2, 'action': 'create_person'}]})
    def predict(self, pid, paths):
        if pid == 1:
            raise RuntimeError('controlled')
        return json.dumps({field: 'ok' for field in FIELDS})
    monkeypatch.setattr(attribute_stage.QwenAttributes, 'predict', predict)
    result = attribute_stage.run_attributes(video, job)
    assert [p['status'] for p in result['persons']] == ['generation_error', 'ok']
    assert parse_json('```json\n' + json.dumps({field: 'ok' for field in FIELDS}) + '\n```') == {field: 'ok' for field in FIELDS}


def test_api_restart_images_and_automatic_values_remain_separate(attribute_job, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    job, video, _ = attribute_job
    result = attribute_stage.run_attributes(video, job)
    monkeypatch.setattr(sm, '_BASE_DIR', job.parent)
    monkeypatch.setattr(sm, '_STORE', {})
    monkeypatch.setattr(app, '_DATASTORE', SimpleNamespace(enabled=False))
    client = TestClient(app.app)
    url = '/api/jobs/job/person-analysis/'
    response = client.patch(url + 'attribute-review', json={'version': result['version'], 'changes': [
        {'person_id': 1, 'field': FIELDS[0], 'value': 'Restart'}]})
    assert response.status_code == 200
    sm._STORE.clear()
    assert client.get(url + 'attributes').json()['persons'][0]['effective'][FIELDS[0]] == 'Restart'
    crop = result['persons'][0]['images'][0]
    image = client.get(url + f"attributes/{result['run_id']}/images/{crop['crop_id']}")
    assert image.status_code == 200 and image.headers['content-type'] == 'image/jpeg'
    assert client.get(url + 'attributes/invalid/images/1').status_code == 404
    assert json.loads(sm.get_job('job')['persons_df'].iloc[0]['attributes']) == {}
    code = 'import json,sys; from backend.pipeline.persons.attribute_state import snapshot; print(json.dumps(snapshot(sys.argv[1])))'
    restarted = json.loads(subprocess.check_output([sys.executable, '-B', '-c', code, str(job)], text=True))
    assert restarted['persons'][0]['effective'][FIELDS[0]] == 'Restart'

def test_split_segments_are_separate_candidates_and_recluster_is_stale(attribute_job):
    job, video, _ = attribute_job
    attribute_stage.run_attributes(video, job)
    faces = stage_state.face_snapshot(job)
    stage_state.save_faces(job, {'version': faces['version'], 'track_changes': [
        {'action': 'split', 'track_id': 1, 'before_frame': 31}]})
    assert attribute_state.status(job)['stale']
    run_identities(video, job)
    assert attribute_state.status(job)['stale']
    result = attribute_stage.run_attributes(video, job)
    assert {c['track_id'] for c in result['persons'][0]['images']} == {6, 7}
    current = review_state.current(job)
    review_state.mutate(job, current['version'], 'metadata', {'person_id': 1, 'name': 'Anna'})
    assert not attribute_state.status(job)['stale']
    assert attribute_state.snapshot(job)['persons'][0]['name'] == 'Anna'


def test_quality_flags_do_not_filter_and_missing_jpeg_is_not_reconstructed(attribute_job):
    job, _, _ = attribute_job
    data, state, _ = attribute_state.source(job)
    expected = attribute_selection.select_existing(data, state, 200, 100)
    for crop in data.by_track[1]:
        crop.update(quality_usable=False, face_usable=False)
    selected = attribute_selection.select_existing(data, state, 200, 100)
    assert [c['crop_id'] for c in selected[1]] == [c['crop_id'] for c in expected[1]]
    path = data.crop_file(data.by_track[1][0]['crop_id'])
    path.write_bytes(b'invalid jpeg')
    with pytest.raises(ReviewError, match='keine Rekonstruktion'):
        attribute_selection.select_existing(data, state, 200, 100)
    assert path.read_bytes() == b'invalid jpeg'


def test_model_load_failure_preserves_previous_run(attribute_job, monkeypatch):
    job, video, _ = attribute_job
    previous = attribute_stage.run_attributes(video, job)
    def fail(self):
        raise RuntimeError('load failed')
    monkeypatch.setattr(attribute_stage.QwenAttributes, '__enter__', fail)
    with pytest.raises(RuntimeError, match='load failed'):
        attribute_stage.run_attributes(video, job)
    assert attribute_state.snapshot(job) == previous
