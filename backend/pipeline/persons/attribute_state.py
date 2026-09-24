"""Aktueller Attributzustand. Manuelle Änderungen werden direkt in attributes.json gespeichert."""
from __future__ import annotations

from . import review_artifacts, stage_state
from .qwen_attributes import FIELDS, LABELS
from .review_artifacts import ReviewError


def source(job_dir):
    data = review_artifacts.load(job_dir)
    if data.identity_revision is None:
        raise ReviewError("Bitte zuerst Personenzuordnung ausführen.", 409)
    return data


def status(job_dir):
    path = stage_state.root(job_dir) / "attributes.json"
    if not path.is_file():
        return {"ready": False, "stale": False, "version": None, "revision": None}
    try:
        data = source(job_dir)
        payload = stage_state.read_json(path)
        stale = payload.get("tracking_revision") != data.tracking_revision or payload.get("assignment_revision") != data.assignment_revision
        revision = payload.get("revision")
        version = f"{data.tracking_revision}:{data.assignment_revision}:{revision}"
        return {"ready": not stale, "stale": stale, "version": version, "revision": revision}
    except (ReviewError, KeyError, TypeError, ValueError) as exc:
        return {"ready": False, "stale": True, "version": None, "revision": None, "error": str(exc)}


def snapshot(job_dir):
    info = status(job_dir)
    if not info["ready"]:
        return {**info, "persons": [], "fields": FIELDS, "labels": LABELS}
    data = source(job_dir)
    payload = stage_state.read_json(data.root / "attributes.json")
    persons = []
    for person_id, person in sorted(data.persons.items()):
        row = payload.get("persons", {}).get(str(person_id))
        if row is None:
            continue
        attributes = row.get("attributes", {})
        persons.append({**row, "name": person["name"], "function": person.get("function", ""), "attributes": attributes})
    version = f"{data.tracking_revision}:{data.assignment_revision}:{payload['revision']}"
    return {**info, "persons": persons, "fields": FIELDS, "labels": LABELS, "version": version,
            "assignment_revision": data.assignment_revision}


def save_review(job_dir, body):
    current = snapshot(job_dir)
    if not current["ready"]:
        raise ReviewError("Kein aktueller Attributstand. Bitte Attribute erneut ausführen.", 409)
    if body.get("version") != current["version"]:
        raise ReviewError("Attribute wurden geändert. Bitte neu laden.", 409)
    changes = body.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ReviewError("Keine Attributänderungen übermittelt.")
    base = stage_state.root(job_dir)
    payload = stage_state.read_json(base / "attributes.json")
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"person_id", "field", "value"}:
            raise ReviewError("Ungültige Attributänderung.")
        person_id, field, value = change["person_id"], change["field"], change["value"]
        key = str(person_id)
        if type(person_id) is not int or key not in payload["persons"] or field not in FIELDS or (person_id, field) in seen:
            raise ReviewError("Unbekannte Person, unbekanntes oder mehrfach übermitteltes Attribut.")
        if value is not None and (not isinstance(value, str) or len(value) > 1000):
            raise ReviewError("Ungültiger Attributwert.")
        seen.add((person_id, field))
        payload["persons"][key]["attributes"][field] = "" if value is None else value.strip()
    payload["revision"] = int(payload["revision"]) + 1
    stage_state.atomic_write(base / "attributes.json", payload)
    return snapshot(job_dir)


def image_file(job_dir, version, crop_id):
    data = review_artifacts.load_for_preview(job_dir)
    # Attribute edits do not invalidate crop metadata. Always read the current
    # small attribute file, without rebuilding the complete review projection.
    payload = stage_state.read_json(data.root / "attributes.json")
    current_version = f"{data.tracking_revision}:{data.assignment_revision}:{payload.get('revision')}"
    if (data.identity_revision is None
            or payload.get("tracking_revision") != data.tracking_revision
            or payload.get("assignment_revision") != data.assignment_revision
            or current_version != str(version)):
        raise ReviewError("Attributstand wurde geändert. Bitte neu laden.", 409)
    for person_id in data.persons:
        person = payload.get("persons", {}).get(str(person_id), {})
        if any(int(image["crop_id"]) == int(crop_id) for image in person.get("images", [])):
            return data.crop_file(int(crop_id))
    raise ReviewError("Auswahlbild nicht gefunden.", 404)
