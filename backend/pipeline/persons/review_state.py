"""Canonical manual whole-track assignments; automatic output remains read-only.

Without review_state.json the automatic assignments are immediately usable.
All public projections are derived, never an independent assignment authority.
The existing application uses one backend worker; its job lock serializes edits.
"""
from __future__ import annotations

import copy
import json
import math
import os
import tempfile
from pathlib import Path

from . import review_artifacts as artifacts
from .review_artifacts import ReviewError


FILENAME = "review_state.json"


def _metadata(person: dict) -> dict:
    # Explicit allowlist: model outputs/embeddings cannot enter review persistence.
    return {key: str(person.get(key) or "") for key in ("name", "description", "function")}


def read(job_dir: str | Path) -> tuple[artifacts.Artifacts, dict]:
    data = artifacts.load(job_dir)
    path = data.root / FILENAME
    state = None
    if data.staged:
        from . import stage_state
        state = stage_state.corrections(job_dir)["identity_reviews"].get(data.identity_id)
    elif path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ReviewError("review_state.json ist ungültig; Korrekturen wurden nicht zurückgesetzt.", 409) from exc
    if state is None:
        return data, {
            "schema_version": 2, "analysis_id": data.analysis_id, "revision": 0,
            "excluded_face_observations": data.used_exclusions if data.staged else [],
            "next_person_id": max(data.persons, default=0) + 1,
            "assignments": {str(tid): pid for tid, pid in data.assignments.items()},
            "persons": {str(pid): _metadata(p) for pid, p in data.persons.items()},
        }
    try:
        if state["analysis_id"] != data.analysis_id:
            raise ReviewError("Die Korrekturen gehören zu einem anderen Analyselauf. Sie wurden nicht übernommen.", 409)
        if type(state["schema_version"]) is not int or state["schema_version"] not in {1, 2} or type(state["revision"]) is not int or state["revision"] < 1:
            raise ValueError("invalid version")
        if set(state["assignments"]) != {str(tid) for tid in data.tracks}:
            raise ValueError("incomplete assignments")
        for pid in state["persons"]:
            if str(int(pid)) != pid or int(pid) < 1:
                raise ValueError("invalid person id")
        for target in state["assignments"].values():
            if target is not None and (type(target) is not int or str(target) not in state["persons"]):
                raise ValueError("invalid target")
        if type(state["next_person_id"]) is not int or state["next_person_id"] <= max(map(int, state["persons"]), default=0):
            raise ValueError("invalid next id")
        excluded = [] if state["schema_version"] == 1 else state["excluded_face_observations"]
        if not isinstance(excluded, list) or any(type(fid) is not int or fid not in data.observations for fid in excluded):
            raise ValueError("invalid face exclusions")
        # Reconstruct, rather than carrying arbitrary JSON fields into a new save.
        return data, {
            "schema_version": 2, "analysis_id": data.analysis_id, "revision": state["revision"],
            "excluded_face_observations": sorted(set(excluded)),
            "next_person_id": state["next_person_id"], "assignments": state["assignments"],
            "persons": {pid: _metadata(p) for pid, p in state["persons"].items()},
        }
    except ReviewError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ReviewError("review_state.json ist ungültig; Korrekturen wurden nicht zurückgesetzt.", 409) from exc


def version(state: dict) -> str:
    return f"{state['analysis_id']}:{state['revision']}"


