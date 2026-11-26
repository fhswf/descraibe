"""Wählt aktuelle Personencrops aus und ersetzt attributes.json nach erfolgreicher Qwen-Auswertung."""
from __future__ import annotations

import hashlib
import threading
import time
from contextlib import nullcontext

from . import attribute_state, review_artifacts, stage_state
from .attribute_selection import select_existing
from .qwen_attributes import FIELDS, GENERATION, MODEL_ID, PROMPT, QwenAttributes, parse_json
from .review_artifacts import ReviewError
from .config import MAX_IMAGES_PER_PERSON, validate_parameter
from .work_pool import CancellationToken, map_bounded, model_slot, report_progress


def run_attributes(video_path, job_dir, progress_cb=None, *, max_images=MAX_IMAGES_PER_PERSON,
                   cancel_token: CancellationToken | None = None):
    validate_parameter("max_images", max_images)
    if cancel_token is not None:
        cancel_token.raise_if_cancelled()
    from ..video_utils import get_video_stats

    data = attribute_state.source(job_dir)
    tracking = data.track_state
    if stage_state.video_digest(video_path) != tracking["video_sha256"]:
        raise ReviewError("Originalvideo wurde geändert. Bitte Tracking erneut ausführen.", 409)
    dimensions = get_video_stats(str(video_path))
    report_progress(progress_cb, "Attributbilder werden ausgewählt …", 0, 100, {
        "phase": "selection", "completed": 0, "total": 100, "unit": "percent",
    })
    selections = select_existing(data, dimensions["width"], dimensions["height"], max_images=max_images)
    ordered_selections = sorted(selections.items())
    state_lock = threading.Lock()
    state = {"queued": 0, "running": 0, "completed": 0, "failed": 0,
             "current_task": None, "last_emit": 0.0}
    started = time.monotonic()

    def publish(force=False):
        now = time.monotonic()
        with state_lock:
            if not force and now - state["last_emit"] < 0.25:
                return
            state["last_emit"] = now
            completed = state["completed"]
            workers = {key: state[key] for key in ("queued", "running", "completed", "failed")}
            current_task = state["current_task"]
        total = len(ordered_selections)
        report_progress(progress_cb, f"Attribute ausgewertet: {completed}/{total} Personen",
                        completed, max(1, total), {
                            "phase": "person_attributes", "completed": completed, "total": total,
                            "unit": "people", "workers": workers, "current_task": current_task,
                            "elapsed_seconds": round(now - started, 1),
                        })

    def task_event(event, item):
        person_id = item[0]
        with state_lock:
            if event == "queued":
                state["queued"] += 1
            elif event == "started":
                state["queued"] = max(0, state["queued"] - 1)
                state["running"] += 1
                state["current_task"] = {"id": f"person-{person_id}", "person_id": person_id}
            elif event == "cancelled":
                state["queued"] = max(0, state["queued"] - 1)
            elif event == "cancelled_running":
                state["running"] = max(0, state["running"] - 1)
                state["current_task"] = {"id": f"person-{person_id}", "status": "cancelled"}
            elif event in {"completed", "failed"}:
                state["running"] = max(0, state["running"] - 1)
                state[event] += 1
                state["current_task"] = {"id": f"person-{person_id}", "status": event}
        publish(force=event in {"completed", "failed", "cancelled_running"})

    def process_person(item):
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        person_id, images = item
        start, error = time.perf_counter(), None
        parsed = {field: "" for field in FIELDS}
        status = "no_eligible_images"
        if images:
            status = "generation_error"
            try:
                if cancel_token is not None:
                    cancel_token.raise_if_cancelled()
                parsed = parse_json(model.predict(person_id, [data.crop_file(image["crop_id"]) for image in images]))
                status = "ok"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        return {
            "person_id": person_id, "images": images, "attributes": parsed, "status": status,
            "error": error, "runtime_seconds": round(time.perf_counter() - start, 3),
        }

    has_images = any(selections.values())
    context = QwenAttributes() if has_images else nullcontext(None)
    slot = model_slot(cancel_token) if has_images else nullcontext()
    with slot:
        with context as model:
            persons = {
                str(result["person_id"]): result
                for result in map_bounded(
                    ordered_selections, process_person, on_task_event=task_event,
                    cancel_token=cancel_token,
                )
            }

    current = review_artifacts.load(job_dir)
    if current.assignment_revision != data.assignment_revision:
        raise ReviewError("Personenzuordnungen wurden während des Attributlaufs geändert. Bitte erneut ausführen.", 409)
    path = data.root / "attributes.json"
    revision = int(stage_state.read_json(path).get("revision", 0)) + 1 if path.is_file() else 1
    report_progress(progress_cb, "Attribute werden gespeichert …", 0, 1, {
        "phase": "publishing", "completed": 0, "total": 1, "unit": "publish",
    })
    if cancel_token is not None:
        cancel_token.begin_commit()
    stage_state.atomic_write(path, {
        "schema_version": 1, "revision": revision, "tracking_revision": data.tracking_revision, "assignment_revision": data.assignment_revision,
        "model_id": MODEL_ID, "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "max_images": max_images,
        "generation": GENERATION, "selection_policy": "existing-crops-v2-small-person-fallback-50-30-20", "persons": persons,
    })
    report_progress(progress_cb, "Attribute abgeschlossen", 1, 1, {
        "phase": "complete", "completed": 1, "total": 1, "unit": "publish",
    })
    return attribute_state.snapshot(job_dir)
