# ── Audiodeskription Webapp Docker Image ──────────────────────────────────────
#
# Single-image build: the FastAPI backend serves the built frontend directly.
#
# Build:
#   docker build -t audiodeskription-webapp webapp/
#
# Run (GPU image, pass your OpenAI API key at runtime):
#   docker run -p 5000:5000 -e OPENAI_API_KEY=sk-... audiodeskription-webapp
#
# The runtime image already includes PyTorch, CUDA and cuDNN. The Kubernetes
# GPU Operator still provides the host driver, device plugin and runtime hooks.

# ── Frontend Build ─────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY webapp/frontend/package*.json ./
RUN npm install
COPY webapp/frontend/ ./
RUN npm run build

# ── Base image ─────────────────────────────────────────────────────────────────
# GPU-first runtime: PyTorch, CUDA 12.8 and cuDNN 9 are preinstalled in
# /opt/conda, which avoids re-downloading the large torch/nvidia wheels in CI.
FROM pytorch/pytorch:2.10.0-cuda12.8-cudnn9-runtime

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

# ── Environment variables ──────────────────────────────────────────────────────
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_SYSTEM_PYTHON=1 \
    PATH="/opt/conda/bin:$PATH"

# ── App source ─────────────────────────────────────────────────────────────────
WORKDIR /app

# Copy dependency manifest and lockfile first so Docker can cache the install layer
COPY webapp/pyproject.toml webapp/uv.lock ./

# Install Python dependencies without bursting cache on every source code change.
# torch/torchaudio and their CUDA libraries come from the PyTorch base image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --no-dev --frozen --no-emit-project \
    --prune torch \
    --prune torchaudio \
    --output-file /tmp/requirements-runtime.txt \
    && uv pip install --requirements /tmp/requirements-runtime.txt \
    && rm /tmp/requirements-runtime.txt

# Copy the rest of the webapp
COPY webapp/backend ./backend
# Copy the built frontend from the builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Install the actual project (nearly instant since deps are already there)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps . \
    && python -c "import torch, torchaudio; assert torch.version.cuda, 'PyTorch CUDA runtime is missing'; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'torchaudio', torchaudio.__version__)"

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