def _representative(data: artifacts.Artifacts, track_ids: list[int], excluded: set[int]) -> dict | None:
    """Human recognition preview from all evidence, independent of preview sampling."""
    def number(value):
        try:
            result = float(value)
            return max(0, result) if math.isfinite(result) else 0
        except (ValueError, TypeError):
            return 0

    faces = []
    for tid in track_ids:
        for c in data.evidence_by_track[tid]:
            if c["face_id"] in excluded:
                continue
            width, height = number(c.get("width")), number(c.get("height"))
            bbox = c.get("face_bbox")
            if not width or not height or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                x1, y1, x2, y2 = map(float, bbox)
            except (ValueError, TypeError):
                continue
            if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
                continue
            fw = min(width, x2) - max(0, x1)
            fh = min(height, y2) - max(0, y1)
            if fw <= 0 or fh <= 0:
                continue
            try:
                data.crop_file(c["crop_id"])
            except ReviewError:
                continue
            faces.append((c, math.log1p(number(c.get("blur_score"))),
                          math.sqrt((fw / width) * (fh / height)),
                          max(0, min(1, 2 * min(x1 / width, y1 / height, (width-x2) / width, (height-y2) / height))),
                          min(1, number(c.get("face_confidence"))), math.log1p(width * height)))
    if faces:
        # Candidate-relative log normalization limits raw-pixel/blur dominance.
        max_blur = max(row[1] for row in faces) or 1
        max_area = max(row[5] for row in faces) or 1

        def face_rank(row):
            crop, blur, size, margin, confidence, area = row
            score = .40 * blur / max_blur + .25 * size + .15 * margin + .10 * confidence + .10 * area / max_area
            # Scores within the same 1e-6 bucket use stable IDs only.
            return (round(score, 6), -crop["crop_id"], -crop["face_id"])

        return max(faces, key=face_rank)[0]
    excluded_crops = {c["crop_id"] for fid, c in data.observations.items() if fid in excluded}
    fallback = [c for tid in track_ids for c in data.by_track[tid] if c["crop_id"] not in excluded_crops]
    # Missing legacy JPEGs must not prevent reviewing an otherwise valid job.
    for crop in sorted(fallback, key=lambda c: (c["width"] * c["height"], -c["crop_id"]), reverse=True):
        try:
            data.crop_file(crop["crop_id"])
            return crop
        except ReviewError:
            continue
    return None


def project(data: artifacts.Artifacts, state: dict) -> dict:
    excluded = set(state["excluded_face_observations"])
    tracks = []
    grouped: dict[int, list[dict]] = {}
    for tid, original in sorted(data.tracks.items()):
        target = state["assignments"][str(tid)]
        crops = data.by_track[tid]
        track = {**original, "person_id": target, "crop_count": len(crops),
                 "original_person_id": data.assignments[tid],
                 "facemoe_observation_count": sum(c["evidence_status"] == "facemoe" for c in data.evidence_by_track[tid]),
                 "review_observation_count": len(data.review_crops(tid, excluded)),
                 "review_mode": (data.evidence_by_track[tid][0]["evidence_status"] if data.evidence_by_track[tid] else "fallback")}
        tracks.append(track)
        if target is not None:
            grouped.setdefault(target, []).append(track)
    persons = []
    for pid, person_tracks in grouped.items():
        person_tracks.sort(key=lambda t: (t["start_s"], t["track_id"]))
        crop_candidates = [c for t in person_tracks for c in data.review_crops(t["track_id"], excluded) if not c["excluded"]]
        crop_candidates.sort(key=lambda c: (c["timestamp_s"], c["crop_id"]))
        representative = _representative(data, [t["track_id"] for t in person_tracks], excluded)
        segments = [{k: t[k] for k in ("track_id", "scene_id", "start_s", "end_s")} for t in person_tracks]
        persons.append({
            "person_id": pid, **state["persons"][str(pid)],
            "track_ids": [t["track_id"] for t in person_tracks], "segments": segments,
            "appearances": [{"start_s": t["start_s"], "end_s": t["end_s"]} for t in person_tracks],
            "appearances_count": len(person_tracks),
            "first_seen_ts": min(t["start_s"] for t in person_tracks),
            "last_seen_ts": max(t["end_s"] for t in person_tracks),
            "representative_crop": "person_analysis/" + representative["crop_path"] if representative else None,
            "representative_crop_id": representative["crop_id"] if representative else None,
            "valid_identity_crop_ids": [c["crop_id"] for t in person_tracks for c in data.evidence_by_track[t["track_id"]] if c["face_id"] not in excluded and c["evidence_status"] == "facemoe"],
            "fallback_crop_ids": [c["crop_id"] for c in crop_candidates if c["evidence_status"] == "fallback"],
            "attributes": data.persons.get(pid, {}).get("attributes", {}),
            "face_ids": [f["face_id"] for f in data.faces if f["face_id"] not in excluded and state["assignments"][str(f["track_id"])] == pid],
        })
    persons.sort(key=lambda p: (p["first_seen_ts"], p["person_id"]))
    stage_info = {}
    if data.staged:
        from .stage_state import status
        stage_info = status(data.base_root.parent)
    return {"persons": persons, "tracks": tracks, **stage_info,
            "unassigned_tracks": [t for t in tracks if t["person_id"] is None],
            "version": version(state), "analysis_id": data.analysis_id,
            "revision": state["revision"], "review_available": not data.staged or data.identity_id is not None,
            "excluded_face_observations": sorted(excluded), "legacy_evidence": data.legacy_evidence,
            "faces": [{**f, "excluded": f["face_id"] in excluded, "person_id": state["assignments"][str(f["track_id"]) ]} for f in data.faces]}


