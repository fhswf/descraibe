"""Dateizugriff für den aktuellen Zustand der Personenanalyse."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
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


def read_csv(path):
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=";")
            return list(reader), list(reader.fieldnames or [])
    except OSError as exc:
        raise ReviewError(f"Zustand nicht lesbar: {Path(path).name}", 409) from exc


def write_csv(path, rows, fieldnames):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def root(job_dir):
    return Path(job_dir) / "person_analysis"


def scene_cuts(job_dir):
    """Read the full-video, one-based cuts produced by image extraction."""
    path = Path(job_dir) / "job.json"
    cuts = read_json(path).get("scene_cut_frames") if path.is_file() else None
    if not isinstance(cuts, list) or any(type(c) is not int or c < 2 for c in cuts) or cuts != sorted(set(cuts)):
        raise ReviewError("Bitte zuerst Bilder extrahieren ausführen. Einstellungsgrenzen fehlen oder sind ungültig.", 409)
    return cuts


def status(job_dir):
    base = root(job_dir)
    tracks = read_json(base / "tracks.json") if (base / "tracks.json").is_file() else None
    persons = read_json(base / "persons.json") if (base / "persons.json").is_file() else None
    attributes = read_json(base / "attributes.json") if (base / "attributes.json").is_file() else None
    tracking_revision = tracks.get("revision") if tracks else None
    identity_revision = persons.get("revision") if persons and persons.get("tracking_revision") == tracking_revision else None
    identities_stale = bool(persons and identity_revision is None)
    attributes_ready = bool(attributes and persons and attributes.get("tracking_revision") == tracking_revision
                            and attributes.get("assignment_revision") == persons.get("assignment_revision"))
    return {
        "tracking_interval_seconds": tracks.get("tracking_interval_seconds") if tracks else None,
        "similarity_threshold": persons.get("similarity_threshold") if persons else None,
        "max_images": attributes.get("max_images") if attributes else None,
        "tracking_ready": tracks is not None, "identities_ready": identity_revision is not None,
        "attributes_ready": attributes_ready, "identities_stale": identities_stale,
        "tracking_revision": tracking_revision, "identity_revision": identity_revision, "legacy": False,
    }


def face_snapshot(job_dir):
    from . import review_artifacts, track_segments

    data = review_artifacts.load_tracking(job_dir)
    metadata = data.track_state
    tracks, result = track_segments.current_tracks(metadata, data.root), []
    frames = track_segments.timeline(str(data.root)) if (data.root / track_segments.TIMELINE).is_file() else {}
    for track in tracks:
        evidence = [row for row in data.evidence_by_track[track["track_id"]] if row["usable"]]
        observations = data.tracking_crops(track["track_id"])
        rows = [row for row in frames.get(track["source_track_id"], []) if track["start_frame"] <= row["frame_number"] <= track["end_frame"]]
        result.append({
            **track, "quality_face_count": len(evidence), "observations": observations,
            "split_options": track_segments.split_options(rows, [row["frame_number"] for row in observations], metadata["fps"]),
        })
    return {
        "tracks": result, "split_available": bool(frames),
        "original_tracks_count": len({track["source_track_id"] for track in tracks}),
        "version": metadata["revision"], "analysis_id": f"tracking-{metadata['revision']}",
        "excluded_face_observations": sorted(face["face_id"] for face in data.faces if face["excluded"]),
        **status(job_dir),
    }


def save_faces(job_dir, body):
    from . import person_crops, review_artifacts, track_segments

    data = review_artifacts.load_tracking(job_dir)
    metadata = data.track_state
    if body.get("version") != metadata.get("revision"):
        raise ReviewError("Gesichts- oder Trackzustand wurde geändert. Bitte neu laden.", 409)
    face_changes, track_changes = body.get("face_exclusions", []), body.get("track_changes", [])
    if not isinstance(face_changes, list) or not isinstance(track_changes, list) or (not face_changes and not track_changes):
        raise ReviewError("Keine Review-Änderungen übermittelt.")

    rows, fields = read_csv(data.root / "face_observations.csv")
    by_id = {int(row["face_id"]): row for row in rows}
    changed = False
    for change in face_changes:
        if not isinstance(change, dict) or set(change) != {"face_id", "excluded"}:
            raise ReviewError("Nur Ausschließen und Wiederherstellen sind erlaubt.")
        face_id, excluded = change["face_id"], change["excluded"]
        if type(face_id) is not int or type(excluded) is not bool or face_id not in by_id:
            raise ReviewError("Ungültige Face-Beobachtung.")
        value = "True" if excluded else "False"
        if by_id[face_id].get("excluded", "False") != value:
            by_id[face_id]["excluded"] = value
            changed = True

    updated = track_segments.apply_changes(data.root, metadata, track_changes)
    changed = changed or updated != metadata
    if not changed:
        return face_snapshot(job_dir)
    if updated == metadata:
        updated = dict(metadata)
        updated["revision"] = int(metadata["revision"]) + 1

    write_csv(data.root / "face_observations.csv", rows, fields)
    atomic_write(data.root / "tracks.json", updated)
    for name in ("persons.json", "attributes.json"):
        (data.root / name).unlink(missing_ok=True)
    person_crops.remove_identity_fallbacks(data.root)
    track_segments.timeline.cache_clear()
    return face_snapshot(job_dir)


def video_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
