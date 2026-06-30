# 1. OBJECTIVE

Extend the DescrAIbe AI-powered audio description pipeline with an automated **Person Analysis** module that:

1. **Detects persons** in extracted scene images using computer vision (OpenCV DNN YuNet face detector)
2. **Tracks persons** across frames over video duration with timecode mapping
3. **Extracts visual attributes** (clothing colors, age estimate, gender, hair, etc.)
4. **Recognizes names** from text overlays (Bauchbinden/name plates) via OCR
5. **Stores person metadata** persistently in job state and optionally PostgreSQL
6. **Injects person data** into LLM prompts to enforce AD naming conventions (first vs. subsequent mentions)

This enables the system to automatically follow the strict German AD rules for person descriptions: "Erstnennung" (first introduction) vs. "Folgebenennung" (subsequent references).

---

# 2. CONTEXT SUMMARY

**Project:** DescrAIbe -- Open-source webapp for AI-generated audio descriptions (AD) for videos.

**Existing pipeline components:**
- `backend/app.py` -- FastAPI application with job management and SSE progress streaming
- `backend/session_manager.py` -- Per-job state persistence (JSON sidecar + Parquet DataFrames)
- `backend/db/store.py` -- PostgreSQL + file-fallback data store for user configs/presets
- `backend/pipeline/image_extraction.py` -- Scene detection and frame extraction (PySceneDetect)
- `backend/pipeline/gpt_description.py` -- GPT-vision-based AD text generation with syllable-aware rewriting
- `backend/pipeline/ad_slots.py` -- AD slot management
- `docs/relational-data-plan.md` -- Plans for relational data schema (job_events, job_artifacts, etc.)

**Technology stack:**
- Python 3.11+, FastAPI, pandas, PyArrow, OpenCV, PySceneDetect
- PyTorch (GPU-accelerated, already in dependencies)
- OpenAI GPT-4 Vision API for description generation
- PostgreSQL (optional, via psycopg)

**Related prompt files** (referenced in issue, not yet in repo):
- `ad_rules.txt` -- AD style rules (German conventions)
- `system_instruction.txt` -- System prompt for GPT

---

# 3. APPROACH OVERVIEW

Add a **new pipeline step** called `person_analysis` that runs after scene image extraction. The step:

1. Processes all scene images using OpenCV DNN YuNet face detector (MIT-licensed)
2. Runs OCR on each image to detect name overlays (Bauchbinden)
3. Tracks detected persons across images using timecode matching and visual similarity
4. Stores per-person metadata (appearance history, recognized names, visual attributes)
5. Exposes person data to the GPT description step via enhanced prompts and context injection

**Architecture pattern:** Follow the existing pipeline module pattern:
- `pipeline/person_analysis.py` -- Core analysis logic
- `pipeline/__init__.py` -- (currently minimal, may add exports)
- `app.py` -- Add `/api/jobs/{job_id}/persons` endpoint, wire `/run/persons` route
- `session_manager.py` -- Add `persons_df` to `_DF_FIELDS` for persistence
- `db/store.py` -- Add `job_persons` table to relational schema (Phase 2)
- Frontend: Add a new `StepPersons.jsx` component (or extend `StepImages.jsx`)

**Key design decisions:**
- **Model choice:** OpenCV DNN Face Detector (YuNet, MIT-licensed) -- deploys via OpenCV's built-in DNN module; RetinaFace via `retinaface_pytorch` as fallback. Both are MIT-licensed, avoiding AGPL/GPL contamination.
- **Tracking:** Simple timecode-window matching + visual embedding clustering; no heavy ReID model needed for MVP
- **OCR:** Tesseract via `pytesseract` (ubiquitous, no API key needed); lightweight name overlay detection (horizontal text bars near top/bottom of frame)
- **Prompt injection:** Add a `persons_context` section to GPT user prompts with person names and appearance descriptions, with flags for first/subsequent mention
- **Persistence:** Store as `persons_df` Parquet (Phase 1); add `job_persons` PostgreSQL table (Phase 2, per relational-data-plan.md)

