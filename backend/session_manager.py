"""session_manager.py – per-job temp directories and state management.

Job state is persisted to disk so it survives server restarts:
  - <job_dir>/job.json           – all scalar / JSON-serialisable fields
  - <job_dir>/<field>.parquet    – DataFrame fields (pauses_df, etc.)

On startup _scan_jobs_from_disk() reloads every job it finds on disk.
"""
from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.pipeline.persons import review_artifacts, review_state, stage_state

log = logging.getLogger(__name__)

JOB_LOG_FILENAME = "job.log"

# Context variable to store the current job_id (used for per-job logging)
job_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("job_id", default=None)


class JobLogFilter(logging.Filter):
    """Filter that only allows records with the current job_id."""
    def filter(self, record):
        current_job_id = job_id_var.get()
        if not current_job_id:
            return False
        record.job_id = current_job_id
        return True


class JobLogHandler(logging.Handler):
    """Handler that writes logs to a job.log file in the job's directory."""
    def __init__(self):
        super().__init__()
        self.addFilter(JobLogFilter())
        self.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))

    def emit(self, record):
        jid = getattr(record, "job_id", None)
        if not jid:
            return
        
        # Determine the log file path
        # We use _BASE_DIR directly to avoid recursive get_job() calls if logging is inside sm.
        jdir = _BASE_DIR / jid
        if not jdir.exists():
            return
            
        log_file = jdir / JOB_LOG_FILENAME
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(self.format(record) + "\n")
        except Exception:
            # Silent fail to avoid infinite recursion / crash during logging
            pass


def setup_job_logging():
    """Add the JobLogHandler to the root logger."""
    root = logging.getLogger()
    # Check if already added
    for h in root.handlers:
        if isinstance(h, JobLogHandler):
            return
    root.addHandler(JobLogHandler())


# Configurable via AD_JOBS_DIR env var so a Docker volume can be mounted.
_BASE_DIR = Path(os.environ.get("AD_JOBS_DIR", "/tmp/ad_jobs"))
_STORE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

# ── Field classification ───────────────────────────────────────────────────────

# DataFrame fields – stored as Parquet, except derived persons for current jobs.
_DF_FIELDS: List[str] = [
    "pauses_df",
    "speech_df",
    "segments_df",
    "slots_df",
    "slot_map_df",
    "persons_df",
]

# Scalar fields – stored in job.json.
_JSON_FIELDS: List[str] = [
    "job_id",
    "job_dir",
    "video_path",
    "original_video_filename",
    "video_sha256",
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
    "final_mp4_path",
    "faces",
    "persons_analysis_running",
    "persons_phase",
]

# ── Persistence helpers ────────────────────────────────────────────────────────

def _apply_person_review(job: Dict[str, Any], force: bool = False) -> None:
    """Refresh derived caches from the current person_analysis files."""
    if job.get("persons_analysis_running") or not review_artifacts.available(job["job_dir"]):
        return
    root = Path(job["job_dir"]) / "person_analysis"
    paths = [root / name for name in review_artifacts.FILES]
    signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None for p in paths)
    if not force and job.get("_person_review_signature") == signature:
        return
    try:
        result = review_state.current(job["job_dir"])
    except review_artifacts.ReviewError as exc:
        job["person_review_error"] = str(exc)
        job.pop("person_review", None)
        job.pop("_person_review_signature", None)
        job["persons_df"] = None
        job["faces"] = []
        return
    columns = ["person_id", "name", "description", "function", "track_ids", "segments", "appearances",
               "appearances_count", "first_seen_ts", "last_seen_ts", "representative_crop",
               "representative_crop_id", "attributes", "face_ids", "valid_identity_crop_ids", "fallback_crop_ids"]
    rows = []
    for person in result["persons"]:
        row = dict(person)
        for field in ("track_ids", "segments", "appearances", "attributes", "face_ids", "valid_identity_crop_ids", "fallback_crop_ids"):
            row[field] = json.dumps(row[field], ensure_ascii=False)
        rows.append(row)
    job["persons_df"] = pd.DataFrame(rows, columns=columns)
    job["faces"] = result["faces"]
    job["person_review"] = {k: v for k, v in result.items() if k != "faces"}
    job.pop("person_review_error", None)
    job["_person_review_signature"] = signature


