"""Integration tests for the person analysis pipeline endpoints."""
import pytest
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


class TestPersonModifications:
    """Tests for the new person editing, merging, and suggestions endpoints."""

    def test_update_person_success(self):
        """POST /api/jobs/{job_id}/persons/{person_id} updates name/function and ignores retired descriptions."""
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend import session_manager as sm

        job_id = sm.create_job()
        persons_df = pd.DataFrame([
            {"person_id": 1, "name": "Old Name", "description": "Old Desc", "first_seen_ts": 1.0, "last_seen_ts": 2.0, "appearances_count": 1}
        ])
        sm.update_job(job_id, persons_df=persons_df)

        client = TestClient(app)
        response = client.post(
            f"/api/jobs/{job_id}/persons/1",
            json={"name": "New Name", "function": "Moderatorin", "description": "Ignored"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["function"] == "Moderatorin"
        assert "description" not in data

        # Force clear test memory cache so it reads from disk
        sm._STORE.pop(job_id, None)

        # Verify state in session manager
        updated_job = sm.get_job(job_id)
        df = updated_job["persons_df"]
        assert df.iloc[0]["name"] == "New Name"
        assert df.iloc[0]["function"] == "Moderatorin"
        assert "description" not in df.columns

        sm.cleanup_job(job_id)

    def test_merge_persons_success(self):
        """POST /api/jobs/{job_id}/persons/merge merges two persons."""
        import json
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend import session_manager as sm

        job_id = sm.create_job()
        persons_df = pd.DataFrame([
            {
                "person_id": 1, 
                "name": "Person A", 
                "description": "Desc A", 
                "first_seen_ts": 10.0, 
                "last_seen_ts": 12.0, 
                "appearances_count": 2,
                "face_ids": "[1, 2]",
                "attributes": '{"top_color": "rot"}',
                "representative_image": "img1.jpg",
                "representative_crop": "crop1.jpg"
            },
            {
                "person_id": 2, 
                "name": "Person B", 
                "description": "Desc B", 
                "first_seen_ts": 5.0, 
                "last_seen_ts": 15.0, 
                "appearances_count": 3,
                "face_ids": "[3]",
                "attributes": '{"bottom_color": "blau"}',
                "representative_image": "img2.jpg",
                "representative_crop": "crop2.jpg"
            }
        ])
        sm.update_job(job_id, persons_df=persons_df)

        client = TestClient(app)
        response = client.post(
            f"/api/jobs/{job_id}/persons/merge",
            json={"source_person_id": 1, "target_person_id": 2}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Force clear test memory cache so it reads from disk
        sm._STORE.pop(job_id, None)

        updated_job = sm.get_job(job_id)
        df = updated_job["persons_df"]
        # Person 1 (source) should be removed
        assert len(df) == 1
        merged = df.iloc[0]
        assert merged["person_id"] == 2
        assert merged["appearances_count"] == 5
        assert merged["first_seen_ts"] == 5.0
        assert merged["last_seen_ts"] == 15.0
        # face_ids combined
        fids = set(json.loads(merged["face_ids"]))
        assert fids == {1, 2, 3}
        # attributes combined
        attrs = json.loads(merged["attributes"])
        assert attrs.get("top_color") == "rot"
        assert attrs.get("bottom_color") == "blau"

        sm.cleanup_job(job_id)

    def test_delete_person_success(self):
        """DELETE /api/jobs/{job_id}/persons/{person_id} deletes the person."""
        from fastapi.testclient import TestClient
        from backend.app import app
        from backend import session_manager as sm

        job_id = sm.create_job()
        persons_df = pd.DataFrame([
            {"person_id": 1, "name": "Person A", "description": "Desc A", "first_seen_ts": 1.0, "last_seen_ts": 2.0, "appearances_count": 1},
            {"person_id": 2, "name": "Person B", "description": "Desc B", "first_seen_ts": 3.0, "last_seen_ts": 4.0, "appearances_count": 2}
        ])
        sm.update_job(job_id, persons_df=persons_df)

        client = TestClient(app)
        response = client.delete(f"/api/jobs/{job_id}/persons/1")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Force clear test memory cache so it reads from disk
        sm._STORE.pop(job_id, None)

        # Verify state in session manager
        updated_job = sm.get_job(job_id)
        df = updated_job["persons_df"]
        assert len(df) == 1
        assert df.iloc[0]["person_id"] == 2

        sm.cleanup_job(job_id)