---

# 4. IMPLEMENTATION STEPS

## Phase 1: Core Person Analysis Pipeline (MVP)

### Step 1 -- Add dependencies
- Add `pytesseract` to `pyproject.toml` dependencies (OpenCV DNN is already included via `opencv-python-headless`)
- Download YuNet `.onnx` model file (`face_detection_yunet_2023mar.onnx`) at build time or first-run; store in `/app/models/` or `AD_JOBS_DIR/models/`
- Optionally add `retinaface_pytorch` (MIT) as a fallback face detector
- Document `tesseract-ocr` system package requirement in `backend/Dockerfile`
- Update Kubernetes `deployment.yaml` ConfigMap/Dockerfile with Tesseract language packs (`deu` for German)
- Add `YU_NET_MODEL_PATH` env var (default: `/app/models/face_detection_yunet_2023mar.onnx`)

**Reference:** `pyproject.toml`, `backend/Dockerfile`, `k8s/base/deployment.yaml`

---

### Step 2 -- Create `backend/pipeline/person_analysis.py`
Implement the core analysis module with:

**2a. Face Detection (OpenCV DNN YuNet)**
- `detect_faces_in_image(image_path)` -- Load YuNet ONNX model via OpenCV DNN (`cv2.dnn.readNet`), run inference, return face bounding boxes + confidence scores
- Implement graceful fallback if YuNet model file is missing (log warning, return empty list)
- Optionally use `retinaface_pytorch` (MIT) as a secondary detector if YuNet returns no results

**2b. Person Region Extraction**
- Given face bounding boxes, extract the full-body region (approximate: extend bbox vertically by 1.5-2x above and below face, crop to image bounds)
- Use this person region for attribute extraction (clothing colors, etc.)

**2c. Name Overlay Detection (OCR)**
- `detect_name_overlay(image_path)` -- Use pytesseract to detect horizontal text bars (Bauchbinden) near frame edges
- Return extracted text if found (e.g., name below person in news/broadcast)
- Filter OCR output to exclude timestamps, watermarks (heuristic: text length, position)

**2d. Person Tracking**
- `track_persons_across_frames(detections_by_image)` -- Match detected persons across scene images using:
  - Timecode window (persons can only appear in overlapping time ranges)
  - Face bbox IoU matching between consecutive frames
  - Simple visual clustering (mean color of clothing region as fingerprint)
- Return a list of unique `Person` objects with assigned IDs

**2e. Attribute Extraction**
- `extract_person_attributes(image, face_bbox, person_region)` -- From cropped person region extract:
  - Dominant clothing colors (top color, bottom color) via k-means on pixels
  - Age estimate (optional, via face detection confidence as proxy)
  - Hair color estimate (optional, heuristic on upper-head region)
- Store as `attributes` dict per person

**2f. Main Entry Point**
- `analyze_persons(scene_images, progress_cb)` -- Orchestrate detection -> OCR -> tracking -> attribute extraction
- Return a `persons_df` pandas DataFrame with columns:
  `[person_id, first_seen_ts, last_seen_ts, name, appearances, attributes, description]`
- Where `attributes` is a JSON-encoded dict: `{colors: {top, bottom}, age_estimate, ...}`
- Where `appearances` is a list of `{timestamp_s, image_path, face_bbox, person_region}` dicts

**Reference:** New file `backend/pipeline/person_analysis.py`

---

### Step 3 -- Wire Person Analysis into `app.py`
Add new API routes:

**3a. Add `POST /api/jobs/{job_id}/persons` endpoint**
- Lazily import `analyze_persons` from `pipeline.person_analysis`
- Mark step running: `_mark_step_running(job_id, "persons", "Detecting persons...")`
- Call `analyze_persons(scene_images, progress_cb)` using existing job's `scene_images`
- Store result as `persons_df` in job state
- Call `_persist_job()` to save to disk
- Push final progress and return `{"status": "done", "persons_count": N}`

