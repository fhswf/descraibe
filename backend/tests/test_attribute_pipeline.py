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


def test_current_values_batch_reload_and_replacement(attribute_job):
    job, video, calls = attribute_job
    result = attribute_stage.run_attributes(video, job)
    assert calls[0] == 'load' and calls[-1] == 'close' and len(calls) == 3
    assert len(result['persons'][0]['images']) == 1
    assert len(result['persons'][0]['attributes']) == 12
    output = stage_state.root(job) / 'attributes.json'
    field = FIELDS[0]
    saved = attribute_state.save_review(job, {'version': result['version'], 'changes': [
        {'person_id': 1, 'field': field, 'value': 'manual'},
        {'person_id': 1, 'field': FIELDS[1], 'value': 'second'}]})
    assert attribute_state.snapshot(job)['persons'][0]['attributes'][field] == 'manual'
    assert saved['persons'][0]['attributes'][FIELDS[1]] == 'second'
    assert json.loads(output.read_text())['persons']['1']['attributes'][field] == 'manual'
    assert not {'automatic', 'overrides', 'effective'} & saved['persons'][0].keys()
    with pytest.raises(ReviewError):
        attribute_state.save_review(job, {'version': result['version'], 'changes': []})
    reset = attribute_state.save_review(job, {'version': saved['version'], 'changes': [
        {'person_id': 1, 'field': field, 'value': ''}]})
    assert reset['persons'][0]['attributes'][field] == ''
    current = review_state.current(job)
    review_state.mutate(job, current['version'], 'assign', {'changes': [
        {'track_id': 2, 'action': 'assign', 'person_id': 1}]})
    assert not attribute_state.status(job)['ready'] and not output.exists()
    with pytest.raises(ReviewError):
        attribute_state.save_review(job, {'version': reset['version'], 'changes': []})
    again = attribute_stage.run_attributes(video, job)
    assert not again['stale'] and again['version'] != result['version']
    assert len(again['persons'][0]['images']) == 2  # existing fallback track
    assert again['persons'][0]['attributes'][field] == 'automatic'
    assert not (stage_state.root(job) / 'runs').exists()


def test_no_eligible_images_does_not_load_model(attribute_job, monkeypatch):
    job, video, calls = attribute_job
    original = attribute_state.source
    def without_crops(job_dir):
        data = original(job_dir)
        data.by_track = {tid: [] for tid in data.by_track}
        return data
    monkeypatch.setattr(attribute_state, 'source', without_crops)
    result = attribute_stage.run_attributes(video, job)
    assert calls == []
    assert result['persons'][0]['status'] == 'no_eligible_images'
    assert result['persons'][0]['images'] == []


def test_small_person_gets_one_image_and_qwen_call(attribute_job, monkeypatch):
    job, video, calls = attribute_job
    current = review_state.current(job)
    review_state.mutate(job, current['version'], 'assign', {'changes': [
        {'track_id': 2, 'action': 'assign', 'person_id': 1}]})
    original = attribute_selection.select_existing
    monkeypatch.setattr(attribute_stage, 'select_existing', lambda data, w, h, **kwargs: original(data, w, h*10, **kwargs))
    result = attribute_stage.run_attributes(video, job)
    person = result['persons'][0]
    assert person['status'] == 'ok'
    assert len(person['images']) == 1
    assert person['images'][0]['height_ratio'] < .15
    assert calls[0] == 'load' and calls[-1] == 'close'
    assert len(calls) == 3 and len(calls[1][1]) == 1


