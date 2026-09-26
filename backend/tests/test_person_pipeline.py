"""Integration tests for the person analysis pipeline endpoints."""
import pytest
from backend.tests.test_person_review import job_dir


class TestPersonsEndpoint:
    """Tests for /api/jobs/{job_id}/persons endpoints."""

    @pytest.fixture
    def app_with_job(self):
        """Create a test app with a mock job."""
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend import session_manager as sm

        # Create a test job
        job_id = sm.create_job()
        job = sm.get_job(job_id)
        job["scene_images"] = [
            "/tmp/test_00-00-10-000.jpg",
            "/tmp/test_00-00-20-000.jpg",
        ]
        sm.update_job(job_id, scene_images=job["scene_images"])

        client = TestClient(app)
        yield client, job_id

        # Cleanup
        sm.cleanup_job(job_id)

    def test_get_persons_empty(self, app_with_job):
        """GET /api/jobs/{job_id}/persons returns empty list when no analysis done."""
        client, job_id = app_with_job

        response = client.get(f"/api/jobs/{job_id}/persons")
        assert response.status_code == 200
        data = response.json()
        assert data == {"persons": []}

    def test_get_persons_unknown_job(self, app_with_job):
        """GET /api/jobs/{unknown_id}/persons returns 404."""
        client, _ = app_with_job

        response = client.get("/api/jobs/unknown-job-id/persons")
        assert response.status_code == 404


class TestPersonHateoasLinks:
    """The API advertises the separate tracking stage, not the retired shortcut."""

    @pytest.mark.parametrize("has_video", [False, True])
    def test_hateoas_tracking_link(self, has_video):
        from backend.app import build_hateoas_links
        from backend import session_manager as sm

        job_id = sm.create_job()
        try:
            sm.update_job(job_id, video_path="/tmp/video.mp4" if has_video else None,
                          scene_images=["/tmp/test.jpg"])
            links = build_hateoas_links(sm.get_job(job_id), "http://localhost:5000")
            assert not any(link["rel"] == "run-persons" for link in links)
            tracking = [link for link in links if link["rel"] == "run-tracking"]
            if has_video:
                assert tracking == [{"rel": "run-tracking", "method": "POST",
                    "href": f"http://localhost:5000/api/jobs/{job_id}/person-analysis/tracking"}]
            else:
                assert tracking == []
        finally:
            sm.cleanup_job(job_id)


@pytest.fixture
def current_api(job_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend import session_manager as sm
    from backend.pipeline.persons import stage_state
    monkeypatch.setattr(sm, "_BASE_DIR", job_dir.parent)
    monkeypatch.setattr(sm, "_STORE", {})
    stage_state.atomic_write(job_dir / "job.json", {"job_id": "job", "status": "idle"})
    return TestClient(app), sm


def test_person_count_comes_from_current_files(current_api):
    client, _ = current_api
    assert client.get("/api/jobs/job").json()["persons_count"] == 2


@pytest.mark.parametrize("operation", ["metadata", "merge", "delete"])
def test_current_person_edits_survive_job_cache_clear(current_api, operation):
    client, sm = current_api
    version = client.get("/api/jobs/job/persons").json()["version"]
    if operation == "metadata":
        response = client.post("/api/jobs/job/persons/1", json={"version": version, "name": "Anna neu", "function": "Moderatorin"})
    elif operation == "merge":
        response = client.post("/api/jobs/job/persons/merge", json={"version": version, "source_person_id": 1, "target_person_id": 2})
    else:
        response = client.request("DELETE", "/api/jobs/job/persons/1", json={"version": version})
    assert response.status_code == 200
    expected = response.json()
    sm._STORE.clear()
    restored = client.get("/api/jobs/job/persons").json()
    assert restored["persons"] == expected["persons"]
    assert restored["unassigned_tracks"] == expected["unassigned_tracks"]
    if operation == "metadata":
        assert restored["persons"][0]["name"] == "Anna neu"
        assert restored["persons"][0]["function"] == "Moderatorin"
    elif operation == "merge":
        assert len(restored["persons"]) == 1
        assert restored["persons"][0]["track_ids"] == [1, 2, 3]
    else:
        assert [p["person_id"] for p in restored["persons"]] == [2]
        assert {t["track_id"] for t in restored["unassigned_tracks"]} == {1, 2, 4, 5}


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/persons/1", {"name": "Anna"}),
    ("POST", "/persons/merge", {"source_person_id": 1, "target_person_id": 2}),
    ("DELETE", "/persons/1", {}),
])
def test_person_edits_require_current_analysis(current_api, job_dir, method, path, body):
    client, _ = current_api
    (job_dir / "person_analysis" / "persons.json").unlink()
    response = client.request(method, "/api/jobs/job" + path, json=body)
    assert response.status_code == 409


def test_person_projection_is_not_a_persisted_table():
    from backend import session_manager as sm
    assert "persons_df" not in sm._DF_FIELDS
    assert "faces" not in sm._JSON_FIELDS