**3b. Add `GET /api/jobs/{job_id}/persons` endpoint**
- Return `make_serializable(job.get("persons_df"))` as list of person dicts

**3c. Add HATEOAS link to `build_hateoas_links`**
- Add `{"rel": "run-persons", "href": f"{base}/api/jobs/{jid}/persons", "method": "POST"}` when `slots_df` and `scene_images` are available

**3d. Update `get_job` response**
- Add `"persons_count": len(persons_df)` to the job payload

**Reference:** `backend/app.py` (existing route patterns for `/vad`, `/transcribe`, `/images`, `/gpt`)

---

### Step 4 -- Update `session_manager.py`
- Add `"persons_df"` to `_DF_FIELDS` list so it auto-persists to Parquet
- Update `create_job()` to initialize `"persons_df": None`

**Reference:** `backend/session_manager.py`

---

### Step 5 -- Create Frontend `StepPersons.jsx`
Create a new React component mirroring the pattern of existing step components:

**5a. Layout**
- Title: "Personenanalyse" (German)
- Show count of detected persons (if results available)
- "Detect Persons" button that POSTs to `/api/jobs/{job_id}/persons`
- SSE progress streaming for the detection step
- Results list showing each detected person:
  - Assigned person ID (e.g., "Person A")
  - Recognized name (if any)
  - First appearance timecode
  - Clothing color description (e.g., "blaues Oberteil, dunkle Hose")
  - Number of appearances across video

**5b. State Management**
- Use existing `useJob` hook to read `persons_df` from `GET /api/jobs/{job_id}`
- Show/hide based on whether `persons_df` exists

**5c. Integrate into App**
- Add `StepPersons` to the pipeline wizard in `App.jsx`, positioned after `StepImages`
- Add navigation link in `build_hateoas_links` response to reflect person analysis step availability

**Reference:** `frontend/src/components/features/StepImages.jsx`, `StepSlots.jsx` (for pattern reference)

---

## Phase 2: Enhanced Prompt Integration & Persistence

### Step 6 -- Update GPT Description Prompts with Person Context
Modify `gpt_description.py` to inject person data into prompts:

**6a. Create `_build_persons_context()` helper**
- Input: `persons_df`, `slot_start_s`, `slot_end_s`
- For each slot, identify which persons appear (based on `first_seen_ts`/`last_seen_ts`)
- Build a context block per slot with:
  - Person name + visual description
  - Flag: `is_first_mention: true/false` (based on whether this is the person's first appearance before `slot_end_s`)
- Format: Markdown section "### Personen im Slot" with per-person details

**6b. Update `describe_slots()` function signature**
- Accept optional `persons_df` parameter
- Inject person context into user prompt before GPT call

**6c. Update `app.py` GPT route**
- Pass `job.get("persons_df")` to `describe_slots()`

**Reference:** `backend/pipeline/gpt_description.py` (`_build_context_block` pattern)

---

### Step 7 -- Add PostgreSQL Table for Person Metadata
Add to `backend/db/` schema:

**7a. Create migration file `backend/db/migrations/0013_job_persons.sql`**
```sql
CREATE TABLE IF NOT EXISTS job_persons (
    id          BIGSERIAL PRIMARY KEY,
    job_id      UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL,
    name        TEXT,
    attributes  JSONB,
    first_seen  DOUBLE PRECISION,
    last_seen   DOUBLE PRECISION,
    description TEXT,
    appearances JSONB,  -- Array of {timestamp_s, image_path, bbox}
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_job_persons_job_id ON job_persons(job_id);
```

**7b. Update `db/store.py`**
- Add `store_persons(job_id, persons_list)`, `get_persons(job_id)` methods
- Use existing `psycopg` pattern from other store methods
- Provide file-based fallback (save as JSON sidecar) if DB unavailable

**7c. Update `app.py` GPT route to dual-write**
- After GPT generation completes, persist person data to DB if enabled

**Reference:** `backend/db/store.py`, `docs/relational-data-plan.md`

---

### Step 8 -- Create Prompt Files for AD Rules
Create `ad_rules.txt` and `system_instruction.txt` as referenced in the issue:

**8a. `ad_rules.txt`**
Document German AD conventions for person descriptions:
- **Erstnennung (first mention):** Full name (if known) + brief visual description
- **Folgebenennung (subsequent mentions):** Only name, or pronoun/descriptor
- Sentence structure rules (passive voice, present tense)
- Forbidden phrases ("man sieht", "es ist zu sehen")
- Syllable density limits per second

**8b. `system_instruction.txt`**
Role-prompt for GPT: "Du bist eine professionelle Audiodeskriptor:in..."

**8c. Add to Kubernetes ConfigMap**
- Add files to `k8s/base/configmap-prompts.yaml`
- Set `GPT_PROMPTS_DIR=/app/config/prompts` (already configured)

**Reference:** `k8s/base/configmap-prompts.yaml` (existing pattern), README section "GPT Prompt Files"

---

## Phase 3: Polish & Testing

### Step 9 -- Add Unit Tests
Create `backend/tests/test_person_analysis.py`:
- Test `_extract_ts_from_filename` (reuse from `image_extraction.py`)
- Test face detection (YuNet) on a sample image with known faces
- Test OCR name overlay detection with synthetic test image
- Test person tracking logic (mock detections across 3 frames)
- Test `persons_df` DataFrame schema validation
- Test graceful fallback when YuNet model file is missing

### Step 10 -- Add Integration Test
Create `backend/tests/test_person_pipeline.py`:
- End-to-end test of `/run/persons` endpoint
- Verify `persons_df` is persisted to disk (Parquet file)
- Verify HATEOAS link appears in job response

### Step 11 -- Documentation
- Add "Person Analysis" section to `README.md` (after GPT Config section)
- Document `ad_rules.txt` and `system_instruction.txt` format
- Add `PERSON_DETECTION_MODEL` env var for model selection
- Add `TESSERACT_CMD` env var for Tesseract binary path

---

# 5. TESTING AND VALIDATION

## Unit Tests
Run with `uv run pytest backend/tests/test_person_analysis.py -v`:
- [ ] Face detection returns valid bounding boxes
- [ ] Graceful fallback when YuNet model unavailable
- [ ] OCR detects name overlay text
- [ ] Person tracking assigns consistent IDs across frames
- [ ] Attribute extraction returns color descriptors
- [ ] `persons_df` DataFrame has correct schema

## Integration Tests
Run with `uv run pytest backend/tests/test_person_pipeline.py -v`:
- [ ] POST `/api/jobs/{job_id}/persons` returns 200 and person count
- [ ] GET `/api/jobs/{job_id}/persons` returns serialized person list
- [ ] `persons_df` persisted to `.parquet` file on disk
- [ ] Job reload from disk restores `persons_df`
- [ ] HATEOAS link "run-persons" appears when `scene_images` available

## End-to-End Manual Testing
1. Upload a test video with known persons (e.g., news broadcast with Bauchbinden)
2. Run pipeline: VAD -> Transcribe -> Slots -> Images -> **Persons** -> GPT
3. Verify persons are detected with correct names from Bauchbinden
4. Verify GPT descriptions use correct naming conventions (first name + description, then name only)

## Success Criteria
- Face detection identifies >= 80% of visible faces in test video frames
- Name recognition from Bauchbinden extracts correct name strings
- Person tracking maintains consistent IDs across scene changes
- GPT prompts include person context and enforce Erstnennung/Folgebenennung rules
- Pipeline step completes within 2x real-time for a 10-minute video
- All existing tests continue to pass (`uv run pytest`)