def current(job_dir: str | Path) -> dict:
    return project(*read(job_dir))


def _write(path: Path, state: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix="review_state-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def mutate(job_dir: str | Path, expected_version: str | None, operation: str, body: dict) -> dict:
    """Caller holds the session-manager lock through commit and cache refresh."""
    data, state = read(job_dir)
    if data.staged and not data.identity_id:
        raise ReviewError("Bitte zuerst Personen & Cluster ausführen.", 409)
    if data.staged and body.get("face_exclusions"):
        raise ReviewError("Face-Ausschlüsse bitte in Tracking & Gesichter ändern.", 409)
    if expected_version != version(state):
        raise ReviewError("Der Personenstand wurde geändert. Bitte neu laden und die Änderung erneut prüfen.", 409)
    state = copy.deepcopy(state)
    active = {pid for pid in state["assignments"].values() if pid is not None}

    def existing(pid: object) -> int:
        if type(pid) is not int or pid not in active:
            raise ReviewError("Zielperson nicht gefunden.", 404)
        return pid

    if operation == "assign":
        changes = body.get("changes")
        exclusions = body.get("face_exclusions", [])
        if not isinstance(changes, list) or not isinstance(exclusions, list) or not (changes or exclusions) or len(changes) > len(data.tracks):
            raise ReviewError("Keine gültigen Trackänderungen übermittelt.")
        seen = set()
        for change in changes:
            if not isinstance(change, dict):
                raise ReviewError("Ungültige Trackänderung.")
            tid = change.get("track_id")
            if type(tid) is not int or tid not in data.tracks or tid in seen:
                raise ReviewError("Unbekannter oder mehrfach übermittelter Track.")
            seen.add(tid)
            action = change.get("action")
            if action == "assign":
                target = existing(change.get("person_id"))
            elif action == "unassign":
                target = None
            elif action == "create_person":
                target = state["next_person_id"]
                state["next_person_id"] += 1
                state["persons"][str(target)] = {"name": f"Person {target}", "description": "", "function": ""}
            else:
                raise ReviewError("Unbekannte Trackaktion.")
            state["assignments"][str(tid)] = target
        excluded = set(state["excluded_face_observations"])
        seen_faces = set()
        for change in exclusions:
            if not isinstance(change, dict) or set(change) != {"face_id", "excluded"}:
                raise ReviewError("Ungültiger Face-Ausschluss. Einzelne Faces können nicht zugewiesen werden.")
            fid = change["face_id"]
            if type(fid) is not int or fid not in data.observations or fid in seen_faces or type(change["excluded"]) is not bool:
                raise ReviewError("Unbekannte oder mehrfach übermittelte Face-Beobachtung.")
            seen_faces.add(fid)
            if change["excluded"]:
                excluded.add(fid)
            else:
                excluded.discard(fid)
        state["excluded_face_observations"] = sorted(excluded)
    elif operation in {"merge", "delete"}:
        source = existing(body.get("source_person_id"))
        target = existing(body.get("target_person_id")) if operation == "merge" else None
        if source == target:
            raise ReviewError("Eine Person kann nicht mit sich selbst zusammengeführt werden.")
        if target is not None:
            for field in ("name", "description", "function"):
                if not state["persons"][str(target)][field]:
                    state["persons"][str(target)][field] = state["persons"][str(source)][field]
        for tid, assigned in state["assignments"].items():
            if assigned == source:
                state["assignments"][tid] = target
    elif operation == "metadata":
        pid = existing(body.get("person_id"))
        for field in ("name", "description"):
            if field in body:
                value = body[field]
                if not isinstance(value, str) or len(value) > 10000:
                    raise ReviewError("Name und Beschreibung müssen gültige Texte sein.")
                state["persons"][str(pid)][field] = value.strip()
    else:
        raise ReviewError("Unbekannte Personenaktion.")
    state["revision"] += 1
    result = project(data, state)
    try:
        if data.staged:
            from . import stage_state
            all_reviews = copy.deepcopy(stage_state.corrections(job_dir))
            all_reviews["identity_reviews"][data.identity_id] = state
            _write(stage_state.root(job_dir) / FILENAME, all_reviews)
        else:
            _write(data.root / FILENAME, state)
    except OSError as exc:
        raise ReviewError("Die Korrekturen konnten nicht gespeichert werden.", 500) from exc
    return result
