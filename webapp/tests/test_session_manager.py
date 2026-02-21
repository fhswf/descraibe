# tests/test_session_manager.py – unit tests for session_manager persistence
"""
Run with:
    uv run --no-sync pytest tests/test_session_manager.py -v
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest


# ── Fixture: fresh temp dir for each test ────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_jobs_dir(monkeypatch, tmp_path):
    """Give each test its own jobs directory so tests don't interfere."""
    monkeypatch.setenv("AD_JOBS_DIR", str(tmp_path))
    # Re-import with the new env var in effect
    import importlib
    import backend.session_manager as sm
    monkeypatch.setattr(sm, "_BASE_DIR", tmp_path)
    monkeypatch.setattr(sm, "_STORE", {})
    yield tmp_path
    # cleanup handled by tmp_path fixture


@pytest.fixture
def sm(isolated_jobs_dir):
    import importlib
    import backend.session_manager as module
    import importlib
    module._STORE.clear()
    return module


# ── Persistence: scalar fields survive a "restart" ────────────────────────────

class TestJobJsonPersistence:
    def test_job_json_created_on_create(self, sm, isolated_jobs_dir):
        job_id = sm.create_job()
        job_json = isolated_jobs_dir / job_id / "job.json"
        assert job_json.exists(), "job.json must be written by create_job()"

    def test_scalar_fields_persisted(self, sm, isolated_jobs_dir):
        job_id = sm.create_job()
        sm.update_job(job_id, video_path="/tmp/test.mp4", video_stats={"duration": 42})
        sm.set_status(job_id, "idle")

        data = json.loads((isolated_jobs_dir / job_id / "job.json").read_text())
        assert data["video_path"] == "/tmp/test.mp4"
        assert data["video_stats"]["duration"] == 42
        assert data["status"] == "idle"

    def test_reload_after_clear(self, sm, isolated_jobs_dir):
        """Simulates a server restart: clear _STORE, scan disk, check job reloaded."""
        job_id = sm.create_job()
        sm.update_job(job_id, video_path="/tmp/movie.mp4", video_stats={"fps": 25})
        sm.set_status(job_id, "idle")

        # Simulate restart
        sm._STORE.clear()
        sm._scan_jobs_from_disk()

        reloaded = sm.get_job(job_id)
        assert reloaded is not None, "Job must be reloaded from disk"
        assert reloaded["video_path"] == "/tmp/movie.mp4"
        assert reloaded["video_stats"]["fps"] == 25
        assert reloaded["status"] == "idle"

    def test_interrupted_status_on_reload(self, sm, isolated_jobs_dir):
        """A job that was 'running' when the server died must become 'interrupted'."""
        job_id = sm.create_job()
        sm.set_status(job_id, "running", "VAD in progress")

        sm._STORE.clear()
        sm._scan_jobs_from_disk()

        reloaded = sm.get_job(job_id)
        assert reloaded["status"] == "interrupted"


# ── Persistence: DataFrame fields ─────────────────────────────────────────────

class TestDataFramePersistence:
    def test_dataframe_parquet_written(self, sm, isolated_jobs_dir):
        job_id = sm.create_job()
        df = pd.DataFrame({"start_s": [0.0, 2.0], "end_s": [1.0, 3.5], "dur_s": [1.0, 1.5]})
        sm.update_job(job_id, pauses_df=df)

        parquet_path = isolated_jobs_dir / job_id / "pauses_df.parquet"
        assert parquet_path.exists(), "pauses_df.parquet must be written"

    def test_dataframe_reloaded_correctly(self, sm, isolated_jobs_dir):
        job_id = sm.create_job()
        df = pd.DataFrame({
            "start_s": [0.0, 5.0],
            "end_s": [2.0, 8.0],
            "dur_s": [2.0, 3.0],
        })
        sm.update_job(job_id, pauses_df=df)

        sm._STORE.clear()
        sm._scan_jobs_from_disk()

        reloaded = sm.get_job(job_id)
        assert reloaded["pauses_df"] is not None
        pd.testing.assert_frame_equal(
            reloaded["pauses_df"].reset_index(drop=True),
            df.reset_index(drop=True),
        )
