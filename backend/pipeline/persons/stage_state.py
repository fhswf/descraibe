"""Versioned stage outputs and independent optional correction state. No ML imports."""
import copy
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from .review_artifacts import ReviewError


def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReviewError(f"Zustand nicht lesbar: {Path(path).name}", 409) from exc


def root(job_dir):
    return Path(job_dir) / "person_analysis"


def active(job_dir):
    path = root(job_dir) / "pipeline_state.json"
    if not path.exists():
        return None
    state = read_json(path)
    try:
        for key in ("tracking_run", "identity_run"):
            if state.get(key) is not None:
                uuid.UUID(state[key])
        if not state.get("tracking_run"):
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ReviewError("Ungültiger Personen-Pipelinestand.", 409) from exc
    return state


def new_run(job_dir, kind):
    run_id = str(uuid.uuid4())
    path = root(job_dir) / "runs" / run_id / kind
    path.mkdir(parents=True)
    return run_id, path


def run_path(job_dir, run_id, kind):
    uuid.UUID(run_id)
    return root(job_dir) / "runs" / run_id / kind


def publish(job_dir, tracking_id, identity_id=None):
    atomic_write(root(job_dir) / "pipeline_state.json", {
        "schema_version": 1, "tracking_run": tracking_id, "identity_run": identity_id})


def corrections(job_dir):
    path = root(job_dir) / "review_state.json"
    if not path.exists():
        return {"schema_version": 3, "face_reviews": {}, "identity_reviews": {}}
    value = read_json(path)
    if not isinstance(value, dict):
        raise ReviewError("Ungültiger Review-State; nichts wurde zurückgesetzt.", 409)
    if value.get("schema_version") in (1, 2):
        # Preserve the entire legacy correction snapshot when the first new edit occurs.
        return {"schema_version": 3, "face_reviews": {}, "identity_reviews": {}, "legacy_review": value}
    if value.get("schema_version") != 3 or not isinstance(value.get("face_reviews"), dict) or not isinstance(value.get("identity_reviews"), dict):
        raise ReviewError("Ungültiger Review-State; nichts wurde zurückgesetzt.", 409)
    return value


def face_state(job_dir, tracking_id):
    state = corrections(job_dir)["face_reviews"].get(tracking_id, {"revision": 0, "excluded_face_observations": []})
    if not isinstance(state, dict) or type(state.get("revision")) is not int or state["revision"] < 0 or not isinstance(state.get("excluded_face_observations"), list) or any(type(fid) is not int for fid in state["excluded_face_observations"]):
        raise ReviewError("Ungültige Gesichtsbereinigung.", 409)
    return state


def face_version(tracking_id, state):
    return f"{tracking_id}:{state['revision']}"


def status(job_dir):
    pointer = active(job_dir)
    if pointer is None:
        return {"tracking_ready": False, "identities_ready": False, "identities_stale": False, "legacy": True}
    face = face_state(job_dir, pointer["tracking_run"])
    report = read_json(run_path(job_dir, pointer["identity_run"], "identities") / "identity_result.json") if pointer["identity_run"] else None
    return {"tracking_ready": True, "identities_ready": report is not None,
            "identities_stale": bool(report and report["face_review_version"] != face_version(pointer["tracking_run"], face)),
            "face_review_version": face_version(pointer["tracking_run"], face), **pointer, "legacy": False}


def face_snapshot(job_dir):
    from . import review_artifacts
    from . import track_segments
    pointer = active(job_dir)
    if pointer is None:
        raise ReviewError("Alter Job: Für Gesichtsbereinigung vor FaceMoE bitte Tracking & Gesichter neu ausführen. Bisherige Ergebnisse bleiben erhalten.", 409)
    data = review_artifacts.load_tracking(job_dir)
    state = face_state(job_dir, pointer["tracking_run"])
    excluded = set(state["excluded_face_observations"])
    metadata = read_json(data.root / "tracks.json")
    return {"tracks": track_segments.review_tracks(data, metadata, state),
            "split_available": (data.root / track_segments.TIMELINE).is_file(),
            "original_tracks_count": len(data.tracks),
            "version": face_version(pointer["tracking_run"], state), "analysis_id": data.analysis_id,
            "excluded_face_observations": sorted(excluded), **status(job_dir)}


def save_faces(job_dir, body):
    from . import review_artifacts
    from . import track_segments
    pointer = active(job_dir)
    if pointer is None:
        raise ReviewError("Tracking-Artefakte fehlen.", 409)
    tid = pointer["tracking_run"]
    state = face_state(job_dir, tid)
    if body.get("version") != face_version(tid, state):
        raise ReviewError("Gesichtsbereinigung wurde geändert. Bitte neu laden.", 409)
    data = review_artifacts.load_tracking(job_dir)
    changes = body.get("face_exclusions", [])
    if not isinstance(changes, list) or (not changes and not body.get("track_changes")):
        raise ReviewError("Keine Review-Änderungen übermittelt.")
    excluded, seen = set(state["excluded_face_observations"]), set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"face_id", "excluded"}:
            raise ReviewError("Nur Ausschließen und Wiederherstellen sind erlaubt.")
        fid = change["face_id"]
        if type(fid) is not int or fid not in data.observations or fid in seen or type(change["excluded"]) is not bool:
            raise ReviewError("Ungültige Face-Beobachtung.")
        seen.add(fid)
        excluded.add(fid) if change["excluded"] else excluded.discard(fid)
    updated = track_segments.apply_changes(data.root, read_json(data.root / "tracks.json"), state, body.get("track_changes", []))
    if excluded != set(state["excluded_face_observations"]) or updated != state:
        all_reviews = copy.deepcopy(corrections(job_dir))
        all_reviews["face_reviews"][tid] = {**updated, "revision": state["revision"] + 1, "excluded_face_observations": sorted(excluded)}
        atomic_write(root(job_dir) / "review_state.json", all_reviews)
    return face_snapshot(job_dir)


def video_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
