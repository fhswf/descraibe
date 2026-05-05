"""app.py – FastAPI web application for the Audiodeskription pipeline."""
from __future__ import annotations

import json
import os
import queue
import threading

from dotenv import load_dotenv
load_dotenv()
import asyncio
import uvicorn
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import sys
sys.path.insert(0, str(Path(__file__).parent))

import session_manager as sm

# Pipeline modules are imported lazily inside route handlers to avoid
# forcing GPU/ML dependencies to be installed just to start the server.

# ── App setup ──────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

app = FastAPI(title="Audiodeskription API", docs_url=None)

ERR_UNKNOWN_JOB = "Unknown job"

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

# SSE progress queues per job
_SSE_QUEUES: Dict[str, queue.Queue] = {}
_SUMMARY_STREAMS: list[dict[str, Any]] = []
_SSE_LOCK = threading.Lock()
_LATEST_PROGRESS_BY_JOB: Dict[str, dict] = {}


def _get_queue(job_id: str) -> queue.Queue:
    with _SSE_LOCK:
        if job_id not in _SSE_QUEUES:
            _SSE_QUEUES[job_id] = queue.Queue()
        return _SSE_QUEUES[job_id]


def _push(job_id: str, event: str, data: Any) -> None:
    if event == "progress":
        _LATEST_PROGRESS_BY_JOB[job_id] = data

    q = _get_queue(job_id)
    q.put({"event": event, "data": data})
    _push_summary_update(job_id)


def _push_summary_update(job_id: str) -> None:
    with _SSE_LOCK:
        subscribers = list(_SUMMARY_STREAMS)

    for subscriber in subscribers:
        if job_id in subscriber["job_ids"]:
            subscriber["queue"].put(job_id)


def _job_summary_payload(job_id: str) -> Optional[dict]:
    job = sm.get_job(job_id)
    if not job:
        return None

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "video_path": job.get("video_path"),
        "latest_progress": _LATEST_PROGRESS_BY_JOB.get(job_id) if job.get("status") == "running" else None,
    }


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
           model: gpt-4o
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


# ── Frontend ───────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    if not FRONTEND_DIR.exists():
        return JSONResponse({"error": "Frontend build not found. Run npm run build in the frontend directory."})
    return FileResponse(FRONTEND_DIR / "index.html")


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

    # Load available models from gpt_config.yaml
    gpt_config_path = os.environ.get("GPT_CONFIG_PATH", "")
    if not gpt_config_path:
        potential_configs = [
            Path("/app/config/gpt_config.yaml"),
            Path(__file__).parent.parent / "config" / "gpt_config.yaml"
        ]
        for p in potential_configs:
            if p.exists():
                gpt_config_path = str(p)
                break

    available_models = _load_available_models(gpt_config_path) if gpt_config_path else []

    # Fallback: if no models found, return sensible defaults
    if not available_models:
        available_models = [
            {"env": "default", "model": "gpt-4o"},
            {"env": "mini", "model": "gpt-4o-mini"},
        ]

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

    part_file = job_path / f"{filename}.part"
    if part_file.exists():
        return {"uploaded_bytes": part_file.stat().st_size}
    
    return {"uploaded_bytes": 0}

