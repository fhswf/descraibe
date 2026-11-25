# Person Workflow Worker-Pool Plan

## Goal

Reduce wall-clock time in person tracking, identity embedding, clustering, and attribute extraction by running independent work concurrently. Keep outputs deterministic, bound CPU/GPU and memory use, preserve the existing review and revision guarantees, and show useful progress after refreshes and SSE reconnects.

This is an in-process worker-pool design for the current single-backend-worker deployment. A durable distributed queue is a later infrastructure step; `docs/relational-data-plan.md` already identifies persisted job steps/events and a broker as the path to multi-replica execution.

## Current flow and constraints

- `backend/app.py` starts one daemon thread per stage with `_start_worker`. Person stages are protected by `session_manager.begin_person_stage`, which reserves the job and prevents review edits while outputs are being built.
- `tracking_stage.run_tracking` decodes the full video sequentially. It applies scene cuts, resets ByteTrack at each cut, and writes one staged set of `tracks.json`, `tracking_frames.csv`, `face_observations.csv`, `person_crops.csv`, and crop files before publishing it atomically.
- Each tracking scene is independent once its frame range is known, but tracking within a scene is temporal and must remain sequential. Parallel workers will produce colliding local track IDs, face IDs, and crop paths unless the coordinator remaps them.
- `identity_stage.run_identities` selects reviewed face observations, decodes frames sequentially, aligns faces, and calls one `FaceMoERecognizer`. Embeddings are kept in memory and are not persisted. `run_clustering` creates a global track-distance matrix and applies deterministic agglomerative merges with a same-frame cannot-link rule. Identities must be clustered across scenes, not independently per scene.
- Attribute generation is independent per person, but `QwenAttributes.predict` uses a shared model and calls the process-global `transformers.set_seed`; concurrent calls to one instance are not safe without changing that behavior.
- Progress currently has only `step`, `message`, `current`, and `total`. `_push_progress` persists every update into `job.json` and emits it over the in-process event bus. The frontend displays one bar; `GlobalProgress` has no labels for tracking, identities, or attributes. SSE replay is bounded and in-memory, while the latest progress snapshot is available from the job sidecar.

## Target design

Add a `PersonWorkManager` and typed work items behind the existing stage endpoints. The manager owns stage coordination and submits bounded sub-tasks to application-lifetime pools. Keep each stage coordinator outside the sub-task pool so it can wait for child work without deadlocking a saturated pool.

Use separate capacity controls for media/CPU work and model inference. Start with conservative defaults and environment-configurable limits, for example `AD_PERSON_CPU_WORKERS` and `AD_PERSON_GPU_WORKERS`; the GPU inference limit should default to one. Apply a bounded submission queue and per-job outstanding-task limit so many large videos cannot create unbounded futures or frame buffers. Add fair scheduling across jobs after the single-job behavior is stable.

Workers return results and write only into task-specific staging locations. A stage coordinator is the sole writer of final manifests and revision files. Publish only after every required task succeeds and the existing tracking/video or assignment revision checks still pass. On failure, cancel work that has not started, wait for active workers to close their captures/models, remove that run's staging directory, and retain the last complete published result.

```text
stage endpoint
     |
     v
PersonWorkManager ---- stage coordinator ---- aggregate + validate ---- atomic publish
     |                         |
     +---- bounded CPU pool ---+---- per-scene / frame-range / per-person tasks
     +---- bounded inference lane(s) -------- model-owned inference
     |
     +---- progress aggregator --> job snapshot + throttled SSE events --> frontend
```

Keep this first version process-local. Do not persist live Python futures or model objects. Store a serializable run/progress snapshot so a reconnect can recover current status; a backend restart marks an unfinished run interrupted, consistent with current job recovery behavior.

## Work decomposition

### 1. Tracking by scene

1. Convert validated, one-based `scene_cut_frames` into deterministic inclusive frame ranges. Preserve current sampling (`tracking_interval_seconds`), cut handling on skipped frames, and frame/time semantics.
2. Submit one task per scene. Each task opens its own `VideoCapture`, creates a scene-local tracker, and processes its sampled frames in order. Never share a capture, tracker, or mutable writer between workers.
3. Write each scene's rows and crops under a unique run/scene staging directory. Use scene-local IDs and scene-qualified crop names while work is in flight.
4. After all scenes succeed, merge in scene order. Assign global track and face IDs deterministically, rewrite references and crop paths, combine rows in frame order, calculate the same aggregate statistics, then write the existing final file formats.
5. Keep the current atomic directory publication. This also provides a clean rollback if a scene fails.

GPU detector calls are the main limit on scene fan-out. Begin with one inference lane and overlap frame decoding, crop writing, and scene orchestration where safe. Increase simultaneous GPU model instances only after measuring peak memory and confirming RF-DETR/RetinaFace thread safety. If models are shared between tasks, guard inference with a model-owned lock; do not assume third-party predictors are thread-safe.

### 2. Identity embedding and clustering

1. Snapshot usable, non-excluded face observations and their tracking/assignment revisions before submitting work.
2. Partition selected observations into bounded contiguous frame ranges. Decoder/alignment tasks each own a capture and return aligned faces keyed by stable `face_id`; keep ordering independent of completion order. Avoid submitting one unbounded task or retaining whole decoded ranges in memory.
3. Feed aligned faces to a bounded FaceMoE inference lane. Prefer batching inference on one loaded model over loading a full model per face or per task. If multiple inference lanes are later enabled, give each lane an explicitly owned model instance and include its memory in the worker budget.
4. Keep embeddings in RAM only. Aggregate results by face ID, update `face_observations.csv` once in the coordinator, and preserve current handling of alignment/embedding failures and rejected same-frame observations.
5. Keep identity clustering global. Parallelize independent upper-triangle track-pair similarity calculations when benchmarks show value; retain a deterministic serial agglomerative merge phase initially because each merge changes the next candidate set and tie handling affects labels. Preserve the hard same-frame cannot-link rule and stable person IDs.
6. Before publishing `persons.json`, recheck the tracking revision and video digest. Continue to remove stale attributes after successful identity changes.

