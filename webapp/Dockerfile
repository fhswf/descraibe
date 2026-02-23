# ── Audiodeskription Webapp Docker Image ──────────────────────────────────────
#
# Single-image build: the Flask backend serves the static frontend directly.
# The frontend is plain HTML/CSS/JS (no build step needed).
#
# Build:
#   docker build -t audiodeskription-webapp .
#
# Run (CPU-only, pass your OpenAI API key at runtime):
#   docker run -p 5000:5000 -e OPENAI_API_KEY=sk-... audiodeskription-webapp
#
# For GPU support, use the CUDA base image variant instead (see comment below).

# ── Base image ─────────────────────────────────────────────────────────────────
# CPU variant (default – no CUDA runtime required):
FROM python:3.11-slim

# GPU variant: uncomment the line below and comment-out the CPU line above.
# The torch index-url in pyproject.toml must also be set to the matching CUDA wheel.
# FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# ── System dependencies ────────────────────────────────────────────────────────
# ffmpeg   – required by moviepy / scenedetect
# libsm6 / libxext6 / libglib2.0-0 – required by opencv-python-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Install uv ─────────────────────────────────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── App source ─────────────────────────────────────────────────────────────────
WORKDIR /app

# Copy dependency manifest first so Docker can cache the install layer
COPY webapp/pyproject.toml .

# Install Python dependencies (no dev extras, compile bytecode)
RUN uv pip install --system --no-cache .

# Copy the rest of the webapp
COPY webapp/backend ./backend
COPY webapp/frontend ./frontend

# ── Runtime config ─────────────────────────────────────────────────────────────
# All values can be overridden at runtime:
#   docker run -e OPENAI_API_KEY=sk-... -e MAX_UPLOAD_MB=4096 ...

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # --- Required (no default) -----------------------------------
    # OpenAI API key used for GPT scene-description calls.
    # Must be set at runtime; the app will reject /api/run/gpt if absent.
    OPENAI_API_KEY="" \
    # --- Job storage ---------------------------------------------
    # Directory where per-job temp files (video, audio, frames) are written.
    # Mount a persistent volume here to survive container restarts.
    AD_JOBS_DIR=/app/jobs \
    # --- Upload limits -------------------------------------------
    # Maximum video upload size in megabytes (Flask MAX_CONTENT_LENGTH).
    MAX_UPLOAD_MB=2048 \
    # --- Uvicorn tuning -----------------------------------------
    # Keep workers=1: the pipeline holds large in-memory state per job.
    UVICORN_WORKERS=1 \
    # Keep-alive timeout (seconds). Uvicorn does not have a hard request timeout like Gunicorn.
    UVICORN_TIMEOUT=600

VOLUME ["/app/jobs"]

EXPOSE 5000

CMD ["sh", "-c", \
    "uvicorn backend.app:app \
    --host 0.0.0.0 \
    --port 5000 \
    --workers $UVICORN_WORKERS \
    --timeout-keep-alive $UVICORN_TIMEOUT"]
