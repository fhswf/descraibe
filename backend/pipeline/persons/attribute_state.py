"""Attribute run provenance and manual overrides, independent of person/AD projection."""
import copy
import hashlib
import json

from . import stage_state, review_state
from .review_artifacts import ReviewError
from .qwen_attributes import FIELDS, LABELS


def source(job_dir):
    stages = stage_state.status(job_dir)
    if not stages.get('identities_ready'):
        raise ReviewError('Bitte zuerst Personen & Cluster ausführen.', 409)
    if stages['identities_stale']:
        raise ReviewError('Personen & Cluster ist veraltet. Bitte zuerst erneut ausführen.', 409)
    data, state = review_state.read(job_dir)
    assignments = json.dumps(state['assignments'], sort_keys=True, separators=(',', ':'))
    return data, state, {'parent_identity_run': data.identity_id, 'parent_tracking_run': data.tracking_id,
                         'analysis_id': data.analysis_id,
                         'assignments_hash': hashlib.sha256(assignments.encode()).hexdigest()}


def run_root(job_dir, run_id):
    try:
        return stage_state.run_path(job_dir, run_id, 'attributes')
    except (ValueError, TypeError, AttributeError) as exc:
        raise ReviewError('Ungültiger Attributlauf.', 404) from exc


def automatic(job_dir, run_id):
    return stage_state.read_json(run_root(job_dir, run_id) / 'attributes.json')


def status(job_dir):
    path = stage_state.root(job_dir) / 'attribute_state.json'
    if not path.exists():
        return {'ready': False, 'stale': False, 'run_id': None}
    try:
        run_id = stage_state.read_json(path)['run_id']
        result = automatic(job_dir, run_id)
        try:
            _, _, current = source(job_dir)
            stale = current != result['source']
        except ReviewError:
            stale = True
        return {'ready': True, 'stale': stale, 'run_id': run_id}
    except (ReviewError, KeyError, TypeError) as exc:
        return {'ready': False, 'stale': True, 'run_id': None, 'error': str(exc)}


def review(job_dir, run_id, result):
    states = stage_state.corrections(job_dir).get('attribute_reviews', {})
    if not isinstance(states, dict):
        raise ReviewError('Ungültige Attributkorrekturen.', 409)
    state = states.get(run_id, {'revision': 0, 'parent_identity_run': result['source']['parent_identity_run'], 'overrides': {}})
    try:
        if (type(state['revision']) is not int or state['revision'] < 0
                or state['parent_identity_run'] != result['source']['parent_identity_run']
                or not isinstance(state['overrides'], dict)):
            raise ValueError()
        for pid, fields in state['overrides'].items():
            if (pid not in result['persons'] or not isinstance(fields, dict)
                    or not all(k in FIELDS and isinstance(v, str) and len(v) <= 1000 for k, v in fields.items())):
                raise ValueError()
    except (ValueError, KeyError, TypeError) as exc:
        raise ReviewError('Ungültige Attributkorrekturen; nichts wurde zurückgesetzt.', 409) from exc
    return state


def snapshot(job_dir):
    info = status(job_dir)
    if not info['ready']:
        return {**info, 'persons': [], 'fields': FIELDS, 'labels': LABELS}
    result = automatic(job_dir, info['run_id'])
    manual = review(job_dir, info['run_id'], result)
    names = {}
    if not info['stale']:
        _, current, _ = source(job_dir)
        names = current['persons']
    persons = []
    for pid, row in result['persons'].items():
        overrides = manual['overrides'].get(pid, {})
        persons.append({**row, 'name': names.get(pid, {}).get('name', row['name']),
                        'overrides': overrides, 'effective': {**row['automatic'], **overrides}})
    return {**info, 'persons': persons, 'fields': FIELDS, 'labels': LABELS,
            'version': f"{info['run_id']}:{manual['revision']}", 'source': result['source']}


def save_review(job_dir, body):
    current = snapshot(job_dir)
    if not current['ready'] or current['stale']:
        raise ReviewError('Kein aktueller Attributlauf. Bitte Attribute erneut ausführen.', 409)
    if body.get('version') != current['version']:
        raise ReviewError('Attribute wurden geändert. Bitte neu laden.', 409)
    changes = body.get('changes')
    if not isinstance(changes, list) or not changes:
        raise ReviewError('Keine Attributänderungen übermittelt.')
    run_id = current['run_id']
    result = automatic(job_dir, run_id)
    state = copy.deepcopy(review(job_dir, run_id, result))
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'person_id', 'field', 'value'}:
            raise ReviewError('Ungültige Attributänderung.')
        pid, field, value = change['person_id'], change['field'], change['value']
        if type(pid) is not int or str(pid) not in result['persons'] or not isinstance(field, str) or field not in FIELDS:
            raise ReviewError('Unbekannte Person oder unbekanntes Attribut.')
        if (pid, field) in seen or (value is not None and (not isinstance(value, str) or len(value) > 1000)):
            raise ReviewError('Ungültiger oder mehrfach übermittelter Attributwert.')
        seen.add((pid, field))
        overrides = state['overrides'].setdefault(str(pid), {})
        if value is None:
            overrides.pop(field, None)
        else:
            overrides[field] = value.strip()
    state['revision'] += 1
    all_reviews = copy.deepcopy(stage_state.corrections(job_dir))
    all_reviews.setdefault('attribute_reviews', {})[run_id] = state
    stage_state.atomic_write(stage_state.root(job_dir) / 'review_state.json', all_reviews)
    return snapshot(job_dir)


def image_file(job_dir, run_id, crop_id):
    result = automatic(job_dir, run_id)
    for person in result['persons'].values():
        for image in person['images']:
            if image['crop_id'] == crop_id:
                base = stage_state.root(job_dir).resolve()
                path = (base / image['crop_path']).resolve()
                if path.is_relative_to(base / 'runs') and path.is_file():
                    return path
    raise ReviewError('Auswahlbild nicht gefunden.', 404)
