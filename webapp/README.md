# Audiodeskription Webapp

A Flask-based web application that runs the Audiodeskription pipeline: VAD pause detection, Whisper transcription, scene image extraction, and GPT-powered audio description generation.

## Quick Start (Docker)

```bash
docker build -f webapp/Dockerfile -t audiodeskription-webapp .

docker run \
  -p 5000:5000 \
  -e OPENAI_API_KEY=sk-... \
  -v /my/local/jobs:/app/jobs \
  audiodeskription-webapp
```

Then open [http://localhost:5000](http://localhost:5000).

---

## Kubernetes / ArgoCD Deployment

All Kubernetes manifests live in [`k8s/`](../k8s/) and are managed by Kustomize.
Point an ArgoCD **Application** at that directory — ArgoCD will create every resource
(Namespace, ConfigMaps, Secret, PVC, Deployment, Service, Ingress) automatically.

### ArgoCD Application manifest

Save this as `k8s/argocd-app.yaml` (already included) and apply it **once** into the
`argocd` namespace. It is **not** part of the Kustomize root so ArgoCD doesn't try to
manage itself.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: audiodeskription
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/YOUR_ORG/Audiodeskriptionen_SS25   # ← replace
    targetRevision: main
    path: k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: audiodeskription
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - ServerSideApply=true
```

```bash
# Apply once – ArgoCD takes it from there
kubectl apply -k k8s/argocd/root -n argocd
```

### Pre-flight checklist

> [!IMPORTANT]
> Complete these steps **before** applying the Application manifest:
>
> 1. **Image** — set your real image reference in `k8s/base/deployment.yaml` and the relevant `k8s/overlays/*/kustomization.yaml`:
>    `ghcr.io/YOUR_ORG/audiodeskription-webapp:latest`
> 2. **Domain** — replace `audiodeskription.example.com` in `k8s/base/ingress.yaml`.
> 3. **OpenAI API key** — inject the real key via External Secrets Operator or ArgoCD Vault Plugin
>    instead of committing it in `k8s/secret.yaml`.
> 4. **Storage class** — update `storageClassName` in `k8s/base/pvc.yaml` to match your cluster
>    (e.g. `gp2`, `longhorn`, `ceph-rbd`).

### What ArgoCD deploys (`k8s/overlays/staging`)

The recommended setup uses the App of Apps pattern:

| Path | Purpose |
|------|---------|
| `k8s/argocd/root` | Root ArgoCD Application. Points to `k8s/argocd/apps`. |
| `k8s/argocd/apps` | Child ArgoCD Applications for staging and release. |
| `k8s/overlays/staging` | Staging deployment in `audiodeskription-staging`, pinned by CI to a `sha-*` image tag. |
| `k8s/overlays/release` | Release deployment in `audiodeskription`, pinned by release-please to a version tag. |

If you manage the root ArgoCD Application outside this repository, point it to
`webapp/k8s/argocd/apps` and deploy it into the `argocd` namespace. The child
Applications then deploy staging and release into their own target namespaces.

| File | Resource | Purpose |
|------|----------|---------|
| `base/namespace.yaml` | Namespace | `audiodeskription` |
| `base/configmap-gpt.yaml` | ConfigMap `gpt-config` | GPT model presets → `/app/config/gpt_config.yaml` |
| `base/configmap-prompts.yaml` | ConfigMap `prompts-config` | Prompt `.txt` files → `/app/config/prompts/` |
| `overlays/*/openai-sealedsecret.yaml` | SealedSecret | OpenAI API key for staging/release |
| `base/pvc.yaml` | PVC `audiodeskription-jobs` | 50 Gi scratch space for `/app/jobs` |
| `base/deployment.yaml` | Deployment | Single-replica Flask/Gunicorn app |
| `base/service.yaml` | Service | ClusterIP, port 80 → 5000 |
| `base/ingress.yaml` | Ingress | Nginx, 4 GB body limit, cert-manager TLS |

### Sealed OpenAI secrets

The app reads `OPENAI_API_KEY` from a Kubernetes Secret. The overlays include
Bitnami SealedSecret placeholders that must be replaced with values encrypted
for your cluster:

```bash
# Staging: creates Secret openai-secret-staging in audiodeskription-staging
printf '%s' 'sk-...' \
  | kubeseal --raw \
      --name openai-secret-staging \
      --namespace audiodeskription-staging

# Release/prod: creates Secret openai-secret in audiodeskription
printf '%s' 'sk-...' \
  | kubeseal --raw \
      --name openai-secret \
      --namespace audiodeskription
```

Paste the resulting ciphertext into:

- `k8s/overlays/staging/openai-sealedsecret.yaml`
- `k8s/overlays/release/openai-sealedsecret.yaml`

Keep the names and namespaces unchanged; SealedSecrets are namespace/name bound
unless you deliberately use a different sealing scope.

### Updating prompts or GPT config

Edit the relevant ConfigMap file and push to `main` — ArgoCD syncs within ≈3 minutes and rolls the pod.

```bash
# Example: update the AD rules
vim k8s/base/configmap-prompts.yaml
git commit -am "chore: update AD rules"
git push
```

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | *(empty)* | **Yes** | OpenAI API key for GPT scene-description calls. The app will reject `/api/run/gpt` if not set. Can also be supplied per-request in the JSON body as `api_key`. |
| `AD_JOBS_DIR` | `/app/jobs` | No | Directory where per-job temp files (uploaded video, extracted audio, frames) are written. **Mount a Docker volume here** to persist data across container restarts. |
| `MAX_UPLOAD_MB` | `2048` | No | Maximum video upload size in megabytes. Maps to Flask's `MAX_CONTENT_LENGTH`. Increase for very large video files. |
| `GUNICORN_WORKERS` | `1` | No | Number of gunicorn worker processes. **Keep at 1** — the pipeline stores large in-memory state (DataFrames, image lists) per job; multiple workers do not share this state. |
| `GUNICORN_THREADS` | `4` | No | Threads per worker. Increase to handle more concurrent SSE progress streams. |
| `GUNICORN_TIMEOUT` | `600` | No | Request timeout in seconds. Pipeline steps (Whisper transcription, GPT calls) can take several minutes. |
| `GPT_CONFIG_PATH` | `/app/config/gpt_config.yaml` | No | Path to the GPT preset YAML (see section below). |
| `GPT_PROMPTS_DIR` | *(unset)* | No | Directory containing the four prompt `.txt` files. When set, `/api/run/gpt` reads and assembles prompts automatically if none are supplied in the request body (see *GPT Prompt Files* section below). |

> [!IMPORTANT]
> `OPENAI_API_KEY` is the only **required** environment variable. The container will start without it, but calls to `/api/run/gpt` will return a `400` error until it is provided.

---

## GPT Config YAML

The app expects a YAML file that defines **presets** – named configurations for the GPT description step. The file path is set via the `GPT_CONFIG_PATH` env var (default: `/app/config/gpt_config.yaml`).

### File format

```yaml
presets:
  <preset-name>:
    model: gpt-4o              # OpenAI model name
    temperature: 0.2           # 0.0 – 2.0
    max_output_tokens: 1024    # Max tokens in the completion
    detail: high               # Image detail level: "low" | "high" | "auto"
```

All keys inside a preset are optional — missing values fall back to the defaults used by `/api/run/gpt`.

### Included presets (K8s ConfigMap default)

| Preset | Model | Temp | Max tokens | Detail |
|--------|-------|------|-----------|--------|
| `standard` | `gpt-4o` | 0.2 | 1024 | high |
| `fast` | `gpt-4o-mini` | 0.3 | 512 | low |
| `quality` | `gpt-4o` | 0.1 | 2048 | high |

### Local Docker usage

Mount your own preset file into the container:

```bash
docker run \
  -p 5000:5000 \
  -e OPENAI_API_KEY=sk-... \
  -e GPT_CONFIG_PATH=/app/config/gpt_config.yaml \
  -v /path/to/my/gpt_config.yaml:/app/config/gpt_config.yaml:ro \
  audiodeskription-webapp
```

### Kubernetes / ArgoCD

In K8s, the file is stored as the `gpt-config` ConfigMap and mounted read-only at `/app/config/`. To add or update presets, edit [`k8s/base/configmap-gpt.yaml`](k8s/base/configmap-gpt.yaml) and push — ArgoCD will sync the change and restart the pod automatically.

---

## GPT Prompt Files

The notebook (step **05a**) loads the GPT prompts from **plain `.txt` files** rather than hard-coding them. The webapp's `/api/run/gpt` endpoint accepts the same content as request-body strings. Understanding the file structure helps you author prompts that match the notebook's behaviour.

### The four prompt files

| File | Required | Role |
|------|----------|------|
| `system_instruction.txt` | **Yes** | Model role & ground rules (e.g. *"You are a professional audio describer…"*). |
| `ad_rules.txt` | **Yes** | Domain-specific AD style rules (e.g. Naturdoku conventions, sentence length, forbidden phrases). |
| `user_instruction.txt` | **Yes** | Task description sent as the user message: what the model should produce, tone, output format. |
| `few_shots.txt` | No | Example input/output pairs that improve stylistic consistency. |

### How they are assembled (notebook `_build_prompts_from_loaded_parts`)

The notebook concatenates the files into two final prompts:

```
SYSTEM_FINAL  =  system_instruction
              +  "\n\n# Audiodeskription – Regeln\n"  +  ad_rules
              +  "\n\n# Few-Shots / Beispiele\n"      +  few_shots   (only if provided)

USER_BASE     =  user_instruction
```

`SYSTEM_FINAL` becomes the OpenAI `system` message. `USER_BASE` is sent as the `user` message together with the slot image(s).

### Using prompt files with the webapp

Pass the assembled text directly in the POST body of `/api/run/gpt`:

```json
{
  "job_id": "<uuid>",
  "system_prompt": "<contents of SYSTEM_FINAL>",
  "user_prompt":   "<contents of USER_BASE>",
  "model": "gpt-4o",
  "temperature": 0.2,
  "max_tokens": 1024,
  "detail": "high"
}
```

> [!TIP]
> To replicate the notebook exactly, read your three text files locally and concatenate them with the separators shown above before sending the request. The frontend wizard's *"Prompts"* step does this for you.

### Auto-loading via `GPT_PROMPTS_DIR`

When the `GPT_PROMPTS_DIR` environment variable is set, the app reads the four files from
that directory at request time and assembles `SYSTEM_FINAL` / `USER_BASE` automatically.
Explicit `system_prompt` / `user_prompt` fields in the request body always take precedence.

#### Local Docker usage

```bash
mkdir -p my_prompts
# put your .txt files in my_prompts/
docker run \
  -p 5000:5000 \
  -e OPENAI_API_KEY=sk-... \
  -e GPT_PROMPTS_DIR=/app/config/prompts \
  -v $(pwd)/my_prompts:/app/config/prompts:ro \
  audiodeskription-webapp
```

#### Kubernetes / ArgoCD

The prompts are stored in [`k8s/base/configmap-prompts.yaml`](k8s/base/configmap-prompts.yaml) and
mounted read-only at `/app/config/prompts/`. Edit the file and push — ArgoCD will sync and
restart the pod. The `GPT_PROMPTS_DIR=/app/config/prompts` env var is already set in
[`k8s/base/deployment.yaml`](k8s/base/deployment.yaml).

---

## Development (without Docker)

### Prerequisites
- Python ≥ 3.11
- [`uv`](https://docs.astral.sh/uv/) (`pip install uv` or `curl -Lsf https://astral.sh/uv/install.sh | sh`)
- `ffmpeg` on `$PATH` (required by moviepy / scenedetect)

### Install & Run

```bash
cd webapp
uv sync                          # installs all deps from uv.lock

export OPENAI_API_KEY=sk-...
uv run python -m backend.app     # or: flask --app backend.app run --debug
```

The dev server starts on [http://localhost:5000](http://localhost:5000).

---

## Job Data & Persistence

Each uploaded video creates a **job directory** under `$AD_JOBS_DIR/<uuid>/` containing:

```
<uuid>/
├── <original-filename>.mp4   # uploaded video
├── audio.wav                 # extracted 16 kHz mono audio
├── frames/                   # scene mid-frames (JPEGs)
├── gapfill/                  # extra frames extracted for AD slots
└── output/
    ├── ad_broadcast.srt
    ├── ad_broadcast.json
    ├── ad_directors.srt
    └── ad_directors.json
```

> [!WARNING]
> Job state is stored **in memory** and is lost on container restart. Only the files in `$AD_JOBS_DIR` survive. Re-uploading and re-running the pipeline is required after a restart.

---

## GPU Support

The image is GPU-first. It is based on the official PyTorch runtime image with
CUDA 12.8 and cuDNN 9 preinstalled, so the Docker build does not download the
large `torch`/CUDA Python wheels again. The Kubernetes GPU Operator must still
provide the node driver, device plugin and NVIDIA container runtime hooks.

Run locally with:

```bash
docker run --gpus all -p 5000:5000 -e OPENAI_API_KEY=sk-... audiodeskription-webapp
```

When changing the PyTorch version, keep the Docker base image tag aligned with
the `torch`/`torchaudio` versions in `uv.lock`.

---

## Running Tests

End-to-end UI tests use [Playwright](https://playwright.dev/):

```bash
cd webapp
npm install          # install Playwright
npm run test         # or: npx playwright test
```

The backend must be running on `http://localhost:5000` before executing tests.