def mutate_face_review(job_id, body):
    with _LOCK:
        job = _STORE.get(job_id)
        if not job:
            raise review_artifacts.ReviewError("Job nicht gefunden.", 404)
        if job.get("status") == "running":
            raise review_artifacts.ReviewError("Bitte laufenden Schritt abwarten.", 409)
        result = stage_state.save_faces(job["job_dir"], body)
        _apply_person_review(job, force=True)
        _persist_job(job)
        return result


def begin_person_stage(job_id, phase):
    with _LOCK:
        job = _STORE.get(job_id)
        if not job or job.get("status") == "running":
            raise review_artifacts.ReviewError("Ein Verarbeitungsschritt läuft bereits.", 409)
        job.update(status="running", persons_analysis_running=True, persons_phase=phase)
        _persist_job(job)


def mutate_attribute_review(job_id, body):
    from backend.pipeline.persons import attribute_state
    with _LOCK:
        job = _STORE.get(job_id)
        if not job:
            raise review_artifacts.ReviewError('Job nicht gefunden.', 404)
        if job.get('status') == 'running':
            raise review_artifacts.ReviewError('Bitte laufenden Schritt abwarten.', 409)
        return attribute_state.save_review(job['job_dir'], body)


def mutate_person_review(job_id: str, expected_version: str | None, operation: str, body: dict) -> dict:
    with _LOCK:
        job = _STORE.get(job_id)
        if not job:
            raise review_artifacts.ReviewError("Job nicht gefunden.", 404)
        if job.get("status") == "running":
            raise review_artifacts.ReviewError("Bitte warten, bis die laufende Verarbeitung abgeschlossen ist.", 409)
        result = review_state.mutate(job["job_dir"], expected_version, operation, body)
        _apply_person_review(job, force=True)
        _persist_job(job)
        return {k: v for k, v in result.items() if k != "faces"}

def _persist_job(job: Dict[str, Any]) -> None:
    """Write job state to disk (must be called while _LOCK is held or with a copy)."""
    job_dir = Path(job["job_dir"])
    job_dir.mkdir(parents=True, exist_ok=True)
    current_persons = review_artifacts.available(job_dir)

    # Save DataFrames as Parquet
    for field in _DF_FIELDS:
        if field == "persons_df" and current_persons:
            continue  # Rebuilt from person_analysis/; legacy jobs keep their copy.
        val = job.get(field)
        parquet_path = job_dir / f"{field}.parquet"
        if val is not None and isinstance(val, pd.DataFrame):
            try:
                val.to_parquet(str(parquet_path), index=True, engine="pyarrow")
            except Exception as exc:
                log.warning("Could not save %s.parquet: %s", field, exc)

    # Save scalar fields as JSON (atomic write via tmp file)
    sidecar: Dict[str, Any] = {field: job.get(field) for field in _JSON_FIELDS}
    if current_persons:
        sidecar.pop("faces", None)
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
    current_persons = review_artifacts.available(job_dir)
    if current_persons:
        job["faces"] = None  # Ignore old copies; _apply_person_review rebuilds both.
        job["persons_df"] = None

    # Reload DataFrames from Parquet
    for field in _DF_FIELDS:
        if field == "persons_df" and current_persons:
            continue
        parquet_path = job_dir / f"{field}.parquet"
        if parquet_path.exists():
            try:
                job[field] = pd.read_parquet(str(parquet_path), engine="pyarrow")
            except Exception as exc:
                log.warning("Could not load %s: %s", parquet_path, exc)

    # Never leave a job stuck in "running" after a restart
    if job.get("status") == "running":
        job["status"] = "interrupted"

    job["job_dir"] = str(job_dir)
    job["persons_analysis_running"] = False
    _apply_person_review(job)

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
        "original_video_filename": None,
        "video_sha256": None,
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
        "persons_df": None,
        "gpt_records_broadcast": None,
        "gpt_records_directors": None,
        "final_mp4_path": None,
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
            _apply_person_review(job)
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
        _apply_person_review(_STORE[job_id], force=bool({"persons_df", "faces"} & kwargs.keys()))
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
