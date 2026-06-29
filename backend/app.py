"""app.py – FastAPI web application for the Audiodeskription pipeline."""
from __future__ import annotations

import json
import re
import logging
import os
import queue
import errno
import hashlib
import shutil
import threading
import time
import urllib.request

from dotenv import load_dotenv
load_dotenv()
import asyncio
import uvicorn
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth, OAuthError
from authlib.jose import JsonWebKey, jwt

import sys
sys.path.insert(0, str(Path(__file__).parent))

from event_bus import BusEvent, event_bus
import session_manager as sm
from db.store import DataStore

# Pipeline modules are imported lazily inside route handlers to avoid
# forcing GPU/ML dependencies to be installed just to start the server.

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(title="Audiodeskription API", docs_url=None)

ERR_UNKNOWN_JOB = "Unknown job"
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Limit upload size (default 2 GB – videos can be large).
_max_mb = int(os.environ.get("MAX_UPLOAD_MB", 2048))
# FastAPI uses starlette.requests.Request, which streams large files automatically.

_SUMMARY_STREAMS: list[dict[str, Any]] = []
_SSE_LOCK = threading.Lock()
_LATEST_PROGRESS_BY_JOB: Dict[str, dict] = {}
_WORKERS: Dict[str, dict[str, Any]] = {}
_WORKER_LOCK = threading.Lock()
_WORKER_MONITOR_STARTED = False
_WORKER_STALE_SECONDS = float(os.environ.get("AD_WORKER_STALE_SECONDS", 30))
_WORKER_MONITOR_INTERVAL_SECONDS = float(os.environ.get("AD_WORKER_MONITOR_INTERVAL_SECONDS", 5))

_STORAGE_ERROR_ERRNOS = {
    errno.ENOSPC,
    errno.EDQUOT,
    errno.EFBIG,
}

_OIDC_ISSUER_URL = os.environ.get("OIDC_ISSUER_URL", "").strip()
_OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "").strip()
_OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "").strip()
_OIDC_SCOPES = os.environ.get("OIDC_SCOPES", "openid profile email").strip() or "openid profile email"
_OIDC_REDIRECT_URI = os.environ.get("OIDC_REDIRECT_URI", "").strip()
_OIDC_ENABLED = bool(_OIDC_ISSUER_URL and _OIDC_CLIENT_ID and _OIDC_CLIENT_SECRET)
_SESSION_SECRET = os.environ.get("OIDC_SESSION_SECRET", "").strip() or os.environ.get("SESSION_SECRET", "").strip() or "change-me-please"
_SESSION_SECURE = os.environ.get("OIDC_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"}
_USER_CONFIG_DIR = Path(os.environ.get("AD_USER_CONFIG_DIR", "") or (os.environ.get("AD_JOBS_DIR", "/tmp/ad_jobs") + "/users"))
_OIDC_ID_TOKEN_COOKIE = os.environ.get("OIDC_ID_TOKEN_COOKIE_NAME", "oidc_id_token").strip() or "oidc_id_token"
_JWKS_CACHE: dict[str, Any] = {"expires_at": 0.0, "key_set": None}
_JWKS_CACHE_TTL_SECONDS = 3600.0
_DATABASE_URL = os.environ.get("AD_DATABASE_URL", "").strip()
_DATASTORE = DataStore(_DATABASE_URL, _USER_CONFIG_DIR, logger)

oauth = OAuth()
if _OIDC_ENABLED:
    if _SESSION_SECRET == "change-me-please":
        logger.warning("OIDC is enabled, but OIDC_SESSION_SECRET/SESSION_SECRET is not set.")
    oauth.register(
        name="oidc",
        server_metadata_url=f"{_OIDC_ISSUER_URL.rstrip('/')}/.well-known/openid-configuration",
        client_id=_OIDC_CLIENT_ID,
        client_secret=_OIDC_CLIENT_SECRET,
        client_kwargs={"scope": _OIDC_SCOPES},
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=_SESSION_SECRET,
    same_site="lax",
    https_only=_SESSION_SECURE,
)


def _progress_payload(
    step: str,
    message: str,
    current: int | float | None = None,
    total: int | float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "step": step,
        "message": message,
    }
    if current is not None:
        payload["current"] = current
    if total is not None:
        payload["total"] = total
    return payload


def _push_progress(
    job_id: str,
    step: str,
    message: str,
    current: int | float | None = None,
    total: int | float | None = None,
) -> None:
    _push(job_id, "progress", _progress_payload(step, message, current, total))
    _touch_worker_progress(job_id, message, current, total)


def _mark_step_running(job_id: str, step: str, message: str) -> None:
    sm.set_status(job_id, "running", message)
    _push_progress(job_id, step, message, 0, 100)


def _touch_worker_progress(
    job_id: str,
    message: str,
    current: int | float | None = None,
    total: int | float | None = None,
) -> None:
    now = time.monotonic()
    with _WORKER_LOCK:
        worker = _WORKERS.get(job_id)
        if not worker:
            return
        worker["last_progress_at"] = now
        worker["last_notice_at"] = now
        worker["last_message"] = message
        worker["last_current"] = current
        worker["last_total"] = total


def _ensure_worker_monitor() -> None:
    global _WORKER_MONITOR_STARTED
    with _WORKER_LOCK:
        if _WORKER_MONITOR_STARTED:
            return
        _WORKER_MONITOR_STARTED = True

    threading.Thread(target=_worker_monitor_loop, name="ad-worker-monitor", daemon=True).start()


def _start_worker(job_id: str, step: str, target) -> None:
    _ensure_worker_monitor()

    def supervised_target():
        try:
            target()
        finally:
            with _WORKER_LOCK:
                worker = _WORKERS.get(job_id)
                if worker and worker.get("thread") is threading.current_thread():
                    worker["finished_at"] = time.monotonic()

    thread = threading.Thread(target=supervised_target, name=f"ad-{step}-{job_id[:8]}", daemon=True)
    now = time.monotonic()
    with _WORKER_LOCK:
        _WORKERS[job_id] = {
            "thread": thread,
            "step": step,
            "started_at": now,
            "last_progress_at": now,
            "last_notice_at": now,
            "last_message": "queued",
            "last_current": 0,
            "last_total": 100,
            "finished_at": None,
        }
    thread.start()


def _worker_monitor_loop() -> None:
    while True:
        time.sleep(_WORKER_MONITOR_INTERVAL_SECONDS)
        now = time.monotonic()
        with _WORKER_LOCK:
            items = list(_WORKERS.items())

        for job_id, worker in items:
            thread = worker.get("thread")
            step = worker.get("step")
            job = sm.get_job(job_id)
            status = job.get("status") if job else None

            if status != "running":
                with _WORKER_LOCK:
                    current = _WORKERS.get(job_id)
                    if current is worker:
                        _WORKERS.pop(job_id, None)
                continue

            if thread is not None and not thread.is_alive():
                sm.set_status(job_id, "error", f"{step} worker stopped unexpectedly")
                _push(job_id, "error", {
                    "step": step,
                    "message": f"{step} worker stopped unexpectedly. Check the job log for details.",
                })
                with _WORKER_LOCK:
                    current = _WORKERS.get(job_id)
                    if current is worker:
                        _WORKERS.pop(job_id, None)
                continue

            last_progress_at = float(worker.get("last_progress_at") or now)
            last_notice_at = float(worker.get("last_notice_at") or last_progress_at)
            if now - last_progress_at < _WORKER_STALE_SECONDS or now - last_notice_at < _WORKER_STALE_SECONDS:
                continue

            current = worker.get("last_current")
            total = worker.get("last_total")
            base_message = worker.get("last_message") or "Still running"
            elapsed = int(now - last_progress_at)
            with _WORKER_LOCK:
                current_worker = _WORKERS.get(job_id)
                if current_worker is worker:
                    current_worker["last_notice_at"] = now
            _push(
                job_id,
                "progress",
                _progress_payload(
                    step,
                    f"{base_message} (still running, no new progress for {elapsed}s)",
                    current,
                    total,
                ),
            )


def _push(job_id: str, event: str, data: Any) -> None:
    if event == "progress":
        _LATEST_PROGRESS_BY_JOB[job_id] = data
        sm.update_job(job_id, progress=data)

    event_bus.publish(f"job:{job_id}", event, data)
    _push_summary_update(job_id)


def _push_summary_update(job_id: str) -> None:
    with _SSE_LOCK:
        subscribers = list(_SUMMARY_STREAMS)

    for subscriber in subscribers:
        if job_id in subscriber["job_ids"]:
            subscriber["queue"].put(job_id)


