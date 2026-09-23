"""Person settings are validated before work starts and passed per request."""
from types import SimpleNamespace

import pytest

from backend.pipeline.persons.config import validate_parameter
from backend.pipeline.persons.review_artifacts import ReviewError


@pytest.mark.parametrize('name,value', [
    ('tracking_interval_seconds', 0), ('tracking_interval_seconds', -1),
    ('tracking_interval_seconds', 11), ('tracking_interval_seconds', float('nan')),
    ('similarity_threshold', 1.1), ('similarity_threshold', -1.1),
    ('similarity_threshold', float('inf')), ('similarity_threshold', True),
    ('max_images', 0), ('max_images', 6), ('max_images', 1.5), ('max_images', True),
    ('max_images', None), ('max_images', '2'),
])
def test_invalid_person_settings(name, value):
    with pytest.raises(ReviewError):
        validate_parameter(name, value)


@pytest.mark.parametrize('phase,key,custom,default', [
    ('tracking', 'tracking_interval_seconds', 0.1, 0.233),
    ('identities', 'similarity_threshold', 0.4, 0.214),
    ('attributes', 'max_images', 2, 5),
])
def test_api_passes_custom_and_default_settings_and_rejects_invalid(monkeypatch, phase, key, custom, default):
    from fastapi.testclient import TestClient
    from backend import app
    from backend.pipeline.persons import tracking_stage, identity_stage, attribute_stage

    monkeypatch.setattr(app, '_DATASTORE', SimpleNamespace(enabled=False))
    monkeypatch.setattr(app.sm, 'get_job', lambda _: {'job_dir': 'fixture', 'video_path': 'video'})
    monkeypatch.setattr(app.sm, 'begin_person_stage', lambda *args: None)
    monkeypatch.setattr(app.sm, 'update_job', lambda *args, **kwargs: None)
    monkeypatch.setattr(app.sm, 'set_status', lambda *args: None)
    monkeypatch.setattr(app, '_mark_step_running', lambda *args: None)
    monkeypatch.setattr(app, '_push', lambda *args: None)
    monkeypatch.setattr(app.stage_state, 'status', lambda _: {'tracking_ready': True, 'tracking_revision': 1, 'identity_revision': 1})
    monkeypatch.setattr(app.attribute_state, 'source', lambda _: None)
    calls = []
    def run(*args, **kwargs):
        calls.append(kwargs)
        return {'version': '1'}
    monkeypatch.setattr(tracking_stage, 'run_tracking', run)
    monkeypatch.setattr(identity_stage, 'run_identities', run)
    monkeypatch.setattr(attribute_stage, 'run_attributes', run)
    monkeypatch.setattr(app, '_start_worker', lambda job, stage, worker: worker())
    client = TestClient(app.app)
    url = f'/api/jobs/fixture/person-analysis/{phase}'
    assert client.post(url, json={key: custom}).status_code == 200
    assert calls[-1] == {key: custom}
    assert client.post(url).status_code == 200
    assert calls[-1] == {key: default}
    assert client.post(url, json={key: None}).status_code == 400
    assert len(calls) == 2