### 3. Attribute extraction

After the tracking and identity pools are stable, schedule selection/validation and person-level attribute tasks through the same manager. First make `QwenAttributes` concurrency-safe: avoid concurrent mutation of its model/processor and process-global RNG, or use a single inference lane with per-person deterministic seeds. Keep per-person errors in results as today so one failed generation does not silently discard successful people. Do not instantiate a large Qwen model once per queued person.

## Progress and API contract

Extend the progress snapshot with a versioned structured payload. Keep existing `step`, `message`, `current`, and `total` during migration, and add fields along these lines:

```json
{
  "schema_version": 2,
  "run_id": "...",
  "step": "tracking",
  "phase": "scenes",
  "status": "running",
  "message": "Scene 3 von 8 wird verarbeitet",
  "completed": 2,
  "total": 8,
  "unit": "scenes",
  "workers": {"queued": 3, "running": 2, "failed": 0},
  "current_task": {"id": "scene-3", "current": 1200, "total": 2400, "unit": "frames"},
  "elapsed_seconds": 31.4,
  "updated_at": "..."
}
```

- Aggregate by completed work and known units: scenes for tracking, face observations for embedding, people for attributes, and named phases for clustering. Derive a percent from the active phase; do not claim total completion until final publication succeeds.
- Throttle SSE and sidecar updates (for example, at most 4 per second per job, plus task start/end and phase changes). Worker tasks report locally; the aggregator coalesces concurrent updates so they do not race on `job.json` or flood the bounded event history.
- Persist the latest snapshot and active run ID in job state. On reconnect, send that snapshot before live events. Mark abandoned runs interrupted after restart and never report a stale worker as running.
- Preserve the existing stage-level `*_done` and `error` events. Include stage/task identity and a useful error summary for failed sub-tasks; emit completion only after atomic publication.
- Extend frontend progress types and label tracking, identities, and attributes in `GlobalProgress`. Show phase, completed/total, and queued/running counts in the relevant stage panels. Keep the existing compact message/progress view for older payloads.

## Implementation phases

1. **Baseline and contracts:** Record representative single-job timings, scene/frame/face/person counts, and peak RAM/VRAM. Add task/result and progress payload types, but keep concurrency at one. Identify output invariants from the current stage tests.
2. **Manager and progress:** Add the process-lifetime manager, bounded queues, stage coordinator lifecycle, structured progress aggregation, and restart/failure cleanup. Route person stages through it with one worker and verify the frontend accepts both old and new progress payloads.
3. **Scene-parallel tracking:** Add independent scene tasks, task staging, deterministic ID/path remapping, and coordinator publication. Raise the CPU scene limit gradually while keeping inference concurrency conservative.
4. **Parallel identity preparation:** Add bounded frame-range decode/alignment work and a controlled FaceMoE inference lane. Parallelize pairwise similarity only if profiling shows clustering distance construction is material; leave global merge semantics unchanged.
5. **Person-parallel attributes:** Resolve Qwen model/RNG ownership, then add a bounded per-person queue and aggregated per-person progress.
6. **Tune and harden:** Compare serial and parallel outputs, profile representative videos, tune worker limits, document supported deployment settings, and only then consider enabling higher concurrency by default.

## Validation and acceptance criteria

- Serial mode (`worker limit = 1`) remains behaviorally compatible with existing stage APIs and artifacts.
- Parallel tracking produces the same scene boundaries, temporal intervals, review observations, fallback behavior, and deterministic logical track IDs as serial tracking, including cuts on skipped frames. A failed scene leaves the previous published tracking revision intact.
- Parallel identity preparation produces the same accepted/rejected face rows and final person assignments as the serial implementation for fixed model outputs. Same-frame cannot-link behavior and deterministic person IDs remain unchanged, and embeddings never appear in files or progress events.
- Worker counts and pending tasks stay within configured limits across concurrent jobs. GPU model loading and VRAM use stay within the configured inference lane budget.
- Progress is monotonic within a phase, reaches completion only after publish, reports queued/running/completed/failed counts accurately, and survives page refresh and SSE reconnect. Stage labels are meaningful in both the global bar and person panels.
- Exercise worker exceptions, cancellation before execution, restart/interruption, stale revision checks, and cleanup of temporary scene/task outputs. Keep existing review mutation exclusion while a stage is queued or running.
- Benchmark serial versus parallel runs on representative short and long videos. Enable concurrency above one by default only when wall-clock improvement is repeatable without unacceptable peak memory or output drift.

## Risks and decisions to settle during implementation

- RF-DETR, RetinaFace, FaceMoE, and Qwen each have different memory and thread-safety characteristics. Pool size must be based on measured model ownership and hardware, not scene count alone.
- Random video seeking can cost more than sequential decode. Benchmark frame-range partitioning and use bounded contiguous batches; scene parallelism is most promising for long scenes and expensive inference.
- Scene-local IDs must be remapped consistently in every CSV, JSON manifest, crop path, and dependent reference. Keep that remapping in one coordinator tested independently from inference.
- The in-process manager improves bounded concurrency on one backend process only. Cross-process scheduling, durable task leases, and event fan-out belong with the later database/broker rollout.
