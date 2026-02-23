"""app.py – Flask web application for the Audiodeskription pipeline."""
from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path
from typing import Any, Dict

import pandas as pd
from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

import sys
sys.path.insert(0, str(Path(__file__).parent))

import session_manager as sm

# Pipeline modules are imported lazily inside route handlers to avoid
# forcing GPU/ML dependencies to be installed just to start the server.

# ── App setup ──────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)

# Limit upload size (default 2 GB – videos can be large).
_max_mb = int(os.environ.get("MAX_UPLOAD_MB", 2048))
app.config["MAX_CONTENT_LENGTH"] = _max_mb * 1024 * 1024

# SSE progress queues per job
_SSE_QUEUES: Dict[str, queue.Queue] = {}
_SSE_LOCK = threading.Lock()


def _get_queue(job_id: str) -> queue.Queue:
    with _SSE_LOCK:
        if job_id not in _SSE_QUEUES:
            _SSE_QUEUES[job_id] = queue.Queue()
        return _SSE_QUEUES[job_id]


def _push(job_id: str, event: str, data: Any) -> None:
    q = _get_queue(job_id)
    q.put({"event": event, "data": data})


# ── Prompt auto-loader (GPT_PROMPTS_DIR) ──────────────────────────────────────
# Mirrors the notebook's _build_prompts_from_loaded_parts() logic (step 05a).
# Returns (system_final, user_base) assembled from the four .txt files.

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


# ── Health check (K8s liveness / readiness probe) ─────────────────────────────

@app.route("/api/ping")
def ping():
    return jsonify({"status": "ok"})


# ── Frontend ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


# ── Upload ─────────────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload():
    # Only initialize the upload session
    if "filename" not in request.form:
        return jsonify({"error": "No filename provided"}), 400
    if "total_size" not in request.form:
        return jsonify({"error": "No total_size provided"}), 400
    
    # Check if a user passes an existing job ID they want to resume/re-upload to
    # Usually the frontend will just ask POST /api/upload to create a new job
    job_id = request.form.get("job_id")
    if not job_id:
        job_id = sm.create_job()
    else:
        # Check if job exists
        job = sm.get_job(job_id)
        if not job:
            job_id = sm.create_job()

    return jsonify({"job_id": job_id})

@app.route("/api/upload_status", methods=["GET"])
def upload_status():
    job_id = request.args.get("job_id")
    filename = request.args.get("filename")
    
    if not job_id or not filename:
        return jsonify({"error": "Missing job_id or filename"}), 400

    job_path = sm.job_dir(job_id)
    if not job_path:
        return jsonify({"error": "Unknown job"}), 404

    part_file = job_path / f"{filename}.part"
    if part_file.exists():
        return jsonify({"uploaded_bytes": part_file.stat().st_size})
    
    return jsonify({"uploaded_bytes": 0})

@app.route("/api/upload_chunk", methods=["POST"])
def upload_chunk():
    from pipeline import video_utils
    
    job_id = request.form.get("job_id")
    filename = request.form.get("filename")
    chunk_index = int(request.form.get("chunkIndex", 0))
    total_chunks = int(request.form.get("totalChunks", 1))
    
    if not job_id or not filename:
        return jsonify({"error": "Missing job_id or filename"}), 400
    
    file_chunk = request.files.get("chunk")
    if not file_chunk:
        return jsonify({"error": "No chunk data provided"}), 400

    job_path = sm.job_dir(job_id)
    if not job_path:
         return jsonify({"error": "Unknown job"}), 404

    part_file = job_path / f"{filename}.part"
    video_path = job_path / filename

    # Append the chunk
    with open(part_file, "ab") as f:
        # If it's the first chunk, ensure we start fresh (in case of a weird retry)
        # But wait, we want to resume! The UI will seek to the right byte. 
        # So we just append. The frontend is responsible for sending the correct chunk.
        f.write(file_chunk.read())

    # If it's the final chunk
    if chunk_index == total_chunks - 1:
        # Rename part to final
        part_file.rename(video_path)
        
        try:
            stats = video_utils.get_video_stats(str(video_path))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        sm.update_job(job_id, video_path=str(video_path), video_stats=stats)
        return jsonify({"job_id": job_id, "stats": stats, "complete": True})

    return jsonify({"success": True, "complete": False})


# ── VAD Pauses ─────────────────────────────────────────────────────────────────