def _latest_progress_for_job(job_id: str, job: dict) -> Optional[dict]:
    if job.get("status") != "running":
        return None
    return _LATEST_PROGRESS_BY_JOB.get(job_id) or job.get("progress")


def _job_sidecar_snapshot(job_id: str) -> Optional[dict]:
    job = sm.get_job(job_id)
    job_dir = Path(job["job_dir"]) if job and job.get("job_dir") else Path(os.environ.get("AD_JOBS_DIR", "/tmp/ad_jobs")) / job_id
    sidecar_path = job_dir / "job.json"
    if not sidecar_path.exists():
        return None
    try:
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _stable_json_key(data: Any) -> str:
    return json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)


def _sse_message(item: BusEvent) -> str:
    payload = {"event": item.event, "data": item.data}
    return f"id: {item.seq}\ndata: {json.dumps(payload)}\n\n"


def _job_summary_payload(job_id: str) -> Optional[dict]:
    job = sm.get_job(job_id)
    if not job:
        return None

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "video_path": job.get("video_path"),
        "original_video_filename": job.get("original_video_filename"),
        "latest_progress": _latest_progress_for_job(job_id, job),
    }


def _format_bytes(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "unknown"

    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    unit_idx = 0
    while value >= 1024 and unit_idx < len(units) - 1:
        value /= 1024
        unit_idx += 1

    precision = 0 if value >= 10 or unit_idx == 0 else 1
    return f"{value:.{precision}f} {units[unit_idx]}"


def _disk_usage_for(path: Path) -> dict[str, Any]:
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent

    usage = shutil.disk_usage(probe)
    return {
        "path": str(probe),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "free": _format_bytes(usage.free),
    }


def _upload_os_error_response(exc: OSError, job_path: Path, phase: str) -> JSONResponse:
    disk = _disk_usage_for(job_path)
    if exc.errno in _STORAGE_ERROR_ERRNOS:
        return JSONResponse(
            {
                "error": (
                    f"Upload failed while {phase}: backend storage is full or the upload exceeds the "
                    f"filesystem quota. Free space on {disk['path']}: {disk['free']}."
                ),
                "code": "backend_storage_full",
                "phase": phase,
                "errno": exc.errno,
                "free_bytes": disk["free_bytes"],
                "storage_path": disk["path"],
            },
            status_code=507,
        )

    if isinstance(exc, PermissionError):
        return JSONResponse(
            {
                "error": f"Upload failed while {phase}: backend cannot write to {job_path}.",
                "code": "backend_storage_permission_denied",
                "phase": phase,
                "errno": exc.errno,
                "storage_path": str(job_path),
            },
            status_code=500,
        )

    return JSONResponse(
        {
            "error": f"Upload failed while {phase}: {exc.strerror or str(exc)}",
            "code": "backend_storage_error",
            "phase": phase,
            "errno": exc.errno,
            "storage_path": str(job_path),
        },
        status_code=500,
    )


def _safe_video_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if 1 < len(suffix) <= 12 and suffix[1:].replace("-", "").replace("_", "").isalnum():
        return suffix
    return ".mp4"


def _original_upload_filename(filename: str) -> str:
    return str(filename).replace("\\", "/").split("/")[-1] or "video"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _oidc_ready() -> bool:
    return _OIDC_ENABLED


def _oidc_metadata() -> dict[str, Any]:
    well_known = f"{_OIDC_ISSUER_URL.rstrip('/')}/.well-known/openid-configuration"
    with urllib.request.urlopen(well_known, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid OIDC metadata response")
    return payload


def _oidc_jwks() -> Any:
    now = time.time()
    cached = _JWKS_CACHE.get("key_set")
    if cached is not None and now < float(_JWKS_CACHE.get("expires_at", 0.0)):
        return cached

    metadata = _oidc_metadata()
    jwks_uri = str(metadata.get("jwks_uri", "")).strip()
    if not jwks_uri:
        raise ValueError("OIDC metadata does not contain jwks_uri")

    with urllib.request.urlopen(jwks_uri, timeout=10) as response:
        jwks_payload = json.loads(response.read().decode("utf-8"))
    key_set = JsonWebKey.import_key_set(jwks_payload)
    _JWKS_CACHE["key_set"] = key_set
    _JWKS_CACHE["expires_at"] = now + _JWKS_CACHE_TTL_SECONDS
    return key_set


def _claims_to_user(claims: dict[str, Any]) -> Optional[dict[str, Any]]:
    subject = str(claims.get("sub", "")).strip()
    if not subject:
        return None
    return {
        "sub": subject,
        "iss": str(claims.get("iss", "")).strip(),
        "name": str(claims.get("name", "")).strip() or None,
        "email": str(claims.get("email", "")).strip() or None,
        "preferred_username": str(claims.get("preferred_username", "")).strip() or None,
        "picture": str(claims.get("picture", "")).strip() or None,
    }


def _validate_id_token(id_token: str) -> Optional[dict[str, Any]]:
    if not id_token:
        return None

    key_set = _oidc_jwks()
    claims = jwt.decode(
        id_token,
        key_set,
        claims_options={
            "iss": {"essential": True, "value": _OIDC_ISSUER_URL},
            "aud": {"essential": True, "value": _OIDC_CLIENT_ID},
            "exp": {"essential": True},
            "iat": {"essential": True},
            "sub": {"essential": True},
        },
    )
    claims.validate(leeway=60)
    return _claims_to_user(dict(claims))


def _current_user(request: Request) -> Optional[dict[str, Any]]:
    raw_token = request.cookies.get(_OIDC_ID_TOKEN_COOKIE, "")
    if not raw_token:
        return None
    try:
        return _validate_id_token(raw_token)
    except Exception:
        return None


def _require_current_user(request: Request) -> dict[str, Any]:
    if not _oidc_ready():
        raise HTTPException(status_code=404, detail="OIDC login is not configured")
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _read_user_config(user: dict[str, Any]) -> dict[str, Any]:
    payload = _DATASTORE.get_user_config(user)
    return payload if isinstance(payload, dict) else {}


def _write_user_config(user: dict[str, Any], config: dict[str, Any]) -> int:
    return _DATASTORE.put_user_config(user, config)


# ── Prompt auto-loader (GPT_PROMPTS_DIR) ──────────────────────────────────────

def _load_prompts_from_dir(prompts_dir: str) -> tuple[str, str] | None:
    """Load and assemble prompt files from a directory.

    Reads:
      system_instruction.txt  (required)
      ad_rules.txt            (required)
      user_instruction.txt    (required)
      few_shots.txt           (optional)

    Assembles:
      SYSTEM_FINAL = system_instruction
                   + "\n\n# Audiodeskription – Regeln\n" + ad_rules
                   + "\n\n# Few-Shots / Beispiele\n"    + few_shots (if non-empty)
      USER_BASE    = user_instruction

    Returns (system_final, user_base), or None if any required file is missing/empty.
    """
    d = Path(prompts_dir)
    required = ["system_instruction.txt", "ad_rules.txt", "user_instruction.txt"]
    texts: dict[str, str] = {}
    for fname in required:
        p = d / fname
        if not p.exists():
            return None
        txt = p.read_text(encoding="utf-8").strip()
        if not txt:
            return None
        texts[fname] = txt

    system_final = (
        texts["system_instruction.txt"]
        + "\n\n# Audiodeskription – Regeln\n"
        + texts["ad_rules.txt"]
    )

    few_shots_path = d / "few_shots.txt"
    if few_shots_path.exists():
        shots = few_shots_path.read_text(encoding="utf-8").strip()
        if shots:
            system_final += "\n\n# Few-Shots / Beispiele\n" + shots

    user_base = texts["user_instruction.txt"]
    return system_final.strip(), user_base.strip()

def _load_raw_prompts_from_dir(prompts_dir: str) -> dict[str, str]:
    """Load individual prompt files without assembling them for the frontend UI."""
    d = Path(prompts_dir)
    res = {}
    for fname in ["system_instruction.txt", "ad_rules.txt", "user_instruction.txt", "few_shots.txt"]:
        p = d / fname
        if p.exists():
            txt = p.read_text(encoding="utf-8").strip()
            if txt:
                res[fname.replace(".txt", "")] = txt
    return res


def _load_available_models(config_path: str) -> list[dict]:
    """Load model list from gpt_config.yaml.

    Unterstützte Formate:
    1) Direkte YAML-Datei:
       presets:
         standard:
           model: gpt-5-mini-2025-08-07
         fast:
           model: gpt-5-nano-2025-08-07

    2) Kubernetes-ConfigMap mit eingebettetem YAML:
       data:
         gpt_config.yaml: |
           presets:
             standard:
               model: gpt-5-mini-2025-08-07

    3) Legacy-Format:
       environments:
         default:
           model: gpt-5-mini-2025-08-07
    """
    try:
        import yaml

        p = Path(config_path)
        if not p.exists():
            print(f"[system_info] GPT config not found: {config_path}")
            return []

        with open(p, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        # Falls eine komplette K8s-ConfigMap gelesen wird und der eigentliche
        # YAML-Inhalt als String unter data["gpt_config.yaml"] liegt:
        if isinstance(config, dict) and "data" in config and "gpt_config.yaml" in config["data"]:
            inner_yaml = config["data"]["gpt_config.yaml"]
            if isinstance(inner_yaml, str) and inner_yaml.strip():
                config = yaml.safe_load(inner_yaml) or {}

        # Primär aktuelles Format: presets
        entries = config.get("presets", {})

        # Rückwärtskompatibilität: älteres Format environments
        if not entries:
            entries = config.get("environments", {})

        if not isinstance(entries, dict):
            print(f"[system_info] Invalid GPT config structure in: {config_path}")
            return []

        seen: set[str] = set()
        models: list[dict] = []

        for entry_name, values in entries.items():
            if not isinstance(values, dict):
                continue

            model = str(values.get("model", "")).strip()
            if not model:
                continue

            if model not in seen:
                seen.add(model)
                models.append({
                    "env": str(entry_name),
                    "model": model,
                    "temperature": float(values.get("temperature", 0.2)),
                    "max_tokens": int(values.get("max_output_tokens", 1024)),
                    "detail": str(values.get("detail", "low"))
                })

        print(f"[system_info] Loaded GPT models from {config_path}: {models}")
        return models

    except Exception as exc:
        print(f"[system_info] Failed to load GPT models from {config_path}: {exc}")
        return []


def _gpt_config_path() -> str:
    gpt_config_path = os.environ.get("GPT_CONFIG_PATH", "")
    if gpt_config_path:
        return gpt_config_path

    potential_configs = [
        Path("/app/config/gpt_config.yaml"),
        Path(__file__).parent.parent / "config" / "gpt_config.yaml"
    ]
    for p in potential_configs:
        if p.exists():
            return str(p)
    return ""


def _available_gpt_models() -> list[dict]:
    gpt_config_path = _gpt_config_path()
    return _load_available_models(gpt_config_path) if gpt_config_path else []


def _default_gpt_model() -> str:
    available_models = _available_gpt_models()
    if available_models:
        return str(available_models[0]["model"])
    return "gpt-5-mini-2025-08-07"

# ── Health check (K8s liveness / readiness probe) ─────────────────────────────

@app.get("/api/ping")
def ping():
    return {"status": "ok"}


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/api/auth/status")
def auth_status(request: Request):
    user = _current_user(request)
    return {
        "enabled": _oidc_ready(),
        "authenticated": bool(user),
        "user": user if user else None,
    }


@app.get("/api/auth/login")
async def auth_login(request: Request, next: str = "/"):
    if not _oidc_ready():
        raise HTTPException(status_code=404, detail="OIDC login is not configured")

    next_path = next if next.startswith("/") else "/"
    request.session["post_login_redirect"] = next_path

    redirect_uri = _OIDC_REDIRECT_URI or str(request.url_for("auth_callback"))
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@app.get("/api/auth/callback")
async def auth_callback(request: Request):
    if not _oidc_ready():
        raise HTTPException(status_code=404, detail="OIDC login is not configured")

    try:
        token = await oauth.oidc.authorize_access_token(request)
        user = token.get("userinfo") or await oauth.oidc.parse_id_token(request, token)
    except OAuthError as exc:
        raise HTTPException(status_code=401, detail=f"OIDC login failed: {exc.error}") from exc

    id_token = str(token.get("id_token", "")).strip()
    if not user or not str(user.get("sub", "")).strip() or not id_token:
        raise HTTPException(status_code=401, detail="OIDC login failed: missing subject claim")

    redirect_to = request.session.pop("post_login_redirect", "/")
    if not isinstance(redirect_to, str) or not redirect_to.startswith("/"):
        redirect_to = "/"
    response = RedirectResponse(url=redirect_to, status_code=303)

    max_age: Optional[int] = None
    try:
        claims = jwt.decode(id_token, _oidc_jwks(), claims_options={})
        exp = int(claims.get("exp", 0))
        now = int(time.time())
        if exp > now:
            max_age = exp - now
    except Exception:
        max_age = 3600

    response.set_cookie(
        _OIDC_ID_TOKEN_COOKIE,
        id_token,
        httponly=True,
        secure=_SESSION_SECURE,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    response = JSONResponse({"ok": True})
    response.delete_cookie(_OIDC_ID_TOKEN_COOKIE, path="/")
    return response


@app.get("/api/user/config")
def get_user_config(request: Request):
    user = _require_current_user(request)
    payload = _read_user_config(user)
    config = payload.get("config")
    if not isinstance(config, dict):
        config = {}

    return {
        "config": config,
        "updated_at": payload.get("updated_at"),
    }


@app.put("/api/user/config")
def put_user_config(request: Request, body: dict = Body(default={})):
    user = _require_current_user(request)
    incoming = body.get("config") if isinstance(body, dict) and isinstance(body.get("config"), dict) else body
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Invalid config payload")

    encoded = json.dumps(incoming, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) > 1_000_000:
        raise HTTPException(status_code=413, detail="Config payload too large (max 1 MB)")

    updated_at = _write_user_config(user, incoming)
    return {"ok": True, "updated_at": updated_at}


@app.get("/api/user/presets")
def list_user_presets(request: Request):
    user = _require_current_user(request)
    presets = _DATASTORE.list_presets(user)
    return {"presets": presets}


@app.post("/api/user/presets")
def create_user_preset(request: Request, body: dict = Body(default={})):
    user = _require_current_user(request)
    incoming = body.get("preset") if isinstance(body, dict) and isinstance(body.get("preset"), dict) else body
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Invalid preset payload")

    try:
        preset = _DATASTORE.create_preset(user, incoming)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create preset: {exc}") from exc
    return {"preset": preset}


@app.put("/api/user/presets/{preset_id}")
def update_user_preset(request: Request, preset_id: str, body: dict = Body(default={})):
    user = _require_current_user(request)
    incoming = body.get("preset") if isinstance(body, dict) and isinstance(body.get("preset"), dict) else body
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="Invalid preset payload")

    try:
        preset = _DATASTORE.update_preset(user, preset_id, incoming)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not update preset: {exc}") from exc
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"preset": preset}


@app.delete("/api/user/presets/{preset_id}")
def delete_user_preset(request: Request, preset_id: str):
    user = _require_current_user(request)
    try:
        deleted = _DATASTORE.delete_preset(user, preset_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete preset: {exc}") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"ok": True}



# ── Upload ─────────────────────────────────────────────────────────────────────

@app.get("/api/system_info")
def system_info():
    """Return backend system information, such as GPU availability, default prompts and available models."""
    gpu_available = False
    try:
        import torch
        gpu_available = torch.cuda.is_available()
    except ImportError:
        pass

    defaults = {}
    prompts_dir = os.environ.get("GPT_PROMPTS_DIR", "")
    if not prompts_dir:
        potential_dirs = [
            Path("/app/config/prompts"),
            Path(__file__).parent.parent / "config" / "prompts"
        ]
        for d in potential_dirs:
            if d.exists() and d.is_dir():
                prompts_dir = str(d)
                break

    if prompts_dir:
        defaults = _load_raw_prompts_from_dir(prompts_dir)

    available_models = _available_gpt_models()
    if not available_models:
        available_models = [{"env": "default", "model": _default_gpt_model()}]

    return {
        "gpu_available": gpu_available,
        "default_prompts": defaults,
        "available_models": available_models,
    }
@app.post("/api/jobs")
async def create_job():
    job_id = sm.create_job()
    return {"job_id": job_id}

@app.get("/api/jobs/{job_id}/upload_status")
def upload_status(job_id: str, filename: str = None):
    if not job_id or not filename:
        return JSONResponse({"error": "Missing job_id or filename"}, status_code=400)

    job_path = sm.job_dir(job_id)
    if not job_path:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    part_file = job_path / "upload.part"
    if part_file.exists():
        return {"uploaded_bytes": part_file.stat().st_size}
    
    return {"uploaded_bytes": 0}

@app.post("/api/jobs/{job_id}/video")
async def upload_chunk(
    job_id: str,
    filename: str = Form(...),
    chunkIndex: int = Form(0),
    totalChunks: int = Form(1),
    totalBytes: int = Form(0),
    chunk: UploadFile = File(...)
):
    from pipeline import video_utils
    
    if not job_id or not filename:
        return JSONResponse({"error": "Missing job_id or filename"}, status_code=400)
    
    if not chunk:
        return JSONResponse({"error": "No chunk data provided"}, status_code=400)

    if totalChunks < 1 or chunkIndex < 0 or chunkIndex >= totalChunks:
        return JSONResponse(
            {
                "error": f"Invalid upload chunk index {chunkIndex} for {totalChunks} total chunks.",
                "code": "invalid_upload_chunk",
            },
            status_code=400,
        )

    max_upload_bytes = _max_mb * 1024 * 1024
    if totalBytes and totalBytes > max_upload_bytes:
        return JSONResponse(
            {
                "error": (
                    f"Upload is too large: {_format_bytes(totalBytes)} exceeds the backend limit "
                    f"of {_format_bytes(max_upload_bytes)}. Increase MAX_UPLOAD_MB to allow this file."
                ),
                "code": "upload_too_large",
                "max_upload_mb": _max_mb,
                "max_upload_bytes": max_upload_bytes,
                "total_bytes": totalBytes,
            },
            status_code=413,
        )

    job_path = sm.job_dir(job_id)
    if not job_path:
         return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    original_filename = _original_upload_filename(filename)
    part_file = job_path / "upload.part"

    # Append the chunk
    try:
        with open(part_file, "ab") as f:
            # We process in chunks to avoid blowing up memory
            while True:
                data = await chunk.read(1024 * 1024)
                if not data:
                    break
                f.write(data)
    except OSError as exc:
        return _upload_os_error_response(exc, job_path, "writing upload chunk")

    # If it's the final chunk
    if chunkIndex == totalChunks - 1:
        # Rename part to a stable, processing-safe filename derived from content.
        try:
            video_sha256 = _sha256_file(part_file)
            video_path = job_path / f"video-{video_sha256}{_safe_video_extension(original_filename)}"
            part_file.rename(video_path)
        except OSError as exc:
            return _upload_os_error_response(exc, job_path, "finalizing uploaded file")
        
        try:
            stats = video_utils.get_video_stats(str(video_path))
        except Exception as exc:
            return JSONResponse(
                {
                    "error": f"Upload completed, but the backend could not read video metadata: {exc}",
                    "code": "video_metadata_failed",
                    "video_path": str(video_path),
                },
                status_code=422,
            )

        try:
            if isinstance(stats, dict):
                stats["filename"] = original_filename
                stats["stored_filename"] = video_path.name
            sm.update_job(
                job_id,
                video_path=str(video_path),
                original_video_filename=original_filename,
                video_sha256=video_sha256,
                video_stats=stats,
            )
        except OSError as exc:
            return _upload_os_error_response(exc, job_path, "persisting job metadata")
        return {"job_id": job_id, "stats": stats, "complete": True}

    return {"success": True, "complete": False}


# ── VAD Pauses ─────────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/vad")
def run_vad(job_id: str, body: dict = Body(default={})):
    from pipeline import vad_pauses
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)
    if not job.get("video_path"):
        return JSONResponse({"error": "No video uploaded"}, status_code=400)

    params = {
        "threshold": float(body.get("threshold", 0.5)),
        "min_speech_duration_ms": int(body.get("min_speech_duration_ms", 1500)),
        "min_silence_duration_ms": int(body.get("min_silence_duration_ms", 400)),
        "speech_pad_ms": int(body.get("speech_pad_ms", 50)),
        "min_pause_duration_s": float(body.get("min_pause_duration_s", 0.3)),
    }

    def run():
        sm.job_id_var.set(job_id)
        try:
            _mark_step_running(job_id, "vad", "VAD detection started")

            def cb(msg, cur=None, total=None):
                _push_progress(job_id, "vad", msg, cur, total)

            audio_path = str(Path(sm.job_dir(job_id)) / "audio.wav")
            pauses_df, speech_df, srt_str = vad_pauses.extract_pauses(
                job["video_path"], audio_path=audio_path, progress_cb=cb, **params
            )
            sm.update_job(job_id,
                          audio_path=audio_path,
                          pauses_df=pauses_df,
                          speech_df=speech_df,
                          pauses_srt=srt_str,
                          slots_df=None,
                          quality_report=None,
                          scene_images=None,
                          slot_map_df=None,
                          gpt_records_broadcast=None,
                          gpt_records_directors=None,
                          final_mp4_path=None)
            sm.set_status(job_id, "idle")
            _push(job_id, "vad_done", {
                "pauses_count": len(pauses_df),
                "pauses": pauses_df.to_dict(orient="records"),
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "vad", "message": str(exc)})

    _mark_step_running(job_id, "vad", "VAD queued…")
    _start_worker(job_id, "vad", run)
    return {"status": "started"}


# ── Transcription ──────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/transcribe")
def run_transcribe(job_id: str, body: dict = Body(default={})):
    from pipeline import transcription as trans_mod, vad_pauses
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    params = {
        "model_size": body.get("model_size", "small"),
        "language": body.get("language", "de"),
        "use_fw_vad": bool(body.get("use_fw_vad", True)),
        "vad_min_silence_ms": int(body.get("vad_min_silence_ms", 350)),
        "word_timestamps": bool(body.get("word_timestamps", True)),
        "use_silero_gate": bool(body.get("use_silero_gate", True)),
        "silero_threshold": float(body.get("silero_threshold", 0.70)),
        "silero_min_speech_s": float(body.get("silero_min_speech_s", 0.45)),
        "silero_min_silence_s": float(body.get("silero_min_silence_s", 0.55)),
        "clamp_to_vad": bool(body.get("clamp_to_vad", True)),
    }

    def run():
        sm.job_id_var.set(job_id)
        try:
            _mark_step_running(job_id, "transcribe", "Extracting audio…")

            video_path = job["video_path"]
            cached_audio_path = job.get("audio_path")
            audio_path = cached_audio_path if cached_audio_path and Path(cached_audio_path).exists() else str(Path(sm.job_dir(job_id)) / "audio.wav")

            video_stats = job.get("video_stats", {})
            total_duration = video_stats.get("duration_s", 0)

            def cb_extract(msg, cur=None, total=None):
                _push_progress(job_id, "transcribe", msg, cur, total)

            vad_pauses.extract_audio(
                video_path,
                audio_path,
                sample_rate_hz=16000,
                total_duration_s=total_duration,
                progress_cb=cb_extract,
            )
            sm.update_job(job_id, audio_path=audio_path)

            _push_progress(job_id, "transcribe", "Running Whisper…", 0, 100)

            def cb(msg, cur=None, total=None):
                _push_progress(job_id, "transcribe", msg, cur, total)

            seg_df, srt_str, meta = trans_mod.transcribe(
                audio_path, progress_cb=cb, 
                total_duration_s=total_duration,
                **params
            )
            sm.update_job(job_id,
                          segments_df=seg_df,
                          transcript_srt=srt_str,
                          transcript_meta=meta,
                          slots_df=None,
                          quality_report=None,
                          scene_images=None,
                          slot_map_df=None,
                          gpt_records_broadcast=None,
                          gpt_records_directors=None,
                          final_mp4_path=None)
            sm.set_status(job_id, "idle")
            _push(job_id, "transcribe_done", {
                "segment_count": len(seg_df),
                "metadata": meta,
                "segments": seg_df.to_dict(orient="records"),
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "transcribe", "message": str(exc)})

    _mark_step_running(job_id, "transcribe", "Transcription queued…")
    _start_worker(job_id, "transcribe", run)
    return {"status": "started"}


# ── Upload existing SRT ────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/srt")
async def upload_srt(job_id: str, srt: UploadFile = File(...)):
    from pipeline import transcription as trans_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    if not srt:
        return JSONResponse({"error": "No SRT file"}, status_code=400)

    srt_path = sm.job_dir(job_id) / "uploaded_transcript.srt"
    
    with open(srt_path, "wb") as f:
        data = await srt.read()
        f.write(data)

    try:
        seg_df = trans_mod.load_srt_as_df(str(srt_path))
        sm.update_job(job_id, segments_df=seg_df,
                      transcript_srt=srt_path.read_text(encoding="utf-8"),
                      transcript_meta={"source": "uploaded"})
        return {"segment_count": len(seg_df),
                "segments": seg_df.to_dict(orient="records")}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ── AD Slots ───────────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/slots")
def run_slots(job_id: str, body: dict = Body(default={})):
    from pipeline import ad_slots as slots_mod
    job = sm.get_job(job_id)
    if not job or job.get("pauses_df") is None:
        return JSONResponse({"error": "Pauses not available. Run VAD first."}, status_code=400)

    def run():
        sm.job_id_var.set(job_id)
        try:
            _mark_step_running(job_id, "slots", "Converting pauses to slots…")

            pauses_df: pd.DataFrame = job["pauses_df"]
            speech_df = job.get("segments_df")  # whisper transcript
            if speech_df is None:
                speech_df = pd.DataFrame(columns=["start_s","end_s"])

            slots_df = slots_mod.pauses_to_slots(
                pauses_df,
                min_slot_s=float(body.get("min_slot_s", 1.0)),
                pad_in_s=float(body.get("pad_in_s", 0.0)),
                pad_out_s=float(body.get("pad_out_s", 0.0)),
                speech_df=speech_df if body.get("filter_whisper", False) else None,
                whisper_overlap_eps_s=float(body.get("whisper_overlap_eps_s",
                                                      body.get("whisper_overlap_threshold", 0.05))),
            )

            _push_progress(job_id, "slots", "Evaluating quality…", 75, 100)
            qr = slots_mod.quality_report(
                pauses_df,
                speech_df,
                slots_df,
            )

            sm.update_job(job_id, 
                          slots_df=slots_df, 
                          quality_report=qr,
                          scene_images=None,
                          slot_map_df=None,
                          gpt_records_broadcast=None,
                          gpt_records_directors=None,
                          final_mp4_path=None)
            sm.set_status(job_id, "idle")
            _push_progress(job_id, "slots", "Slot generation complete.", 100, 100)
            _push(job_id, "slots_done", {
                "slot_count": len(slots_df),
                "slots": slots_df.to_dict(orient="records"),
                "quality": qr,
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "slots", "message": str(exc)})

    _mark_step_running(job_id, "slots", "Slot generation queued…")
    _start_worker(job_id, "slots", run)
    return {"status": "started"}


# ── Image Extraction ───────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/images")
def run_images(job_id: str, body: dict = Body(default={})):
    from pipeline import image_extraction as img_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)
    if job.get("slots_df") is None:
        return JSONResponse({"error": "Slots not available. Run slot generation first."}, status_code=400)

    def run():
        sm.job_id_var.set(job_id)
        try:
            _mark_step_running(job_id, "images", "Starting scene detection…")

            job_path = sm.job_dir(job_id)
            frames_dir = str(job_path / "frames")
            gap_dir = str(job_path / "gapfill")

            extractor = img_mod.MidframeExtractor(
                output_dir=frames_dir,
                threshold=float(body.get("threshold", 24.0)),
                min_scene_length=int(body.get("min_scene_length", 20)),
                blur_threshold=float(body.get("blur_threshold", 80.0)),
                short_scene_s=float(body.get("short_scene_s", 3.0)),
            )

            def cb_scene(msg: str, current: int | None = None, total: int | None = None):
                message = str(msg or "")
                lower_message = message.lower()
                is_detection = (
                    lower_message.startswith("detecting scenes")
                    or lower_message.startswith("scene detection")
                )
                if is_detection:
                    base = 5
                    span = 30
                else:
                    base = 35
                    span = 35

                if total:
                    percent = base + round((max(0, min(current or 0, total)) / total) * span)
                else:
                    percent = base
                _push_progress(job_id, "images", msg, percent, 100)

            scene_images, scene_timestamps = extractor.process_video(
                job["video_path"],
                window_start_s=float(body.get("window_start_s", 0.0)),
                window_end_s=float(body.get("window_end_s", 0)) or None,
                progress_cb=cb_scene,
            )

            _push_progress(job_id, "images", "Gapfill for AD slots…", 70, 100)
            slots_df: pd.DataFrame = job["slots_df"]

            def cb_gapfill(msg: str, current: int | None = None, total: int | None = None):
                if total:
                    percent = 70 + round((max(0, min(current or 0, total)) / total) * 30)
                else:
                    percent = 70
                _push_progress(job_id, "images", msg, percent, 100)

            all_images, slot_map_df = img_mod.gapfill_images_for_ad_slots(
                video_path=job["video_path"],
                ad_slots_df=slots_df,
                existing_images=scene_images,
                output_dir=gap_dir,
                blur_threshold=float(body.get("blur_threshold", 80.0)),
                progress_cb=cb_gapfill,
            )

            sm.update_job(job_id,
                          scene_images=all_images,
                          slot_map_df=slot_map_df,
                          gpt_records_broadcast=None,
                          gpt_records_directors=None,
                          final_mp4_path=None)
            sm.set_status(job_id, "idle")
            _push_progress(job_id, "images", "Image extraction complete.", 100, 100)
            _push(job_id, "images_done", {
                "scene_count": len(scene_images),
                "total_images": len(all_images),
                "slots_mapped": len(slot_map_df),
                "slot_map": slot_map_df.to_dict(orient="records"),
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "images", "message": str(exc)})

    _mark_step_running(job_id, "images", "Image extraction queued…")
    _start_worker(job_id, "images", run)
    return {"status": "started"}


# ── Person Analysis ─────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/persons")
def run_persons(job_id: str, body: dict = Body(default={})):
    from pipeline import person_analysis as persons_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)
    if job.get("scene_images") is None or len(job.get("scene_images", [])) == 0:
        return JSONResponse({"error": "Scene images not available. Run image extraction first."}, status_code=400)

    def run():
        sm.job_id_var.set(job_id)
        try:
            _mark_step_running(job_id, "persons", "Detecting persons in images…")

            def cb_persons(msg: str, current: int | None = None, total: int | None = None):
                if total:
                    percent = round((max(0, min(current or 0, total)) / total) * 100)
                else:
                    percent = 50
                _push_progress(job_id, "persons", msg, percent, 100)

            job_dir = sm.job_dir(job_id)
            persons_df, faces = persons_mod.analyze_persons(
                job["scene_images"],
                job_dir=str(job_dir),
                progress_cb=cb_persons,
            )

            # Store faces list in job state
            sm.update_job(job_id, persons_df=persons_df, faces=faces)

            # Persist persons to PostgreSQL if enabled
            if _DATASTORE.enabled and persons_df is not None and not persons_df.empty:
                persons_list = persons_df.to_dict(orient="records")
                _DATASTORE.store_persons(job_id, persons_list)

            sm.set_status(job_id, "idle")
            _push_progress(job_id, "persons", "Person analysis complete.", 100, 100)
            _push(job_id, "persons_done", {
                "persons_count": len(persons_df),
                "faces_count": len(faces),
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "persons", "message": str(exc)})

    _mark_step_running(job_id, "persons", "Person analysis queued…")
    _start_worker(job_id, "persons", run)
    return {"status": "started"}


