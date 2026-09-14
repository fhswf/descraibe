"""Human preview ranking, independent of automatic clustering and attribute images."""
import csv

import pytest

from test_person_review import job_dir, change
from backend.pipeline.persons import review_artifacts as artifacts, review_state as review


@pytest.fixture
def ranked_job(job_dir):
    root = job_dir / 'person_analysis'
    data = artifacts.load(job_dir)
    rows = []
    for cid in range(1, 25):
        rows.append(dict(face_id=cid, person_crop_path=data.crops[cid]['crop_path'],
                         face_x1=10, face_y1=20, face_x2=40, face_y2=60,
                         face_usable=True, face_confidence=.9, alignment_ok=True,
                         embedding_created=True, blur_score=100 if cid == 6 else 10))
    with (root / 'face_observations.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    return job_dir


def people(result):
    return {p['person_id']: p['representative_crop_id'] for p in result['persons']}


def test_later_sharp_face_even_outside_sample(ranked_job, monkeypatch):
    data, state = review.read(ranked_job)
    original = data.review_crops
    monkeypatch.setattr(data, 'review_crops', lambda tid, excluded: original(tid, excluded)[::3])
    assert 6 not in [c['crop_id'] for c in data.review_crops(1, set())]
    assert people(review.project(data, state))[1] == 6


def test_exclude_restore_move_merge_delete(ranked_job):
    result = review.current(ranked_job)
    result = review.mutate(ranked_job, result['version'], 'assign', {'changes': [], 'face_exclusions': [{'face_id': 6, 'excluded': True}]})
    assert people(result)[1] == 1
    result = review.mutate(ranked_job, result['version'], 'assign', {'changes': [], 'face_exclusions': [{'face_id': 6, 'excluded': False}]})
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
    data, state = review.read(ranked_job)
    state['excluded_face_observations'] = list(range(1, 25))
    assert people(review.project(data, state))[1] is None
    assert people(review.project(data, state))[2] == 25
    data.crop_file(25).unlink()
    assert people(review.project(data, state))[2] == 26


@pytest.mark.parametrize('field,value', [('blur_score', 200), ('face_confidence', .99), ('face_bbox', [10, 20, 60, 90])])
def test_quality_tiebreaks(ranked_job, field, value):
    data, state = review.read(ranked_job)
    for crop in data.observations.values():
        crop['blur_score'] = 10
    data.observations[12][field] = value
    assert people(review.project(data, state))[1] == 12


def test_missing_sharpness_in_old_jobs(job_dir):
    assert people(review.current(job_dir)) == {1: 1, 2: 25}


def test_larger_face_wins_despite_slightly_lower_sharpness(ranked_job):
    data, state = review.read(ranked_job)
    for c in data.observations.values():
        c['blur_score'] = 100
    data.observations[12].update(blur_score=99, face_bbox=[20, 40, 80, 120])
    assert people(review.project(data, state))[1] == 12


def test_same_size_face_away_from_edge_wins(ranked_job):
    data, state = review.read(ranked_job)
    for c in data.observations.values():
        c.update(blur_score=100, face_bbox=[0, 0, 30, 40])
    data.observations[12]['face_bbox'] = [35, 80, 65, 120]
    assert people(review.project(data, state))[1] == 12


def test_missing_values_and_stable_near_tie(ranked_job):
    data, state = review.read(ranked_job)
    for c in data.observations.values():
        c.update(blur_score=None, face_confidence=float('nan'))
    data.observations[12]['face_confidence'] = 1e-9
    assert people(review.project(data, state))[1] == 1


@pytest.mark.parametrize('bbox', [[0, 0, 0, 0], [200, 0, 220, 20], [0, 0, float('nan'), 20], None])
def test_invalid_face_geometry_cannot_win(ranked_job, bbox):
    data, state = review.read(ranked_job)
    data.observations[6]['face_bbox'] = bbox
    assert people(review.project(data, state))[1] == 1


def test_missing_best_jpeg_does_not_affect_normalization(ranked_job):
    data, state = review.read(ranked_job)
    data.crop_file(6).unlink()
    data.observations[6]['blur_score'] = 1e100
    data.observations[12].update(blur_score=9.9, face_bbox=[20, 40, 80, 120])
    assert people(review.project(data, state))[1] == 12


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