@app.route("/api/run/vad", methods=["POST"])
def run_vad():
    from pipeline import vad_pauses
    body = request.json or {}
    job_id = body.get("job_id")
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    if not job.get("video_path"):
        return jsonify({"error": "No video uploaded"}), 400

    params = {
        "threshold": float(body.get("threshold", 0.5)),
        "min_speech_duration_ms": int(body.get("min_speech_duration_ms", 1500)),
        "min_silence_duration_ms": int(body.get("min_silence_duration_ms", 400)),
        "speech_pad_ms": int(body.get("speech_pad_ms", 50)),
        "min_pause_duration_s": float(body.get("min_pause_duration_s", 0.3)),
    }

    def run():
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
                          pauses_srt=srt_str)
            sm.set_status(job_id, "idle")
            _push(job_id, "vad_done", {
                "pauses_count": len(pauses_df),
                "pauses": pauses_df.to_dict(orient="records"),
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "vad", "message": str(exc)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


# ── Transcription ──────────────────────────────────────────────────────────────

@app.route("/api/run/transcribe", methods=["POST"])
def run_transcribe():
    from pipeline import transcription as trans_mod
    body = request.json or {}
    job_id = body.get("job_id")
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404

    # Optional: upload existing SRT handled by /api/upload_srt
    params = {
        "model_size": body.get("model_size", "small"),
        "language": body.get("language", "de"),
        "use_fw_vad": bool(body.get("use_fw_vad", True)),
        "vad_min_silence_ms": int(body.get("vad_min_silence_ms", 350)),
        "word_timestamps": bool(body.get("word_timestamps", True)),
        # Silero-gate (P1-A): double-VAD pass to prevent timestamp bleed
        "use_silero_gate": bool(body.get("use_silero_gate", True)),
        "silero_threshold": float(body.get("silero_threshold", 0.70)),
        "silero_min_speech_s": float(body.get("silero_min_speech_s", 0.45)),
        "silero_min_silence_s": float(body.get("silero_min_silence_s", 0.55)),
        "clamp_to_vad": bool(body.get("clamp_to_vad", True)),
    }

    # We need audio – extract if needed
    def run():
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
                          transcript_meta=meta)
            sm.set_status(job_id, "idle")
            _push(job_id, "transcribe_done", {
                "segment_count": len(seg_df),
                "metadata": meta,
                "segments": seg_df.to_dict(orient="records"),
            })
        except Exception as exc:
            sm.set_status(job_id, "error", str(exc))
            _push(job_id, "error", {"step": "transcribe", "message": str(exc)})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


# ── Upload existing SRT ────────────────────────────────────────────────────────

@app.route("/api/upload_srt", methods=["POST"])
def upload_srt():
    from pipeline import transcription as trans_mod
    job_id = request.form.get("job_id")
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404

    f = request.files.get("srt")
    if not f:
        return jsonify({"error": "No SRT file"}), 400

    srt_path = sm.job_dir(job_id) / "uploaded_transcript.srt"
    f.save(str(srt_path))

    try:
        seg_df = trans_mod.load_srt_as_df(str(srt_path))
        sm.update_job(job_id, segments_df=seg_df,
                      transcript_srt=srt_path.read_text(encoding="utf-8"),
                      transcript_meta={"source": "uploaded"})
        return jsonify({"segment_count": len(seg_df),
                        "segments": seg_df.to_dict(orient="records")})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── AD Slots ───────────────────────────────────────────────────────────────────

@app.route("/api/run/slots", methods=["POST"])
def run_slots():
    from pipeline import ad_slots as slots_mod
    body = request.json or {}
    job_id = body.get("job_id")
    job = sm.get_job(job_id)
    if not job or job.get("pauses_df") is None:
        return jsonify({"error": "Pauses not available. Run VAD first."}), 400

    def run():
        try:
            sm.set_status(job_id, "running", "Generating AD slots…")
            _push(job_id, "progress", {"step": "slots", "message": "Converting pauses to slots…"})

            pauses_df: pd.DataFrame = job["pauses_df"]
            speech_df: pd.DataFrame = job.get("segments_df")  # whisper transcript

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
                speech_df if speech_df is not None else pd.DataFrame(columns=["start_s","end_s"]),
                slots_df,
            )

            sm.update_job(job_id, slots_df=slots_df, quality_report=qr)
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
    return jsonify({"status": "started"})


# ── Image Extraction ───────────────────────────────────────────────────────────

@app.route("/api/run/images", methods=["POST"])
def run_images():
    from pipeline import image_extraction as img_mod
    body = request.json or {}
    job_id = body.get("job_id")
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    if job.get("slots_df") is None:
        return jsonify({"error": "Slots not available. Run slot generation first."}), 400

    def run():
        try:
            sm.set_status(job_id, "running", "Extracting scene images…")
            _push(job_id, "progress", {"step": "images", "message": "Starting scene detection…"})

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

            _push(job_id, "progress", {"step": "images", "message": "Detecting scenes…"})
            scene_images, scene_timestamps = extractor.process_video(
                job["video_path"],
                window_start_s=float(body.get("window_start_s", 0.0)),
                window_end_s=float(body.get("window_end_s", 0)) or None,
            )

            _push(job_id, "progress", {"step": "images", "message": "Gapfill for AD slots…"})
            slots_df: pd.DataFrame = job["slots_df"]

            all_images, slot_map_df = img_mod.gapfill_images_for_ad_slots(
                video_path=job["video_path"],
                ad_slots_df=slots_df,
                existing_images=scene_images,
                output_dir=gap_dir,
                blur_threshold=float(body.get("blur_threshold", 80.0)),
            )

            sm.update_job(job_id,
                          scene_images=all_images,
                          slot_map_df=slot_map_df)
            sm.set_status(job_id, "idle")
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
    return jsonify({"status": "started"})