@app.get("/api/jobs/{job_id}/persons")
def get_persons(job_id: str):
    """Return the persons DataFrame for a job."""
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    persons_df = job.get("persons_df")
    if persons_df is None or persons_df.empty:
        return {"persons": []}

    # Replace NaN with None and convert to dict
    persons_clean = persons_df.replace({float('nan'): None})
    persons_list = persons_clean.to_dict(orient="records")

    # Parse face_ids from JSON string
    for person in persons_list:
        face_ids = person.get("face_ids")
        if isinstance(face_ids, str):
            try:
                person["face_ids"] = json.loads(face_ids) if face_ids else []
            except:
                person["face_ids"] = []
        elif face_ids is None:
            person["face_ids"] = []

    # Backfill representative_image from first_seen_ts if not present
    scene_images = job.get("scene_images") or []
    for person in persons_list:
        if "representative_image" not in person or not person["representative_image"]:
            ts = person.get("first_seen_ts", 0)
            if ts and scene_images:
                def extract_ts(path):
                    m = re.search(r'(\d{2})-(\d{2})-(\d{2})-(\d{3})', path)
                    if m:
                        h, mn, s, ms = map(int, m.groups())
                        return h * 3600 + mn * 60 + s + ms / 1000
                    return 0
                closest = min(scene_images, key=lambda p: abs(extract_ts(p) - ts), default=None)
                person["representative_image"] = closest

    return {"persons": persons_list}