@pytest.mark.parametrize('height,expected', [(15, [1, 2]), (14, [1])])
def test_height_boundary_and_person_wide_fallback(tmp_path, height, expected):
    import cv2
    import numpy as np
    path = tmp_path / 'crop.jpg'
    path.write_bytes(cv2.imencode('.jpg', np.zeros((20, 20, 3), np.uint8))[1].tobytes())
    def crop(cid, tid, size):
        return dict(crop_id=cid, track_id=tid, frame_number=cid,
                    person_bbox=[30, 30, 50, 30+size], face_bbox=[1, 1, 5, 5])
    data = SimpleNamespace(
        persons={1: {}, 2: {}}, assignments={1: 1, 2: 1, 3: 2},
        tracks={tid: {'excluded': False} for tid in (1, 2, 3)},
        by_track={1: [crop(1, 1, height)], 2: [crop(2, 2, height)], 3: [crop(3, 3, 10)]},
        crop_file=lambda cid: path)
    # Both normal representatives survive at exactly 15%; below it only one wins.
    # Person 2 needs its own fallback even when person 1 has normal images.
    selected = attribute_selection.select_existing(data, 100, 100)
    assert [c['crop_id'] for c in selected[1]] == expected
    assert [c['crop_id'] for c in selected[2]] == [3]
    if height == 15:
        # A small candidate of a person with normal images is never even opened.
        data.by_track[1].append(crop(4, 1, 10))
        def read(cid):
            assert cid != 4
            return path
        data.crop_file = read
        assert attribute_selection.select_existing(data, 100, 100) == selected


def test_small_fallback_keeps_face_preference_score_and_exclusions(tmp_path):
    import cv2
    import numpy as np
    path = tmp_path / 'crop.jpg'
    path.write_bytes(cv2.imencode('.jpg', np.zeros((20, 20, 3), np.uint8))[1].tobytes())
    def crop(cid, tid, size, face):
        return dict(crop_id=cid, track_id=tid, frame_number=cid,
                    person_bbox=[30, 30, 50, 30+size], face_bbox=[1, 1, 5, 5] if face else None,
                    excluded=True, face_usable=False)
    def read(cid):
        assert cid not in (5, 6)  # excluded and unassigned tracks never participate
        return path
    data = SimpleNamespace(
        persons={1: {}}, assignments={1: 1, 2: 1, 3: 1, 4: None},
        tracks={tid: {'excluded': tid == 3} for tid in (1, 2, 3, 4)},
        by_track={1: [crop(1, 1, 14, False), crop(2, 1, 8, True), crop(3, 1, 10, True)],
                  2: [crop(4, 2, 9, False)], 3: [crop(5, 3, 14, True)], 4: [crop(6, 4, 14, True)]},
        crop_file=read)
    selected = attribute_selection.select_existing(data, 100, 100)
    # Face preference rejects crop 1 despite its size; score chooses 3 over 2 and 4.
    assert [c['crop_id'] for c in selected[1]] == [3]
    data.tracks[1]['excluded'] = True
    data.tracks[2]['excluded'] = True
    assert attribute_selection.select_existing(data, 100, 100) == {1: []}


def test_face_exclusion_retains_crop_but_invalidates_run(attribute_job):
    job, video, _ = attribute_job
    data = attribute_state.source(job)
    before = attribute_selection.select_existing(data, 200, 100)
    faces = stage_state.face_snapshot(job)
    stage_state.save_faces(job, {'version': faces['version'], 'face_exclusions': [
        {'face_id': faces['tracks'][0]['observations'][0]['face_id'], 'excluded': True}]})
    from backend.pipeline.persons import review_artifacts
    after_data = review_artifacts.load_tracking(job)
    # Only the face flag changed; use the previous assignment to compare candidates.
    after_data.persons, after_data.assignments = data.persons, data.assignments
    assert attribute_selection.select_existing(after_data, 200, 100) == before
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


