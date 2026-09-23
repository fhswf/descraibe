"""Logische Tracks über unveränderten ByteTrack-Beobachtungen."""
from __future__ import annotations

import bisect
import csv
from functools import lru_cache
from pathlib import Path

from .review_artifacts import ReviewError

TIMELINE = "tracking_frames.csv"


class TimelineWriter:
    def __init__(self, root):
        self.stream = (Path(root) / TIMELINE).open("w", encoding="utf-8", newline="")
        self.writer = csv.writer(self.stream, delimiter=";")
        self.writer.writerow(["source_track_id", "frame_number", "scene_id", "x1", "y1", "x2", "y2", "confidence"])

    def observe(self, person, number, width, height):
        x1, y1, x2, y2 = map(float, person["bbox"])
        box = [max(0, min(width, round(x1))), max(0, min(height, round(y1))),
               max(0, min(width, round(x2))), max(0, min(height, round(y2)))]
        self.writer.writerow([int(person["track_id"]), int(number), int(person["scene_id"]), *box, person.get("confidence", "")])

    def close(self):
        self.stream.close()


@lru_cache(maxsize=4)
def timeline(root):
    path = Path(root) / TIMELINE
    if not path.is_file():
        raise ReviewError("Tracking-Zeitstruktur fehlt.", 409)
    result = {}
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter=";"):
            source, number = int(row["source_track_id"]), int(row["frame_number"])
            rows = result.setdefault(source, [])
            if rows and rows[-1]["frame_number"] >= number:
                raise ReviewError("Tracking-Zeitstruktur ist nicht eindeutig.", 409)
            rows.append({
                "source_track_id": source, "frame_number": number, "scene_id": int(row["scene_id"]),
                "bbox": [float(row[k]) for k in ("x1", "y1", "x2", "y2")],
                "confidence": float(row["confidence"]) if row["confidence"] else None,
            })
    return result


def initial_state(raw_tracks, fps, video_sha256, stats=None):
    tracks = [{
        "track_id": int(track["track_id"]), "source_track_id": int(track["track_id"]),
        "scene_id": int(track["scene_id"]), "start_frame": int(track["start_frame"]), "end_frame": int(track["end_frame"]),
        "start_s": float(track["start_s"]), "end_s": float(track["end_s"]),
        "observation_count": int(track["observation_count"]), "excluded": False,
    } for track in raw_tracks]
    return {
        "schema_version": 1, "revision": 1, "next_track_id": max((t["track_id"] for t in tracks), default=0) + 1,
        "fps": float(fps), "video_sha256": str(video_sha256), "stats": stats or {}, "tracks": tracks,
    }