@app.post("/api/jobs/{job_id}/video")
async def upload_chunk(
    job_id: str,
    filename: str = Form(...),
    chunkIndex: int = Form(0),
    totalChunks: int = Form(1),
    chunk: UploadFile = File(...)
):
    from pipeline import video_utils
    
    if not job_id or not filename:
        return JSONResponse({"error": "Missing job_id or filename"}, status_code=400)
    
    if not chunk:
        return JSONResponse({"error": "No chunk data provided"}, status_code=400)

    job_path = sm.job_dir(job_id)
    if not job_path:
         return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)

    part_file = job_path / f"{filename}.part"
    video_path = job_path / filename

    # Append the chunk
    with open(part_file, "ab") as f:
        # We process in chunks to avoid blowing up memory
        while True:
            data = await chunk.read(1024 * 1024)
            if not data:
                break
            f.write(data)

    # If it's the final chunk
    if chunkIndex == totalChunks - 1:
        # Rename part to final
        part_file.rename(video_path)
        
        try:
            stats = video_utils.get_video_stats(str(video_path))
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        sm.update_job(job_id, video_path=str(video_path), video_stats=stats)
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
            sm.set_status(job_id, "running", "VAD detection started")

            def cb(msg):
                _push(job_id, "progress", {"step": "vad", "message": msg})

            pauses_df, speech_df, srt_str = vad_pauses.extract_pauses(
                job["video_path"], progress_cb=cb, **params
            )
            sm.update_job(job_id,
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

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


# ── Transcription ──────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/transcribe")
def run_transcribe(job_id: str, body: dict = Body(default={})):
    from pipeline import transcription as trans_mod
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
            sm.set_status(job_id, "running", "Extracting audio…")
            _push(job_id, "progress", {"step": "transcribe", "message": "Extracting audio…"})

            video_path = job["video_path"]
            audio_path = str(Path(sm.job_dir(job_id)) / "audio.wav")

            from moviepy import VideoFileClip
            from proglog import ProgressBarLogger

            class AudioExtractionLogger(ProgressBarLogger):
                def bars_callback(self, bar, attr, value, old_value=None):
                    if bar == "t":
                        total = self.state.bars[bar].get("total", 1)
                        _push(job_id, "progress", {
                            "step": "transcribe",
                            "message": "Extracting audio…",
                            "current": value,
                            "total": total
                        })

            clip = VideoFileClip(video_path)
            logger = AudioExtractionLogger()
            clip.audio.write_audiofile(audio_path, fps=16000, nbytes=2,
                                       ffmpeg_params=["-ac", "1"], logger=logger)
            clip.close()
            sm.update_job(job_id, audio_path=audio_path)

            _push(job_id, "progress", {"step": "transcribe", "message": "Running Whisper…", "current": 0, "total": 100})

            def cb(msg, cur=None, total=None):
                _push(job_id, "progress", {"step": "transcribe", "message": msg, "current": cur, "total": total})

            video_stats = job.get("video_stats", {})
            total_duration = video_stats.get("duration_s", 0)

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

    sm.set_status(job_id, "running", "Transcription queued…")
    _push(job_id, "progress", {"step": "transcribe", "message": "Transcription queued…", "current": 0, "total": 100})
    threading.Thread(target=run, daemon=True).start()
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
            sm.set_status(job_id, "running", "Generating AD slots…")
            _push(job_id, "progress", {"step": "slots", "message": "Converting pauses to slots…"})

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

            _push(job_id, "progress", {"step": "slots", "message": "Evaluating quality…"})
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
            _push(job_id, "slots_done", {
                "slot_count": len(slots_df),
                "slots": slots_df.to_dict(orient="records"),
                "quality": qr,
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "slots", "message": str(exc)})

    threading.Thread(target=run, daemon=True).start()
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
            sm.set_status(job_id, "running", "Extracting scene images…")
            _push(job_id, "progress", {"step": "images", "message": "Starting scene detection…", "current": 0, "total": 100})

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
                if total:
                    percent = 20 + round((max(0, min(current or 0, total)) / total) * 50)
                else:
                    percent = 10
                _push(job_id, "progress", {
                    "step": "images",
                    "message": msg,
                    "current": percent,
                    "total": 100,
                })

            scene_images, scene_timestamps = extractor.process_video(
                job["video_path"],
                window_start_s=float(body.get("window_start_s", 0.0)),
                window_end_s=float(body.get("window_end_s", 0)) or None,
                progress_cb=cb_scene,
            )

            _push(job_id, "progress", {"step": "images", "message": "Gapfill for AD slots…", "current": 70, "total": 100})
            slots_df: pd.DataFrame = job["slots_df"]

            def cb_gapfill(msg: str, current: int | None = None, total: int | None = None):
                if total:
                    percent = 70 + round((max(0, min(current or 0, total)) / total) * 30)
                else:
                    percent = 70
                _push(job_id, "progress", {
                    "step": "images",
                    "message": msg,
                    "current": percent,
                    "total": 100,
                })

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
            _push(job_id, "progress", {"step": "images", "message": "Image extraction complete.", "current": 100, "total": 100})
            _push(job_id, "images_done", {
                "scene_count": len(scene_images),
                "total_images": len(all_images),
                "slots_mapped": len(slot_map_df),
                "slot_map": slot_map_df.to_dict(orient="records"),
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "images", "message": str(exc)})

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


# ── GPT Description ────────────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/gpt")
def run_gpt(job_id: str, body: dict = Body(default={})):
    from pipeline import gpt_description as gpt_mod, export as export_mod
    job = sm.get_job(job_id)
    if not job:
        return JSONResponse({"error": ERR_UNKNOWN_JOB}, status_code=404)
    if job.get("slots_df") is None:
        return JSONResponse({"error": "Slots not available"}, status_code=400)

    api_key = body.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
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
    model_name = body.get("model", "gpt-4o")
    
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
        "min_slot_s": float(body.get("min_slot_s", 0.5)),
    }

    def run():
        sm.job_id_var.set(job_id)
        try:
            sm.set_status(job_id, "running", "Generating descriptions…")

            slots_df: pd.DataFrame = job["slots_df"]
            slot_map_df = job.get("slot_map_df")
            if slot_map_df is None:
                slot_map_df = pd.DataFrame()

            def cb(msg, cur, total):
                _push(job_id, "progress", {
                    "step": "gpt",
                    "message": msg,
                    "current": cur,
                    "total": total,
                })

            records = gpt_mod.describe_slots(
                slots_df, slot_map_df,
                system_prompt, user_prompt,
                progress_cb=cb,
                **gpt_params,
            )

            # Write output files
            run_folder = sm.job_dir(job_id) / "output"
            paths = export_mod.write_outputs(run_folder, records, cut)

            key = f"gpt_records_{cut}"
            sm.update_job(job_id, **{key: records},
                          output_paths={**job.get("output_paths", {}), **paths},
                          final_mp4_path=None)
            sm.set_status(job_id, "idle")
            _push(job_id, "gpt_done", {
                "total": len(records),
                "ok_count": sum(1 for r in records if r.get("ok") and not r.get("skipped")),
                "skip_count": sum(1 for r in records if r.get("skipped")),
                "error_count": sum(1 for r in records if not r.get("ok")),
                "output_files": list(paths.keys()),
                "records": records,
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "gpt", "message": str(exc)})

    threading.Thread(target=run, daemon=True).start()
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
            rec["text"] = updates[s_id]
            rec["ok"] = True
            rec["skipped"] = False

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
        
    api_key = body.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return JSONResponse({"error": "OpenAI API key required"}, status_code=400)
        
    voice = body.get("voice", "alloy")
    ducking_volume = float(body.get("ducking_volume", 0.4))
    
    def run():
        sm.job_id_var.set(job_id)
        try:
            sm.set_status(job_id, "running", "Generating TTS audio...")
            
            job_path = sm.job_dir(job_id)
            tts_dir = job_path / "tts"
            
            def cb_tts(msg, cur, total):
                _push(job_id, "progress", {"step": "tts", "message": msg, "current": cur, "total": total})
                
            tts_files = tts_mod.generate_tts(
                records=records,
                api_key=api_key,
                output_dir=tts_dir,
                voice=voice,
                progress_cb=cb_tts
            )
            
            _push(job_id, "progress", {"step": "tts", "message": "Mixing audio into MP4...", "current": 0, "total": 100})
            
            def cb_export(msg, cur, total):
                 _push(job_id, "progress", {"step": "tts", "message": msg, "current": cur, "total": total})
                 
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
            _push(job_id, "tts_done", {
                "tts_files_count": len(tts_files),
                "final_mp4": final_mp4_path
            })
            
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "tts", "message": str(exc)})
            
    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