def test_api_restart_current_values_and_versioned_images(attribute_job, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app, session_manager as sm
    job, video, _ = attribute_job
    result = attribute_stage.run_attributes(video, job)
    monkeypatch.setattr(sm, '_BASE_DIR', job.parent)
    monkeypatch.setattr(sm, '_STORE', {})
    monkeypatch.setattr(app, '_DATASTORE', SimpleNamespace(enabled=False))
    client = TestClient(app.app)
    url = '/api/jobs/job/person-analysis/'
    original_attributes = (stage_state.root(job) / 'attributes.json').read_bytes()
    for function in ('Förster', ''):
        persons = client.get('/api/jobs/job/persons').json()
        updated = client.post('/api/jobs/job/persons/1', json={
            'version': persons['version'], 'name': 'Anna', 'function': function})
        assert updated.status_code == 200
        sm._STORE.clear()
        for endpoint in ('/api/jobs/job/persons', url + 'attributes'):
            person = client.get(endpoint).json()['persons'][0]
            assert person['name'] == 'Anna'
            assert person['function'] == function
        assert (stage_state.root(job) / 'attributes.json').read_bytes() == original_attributes
        assert attribute_state.status(job)['ready']
    response = client.patch(url + 'attribute-review', json={'version': result['version'], 'changes': [
        {'person_id': 1, 'field': FIELDS[0], 'value': 'Restart'}]})
    assert response.status_code == 200
    sm._STORE.clear()
    loaded = client.get(url + 'attributes').json()
    assert loaded['persons'][0]['attributes'][FIELDS[0]] == 'Restart'
    crop = result['persons'][0]['images'][0]
    image = client.get(url + f"attributes/{loaded['version']}/images/{crop['crop_id']}")
    assert image.status_code == 200 and image.headers['content-type'] == 'image/jpeg'
    assert client.get(url + 'attributes/invalid/images/1').status_code == 409
    assert json.loads(sm.get_job('job')['persons_df'].iloc[0]['attributes'])[FIELDS[0]] == 'Restart'
    code = 'import json,sys; from backend.pipeline.persons.attribute_state import snapshot; print(json.dumps(snapshot(sys.argv[1])))'
    restarted = json.loads(subprocess.check_output([sys.executable, '-B', '-c', code, str(job)], text=True))
    assert restarted['persons'][0]['attributes'][FIELDS[0]] == 'Restart'

def test_split_segments_are_separate_candidates_and_recluster_removes_attributes(attribute_job):
    job, video, _ = attribute_job
    attribute_stage.run_attributes(video, job)
    faces = stage_state.face_snapshot(job)
    stage_state.save_faces(job, {'version': faces['version'], 'track_changes': [
        {'action': 'split', 'track_id': 1, 'before_frame': 29}]})
    assert not attribute_state.status(job)['ready']
    run_identities(video, job)
    assert not attribute_state.status(job)['ready']
    result = attribute_stage.run_attributes(video, job)
    assert {c['track_id'] for c in result['persons'][0]['images']} == {6, 7}
    current = review_state.current(job)
    review_state.mutate(job, current['version'], 'metadata', {'person_id': 1, 'name': 'Anna'})
    assert not attribute_state.status(job)['stale']
    assert attribute_state.snapshot(job)['persons'][0]['name'] == 'Anna'


def test_quality_flags_do_not_filter_and_corrupt_jpeg_is_not_reconstructed(attribute_job):
    job, _, _ = attribute_job
    data = attribute_state.source(job)
    expected = attribute_selection.select_existing(data, 200, 100)
    for crop in data.by_track[1]:
        crop.update(quality_usable=False, face_usable=False)
    selected = attribute_selection.select_existing(data, 200, 100)
    assert [c['crop_id'] for c in selected[1]] == [c['crop_id'] for c in expected[1]]
    path = data.crop_file(data.by_track[1][0]['crop_id'])
    path.write_bytes(b'invalid jpeg')
    with pytest.raises(ReviewError, match='nicht lesbar'):
        attribute_selection.select_existing(data, 200, 100)
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


def test_configurable_image_limit_preserves_selection_and_current_setting(attribute_job):
    job, video, _ = attribute_job
    current = review_state.current(job)
    review_state.mutate(job, current['version'], 'assign', {'changes': [
        {'track_id': 2, 'action': 'assign', 'person_id': 1}]})
    result = attribute_stage.run_attributes(video, job, max_images=1)
    assert len(result['persons'][0]['images']) == 1
    assert stage_state.status(job)['max_images'] == 1
    saved = attribute_state.save_review(job, {'version': result['version'], 'changes': [
        {'person_id': 1, 'field': FIELDS[0], 'value': 'manual'}]})
    assert stage_state.status(job)['max_images'] == 1
    assert saved['persons'][0]['attributes'][FIELDS[0]] == 'manual'
    result = attribute_stage.run_attributes(video, job)
    assert len(result['persons'][0]['images']) == 2
    assert stage_state.status(job)['max_images'] == 5
