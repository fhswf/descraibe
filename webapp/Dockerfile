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
RUN uv pip install --system --no-cache . \
    && uv pip install --system --no-cache gunicorn

# Copy the rest of the webapp
COPY webapp/backend ./backend
COPY webapp/frontend ./frontend

# ── Runtime config ─────────────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Job data is written here; mount a volume to persist across restarts.
    JOBS_DIR=/app/jobs

VOLUME ["/app/jobs"]

EXPOSE 5000

# Use gunicorn for production; Flask dev server for quick debugging.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", \
     "--timeout", "600", "backend.app:app"]
