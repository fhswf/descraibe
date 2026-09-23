"""Human preview ranking, independent of automatic clustering and attribute images."""
import csv

import pytest

from test_person_review import job_dir, change
from backend.pipeline.persons import review_artifacts as artifacts, review_state as review
from backend.pipeline.persons import stage_state
from backend.tests.test_person_review import api


@pytest.fixture
def ranked_job(job_dir):
    root = job_dir / 'person_analysis'
    data = artifacts.load(job_dir)
    rows = []
    for cid in range(1, 25):
        crop = data.crops[cid]
        rows.append(dict(face_id=cid, source_track_id=crop['source_track_id'], scene_id=1,
                         frame_number=crop['frame_number'], timestamp_s=crop['timestamp_s'], excluded=False,
                         person_crop_path=crop['crop_path'],
                         face_x1=10, face_y1=20, face_x2=40, face_y2=60,
                         face_usable=True, face_confidence=.99 if cid == 6 else .9, alignment_ok=True,
                         embedding_created=True, blur_score=100 if cid == 6 else 10))
    with (root / 'face_observations.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    return job_dir


def people(result):
    return {p['person_id']: p['representative_crop_id'] for p in result['persons']}


def test_size_only_breaks_near_confidence_ties(ranked_job):
    data = artifacts.load(ranked_job)
    data.observations[6]['face_confidence'] = .9999
    data.observations[12].update(face_confidence=.99981, face_bbox=[0, 0, 80, 100])
    assert people(review.project(data))[1] == 12
    data.observations[12]['face_confidence'] = .9997
    assert people(review.project(data))[1] == 6
    # No minimum size: even a small valid face can win by confidence.
    data.observations[6]['face_bbox'] = [1, 1, 11, 11]
    assert people(review.project(data))[1] == 6


def test_manual_profile_api_reload_reset_and_attribute_preservation(api, job_dir):
    client, sm, _ = api
    path = job_dir / 'person_analysis' / 'attributes.json'
    stage_state.atomic_write(path, {'assignment_revision': 1, 'persons': {}})
    original = path.read_bytes()
    url = '/api/jobs/job/persons/1'
    candidates = client.get('/api/jobs/job/tracks/2/crops').json()
    assert 24 in [c['crop_id'] for c in candidates['crops']]
    response = client.post(url, json={'version': candidates['version'], 'profile_crop_id': 24})
    assert response.status_code == 200
    saved = response.json()
    assert people(saved)[1] == 24
    assert path.read_bytes() == original
    payload = stage_state.read_json(job_dir / 'person_analysis' / 'persons.json')
    assert payload['assignment_revision'] == 1
    assert payload['persons'][0]['profile_crop_id'] == 24
    sm._STORE.clear()
    assert people(client.get('/api/jobs/job/persons').json())[1] == 24
    assert client.post(url, json={'version': candidates['version'], 'profile_crop_id': 1}).status_code == 409
    assert client.post(url, json={'version': saved['version'], 'profile_crop_id': 25}).status_code == 400
    response = client.post(url, json={'version': saved['version'], 'profile_crop_id': None})
    assert response.status_code == 200
    assert people(review.current(job_dir))[1] == 1


def test_manual_profile_follows_membership_and_metadata(job_dir):
    result = review.mutate(job_dir, review.current(job_dir)['version'], 'metadata', {'person_id': 1, 'profile_crop_id': 12})
    result = review.mutate(job_dir, result['version'], 'metadata', {'person_id': 1, 'name': 'Neu'})
    assert people(result)[1] == 12
    result = change(job_dir, [{'track_id': 1, 'action': 'assign', 'person_id': 2}])
    assert people(result)[1] != 12
    payload = stage_state.read_json(job_dir / 'person_analysis' / 'persons.json')
    assert payload['persons'][0]['profile_crop_id'] is None


def test_manual_profile_rejects_excluded_face(ranked_job):
    data = artifacts.load(ranked_job)
    data.observations[6]['excluded'] = True
    next(f for f in data.faces if f['face_id'] == 6)['excluded'] = True
    assert review.profile_crop(data, 6, [1, 2]) is None
    assert review.profile_crop(data, True, [1, 2]) is None


def test_highest_face_confidence_even_outside_sample(ranked_job, monkeypatch):
    data = artifacts.load(ranked_job)
    original = data.review_crops
    monkeypatch.setattr(data, 'review_crops', lambda tid: original(tid)[::3])
    assert 6 not in [c['crop_id'] for c in data.review_crops(1)]
    assert people(review.project(data))[1] == 6


def test_exclude_restore_move_merge_delete(ranked_job):
    result = review.current(ranked_job)
    data = artifacts.load(ranked_job)
    data.observations[6]['excluded'] = True
    assert people(review.project(data))[1] == 1
    data.observations[6]['excluded'] = False
    result = review.project(data)
    assert people(result)[1] == 6
    result = change(ranked_job, [{'track_id': 1, 'action': 'assign', 'person_id': 2}])
    assert people(result) == {1: 13, 2: 6}
    assert people(review.current(ranked_job)) == people(result)
    result = review.mutate(ranked_job, result['version'], 'merge', {'source_person_id': 2, 'target_person_id': 1})
    assert people(result) == {1: 6}
    result = change(ranked_job, [{'track_id': 1, 'action': 'unassign'}])
    assert people(result) == {1: 13}
    result = review.mutate(ranked_job, result['version'], 'delete', {'source_person_id': 1})
    assert result['persons'] == []
    assert len(result['unassigned_tracks']) == 5


def test_all_faces_excluded_fallback_and_missing_files(ranked_job):
    data = artifacts.load(ranked_job)
    for row in data.observations.values():
        row['excluded'] = True
    # Existing body crops remain usable as previews even without valid faces.
    assert people(review.project(data))[1] == 1
    assert people(review.project(data))[2] == 25
    data.crop_file(25).unlink()
    assert people(review.project(data))[2] == 26


@pytest.mark.parametrize('field,value', [('face_confidence', .99), ('face_bbox', [10, 20, 60, 90])])
def test_quality_tiebreaks(ranked_job, field, value):
    data = artifacts.load(ranked_job)
    for crop in data.observations.values():
        crop['face_confidence'] = .9
    data.observations[12][field] = value
    assert people(review.project(data))[1] == 12


def test_missing_sharpness_in_old_jobs(job_dir):
    assert people(review.current(job_dir)) == {1: 1, 2: 25}


def test_larger_face_wins_without_sharpness_ranking(ranked_job):
    data = artifacts.load(ranked_job)
    for c in data.observations.values():
        c['face_confidence'] = .9
    data.observations[12].update(blur_score=99, face_bbox=[20, 40, 80, 120])
    assert people(review.project(data))[1] == 12


def test_edge_distance_does_not_change_selection(ranked_job):
    data = artifacts.load(ranked_job)
    for c in data.observations.values():
        c.update(face_confidence=.9, blur_score=100, face_bbox=[0, 0, 30, 40])
    data.observations[12]['face_bbox'] = [35, 80, 65, 120]
    assert people(review.project(data))[1] == 1


def test_missing_values_and_stable_near_tie(ranked_job):
    data = artifacts.load(ranked_job)
    for c in data.observations.values():
        c.update(blur_score=None, face_confidence=float('nan'))
    data.observations[12]['face_confidence'] = 1e-9
    assert people(review.project(data))[1] == 12


@pytest.mark.parametrize('bbox', [[0, 0, 0, 0], [200, 0, 220, 20], [0, 0, float('nan'), 20], None])
def test_invalid_face_geometry_cannot_win(ranked_job, bbox):
    data = artifacts.load(ranked_job)
    data.observations[6]['face_bbox'] = bbox
    assert people(review.project(data))[1] == 1


def test_missing_best_jpeg_does_not_affect_normalization(ranked_job):
    data = artifacts.load(ranked_job)
    data.crop_file(6).unlink()
    data.observations[6]['blur_score'] = 1e100
    data.observations[12].update(blur_score=9.9, face_bbox=[20, 40, 80, 120])
    assert people(review.project(data))[1] == 12


@pytest.mark.parametrize('confidence', ['', 'nan', 'invalid'])
def test_missing_confidence_in_persisted_metadata(job_dir, confidence):
    path = job_dir / 'person_analysis' / 'face_observations.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream, delimiter=';'))
    rows[0]['face_confidence'] = confidence
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    assert people(review.current(job_dir))[1] == 1
