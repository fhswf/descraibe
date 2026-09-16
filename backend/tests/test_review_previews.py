"""Review visibility and reuse of current metadata; no model inference needed."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.pipeline.persons import review_artifacts as artifacts, stage_state
from backend.tests.test_person_review import job_dir, api


def test_tracking_keeps_all_faces_after_identity_and_all_exclusions(job_dir):
    root = job_dir / 'person_analysis'
    rows, fields = stage_state.read_csv(root / 'face_observations.csv')
    crops, _ = stage_state.read_csv(root / 'person_crops.csv')
    faces = [{**rows[0], 'face_id': index + 1, 'frame_number': crop['frame_number'],
              'person_crop_path': crop['crop_path'], 'timestamp_s': crop['timestamp_s'],
              'embedding_created': '', 'excluded': index in (0, 7, 11)}
             for index, crop in enumerate(crops[:12])]
    stage_state.write_csv(root / 'face_observations.csv', faces, fields)
    before = stage_state.face_snapshot(job_dir)['tracks'][0]['observations']
    assert len(before) == 12
    for face in faces:
        face['embedding_created'] = not face['excluded']
    stage_state.write_csv(root / 'face_observations.csv', faces, fields)
    after = stage_state.face_snapshot(job_dir)['tracks'][0]['observations']
    assert [(r['face_id'], r['excluded']) for r in after] == [(r['face_id'], r['excluded']) for r in before]
    cluster = artifacts.load(job_dir).review_crops(1)
    assert len(cluster) == 5 and all(not r['excluded'] for r in cluster)

    saved = stage_state.save_faces(job_dir, {'version': 1, 'face_exclusions': [
        {'face_id': i, 'excluded': True} for i in range(1, 13)]})
    assert len(saved['tracks'][0]['observations']) == 12
    assert all(r['excluded'] for r in saved['tracks'][0]['observations'])
    restored = stage_state.save_faces(job_dir, {'version': saved['version'], 'face_exclusions': [
        {'face_id': 12, 'excluded': False}]})
    assert restored['tracks'][0]['observations'][-1]['excluded'] is False
    assert all(artifacts.load_tracking(job_dir).crop_file(i).exists() for i in range(1, 13))


def test_concurrent_previews_load_metadata_once(job_dir, monkeypatch):
    calls = []
    original = artifacts.load
    def counted(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(artifacts, 'load', counted)
    with ThreadPoolExecutor(max_workers=8) as pool:
        paths = list(pool.map(lambda i: artifacts.load_for_preview(job_dir).crop_file(i), range(1, 13)))
    assert len(calls) == 1
    assert len(set(paths)) == 12
    # Mutation code receives its own instance, never the cached dictionaries.
    independent = original(job_dir)
    independent.assignments[1] = None
    assert artifacts.load_for_preview(job_dir).assignments[1] == 1


@pytest.mark.parametrize('name', [*artifacts.TRACKING_FILES, 'persons.json'])
def test_preview_cache_refreshes_on_each_source_file_replacement(job_dir, name):
    first = artifacts.load_for_preview(job_dir)
    path = first.root / name
    replacement = path.with_suffix('.tmp')
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)
    second = artifacts.load_for_preview(job_dir)
    assert second is not first
    assert artifacts.load_for_preview(job_dir) is second
    assert list(artifacts._preview_cache).count(first.root) == 1
    assert len(artifacts._preview_cache) <= 4


def test_preview_cache_after_review_and_missing_files(job_dir):
    first = artifacts.load_for_preview(job_dir)
    stage_state.save_faces(job_dir, {'version': 1, 'face_exclusions': [{'face_id': 1, 'excluded': True}]})
    changed = artifacts.load_for_preview(job_dir)
    assert changed is not first
    assert changed.faces[0]['excluded'] is True
    assert changed.identity_revision is None
    assert changed.analysis_id == 'tracking-2'
    (changed.root / 'face_observations.csv').unlink()
    with pytest.raises(artifacts.ReviewError):
        artifacts.load_for_preview(job_dir)


def test_image_routes_reuse_metadata_and_reject_old_revision(api, job_dir, monkeypatch):
    client, _, _ = api
    client.get('/api/jobs/job')  # Warm the separate session projection.
    calls = []
    original = artifacts.load
    def counted(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(artifacts, 'load', counted)
    for crop_id in range(1, 13):
        response = client.get(f'/api/jobs/job/person-crops/{crop_id}?analysis_id=tracking-1')
        assert response.status_code == 200
        assert response.content == b'test-jpeg'
    assert client.get('/api/jobs/job/tracks/1/crops').status_code == 200
    assert len(calls) == 1
    stage_state.save_faces(job_dir, {'version': 1, 'face_exclusions': [{'face_id': 1, 'excluded': True}]})
    assert client.get('/api/jobs/job/person-crops/1?analysis_id=tracking-1').status_code == 409
    assert client.get('/api/jobs/job/person-crops/1?analysis_id=tracking-2').status_code == 200
