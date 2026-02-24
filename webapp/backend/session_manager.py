"""session_manager.py – per-job temp directories and state management.

Job state is persisted to disk so it survives server restarts:
  - <job_dir>/job.json           – all scalar / JSON-serialisable fields
  - <job_dir>/<field>.parquet    – DataFrame fields (pauses_df, etc.)

On startup _scan_jobs_from_disk() reloads every job it finds on disk.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)

# Configurable via AD_JOBS_DIR env var so a Docker volume can be mounted.
_BASE_DIR = Path(os.environ.get("AD_JOBS_DIR", "/tmp/ad_jobs"))
_STORE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

# ── Field classification ───────────────────────────────────────────────────────

# DataFrame fields – stored as CSV files in the job directory.
_DF_FIELDS: List[str] = [
    "pauses_df",
    "speech_df",
    "segments_df",
    "slots_df",
    "slot_map_df",
]

# Scalar fields – stored in job.json.
_JSON_FIELDS: List[str] = [
    "job_id",
    "job_dir",
    "video_path",
    "audio_path",
    "video_stats",
    "pauses_srt",
    "transcript_srt",
    "transcript_meta",
    "quality_report",
    "output_paths",
    "config",
    "status",
    "progress",
    "scene_images",
    "gpt_records_broadcast",
    "gpt_records_directors",
]

# ── Persistence helpers ────────────────────────────────────────────────────────

def _persist_job(job: Dict[str, Any]) -> None:
    """Write job state to disk (must be called while _LOCK is held or with a copy)."""
    job_dir = Path(job["job_dir"])
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save DataFrames as Parquet
    for field in _DF_FIELDS:
        val = job.get(field)
        parquet_path = job_dir / f"{field}.parquet"
        if val is not None and isinstance(val, pd.DataFrame):
            try:
                val.to_parquet(str(parquet_path), index=True, engine="pyarrow")
            except Exception as exc:
                log.warning("Could not save %s.parquet: %s", field, exc)

    # Save scalar fields as JSON (atomic write via tmp file)
    sidecar: Dict[str, Any] = {field: job.get(field) for field in _JSON_FIELDS}
    try:
        tmp = job_dir / "job.json.tmp"
        tmp.write_text(json.dumps(sidecar, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(job_dir / "job.json")
    except Exception as exc:
        log.warning("Could not save job.json for %s: %s", job.get("job_id"), exc)


def _load_job_from_disk(job_dir: Path) -> Optional[Dict[str, Any]]:
    """Reload a job from its directory. Returns None if job.json is missing/corrupt."""
    sidecar_path = job_dir / "job.json"
    if not sidecar_path.exists():
        return None

    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Skipping %s – bad job.json: %s", job_dir, exc)
        return None

    job: Dict[str, Any] = {field: None for field in _JSON_FIELDS + _DF_FIELDS}
    job.update(sidecar)

    # Reload DataFrames from Parquet
    for field in _DF_FIELDS:
        parquet_path = job_dir / f"{field}.parquet"
        if parquet_path.exists():
            try:
                job[field] = pd.read_parquet(str(parquet_path), engine="pyarrow")
            except Exception as exc:
                log.warning("Could not load %s: %s", parquet_path, exc)

    # Never leave a job stuck in "running" after a restart
    if job.get("status") == "running":
        job["status"] = "interrupted"

    return job


def _scan_jobs_from_disk() -> None:
    """Scan _BASE_DIR and reload all persisted jobs into _STORE."""
    if not _BASE_DIR.exists():
        return
    loaded = 0
    for entry in _BASE_DIR.iterdir():
        if not entry.is_dir():
            continue
        job = _load_job_from_disk(entry)
        if job is None:
            continue
        job_id = job.get("job_id") or entry.name
        job["job_id"] = job_id
        job["job_dir"] = str(entry)
        with _LOCK:
            _STORE[job_id] = job
        loaded += 1
    if loaded:
        log.info("Reloaded %d job(s) from %s", loaded, _BASE_DIR)


# ── Public API ─────────────────────────────────────────────────────────────────

def create_job() -> str:
    """Create a new job, return its job_id."""
    job_id = str(uuid.uuid4())
    job_dir = _BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job: Dict[str, Any] = {
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

    with _LOCK:
        _STORE[job_id] = job
        _persist_job(job)

    return job_id


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        job = _STORE.get(job_id)
        if job:
            return job
            
    # Fallback to disk if not in memory (e.g. populated externally)
    job_dir = _BASE_DIR / job_id
    if job_dir.exists():
        job = _load_job_from_disk(job_dir)
        if job:
            job["job_id"] = job_id
            job["job_dir"] = str(job_dir)
            with _LOCK:
                _STORE[job_id] = job
            return job
            
    return None


def update_job(job_id: str, **kwargs) -> None:
    with _LOCK:
        if job_id not in _STORE:
            return
        _STORE[job_id].update(kwargs)
        _persist_job(_STORE[job_id])


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


# ── Startup scan ───────────────────────────────────────────────────────────────
# Runs once at import time so existing jobs are available immediately.
_scan_jobs_from_disk()
