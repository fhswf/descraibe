"""Projiziert den aktuellen Personenstand und schreibt Änderungen direkt in persons.json."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import review_artifacts as artifacts
from . import stage_state
from .clustering import calculate_cluster_distance, create_track_distance_matrix
from .review_artifacts import ReviewError

FILENAME = "persons.json"


def _metadata(person: dict) -> dict:
    return {key: str(person.get(key) or "") for key in ("name", "function")}


def _version(data: artifacts.Artifacts) -> str:
    return f"{data.tracking_revision}:{data.identity_revision or 0}"


def _representative(data: artifacts.Artifacts, track_ids: list[int]) -> dict | None:
    def number(value):
        try:
            result = float(value)
            return max(0.0, result) if math.isfinite(result) else 0.0
        except (TypeError, ValueError):
            return 0.0

    faces = []
    for track_id in track_ids:
        for crop in data.evidence_by_track[track_id]:
            if crop["excluded"]:
                continue
            width, height = number(crop.get("width")), number(crop.get("height"))
            bbox = crop.get("face_bbox")
            if not width or not height or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                x1, y1, x2, y2 = map(float, bbox)
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
                continue
            face_width, face_height = min(width, x2) - max(0, x1), min(height, y2) - max(0, y1)
            if face_width <= 0 or face_height <= 0:
                continue
            try:
                data.crop_file(crop["crop_id"])
            except ReviewError:
                continue
            faces.append((crop, min(1.0, number(crop.get("face_confidence"))), face_width * face_height,
                          face_width / face_height))
    if faces:
        best_confidence = max(row[1] for row in faces)
        # Confidence chooses a usable detection; a wider face and larger face
        # area favor a clear, front-facing representative among near-ties.
        close = [row for row in faces if best_confidence - row[1] <= 0.0001 + 1e-12]
        return max(close, key=lambda row: (row[3], row[2], row[1], -row[0]["crop_id"]))[0]
    fallback = [crop for track_id in track_ids for crop in data.by_track[track_id]]
    for crop in sorted(fallback, key=lambda item: (item["width"] * item["height"], -item["crop_id"]), reverse=True):
        try:
            data.crop_file(crop["crop_id"])
            return crop
        except ReviewError:
            continue
    return None


def profile_crop(data, crop_id, track_ids):
    if type(crop_id) is not int:
        return None
    crop = data.crops.get(crop_id)
    if crop is None or crop["track_id"] not in track_ids or data.tracks[crop["track_id"]]["excluded"]:
        return None
    evidence = [face for face in data.faces if face["crop_id"] == crop_id]
    if evidence and not any(face["usable"] and not face["excluded"] for face in evidence):
        return None
    try:
        data.crop_file(crop_id)
    except ReviewError:
        return None
    return crop


def _attributes(data: artifacts.Artifacts) -> dict[int, dict]:
    path = data.root / "attributes.json"
    if data.assignment_revision is None or not path.is_file():
        return {}
    payload = stage_state.read_json(path)
    if payload.get("assignment_revision") != data.assignment_revision:
        return {}
    return {int(pid): row.get("attributes", {}) for pid, row in payload.get("persons", {}).items()}


def _person_similarities(data: artifacts.Artifacts, persons: list[dict], distance_data=None) -> list[dict]:
    if not data.track_references:
        return []

    if distance_data is None:
        active_track_ids = sorted({track_id for person in persons for track_id in person["track_ids"]
                                    if track_id in data.track_references})
        if not active_track_ids:
            return []
        track_ids = np.asarray(active_track_ids, dtype=np.int32)
        references = {track_id: data.track_references[track_id] for track_id in active_track_ids}
        distance_matrix = create_track_distance_matrix(track_ids, references)
    else:
        track_ids, distance_matrix = distance_data
    track_id_to_index = {int(track_id): index for index, track_id in enumerate(track_ids)}
    embedded_track_ids = set(track_id_to_index)

    cannot_link = set()
    frame_tracks = {}
    for face in data.faces:
        if not face["excluded"]:
            frame_tracks.setdefault(face["frame_number"], set()).add(face["track_id"])
    for track_ids in frame_tracks.values():
        track_ids = sorted(track_ids)
        for index, left in enumerate(track_ids):
            for right in track_ids[index + 1:]:
                cannot_link.add((left, right))

    similarities = []
    threshold = data.similarity_threshold
    try:
        distance_threshold = 1.0 - float(threshold)
    except (TypeError, ValueError):
        distance_threshold = None
    for index, left in enumerate(persons):
        for right in persons[index + 1:]:
            cluster_a = set(left["track_ids"]) & embedded_track_ids
            cluster_b = set(right["track_ids"]) & embedded_track_ids
            if not cluster_a or not cluster_b:
                continue
            blocked = False
            for track_a in left["track_ids"]:
                for track_b in right["track_ids"]:
                    key = (min(track_a, track_b), max(track_a, track_b))
                    if key in cannot_link:
                        blocked = True
            distance = calculate_cluster_distance(cluster_a, cluster_b, track_id_to_index, distance_matrix)
            similarities.append({
                "person_a": left["person_id"], "person_b": right["person_id"],
                "distance": distance,
                "suggested": not blocked and distance_threshold is not None and distance <= distance_threshold,
            })
    return sorted(similarities, key=lambda pair: (pair["distance"], pair["person_a"], pair["person_b"]))


def project(data: artifacts.Artifacts, distance_data=None) -> dict:
    tracks, grouped = [], {}
    for track_id, original in sorted(data.tracks.items()):
        person_id = data.assignments[track_id]
        review_crops = data.review_crops(track_id)
        track = {
            **original, "person_id": person_id, "crop_count": len(data.by_track[track_id]),
            "facemoe_observation_count": sum(bool(row["embedding_created"]) and not row["excluded"] for row in data.evidence_by_track[track_id]),
            "review_observation_count": len(review_crops),
            "review_mode": review_crops[0]["evidence_status"] if review_crops else "fallback",
        }
        tracks.append(track)
        if person_id is not None:
            grouped.setdefault(person_id, []).append(track)

    current_attributes = _attributes(data)
    persons = []
    for person_id, person_tracks in grouped.items():
        person_tracks.sort(key=lambda track: (track["start_s"], track["track_id"]))
        source = data.persons[person_id]
        track_ids = [track["track_id"] for track in person_tracks]
        manual = profile_crop(data, source.get("profile_crop_id"), track_ids)
        representative = manual or _representative(data, track_ids)
        crop_candidates = [crop for track_id in track_ids for crop in data.review_crops(track_id)]
        persons.append({
            "person_id": person_id, **_metadata(source), "track_ids": track_ids,
            "segments": [{key: track[key] for key in ("track_id", "scene_id", "start_s", "end_s")} for track in person_tracks],
            "appearances": [{"start_s": track["start_s"], "end_s": track["end_s"]} for track in person_tracks],
            "appearances_count": len(person_tracks), "first_seen_ts": min(track["start_s"] for track in person_tracks),
            "last_seen_ts": max(track["end_s"] for track in person_tracks),
            "representative_crop": "person_analysis/" + representative["crop_path"] if representative else None,
            "representative_crop_id": representative["crop_id"] if representative else None,
            "profile_crop_id": manual["crop_id"] if manual else None,
            "valid_identity_crop_ids": [crop["crop_id"] for track_id in track_ids for crop in data.evidence_by_track[track_id]
                                        if not crop["excluded"] and crop["embedding_created"]],
            "fallback_crop_ids": [crop["crop_id"] for crop in crop_candidates if crop["evidence_status"] == "fallback"],
            "attributes": current_attributes.get(person_id, {}),
            "face_ids": [face["face_id"] for face in data.faces if not face["excluded"] and data.assignments[face["track_id"]] == person_id],
        })
    persons.sort(key=lambda person: (person["first_seen_ts"], person["person_id"]))
    person_similarities = _person_similarities(data, persons, distance_data)
    identity_ready = data.identity_revision is not None
    return {
        "persons": persons, "tracks": tracks,
        "person_similarities": person_similarities,
        "unassigned_tracks": [track for track in tracks if track["person_id"] is None and not track["excluded"]],
        "version": _version(data), "analysis_id": data.analysis_id, "revision": data.identity_revision or 0,
        "review_available": identity_ready,
        "excluded_face_observations": sorted(face["face_id"] for face in data.faces if face["excluded"]),
        "faces": [{**face, "person_id": data.assignments[face["track_id"]]} for face in data.faces],
        **stage_state.status(data.root.parent),
    }


def current(job_dir: str | Path, distance_data=None) -> dict:
    return project(artifacts.load(job_dir), distance_data)


def _payload(data: artifacts.Artifacts, persons: dict[int, dict], revision: int, assignment_revision: int) -> dict:
    return {
        "schema_version": 1, "revision": revision, "assignment_revision": assignment_revision,
        "tracking_revision": data.tracking_revision,
        "similarity_threshold": data.similarity_threshold,
        "persons": [{"person_id": person_id, **_metadata(person), "track_ids": sorted(set(person["track_ids"])),
                     "profile_crop_id": person.get("profile_crop_id") if profile_crop(data, person.get("profile_crop_id"), person["track_ids"]) else None}
                    for person_id, person in sorted(persons.items()) if person["track_ids"]],
    }


def mutate(job_dir: str | Path, expected_version: str | None, operation: str, body: dict) -> dict:
    data = artifacts.load(job_dir)
    if data.identity_revision is None:
        raise ReviewError("Bitte zuerst Personenzuordnung ausführen.", 409)
    if expected_version != _version(data):
        raise ReviewError("Der Personenstand wurde geändert. Bitte neu laden.", 409)
    persons = {pid: {**_metadata(person), "profile_crop_id": person.get("profile_crop_id"), "track_ids": list(person["track_ids"])} for pid, person in data.persons.items()}

    def existing(person_id):
        if type(person_id) is not int or person_id not in persons:
            raise ReviewError("Person nicht gefunden.", 404)
        return person_id

    assignments_changed = False
    if operation == "assign":
        changes = body.get("changes")
        if not isinstance(changes, list) or not changes:
            raise ReviewError("Keine gültigen Trackänderungen übermittelt.")
        next_person_id = max(persons, default=0) + 1
        seen_tracks = set()
        for change in changes:
            track_id = change.get("track_id") if isinstance(change, dict) else None
            if type(track_id) is not int or track_id not in data.tracks or data.tracks[track_id]["excluded"]:
                raise ReviewError("Unbekannter oder ausgeschlossener Track.")
            if track_id in seen_tracks:
                raise ReviewError("Track mehrfach übermittelt.")
            seen_tracks.add(track_id)
            old = data.assignments[track_id]
            action = change.get("action")
            if action == "assign":
                target = existing(change.get("person_id"))
            elif action == "unassign":
                target = None
            elif action == "create_person":
                target = next_person_id; next_person_id += 1
                persons[target] = {"name": f"Person {target}", "function": "", "track_ids": []}
            else:
                raise ReviewError("Unbekannte Trackaktion.")
            if old == target:
                continue
            if old in persons:
                persons[old]["track_ids"] = [value for value in persons[old]["track_ids"] if value != track_id]
            if target is not None and track_id not in persons[target]["track_ids"]:
                persons[target]["track_ids"].append(track_id)
            data.assignments[track_id] = target
            assignments_changed = True
    elif operation == "merge":
        source, target = existing(body.get("source_person_id")), existing(body.get("target_person_id"))
        if source == target:
            raise ReviewError("Eine Person kann nicht mit sich selbst zusammengeführt werden.")
        for field in ("name", "function"):
            if not persons[target][field]:
                persons[target][field] = persons[source][field]
        if not persons[target].get("profile_crop_id"):
            persons[target]["profile_crop_id"] = persons[source].get("profile_crop_id")
        persons[target]["track_ids"] = sorted(set(persons[target]["track_ids"] + persons[source]["track_ids"]))
        del persons[source]
        assignments_changed = True
    elif operation == "delete":
        del persons[existing(body.get("source_person_id"))]
        assignments_changed = True
    elif operation == "metadata":
        person = persons[existing(body.get("person_id"))]
        changed = False
        for field in ("name", "function"):
            if field in body:
                value = body[field]
                if not isinstance(value, str) or len(value) > 10000:
                    raise ReviewError("Ungültige Personenmetadaten.")
                value = value.strip()
                changed |= person[field] != value
                person[field] = value
        if "profile_crop_id" in body:
            crop_id = body["profile_crop_id"]
            if crop_id is not None and profile_crop(data, crop_id, person["track_ids"]) is None:
                raise ReviewError("Profilbild muss ein gültiger Crop dieser Person sein.")
            changed |= person.get("profile_crop_id") != crop_id
            person["profile_crop_id"] = crop_id
        if not changed:
            return project(data)
    else:
        raise ReviewError("Unbekannte Personenaktion.")

    persons = {pid: person for pid, person in persons.items() if person["track_ids"]}
    revision = data.identity_revision + 1
    assignment_revision = data.assignment_revision + int(assignments_changed)
    stage_state.atomic_write(data.root / FILENAME, _payload(data, persons, revision, assignment_revision))
    if assignments_changed:
        (data.root / "attributes.json").unlink(missing_ok=True)
    return project(artifacts.load(job_dir))
