"""Integration tests for the person analysis pipeline endpoints."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd


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

    @patch("backend.pipeline.person_analysis.analyze_persons")
    def test_post_persons_success(self, mock_analyze, app_with_job):
        """POST /api/jobs/{job_id}/persons triggers analysis."""
        from backend import session_manager as sm

        client, job_id = app_with_job

        # Mock the analysis function to return a sample DataFrame
        mock_df = pd.DataFrame([
            {
                "person_id": 1,
                "name": "Test Person",
                "first_seen_ts": 10.0,
                "last_seen_ts": 20.0,
                "appearances_count": 2,
                "attributes": '{"top_color": "blau"}',
                "description": "Test Person: blaues Oberteil",
            }
        ])
        mock_analyze.return_value = mock_df

        response = client.post(f"/api/jobs/{job_id}/persons")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "started"}

    def test_post_persons_no_images(self, app_with_job):
        """POST /api/jobs/{job_id}/persons returns 400 when no images."""
        from backend import session_manager as sm

        client, job_id = app_with_job

        # Remove scene images
        sm.update_job(job_id, scene_images=None)

        response = client.post(f"/api/jobs/{job_id}/persons")
        assert response.status_code == 400
        assert "Scene images not available" in response.json()["error"]


class TestPersonHateoasLinks:
    """Tests for HATEOAS links including persons step."""

    def test_hateoas_link_appears_after_images(self):
        """run-persons link appears when scene_images are available."""
        from backend.app import build_hateoas_links
        from backend import session_manager as sm

        job_id = sm.create_job()
        job = sm.get_job(job_id)
        job["scene_images"] = ["/tmp/test.jpg"]
        sm.update_job(job_id, scene_images=job["scene_images"])

        links = build_hateoas_links(job, "http://localhost:5000")

        run_persons_link = next(
            (l for l in links if l["rel"] == "run-persons"), None
        )
        assert run_persons_link is not None
        assert run_persons_link["method"] == "POST"
        assert f"/api/jobs/{job_id}/persons" in run_persons_link["href"]

        sm.cleanup_job(job_id)

    def test_hateoas_link_missing_without_images(self):
        """run-persons link does not appear when scene_images are missing."""
        from backend.app import build_hateoas_links
        from backend import session_manager as sm

        job_id = sm.create_job()
        job = sm.get_job(job_id)
        job["scene_images"] = None
        sm.update_job(job_id, scene_images=None)

        links = build_hateoas_links(job, "http://localhost:5000")

        run_persons_link = next(
            (l for l in links if l["rel"] == "run-persons"), None
        )
        assert run_persons_link is None

        sm.cleanup_job(job_id)


class TestPersonJobResponse:
    """Tests for persons_count in job response."""

    def test_job_response_includes_persons_count(self):
        """GET /api/jobs/{job_id} includes persons_count."""
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend import session_manager as sm

        job_id = sm.create_job()
        job = sm.get_job(job_id)

        # Set persons_df
        persons_df = pd.DataFrame([
            {"person_id": 1, "name": "Person A"},
            {"person_id": 2, "name": "Person B"},
        ])
        sm.update_job(job_id, persons_df=persons_df)

        client = TestClient(app)
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["persons_count"] == 2

        sm.cleanup_job(job_id)

    def test_job_response_persons_count_zero_when_empty(self):
        """GET /api/jobs/{job_id} includes persons_count=0 when no persons."""
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend import session_manager as sm

        job_id = sm.create_job()
        sm.update_job(job_id, persons_df=None)

        client = TestClient(app)
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["persons_count"] == 0

        sm.cleanup_job(job_id)


class TestSessionManagerPersons:
    """Tests for session_manager persons_df persistence."""

    def test_persons_df_in_df_fields(self):
        """persons_df is listed in _DF_FIELDS."""
        from backend import session_manager as sm

        assert "persons_df" in sm._DF_FIELDS

    def test_job_initializes_persons_df_none(self):
        """create_job initializes persons_df to None."""
        from backend import session_manager as sm

        job_id = sm.create_job()
        job = sm.get_job(job_id)
        assert job["persons_df"] is None
        sm.cleanup_job(job_id)