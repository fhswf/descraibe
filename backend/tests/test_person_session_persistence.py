"""Current person manifests replace persisted projections; legacy jobs still load."""
import json

import pandas as pd

from backend.tests.test_person_review import job_dir
from backend.pipeline.persons import review_state, stage_state


def test_current_job_rebuilds_persons_faces_and_attributes_after_restart(job_dir, monkeypatch):
    from backend import session_manager as sm
    monkeypatch.setattr(sm, '_BASE_DIR', job_dir.parent)
    monkeypatch.setattr(sm, '_STORE', {})
    root = job_dir / 'person_analysis'
    review_state.mutate(job_dir, review_state.current(job_dir)['version'], 'metadata',
                        {'person_id': 1, 'name': 'Anna korrigiert', 'description': 'Beschreibung'})
    stage_state.atomic_write(root / 'attributes.json', {
        'revision': 1, 'tracking_revision': 1, 'assignment_revision': 1,
        'persons': {'1': {'attributes': {'hair_color': 'schwarz'}}}})
    job = {'job_id': 'job', 'job_dir': str(job_dir), 'status': 'idle',
           'slots_df': pd.DataFrame([{'slot': 1, 'start_s': 10.0}])}
    sm._STORE['job'] = job
    sm._apply_person_review(job)
    expected = job['persons_df'].copy(deep=True)
    faces = job['faces']
    canonical = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    sm._persist_job(job)
    assert not (job_dir / 'persons_df.parquet').exists()
    assert 'faces' not in json.loads((job_dir / 'job.json').read_text())
    # Existing stale copies must not even be decoded on restart, or rewritten.
    stale = job_dir / 'persons_df.parquet'
    stale.write_bytes(b'not a parquet file')
    saved = json.loads((job_dir / 'job.json').read_text())
    saved['faces'] = [{'face_id': 999}]
    (job_dir / 'job.json').write_text(json.dumps(saved))
    original_read = pd.read_parquet
    def read(path, **kwargs):
        assert not str(path).endswith('persons_df.parquet')
        return original_read(path, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', read)
    sm._STORE.clear()
    restored = sm.get_job('job')
    pd.testing.assert_frame_equal(restored['persons_df'], expected)
    assert restored['faces'] == faces
    assert json.loads(restored['persons_df'].iloc[0]['attributes'])['hair_color'] == 'schwarz'
    pd.testing.assert_frame_equal(restored['slots_df'], job['slots_df'])
    sm._persist_job(restored)
    assert stale.read_bytes() == b'not a parquet file'
    assert 'faces' not in json.loads((job_dir / 'job.json').read_text())
    assert canonical == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    # A review invalidates Identity: old saved persons must not reappear.
    stage_state.save_faces(job_dir, {'version': 1, 'face_exclusions': [{'face_id': 1, 'excluded': True}]})
    sm._STORE.clear()
    assert sm.get_job('job')['persons_df'].empty
    assert sm.get_job('job')['faces'][0]['excluded'] is True


def test_legacy_job_still_persists_persons_and_faces(tmp_path, monkeypatch):
    from backend import session_manager as sm
    monkeypatch.setattr(sm, '_BASE_DIR', tmp_path)
    monkeypatch.setattr(sm, '_STORE', {})
    job_id = sm.create_job()
    persons = pd.DataFrame([{'person_id': 1, 'name': 'Legacy'}])
    faces = [{'face_id': 1, 'person_id': 1}]
    sm.update_job(job_id, persons_df=persons, faces=faces)
    assert (tmp_path / job_id / 'persons_df.parquet').is_file()
    sm._STORE.clear()
    restored = sm.get_job(job_id)
    pd.testing.assert_frame_equal(restored['persons_df'], persons)
    assert restored['faces'] == faces
