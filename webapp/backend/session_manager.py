"""session_manager.py – per-job temp directories and state management."""
from __future__ import annotations

import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


# Configurable via AD_JOBS_DIR env var so a Docker volume can be mounted.
_BASE_DIR = Path(os.environ.get("AD_JOBS_DIR", "/tmp/ad_jobs"))
_STORE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def create_job() -> str:
    """Create a new job, return its job_id."""
    job_id = str(uuid.uuid4())
    job_dir = _BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with _LOCK:
        _STORE[job_id] = {
            "job_id": job_id,
            "job_dir": str(job_dir),
            "video_path": None,
            "audio_path": None,
            "video_stats": None,
            "pauses_df": None,
            "speech_df": None,
            "pauses_srt": None,
            "segments_df": None,
            "transcript_srt": None,
            "transcript_meta": None,
            "slots_df": None,
            "quality_report": None,
            "scene_images": None,
            "slot_map_df": None,
            "gpt_records_broadcast": None,
            "gpt_records_directors": None,
            "output_paths": {},
            "config": {},
            "status": "created",
            "progress": {},
        }

    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        return _STORE.get(job_id)


def update_job(job_id: str, **kwargs) -> None:
    with _LOCK:
        if job_id in _STORE:
            _STORE[job_id].update(kwargs)


def set_status(job_id: str, status: str, message: str = "") -> None:
    update_job(job_id, status=status, progress={"message": message})


def cleanup_job(job_id: str) -> None:
    """Remove temp files and job state."""
    with _LOCK:
        job = _STORE.pop(job_id, None)

    if job:
        job_dir = Path(job.get("job_dir", ""))
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)


def job_dir(job_id: str) -> Optional[Path]:
    job = get_job(job_id)
    if job:
        return Path(job["job_dir"])
    return None
