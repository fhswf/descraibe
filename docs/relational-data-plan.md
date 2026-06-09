# Relational Data Handling Plan (PostgreSQL + CNPG)

## Goals
- Make user and job metadata durable across restarts and replicas.
- Keep large binaries (video/audio/frames) in file/object storage, reference them from DB.
- Support user-managed AD presets as first-class records.
- Prepare for multi-worker/multi-replica backend operation.

## Data Placement

### Move to PostgreSQL
- `app_users`: authenticated users (`iss`, `sub`, profile claims).
- `user_configs`: saved jobs, metadata, and UI pipeline settings.
- `ad_presets`: user-managed reusable presets per AD job type.
- `jobs`: lifecycle status, progress snapshot, config snapshot.
- `job_steps`: per-step execution state and errors.
- `job_artifacts`: references to generated files (URI/path/checksum/size).
- `job_slot_texts`: editable text by slot.
- `job_events`: event history for replay/audit.

### Keep on Volume/Object Storage
- Uploaded source videos.
- Extracted audio.
- Extracted frame images.
- Rendered output media files.

## Rollout Phases

1. Infrastructure
- Deploy CNPG `Cluster` and `Pooler` in Kubernetes.
- Manage CNPG bootstrap credentials via Bitnami SealedSecrets (no plain Secret manifests in git).
- Wire backend `AD_DATABASE_URL` from CNPG app secret.

2. Schema & migrations
- Apply SQL migrations (`backend/db/migrations/*.sql`) via `backend.db.migrate`.
- Add indexes/constraints for uniqueness and integrity.

3. Application integration
- Use datastore abstraction for `/api/user/config`.
- Add CRUD endpoints for `/api/user/presets`.
- Keep file fallback if DB is unavailable (graceful degradation).

4. Job metadata migration
- Add dual-write for selected job metadata.
- Backfill from existing `job.json` sidecars.

5. Event durability
- Persist progress/events to `job_events`.
- Optionally introduce Redis for pub/sub fanout and keep DB as durable sink.

6. Cleanup and hardening
- Retention policies for old jobs/events.
- Backup policy for CNPG.
- Alerting and dashboards for DB health and slow queries.

## Presets Model
- Presets are user-owned.
- Each preset has:
  - `id`
  - `name`
  - `job_type` (e.g. `broadcast`, `directors_cut`, `kids`, `news`)
  - `description`
  - `settings` (JSON object containing step parameters)
  - `is_default` (at most one default per user + `job_type`)

## Operational Notes
- Use CNPG-generated application secret (`<cluster>-app`) to provide `uri` to backend.
- Run migrations as part of deployment pipeline before backend rollout.
- Prefer transaction pooler endpoint for API workloads.