def current_tracks(metadata, root=None):
    tracks = metadata.get("tracks")
    if not isinstance(tracks, list):
        raise ReviewError("Ungültiger Trackzustand.", 409)
    result, ids = [], set()
    for raw in tracks:
        try:
            track = {
                "track_id": int(raw["track_id"]), "source_track_id": int(raw["source_track_id"]), "scene_id": int(raw["scene_id"]),
                "start_frame": int(raw["start_frame"]), "end_frame": int(raw["end_frame"]),
                "start_s": float(raw["start_s"]), "end_s": float(raw["end_s"]),
                "observation_count": int(raw["observation_count"]), "excluded": bool(raw["excluded"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ReviewError("Ungültiger Trackzustand.", 409) from exc
        if track["track_id"] < 1 or track["track_id"] in ids or track["start_frame"] > track["end_frame"]:
            raise ReviewError("Ungültiger Trackzustand.", 409)
        ids.add(track["track_id"])
        result.append(track)
    counts = {}
    for track in result:
        counts[track["source_track_id"]] = counts.get(track["source_track_id"], 0) + 1
    result = [{**track, "is_split": counts[track["source_track_id"]] > 1} for track in result]
    if root is not None:
        _validate(result, root)
    return sorted(result, key=lambda t: (t["source_track_id"], t["start_frame"]))


def _validate(tracks, root):
    frames = timeline(str(root))
    for source in {track["source_track_id"] for track in tracks}:
        expected = [row["frame_number"] for row in frames.get(source, [])]
        covered = []
        for track in [t for t in tracks if t["source_track_id"] == source]:
            numbers = [n for n in expected if track["start_frame"] <= n <= track["end_frame"]]
            if not numbers or numbers[0] != track["start_frame"] or numbers[-1] != track["end_frame"] or len(numbers) != track["observation_count"]:
                raise ReviewError("Tracksegmente passen nicht zu den Trackingframes.", 409)
            covered.extend(numbers)
        if sorted(covered) != expected or len(covered) != len(set(covered)):
            raise ReviewError("Tracksegmente müssen alle Trackingframes genau einmal abdecken.", 409)


def resolve_track(source_track_id, frame_number, metadata):
    for track in current_tracks(metadata):
        if track["source_track_id"] == int(source_track_id) and track["start_frame"] <= int(frame_number) <= track["end_frame"]:
            return track["track_id"]
    raise ReviewError("Beobachtung liegt außerhalb der aktuellen Tracksegmente.", 409)


def apply_changes(root, metadata, changes):
    if not isinstance(changes, list):
        raise ReviewError("Ungültige Track-Änderungen.")
    if not changes:
        return metadata
    tracks = current_tracks(metadata, root)
    frames = timeline(str(root))
    next_id = int(metadata.get("next_track_id", max((t["track_id"] for t in tracks), default=0) + 1))

    for change in changes:
        if not isinstance(change, dict):
            raise ReviewError("Ungültige Track-Änderung.")
        action = change.get("action")
        if action == "set_excluded":
            track_id, excluded = change.get("track_id"), change.get("excluded")
            if type(track_id) is not int or type(excluded) is not bool or not any(t["track_id"] == track_id for t in tracks):
                raise ReviewError("Ungültiger Track-Ausschluss.")
            tracks = [{**t, "excluded": excluded} if t["track_id"] == track_id else t for t in tracks]
            continue
        if action == "undo_split":
            source = change.get("source_track_id")
            parts = [t for t in tracks if t["source_track_id"] == source]
            rows = frames.get(source, []) if type(source) is int else []
            if len(parts) < 2 or not rows:
                raise ReviewError("Kein Split für diesen Originaltrack vorhanden.")
            restored = {
                "track_id": source, "source_track_id": source, "scene_id": parts[0]["scene_id"],
                "start_frame": rows[0]["frame_number"], "end_frame": rows[-1]["frame_number"],
                "start_s": (rows[0]["frame_number"] - 1) / metadata["fps"], "end_s": (rows[-1]["frame_number"] - 1) / metadata["fps"],
                "observation_count": len(rows), "excluded": all(t["excluded"] for t in parts), "is_split": False,
            }
            tracks = [t for t in tracks if t["source_track_id"] != source] + [restored]
            continue
        if action != "split" or type(change.get("track_id")) is not int or type(change.get("before_frame")) is not int:
            raise ReviewError("Split benötigt Track-ID und einen Frame als Beginn des rechten Segments.")
        track = next((t for t in tracks if t["track_id"] == change["track_id"]), None)
        if track is None:
            raise ReviewError("Tracksegment existiert nicht mehr. Bitte neu laden.", 409)
        rows = [row for row in frames.get(track["source_track_id"], []) if track["start_frame"] <= row["frame_number"] <= track["end_frame"]]
        numbers = [row["frame_number"] for row in rows]
        cut = change["before_frame"]
        at = bisect.bisect_left(numbers, cut)
        if at == 0 or at == len(numbers) or numbers[at] != cut:
            raise ReviewError("Der Schnitt muss auf einem beobachteten Trackingframe liegen und zwei nichtleere Segmente erzeugen.")
        chunks = (numbers[:at], numbers[at:])
        replacements = []
        for new_id, chunk in zip((next_id, next_id + 1), chunks):
            replacements.append({
                "track_id": new_id, "source_track_id": track["source_track_id"], "scene_id": track["scene_id"],
                "start_frame": chunk[0], "end_frame": chunk[-1],
                "start_s": (chunk[0] - 1) / metadata["fps"], "end_s": (chunk[-1] - 1) / metadata["fps"],
                "observation_count": len(chunk), "excluded": track["excluded"], "is_split": True,
            })
        tracks = [t for t in tracks if t["track_id"] != track["track_id"]] + replacements
        next_id += 2

    fields = ("track_id", "source_track_id", "scene_id", "start_frame", "end_frame", "start_s", "end_s", "observation_count", "excluded")
    result = dict(metadata)
    result["tracks"] = [{key: track[key] for key in fields} for track in sorted(tracks, key=lambda t: (t["source_track_id"], t["start_frame"]))]
    result["next_track_id"] = next_id
    result["revision"] = int(metadata.get("revision", 0)) + 1
    current_tracks(result, root)
    return result


def spaced(rows, limit=5):
    if len(rows) <= limit:
        return list(rows)
    selected = set()
    first, last = rows[0]["frame_number"], rows[-1]["frame_number"]
    for i in range(limit):
        target = first + i * (last - first) / (limit - 1)
        selected.add(min((j for j in range(len(rows)) if j not in selected), key=lambda j: (abs(rows[j]["frame_number"] - target), j)))
    return [rows[i] for i in sorted(selected)]


def split_options(rows, visible_frames, fps):
    numbers = [row["frame_number"] for row in rows]
    result = []
    for frame in sorted(set(visible_frames))[1:]:
        at = bisect.bisect_left(numbers, frame)
        if 0 < at < len(numbers) and numbers[at] == frame:
            result.append({"before_frame": frame, "left_end_s": (numbers[at - 1] - 1) / fps, "right_start_s": (frame - 1) / fps})
    return result
