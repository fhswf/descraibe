"""Wählt aktuelle Personencrops aus und ersetzt attributes.json nach erfolgreicher Qwen-Auswertung."""
from __future__ import annotations

import hashlib
import time
from contextlib import nullcontext

from . import attribute_state, review_artifacts, stage_state
from .attribute_selection import select_existing
from .qwen_attributes import FIELDS, GENERATION, MODEL_ID, PROMPT, QwenAttributes, parse_json
from .review_artifacts import ReviewError


def run_attributes(video_path, job_dir, progress_cb=None):
    from ..video_utils import get_video_stats

    data = attribute_state.source(job_dir)
    tracking = data.track_state
    if stage_state.video_digest(video_path) != tracking["video_sha256"]:
        raise ReviewError("Originalvideo wurde geändert. Bitte Tracking erneut ausführen.", 409)
    dimensions = get_video_stats(str(video_path))
    if progress_cb:
        progress_cb("Attributbilder werden ausgewählt …", 0, 100)
    selections = select_existing(data, dimensions["width"], dimensions["height"])
    persons = {}
    context = QwenAttributes() if any(selections.values()) else nullcontext(None)
    with context as model:
        for index, (person_id, images) in enumerate(selections.items()):
            start, error = time.perf_counter(), None
            parsed = {field: "" for field in FIELDS}
            status = "no_eligible_images"
            if images:
                status = "generation_error"
                try:
                    parsed = parse_json(model.predict(person_id, [data.crop_file(image["crop_id"]) for image in images]))
                    status = "ok"
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
            persons[str(person_id)] = {
                "person_id": person_id, "images": images, "attributes": parsed, "status": status,
                "error": error, "runtime_seconds": round(time.perf_counter() - start, 3),
            }
            if progress_cb:
                progress_cb(f"Attribute: Person {index + 1}/{len(selections)}", index + 1, len(selections))

    current = review_artifacts.load(job_dir)
    if current.assignment_revision != data.assignment_revision:
        raise ReviewError("Personenzuordnungen wurden während des Attributlaufs geändert. Bitte erneut ausführen.", 409)
    path = data.root / "attributes.json"
    revision = int(stage_state.read_json(path).get("revision", 0)) + 1 if path.is_file() else 1
    stage_state.atomic_write(path, {
        "schema_version": 1, "revision": revision, "tracking_revision": data.tracking_revision, "assignment_revision": data.assignment_revision,
        "model_id": MODEL_ID, "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "generation": GENERATION, "selection_policy": "existing-crops-v1-reference-50-30-20", "persons": persons,
    })
    return attribute_state.snapshot(job_dir)
