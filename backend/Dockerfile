# ── Audiodeskription Backend Docker Image ─────────────────────────────────────
#
# FastAPI/PyTorch backend. Static frontend is served separately by nginx.
#
# Build:
#   docker build -t audiodeskription-backend .
#
# Run (GPU image, pass your OpenAI API key at runtime):
#   docker run -p 5000:5000 -e OPENAI_API_KEY=sk-... audiodeskription-backend
#
# The runtime image already includes PyTorch, CUDA and cuDNN. The Kubernetes
# GPU Operator still provides the host driver, device plugin and runtime hooks.

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
    UV_BREAK_SYSTEM_PACKAGES=1 \
    PATH="/opt/conda/bin:$PATH"

# ── App source ─────────────────────────────────────────────────────────────────
WORKDIR /app

# Copy dependency manifest and lockfile first so Docker can cache the install layer
COPY pyproject.toml uv.lock ./

# Install Python dependencies without bursting cache on every source code change.
# torch/torchaudio and their CUDA libraries come from the PyTorch base image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --quiet --no-dev --frozen --no-emit-project \
    --prune torch \
    --prune torchaudio \
    --output-file /tmp/requirements-runtime.txt \
    && uv pip install --break-system-packages --requirements /tmp/requirements-runtime.txt \
    && rm /tmp/requirements-runtime.txt

# Copy the backend source
COPY backend ./backend

# Install the actual project (nearly instant since deps are already there)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --break-system-packages --no-deps . \
    && python -c "import torch, torchaudio; assert torch.version.cuda, 'PyTorch CUDA runtime is missing'; print('torch', torch.__version__, 'cuda', torch.version.cuda, 'torchaudio', torchaudio.__version__)"

# ── Runtime config ─────────────────────────────────────────────────────────────
# All values can be overridden at runtime:
#   docker run -e OPENAI_API_KEY=sk-... -e MAX_UPLOAD_MB=4096 ...
#
# NOTE: OPENAI_API_KEY is intentionally NOT set here. It must be injected at
# runtime only (via k8s Secret / envFrom, or -e at docker run). Setting it in
# ENV would persist the value (or an empty placeholder) in the image metadata.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # --- Job storage ---------------------------------------------
    # Directory where per-job temp files (video, audio, frames) are written.
    # Mount a persistent volume here to survive container restarts.
    AD_JOBS_DIR=/app/jobs \
    # --- Upload limits -------------------------------------------
    # Maximum video upload size in megabytes.
    MAX_UPLOAD_MB=2048 \
    # --- Uvicorn tuning -----------------------------------------
    # Keep workers=1: the pipeline holds large in-memory state per job.
    UVICORN_WORKERS=1 \
    # Keep-alive timeout (seconds).
    UVICORN_TIMEOUT=600 \
    # Graceful shutdown timeout (seconds), relevant for open SSE/video connections.
    UVICORN_GRACEFUL_TIMEOUT=30

VOLUME ["/app/jobs"]

EXPOSE 5000

CMD ["sh", "-c", \
    "uvicorn backend.app:app \
    --host 0.0.0.0 \
    --port 5000 \
    --workers $UVICORN_WORKERS \
    --timeout-keep-alive $UVICORN_TIMEOUT \
    --timeout-graceful-shutdown $UVICORN_GRACEFUL_TIMEOUT"]
