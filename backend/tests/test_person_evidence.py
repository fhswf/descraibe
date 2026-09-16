"""Current face flags, invalidation, restart and rejection of old jobs."""
import json
import subprocess
import sys
import pytest
from backend.tests.test_person_review import job_dir, api
from backend.pipeline.persons import stage_state, review_state as review, review_artifacts as artifacts


def exclude(job, value=True):
    return stage_state.save_faces(job, {'version': stage_state.face_snapshot(job)['version'],
        'face_exclusions': [{'face_id': 1, 'excluded': value}]})


def test_exclusion_restore_preserves_track_times_and_crops(job_dir):
    root = job_dir / 'person_analysis'
    initial = stage_state.face_snapshot(job_dir)
    originals = {name: (root / name).read_bytes() for name in ('tracking_frames.csv', 'person_crops.csv')}
    stage_state.atomic_write(root / 'attributes.json', {'persons': {}})
    result = exclude(job_dir)
    assert [(t['start_s'], t['end_s']) for t in result['tracks']] == [(t['start_s'], t['end_s']) for t in initial['tracks']]
    assert result['excluded_face_observations'] == [1]
    rows, _ = stage_state.read_csv(root / 'face_observations.csv')
    assert rows[0]['excluded'] == 'True'
    assert not (root / 'persons.json').exists() and not (root / 'attributes.json').exists()
    assert artifacts.load_tracking(job_dir).review_crops(1, include_excluded=True)[0]['excluded']
    assert exclude(job_dir, False)['excluded_face_observations'] == []
    assert originals == {name: (root / name).read_bytes() for name in originals}
    assert not (root / 'review_state.json').exists()


@pytest.mark.parametrize('bad', [{'face_id': 999, 'excluded': True}, {'face_id': True, 'excluded': True},
    {'face_id': 1, 'excluded': 'true'}, {'face_id': 1, 'excluded': True, 'person_id': 2}])
def test_invalid_exclusion_rolls_back_entire_batch(job_dir, bad):
    before = review.current(job_dir)
    version = stage_state.face_snapshot(job_dir)['version']
    with pytest.raises(artifacts.ReviewError):
        stage_state.save_faces(job_dir, {'version': version,
            'face_exclusions': [{'face_id': 1, 'excluded': True}, bad],
            'track_changes': [{'action': 'set_excluded', 'track_id': 2, 'excluded': True}]})
    assert review.current(job_dir) == before


def test_old_run_structure_is_not_migrated(tmp_path):
    root = tmp_path / 'person_analysis'
    old = root / 'runs' / 'old-run'
    old.mkdir(parents=True)
    (old / 'persons.json').write_text('{"persons": []}')
    (root / 'pipeline_state.json').write_text('{"tracking_run": "old-run"}')
    before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert not stage_state.status(tmp_path)['tracking_ready']
    with pytest.raises(artifacts.ReviewError):
        artifacts.load(tmp_path)
    assert before == {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_pending_embedding_counts_as_zero(job_dir):
    root = job_dir / 'person_analysis'
    rows, fields = stage_state.read_csv(root / 'face_observations.csv')
    rows[0]['embedding_created'] = ''
    stage_state.write_csv(root / 'face_observations.csv', rows, fields)
    (root / 'persons.json').unlink()
    assert review.current(job_dir)['tracks'][0]['facemoe_observation_count'] == 0
    assert artifacts.load_tracking(job_dir).faces[0]['embedding_created'] is None


def test_api_exclusions_reload_and_restore(api, job_dir):
    client, sm, _ = api
    url = '/api/jobs/job/person-analysis/'
    first = client.get(url + 'tracking').json()
    response = client.patch(url + 'face-review', json={'version': first['version'],
        'face_exclusions': [{'face_id': 1, 'excluded': True}]})
    assert response.status_code == 200
    sm._STORE.clear()
    reloaded = client.get(url + 'tracking').json()
    assert reloaded['excluded_face_observations'] == [1]
    script = 'import json,sys; from backend.pipeline.persons.stage_state import face_snapshot; print(json.dumps(face_snapshot(sys.argv[1])))'
    restarted = json.loads(subprocess.check_output([sys.executable, '-c', script, str(job_dir)], text=True))
    assert restarted == reloaded
    response = client.patch(url + 'face-review', json={'version': reloaded['version'],
        'face_exclusions': [{'face_id': 1, 'excluded': False}]})
    assert response.status_code == 200 and response.json()['excluded_face_observations'] == []


def test_track_exclusion_is_persistent_reversible_and_invalidates(job_dir):
    first = stage_state.face_snapshot(job_dir)
    changed = stage_state.save_faces(job_dir, {'version': first['version'], 'track_changes': [
        {'action': 'set_excluded', 'track_id': 1, 'excluded': True}]})
    state = stage_state.read_json(job_dir / 'person_analysis' / 'tracks.json')
    assert state['tracks'][0]['excluded'] is True
    assert 1 not in [t['track_id'] for t in review.current(job_dir)['unassigned_tracks']]
    restored = stage_state.save_faces(job_dir, {'version': changed['version'], 'track_changes': [
        {'action': 'set_excluded', 'track_id': 1, 'excluded': False}]})
    assert restored['tracks'][0]['excluded'] is False
    assert 1 in [t['track_id'] for t in review.current(job_dir)['unassigned_tracks']]