# ── GPT Description ────────────────────────────────────────────────────────────

@app.route("/api/run/gpt", methods=["POST"])
def run_gpt():
    from pipeline import gpt_description as gpt_mod, export as export_mod
    body = request.json or {}
    job_id = body.get("job_id")
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    if job.get("slots_df") is None:
        return jsonify({"error": "Slots not available"}), 400

    api_key = body.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return jsonify({"error": "OpenAI API key required"}), 400

    system_prompt = body.get("system_prompt", "")
    user_prompt = body.get("user_prompt", "")

    # If the request body doesn't supply prompts, try loading from GPT_PROMPTS_DIR.
    # This allows K8s ConfigMap-mounted files to serve as the default prompt source.
    if not system_prompt or not user_prompt:
        prompts_dir = os.environ.get("GPT_PROMPTS_DIR", "")
        if prompts_dir:
            loaded = _load_prompts_from_dir(prompts_dir)
            if loaded:
                if not system_prompt:
                    system_prompt = loaded[0]
                if not user_prompt:
                    user_prompt = loaded[1]

    cut = body.get("cut", "broadcast")

    gpt_params = {
        "api_key": api_key,
        "model": body.get("model", "gpt-4o"),
        "temperature": float(body.get("temperature", 0.2)),
        "max_tokens": int(body.get("max_tokens", 1024)),
        "detail": body.get("detail", "low"),
        "cut": cut,
        "syllables_per_second": float(body.get("syllables_per_second", 12.0)),
        "syl_safety_factor": float(body.get("syl_safety_factor", 0.85)),
        "max_rewrite_attempts": int(body.get("max_rewrite_attempts", 2)),
        "min_slot_s": float(body.get("min_slot_s", 0.5)),
    }

    def run():
        try:
            sm.set_status(job_id, "running", "Generating descriptions…")

            slots_df: pd.DataFrame = job["slots_df"]
            slot_map_df: pd.DataFrame = job.get("slot_map_df") or pd.DataFrame()

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
                          output_paths={**job.get("output_paths", {}), **paths})
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
    return jsonify({"status": "started"})


# ── SSE Progress Stream ────────────────────────────────────────────────────────

@app.route("/api/status/<job_id>")
def status_stream(job_id: str):
    def generate():
        q = _get_queue(job_id)
        # Send current job state immediately
        job = sm.get_job(job_id)
        if job:
            yield f"data: {json.dumps({'event': 'connected', 'status': job['status']})}\n\n"
        while True:
            try:
                item = q.get(timeout=30)
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield "data: {\"event\":\"ping\"}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Results ────────────────────────────────────────────────────────────────────

@app.route("/api/results/<job_id>")
def results(job_id: str):
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404

    # Return serialisable subset
    out = {
        "job_id": job_id,
        "status": job.get("status"),
        "video_stats": job.get("video_stats"),
        "pauses_count": len(job["pauses_df"]) if job.get("pauses_df") is not None else 0,
        "slots_count": len(job["slots_df"]) if job.get("slots_df") is not None else 0,
        "images_count": len(job["scene_images"]) if job.get("scene_images") else 0,
        "transcript_meta": job.get("transcript_meta"),
        "quality_report": job.get("quality_report"),
        "output_paths": {k: Path(v).name for k, v in (job.get("output_paths") or {}).items()},
    }
    return jsonify(out)


# ── Download ───────────────────────────────────────────────────────────────────

@app.route("/api/download/<job_id>/<file_key>")
def download(job_id: str, file_key: str):
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404

    paths = job.get("output_paths") or {}
    file_path = paths.get(file_key)
    if not file_path or not Path(file_path).exists():
        return jsonify({"error": "File not found"}), 404

    return send_file(file_path, as_attachment=True)


# ── Image Preview ──────────────────────────────────────────────────────────────

@app.route("/api/preview/<job_id>/image/<path:img_name>")
def preview_image(job_id: str, img_name: str):
    job = sm.get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404

    job_path = sm.job_dir(job_id)
    # Restrict to frames / gapfill subdirs
    for subdir in ["frames", "gapfill"]:
        candidate = job_path / subdir / img_name
        if candidate.exists():
            return send_file(str(candidate), mimetype="image/jpeg")

    return jsonify({"error": "Image not found"}), 404


# ── Run Server ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