# ── SSE Progress Stream ────────────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}/stream")
async def status_stream(job_id: str, request: Request):
    async def generate():
        q = _get_queue(job_id)
        # Send current job state immediately
        job = sm.get_job(job_id)
        if job:
            yield f"data: {json.dumps({'event': 'connected', 'status': job['status']})}\n\n"
        
        loop = asyncio.get_running_loop()
        while True:
            if await request.is_disconnected():
                break
            try:
                # Use run_in_executor to avoid blocking the event loop
                item = await loop.run_in_executor(None, q.get, True, 1.0)
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
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
        
        # Timeline data
        "pauses": make_serializable(job.get("pauses_df")),
        "slots": make_serializable(job.get("slots_df")),
        "scenes": make_serializable(job.get("scenes_df")),
        "slot_map": job.get("slot_map_df").to_dict(orient="records") if (job.get("slot_map_df") is not None and not job.get("slot_map_df").empty) else None,
        "video_path": video_path,
        "video_cache_key": video_cache_key,
        
        "transcript_meta": job.get("transcript_meta"),
        "segments": segments,
        "quality_report": job.get("quality_report"),
        "output_paths": {**{k: Path(v).name for k, v in (job.get("output_paths") or {}).items()}, 
                         **({"log": sm.JOB_LOG_FILENAME} if Path(sm.job_dir(job_id) / sm.JOB_LOG_FILENAME).exists() else {})},
        "gpt_records": job.get("gpt_records_broadcast", job.get("gpt_records_directors")),
        "links": build_hateoas_links(job, str(request.base_url)),
        "latest_progress": _LATEST_PROGRESS_BY_JOB.get(job_id) if job.get("status") == "running" else None
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


# Mount static files last so it doesn't intercept API routes
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


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