@app.get("/api/jobs/{job_id}/faces")
def get_faces(job_id: str):
    """Return all detected faces for a job."""
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    faces = job.get("faces")
    if faces is None:
        return {"faces": []}

    return {"faces": faces}


# ── Face Image Endpoint ─────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/faces/{face_id}")
def get_face_image(job_id: str, face_id: int):
    """Return the face crop image for a face."""
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    faces = job.get("faces") or []
    for face in faces:
        if face.get("face_id") == face_id and face.get("crop_path"):
            job_path = sm.job_dir(job_id)
            crop_path = job_path / face["crop_path"]
            if crop_path.exists():
                return FileResponse(crop_path, media_type="image/jpeg")

    return JSONResponse({"error": "Face not found"}, status_code=404)


# ── GPT Description ────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/gpt")
def run_gpt(job_id: str, body: dict = Body(default={})):
    from pipeline import gpt_description as gpt_mod, export as export_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)
    if job.get("slots_df") is None:
        return JSONResponse({"error": "Slots not available"}, status_code=400)

    api_key = str(body.get("api_key") or os.environ.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return JSONResponse({"error": "OpenAI API key required"}, status_code=400)

    system_prompt = body.get("system_prompt", "")
    user_prompt = body.get("user_prompt", "")

    if not system_prompt or not user_prompt:
        prompts_dir = os.environ.get("GPT_PROMPTS_DIR", "")
        if not prompts_dir:
            potential_dirs = [
                Path("/app/config/prompts"),
                Path(__file__).parent.parent / "config" / "prompts"
            ]
            for d in potential_dirs:
                if d.exists() and d.is_dir():
                    prompts_dir = str(d)
                    break

        if prompts_dir:
            loaded = _load_prompts_from_dir(prompts_dir)
            if loaded:
                if not system_prompt:
                    system_prompt = loaded[0]
                if not user_prompt:
                    user_prompt = loaded[1]

    cut = body.get("cut", "broadcast")
    model_name = str(body.get("model") or "").strip() or _default_gpt_model()
    
    # O1/O3/gpt-5 models require temperature = 1.0 exactly
    raw_temp = float(body.get("temperature", 0.2))
    is_reasoning = model_name.startswith("o1") or model_name.startswith("o3") or "gpt-5" in model_name
    temperature = 1.0 if is_reasoning else raw_temp

    gpt_params = {
        "api_key": api_key,
        "model": model_name,
        "temperature": temperature,
        "max_tokens": int(body.get("max_tokens", 1024)),
        "detail": body.get("detail", "low"),
        "cut": cut,
        "syllables_per_second": float(body.get("syllables_per_second", 6.0)),
        "syl_safety_factor": float(body.get("syl_safety_factor", 0.85)),
        "max_rewrite_attempts": int(body.get("max_rewrite_attempts", 2)),
        "max_consecutive_gpt_errors": int(body.get(
            "max_consecutive_gpt_errors",
            os.environ.get("GPT_MAX_CONSECUTIVE_ERRORS", 3),
        )),
        "min_slot_s": float(body.get("min_slot_s", 0.5)),
        "transcript_window_before_s": float(body.get("transcript_window_before_s", 20.0)),
        "transcript_window_after_s": float(body.get("transcript_window_after_s", 5.0)),
        "transcript_context_max_chars": int(body.get("transcript_context_max_chars", 2000)),
        "previous_context_max_chars": int(body.get("previous_context_max_chars", 3000)),
    }
    gpt_run_config = {k: v for k, v in gpt_params.items() if k != "api_key"}

    def run():
        sm.job_id_var.set(job_id)
        try:
            _mark_step_running(job_id, "gpt", "Generating descriptions…")
            logger.info("Starting GPT description generation with config: %s", gpt_run_config)

            slots_df: pd.DataFrame = job["slots_df"]
            slot_map_df = job.get("slot_map_df")
            if slot_map_df is None:
                slot_map_df = pd.DataFrame()

            def cb(msg, cur, total):
                _push_progress(job_id, "gpt", msg, cur, total)

            records = gpt_mod.describe_slots(
                slots_df, slot_map_df,
                system_prompt, user_prompt,
                transcript_df=job.get("segments_df"),
                persons_df=job.get("persons_df"),
                progress_cb=cb,
                **gpt_params,
            )

            # Write output files
            run_folder = sm.job_dir(job_id) / "output"
            paths = export_mod.write_outputs(run_folder, records, cut)

            key = f"gpt_records_{cut}"
            job_config = job.get("config") or {}
            sm.update_job(job_id, **{key: records},
                          config={**job_config, "gpt": gpt_run_config},
                          output_paths={**job.get("output_paths", {}), **paths},
                          final_mp4_path=None)
            sm.set_status(job_id, "idle")
            _push_progress(job_id, "gpt", "Description generation complete.", 100, 100)
            _push(job_id, "gpt_done", {
                "total": len(records),
                "ok_count": sum(1 for r in records if r.get("ok") and not r.get("skipped")),
                "skip_count": sum(1 for r in records if r.get("skipped")),
                "error_count": sum(1 for r in records if not r.get("ok")),
                "model": model_name,
                "gpt_config": gpt_run_config,
                "output_files": list(paths.keys()),
                "records": records,
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "gpt", "message": str(exc)})

    _mark_step_running(job_id, "gpt", "GPT generation queued…")
    _start_worker(job_id, "gpt", run)
    return {"status": "started"}


@app.put("/api/jobs/{job_id}/texts")
def update_texts(job_id: str, body: dict = Body(...)):
    from pipeline import export as export_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    cut = body.get("cut", "broadcast")
    key = f"gpt_records_{cut}"
    records = job.get(key, [])
    
    if not records:
        return JSONResponse({"error": "No records found to update"}, status_code=400)

    updates = body.get("texts", {})
    if not updates:
        return JSONResponse({"error": "No text updates provided"}, status_code=400)

    # Apply updates
    for rec in records:
        s_id = str(rec.get("slot"))
        if s_id in updates:
            old_text = str(rec.get("text") or "")
            new_text = str(updates[s_id] or "")
            rec["text"] = new_text

            # A failed/skipped slot should only become usable AD text when the
            # user has actually supplied replacement content.
            if new_text.strip() and new_text != old_text:
                rec["ok"] = True
                rec["skipped"] = False
                rec["reason"] = ""
                rec.pop("error", None)

    try:
        # Re-export files with the new texts
        run_folder = sm.job_dir(job_id) / "output"
        paths = export_mod.write_outputs(run_folder, records, cut)

        # Update job state
        sm.update_job(job_id, **{key: records}, 
                      output_paths={**job.get("output_paths", {}), **paths})
        
        return {"status": "success", "updated_count": len(updates)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.put("/api/jobs/{job_id}/slots")
def update_slots(job_id: str, body: dict = Body(...)):
    """Update slot timings and implicitly update corresponding gpt_records and output files."""
    from pipeline import export as export_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    slots_df = job.get("slots_df")
    if slots_df is None:
        return JSONResponse({"error": "No slots found to update"}, status_code=400)

    updates = body.get("slots", [])
    if not updates:
        return JSONResponse({"error": "No slot updates provided"}, status_code=400)

    # Check if updates is an array (the UI might send it wrapped in `{ slots: [...] }` or natively)
    if not isinstance(updates, list):
        keys = list(updates.keys())
        if keys and isinstance(updates[keys[0]], dict):
            # Dict mapping of slot ID -> string text maybe? No, this is for /slots
            pass
    cut = body.get("cut")
    if not cut:
        if job.get("gpt_records_broadcast"):
            cut = "broadcast"
        elif job.get("gpt_records_directors"):
            cut = "directors"
        else:
            cut = "broadcast" # default fallback
            
    key = f"gpt_records_{cut}"
    records = job.get(key, [])

    # Update slots_df inline
    # For a robust approach we can index by 'slot'
    slots_updated_count = 0
    records_updated_count = 0
    
    # Create quick lookups
    # It might be easier to iterate over the provided array
    for update in updates:
        s_id = update.get("slot")
        start_s = update.get("start_s")
        end_s = update.get("end_s")
        if s_id is None or start_s is None or end_s is None:
            continue
            
        # 1. Update slots_df
        # Check if the slot exists in the dataframe
        if "slot" in slots_df.columns:
            mask = slots_df["slot"] == s_id
            if mask.any():
                slots_df.loc[mask, "start_s"] = float(start_s)
                slots_df.loc[mask, "end_s"] = float(end_s)
                slots_updated_count += 1
        
        # 2. Update gpt_records if they exist
        if records:
            for rec in records:
                if str(rec.get("slot")) == str(s_id):
                    rec["start_s"] = float(start_s)
                    rec["end_s"] = float(end_s)
                    rec["duration_s"] = rec["end_s"] - rec["start_s"]
                    records_updated_count += 1
                    break

    try:
        paths = job.get("output_paths", {})
        # Only re-export if we have records to export
        if records:
            run_folder = sm.job_dir(job_id) / "output"
            new_paths = export_mod.write_outputs(run_folder, records, cut)
            paths.update(new_paths)

        # Update job state
        sm.update_job(job_id, slots_df=slots_df, **{key: records}, output_paths=paths)
        
        return {
            "status": "success", 
            "slots_updated": slots_updated_count,
            "records_updated": records_updated_count
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
# ── TTS & Export ──────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/tts")
def run_tts_export(job_id: str, body: dict = Body(default={})):
    from pipeline import tts_export as tts_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)
        
    cut = body.get("cut", "broadcast")
    key = f"gpt_records_{cut}"
    records = job.get(key)
    
    if not records:
        return JSONResponse({"error": f"No GPT records found for cut '{cut}'. Run generation first."}, status_code=400)
        
    api_key = str(body.get("api_key") or os.environ.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return JSONResponse({"error": "OpenAI API key required"}, status_code=400)
        
    voice = body.get("voice", "alloy")
    ducking_volume = float(body.get("ducking_volume", 0.4))
    
    def run():
        sm.job_id_var.set(job_id)
        try:
            _mark_step_running(job_id, "tts", "Generating TTS audio...")
            
            job_path = sm.job_dir(job_id)
            tts_dir = job_path / "tts"
            
            def cb_tts(msg, cur, total):
                _push_progress(job_id, "tts", msg, cur, total)
                
            tts_files = tts_mod.generate_tts(
                records=records,
                api_key=api_key,
                output_dir=tts_dir,
                voice=voice,
                progress_cb=cb_tts
            )
            
            _push_progress(job_id, "tts", "Mixing audio into MP4...", 0, 100)
            
            def cb_export(msg, cur, total):
                 _push_progress(job_id, "tts", msg, cur, total)
                 
            final_mp4_path = str(job_path / f"output_{cut}.mp4")
            
            tts_mod.mix_audio_and_export(
                video_path=job["video_path"],
                records=records,
                output_path=final_mp4_path,
                ducking_volume=ducking_volume,
                progress_cb=cb_export
            )
            
            paths = job.get("output_paths", {})
            paths["final_mp4"] = final_mp4_path
            
            sm.update_job(job_id, 
                          final_mp4_path=final_mp4_path,
                          output_paths=paths,
                          **{key: records})
            
            sm.set_status(job_id, "idle")
            _push_progress(job_id, "tts", "TTS export complete.", 100, 100)
            _push(job_id, "tts_done", {
                "tts_files_count": len(tts_files),
                "final_mp4": final_mp4_path
            })
            
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "tts", "message": str(exc)})
            
    _mark_step_running(job_id, "tts", "TTS export queued…")
    _start_worker(job_id, "tts", run)
    return {"status": "started"}


# ── SSE Progress Stream ────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/stream")
async def status_stream(job_id: str, request: Request):
    async def generate():
        topic = f"job:{job_id}"
        last_event_id = request.headers.get("last-event-id", "")
        try:
            cursor = int(last_event_id) if last_event_id else 0
        except ValueError:
            cursor = 0

        job = sm.get_job(job_id)
        last_status = job.get("status") if job else None
        last_progress_key: Optional[str] = None
        if job:
            yield f"data: {json.dumps({'event': 'connected', 'status': job['status']})}\n\n"

        if cursor > 0:
            missed_events = event_bus.replay_after(topic, cursor)
            for item in missed_events:
                yield _sse_message(item)
                cursor = item.seq
                if item.event == "progress":
                    last_progress_key = _stable_json_key(item.data)
        elif job:
            latest_event = event_bus.latest(topic, "progress")
            if latest_event:
                yield _sse_message(latest_event)
                cursor = latest_event.seq
                last_progress_key = _stable_json_key(latest_event.data)
            else:
                latest_progress = _latest_progress_for_job(job_id, job)
                if latest_progress:
                    yield f"data: {json.dumps({'event': 'progress', 'data': latest_progress})}\n\n"
                    last_progress_key = _stable_json_key(latest_progress)
                latest_any_event = event_bus.latest(topic)
                if latest_any_event:
                    cursor = latest_any_event.seq

        loop = asyncio.get_running_loop()
        while True:
            if await request.is_disconnected():
                break
            try:
                # Use run_in_executor to avoid blocking the event loop
                new_events = await loop.run_in_executor(None, event_bus.wait_after, topic, cursor, 1.0)
                if new_events:
                    for item in new_events:
                        yield _sse_message(item)
                        cursor = item.seq
                        if item.event == "progress":
                            last_progress_key = _stable_json_key(item.data)
                else:
                    sidecar = _job_sidecar_snapshot(job_id)
                    if not sidecar:
                        yield "data: {\"event\":\"ping\"}\n\n"
                        continue

                    status = sidecar.get("status")
                    progress = sidecar.get("progress")
                    progress_key = _stable_json_key(progress) if progress else None
                    if status != last_status:
                        last_status = status
                        yield f"data: {json.dumps({'event': 'job_status', 'data': {'status': status}})}\n\n"
                    elif status == "running" and progress and progress_key != last_progress_key:
                        last_progress_key = progress_key
                        yield f"data: {json.dumps({'event': 'progress', 'data': progress})}\n\n"
                    else:
                        yield "data: {\"event\":\"ping\"}\n\n"
            except Exception:
                pass

    return StreamingResponse(generate(), media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/summary_stream")
async def job_summary_stream(request: Request, job_ids: str = ""):
    ids = [job_id.strip() for job_id in job_ids.split(",") if job_id.strip()]
    subscriber = {"job_ids": set(ids), "queue": queue.Queue()}

    def summaries_event() -> str:
        summaries = [
            summary
            for job_id in ids
            if (summary := _job_summary_payload(job_id)) is not None
        ]
        return f"event: summaries\ndata: {json.dumps(summaries)}\n\n"

    async def generate():
        with _SSE_LOCK:
            _SUMMARY_STREAMS.append(subscriber)

        loop = asyncio.get_running_loop()
        try:
            yield summaries_event()
            while True:
                if await request.is_disconnected():
                    break

                try:
                    await loop.run_in_executor(None, subscriber["queue"].get, True, 2.0)
                except queue.Empty:
                    pass

                yield summaries_event()
                yield "event: ping\ndata: {}\n\n"
        finally:
            with _SSE_LOCK:
                if subscriber in _SUMMARY_STREAMS:
                    _SUMMARY_STREAMS.remove(subscriber)

    return StreamingResponse(generate(), media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Results ────────────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    # Return serialisable subset
    import math

    def make_serializable(df):
        if df is None:
            return None
        # Replace NaN with None
        df_clean = df.replace({float('nan'): None})
        return df_clean.to_dict(orient="records")

    segments = make_serializable(job.get("segments_df")) or []
    transcript_preview = "\n".join(
        str(segment.get("text", "")).strip()
        for segment in segments[:5]
        if str(segment.get("text", "")).strip()
    )
    video_path = job.get("video_path")
    video_cache_key = None
    if video_path and Path(video_path).exists():
        stat = Path(video_path).stat()
        video_cache_key = f"{stat.st_size}-{stat.st_mtime_ns}"

    out = {
        "job_id": job_id,
        "status": job.get("status"),
        "video_stats": job.get("video_stats"),
        "pauses_count": len(job["pauses_df"]) if job.get("pauses_df") is not None else 0,
        "transcript_segments_count": len(segments),
        "transcript_preview": transcript_preview,
        "slots_count": len(job["slots_df"]) if job.get("slots_df") is not None else 0,
        "images_count": len(job["scene_images"]) if job.get("scene_images") else 0,
        "persons_count": len(job["persons_df"]) if job.get("persons_df") is not None else 0,
        
        # Timeline data
        "pauses": make_serializable(job.get("pauses_df")),
        "slots": make_serializable(job.get("slots_df")),
        "scenes": make_serializable(job.get("scenes_df")),
        "slot_map": job.get("slot_map_df").to_dict(orient="records") if (job.get("slot_map_df") is not None and not job.get("slot_map_df").empty) else None,
        "video_path": video_path,
        "original_video_filename": job.get("original_video_filename"),
        "video_sha256": job.get("video_sha256"),
        "video_cache_key": video_cache_key,
        
        "transcript_meta": job.get("transcript_meta"),
        "segments": segments,
        "quality_report": job.get("quality_report"),
        "config": job.get("config"),
        "output_paths": {**{k: Path(v).name for k, v in (job.get("output_paths") or {}).items()}, 
                         **({"log": sm.JOB_LOG_FILENAME} if Path(sm.job_dir(job_id) / sm.JOB_LOG_FILENAME).exists() else {})},
        "gpt_records": job.get("gpt_records_broadcast", job.get("gpt_records_directors")),
        "links": build_hateoas_links(job, str(request.base_url)),
        "latest_progress": _latest_progress_for_job(job_id, job)
    }
    return out

@app.get("/api/jobs/{job_id}/summary")
def get_job_summary(job_id: str):
    summary = _job_summary_payload(job_id)
    if summary is None:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    return summary

def build_hateoas_links(job: dict, base_url: str):
    """Dynamically generate valid next actions for a single job."""
    base = base_url.rstrip("/")
    jid = job["job_id"]
    links = [
        {"rel": "self", "href": f"{base}/api/jobs/{jid}", "method": "GET"},
        {"rel": "stream", "href": f"{base}/api/jobs/{jid}/stream", "method": "GET"},
        {"rel": "upload-video", "href": f"{base}/api/jobs/{jid}/video", "method": "POST"},
        {"rel": "upload-srt", "href": f"{base}/api/jobs/{jid}/srt", "method": "POST"}
    ]
    if job.get("video_path"):
        links.append({"rel": "run-vad", "href": f"{base}/api/jobs/{jid}/vad", "method": "POST"})
        links.append({"rel": "run-transcribe", "href": f"{base}/api/jobs/{jid}/transcribe", "method": "POST"})
        
    if job.get("pauses_df") is not None:
        links.append({"rel": "run-slots", "href": f"{base}/api/jobs/{jid}/slots", "method": "POST"})
        
    if job.get("slots_df") is not None and job.get("video_path"):
        links.append({"rel": "run-images", "href": f"{base}/api/jobs/{jid}/images", "method": "POST"})

    if job.get("scene_images") is not None and len(job.get("scene_images", [])) > 0:
        links.append({"rel": "run-persons", "href": f"{base}/api/jobs/{jid}/persons", "method": "POST"})
        links.append({"rel": "run-gpt", "href": f"{base}/api/jobs/{jid}/gpt", "method": "POST"})
        
    return links


# ── Download ───────────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/downloads/{file_key}")
def download(job_id: str, file_key: str):
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    if file_key == "video":
        file_path = job.get("video_path")
    elif file_key == "log":
        file_path = str(Path(job["job_dir"]) / sm.JOB_LOG_FILENAME)
    else:
        paths = job.get("output_paths") or {}
        file_path = paths.get(file_key)
        
    if not file_path or not Path(file_path).exists():
        return JSONResponse({"error": "File not found"}, status_code=404)

    filename = Path(file_path).name
    if file_key == "video":
        return FileResponse(
            file_path,
            filename=filename,
            headers={"Cache-Control": "private, max-age=604800, immutable"},
            content_disposition_type="inline",
        )

    return FileResponse(file_path, filename=filename)


# ── TTS Audio Preview ──────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/tts/{slot_id}")
def preview_tts(job_id: str, slot_id: int):
    """Serve the per-slot TTS mp3 file for inline browser playback."""
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    job_path = sm.job_dir(job_id)
    audio_path = job_path / "tts" / f"slot_{slot_id}.mp3"
    if not audio_path.exists():
        return JSONResponse({"error": f"TTS file for slot {slot_id} not found"}, status_code=404)

    return FileResponse(str(audio_path), media_type="audio/mpeg", filename=audio_path.name)


# ── Image Preview ──────────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/images/{img_name:path}")
def preview_image(job_id: str, img_name: str):
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    job_path = sm.job_dir(job_id)
    # Restrict to frames / gapfill subdirs
    for subdir in ["frames", "gapfill"]:
        candidate = job_path / subdir / img_name
        if candidate.exists():
            return FileResponse(candidate, media_type="image/jpeg")

    return JSONResponse({"error": "Image not found"}, status_code=404)



# ── Run Server ─────────────────────────────────────────────────────────────────

def main():
    sm.setup_job_logging()
    graceful_timeout = int(os.environ.get("UVICORN_GRACEFUL_TIMEOUT", "1"))
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        timeout_graceful_shutdown=graceful_timeout,
    )

if __name__ == "__main__":
    main()


# ── Similar Faces Endpoint ─────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@app.get("/api/jobs/{job_id}/persons/{person_id}/similar-faces")
def get_similar_faces(job_id: str, person_id: int, threshold: float = 0.5):
    """Find faces similar to a person's faces that might belong to the same person."""
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    faces = job.get("faces") or []
    if not faces:
        return {"similar_faces": [], "unassigned_faces": []}

    # Get person's face IDs
    persons_df = job.get("persons_df")
    if persons_df is None or persons_df.empty:
        return {"similar_faces": [], "unassigned_faces": []}

    # Find the person
    person_row = persons_df[persons_df["person_id"] == person_id]
    if person_row.empty:
        return JSONResponse({"error": "Person not found"}, status_code=404)

    # Parse face_ids
    face_ids_str = person_row.iloc[0].get("face_ids", "[]")
    if isinstance(face_ids_str, str):
        try:
            person_face_ids = set(json.loads(face_ids_str) or [])
        except:
            person_face_ids = set()
    else:
        person_face_ids = set(face_ids_str or [])

    # Get all face embeddings
    faces_with_embeddings = [f for f in faces if f.get("embedding")]
    if not faces_with_embeddings:
        return {"similar_faces": [], "unassigned_faces": []}

    # Collect person's embeddings
    person_embeddings = []
    for fid in person_face_ids:
        for f in faces_with_embeddings:
            if f.get("face_id") == fid:
                person_embeddings.append(f)
                break

    if not person_embeddings:
        return {"similar_faces": [], "unassigned_faces": []}

    # Find faces similar to any of person's faces
    similar = []
    unassigned = []

    for face in faces_with_embeddings:
        if face.get("face_id") in person_face_ids:
            continue  # Skip own faces

        # Check similarity to any of person's faces
        max_sim = 0.0
        best_match = None
        for person_face in person_embeddings:
            sim = _cosine_similarity(face.get("embedding", []), person_face.get("embedding", []))
            if sim > max_sim:
                max_sim = sim
                best_match = person_face.get("face_id")

        if max_sim >= threshold:
            similar.append({
                "face": face,
                "similarity": round(max_sim, 3),
                "matches_face_id": best_match,
            })
        else:
            # Check if unassigned (not in any person's face_ids)
            is_assigned = False
            for _, p_row in persons_df.iterrows():
                p_face_ids_str = p_row.get("face_ids", "[]")
                if isinstance(p_face_ids_str, str):
                    try:
                        p_face_ids = set(json.loads(p_face_ids_str) or [])
                    except:
                        p_face_ids = set()
                else:
                    p_face_ids = set(p_face_ids_str or [])
                if face.get("face_id") in p_face_ids:
                    is_assigned = True
                    break
            if not is_assigned:
                unassigned.append(face)

    # Sort similar faces by similarity (highest first)
    similar.sort(key=lambda x: x["similarity"], reverse=True)

    return {
        "similar_faces": similar[:20],  # Top 20 similar
        "unassigned_faces": unassigned[:20],  # Top 20 unassigned
    }


@app.post("/api/jobs/{job_id}/faces/merge")
def merge_faces(job_id: str, body: dict = Body(...)):
    """Move faces between persons or merge two persons."""
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    action = body.get("action")  # "merge_to_person" or "split_from_person"
    face_ids = body.get("face_ids", [])  # List of face IDs to move
    target_person_id = body.get("target_person_id")  # Target person ID (for merge)
    source_person_id = body.get("source_person_id")  # Source person ID (for split)

    if not face_ids:
        return JSONResponse({"error": "No face_ids provided"}, status_code=400)

    persons_df = job.get("persons_df")
    if persons_df is None or persons_df.empty:
        return JSONResponse({"error": "No persons found"}, status_code=400)

    faces = job.get("faces") or []
    face_id_set = set(face_ids)

    # Validate faces exist
    valid_face_ids = set()
    for f in faces:
        if f.get("face_id") in face_id_set:
            valid_face_ids.add(f.get("face_id"))

    if not valid_face_ids:
        return JSONResponse({"error": "No valid faces found"}, status_code=400)

    # Update persons_df
    df_list = persons_df.to_dict(orient="records")
    modified = False

    for person in df_list:
        face_ids_str = person.get("face_ids", "[]")
        if isinstance(face_ids_str, str):
            try:
                p_face_ids = json.loads(face_ids_str) if face_ids_str else []
            except:
                p_face_ids = []
        else:
            p_face_ids = face_ids_str or []

        p_face_ids_set = set(p_face_ids)

        if action == "merge_to_person":
            # Add faces TO target person
            if person["person_id"] == target_person_id:
                new_face_ids = list(p_face_ids_set | valid_face_ids)
                person["face_ids"] = json.dumps(new_face_ids)
                modified = True

        elif action == "split_from_person":
            # Remove faces FROM source person
            if person["person_id"] == source_person_id:
                new_face_ids = list(p_face_ids_set - valid_face_ids)
                person["face_ids"] = json.dumps(new_face_ids)
                modified = True

    if modified:
        # Reconstruct DataFrame
        new_df = pd.DataFrame(df_list)
        new_df = new_df.sort_values("first_seen_ts").reset_index(drop=True)
        sm.update_job(job_id, persons_df=new_df)

    return {"status": "ok", "modified": modified, "face_ids": list(valid_face_ids)}
