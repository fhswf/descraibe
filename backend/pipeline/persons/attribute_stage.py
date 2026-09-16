"""Existing crop selection -> one model per run -> immutable automatic attributes."""
from contextlib import nullcontext
import hashlib
import time

from . import attribute_state, stage_state
from .attribute_selection import select_existing
from .qwen_attributes import QwenAttributes, FIELDS, MODEL_ID, PROMPT, GENERATION, parse_json
from .review_artifacts import ReviewError


def run_attributes(video_path, job_dir, progress_cb=None):
    from ..video_utils import get_video_stats
    data, state, parent = attribute_state.source(job_dir)
    tracking = stage_state.read_json(data.root / 'tracks.json')
    if stage_state.video_digest(video_path) != tracking['video_sha256']:
        raise ReviewError('Originalvideo wurde geändert. Bitte Tracking erneut ausführen.', 409)
    dimensions = get_video_stats(str(video_path))
    if progress_cb:
        progress_cb('Attributbilder werden ausgewählt …', 0, 100)
    selections = select_existing(data, state, dimensions['width'], dimensions['height'])
    run_id, output = stage_state.new_run(job_dir, 'attributes')
    stage_state.atomic_write(output / 'selection.json', {'run_id': run_id, 'source': parent,
        'identity_review_version': review_version(state), 'video_sha256': tracking['video_sha256'],
        'frame_width': dimensions['width'], 'frame_height': dimensions['height'],
        'selection_policy': 'existing-crops-v1-reference-50-30-20', 'persons': selections})
    persons = {}
    context = QwenAttributes() if any(selections.values()) else nullcontext(None)
    with context as model:
        for index, (pid, images) in enumerate(selections.items()):
            start = time.perf_counter()
            raw, error, parsed = '', None, {field: '' for field in FIELDS}
            status = 'no_eligible_images'
            if images:
                status = 'generation_error'
                try:
                    raw = model.predict(pid, [data.crop_file(c['crop_id']) for c in images])
                    status = 'parse_error'
                    parsed = parse_json(raw)
                    status = 'ok'
                except Exception as exc:
                    error = f'{type(exc).__name__}: {exc}'
            persons[str(pid)] = {'person_id': pid, 'name': state['persons'][str(pid)]['name'],
                'images': images, 'automatic': parsed, 'raw_output': raw, 'status': status,
                'error': error, 'runtime_seconds': round(time.perf_counter()-start, 3)}
            if progress_cb:
                progress_cb(f'Attribute: Person {index+1}/{len(selections)}', index+1, len(selections))
    stage_state.atomic_write(output / 'attributes.json', {'run_id': run_id, 'source': parent,
        'model_id': MODEL_ID, 'prompt': PROMPT, 'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(),
        'generation': GENERATION, 'enable_thinking': False, 'seed_base': 42, 'persons': persons})
    if attribute_state.source(job_dir)[2] != parent:
        raise ReviewError('Personenzuordnungen wurden während des Attributlaufs geändert; Ergebnis nicht aktiviert.', 409)
    stage_state.atomic_write(stage_state.root(job_dir) / 'attribute_state.json', {'schema_version': 1, 'run_id': run_id})
    return attribute_state.snapshot(job_dir)


def review_version(state):
    return f"{state['analysis_id']}:{state['revision']}"
