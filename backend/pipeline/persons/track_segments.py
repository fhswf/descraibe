"""Logical segments over immutable observed tracking frames. No ML imports."""
import bisect
import copy
import csv
from functools import lru_cache
from pathlib import Path
from .review_artifacts import ReviewError

TIMELINE = "tracking_frames.csv"


class TimelineWriter:
    def __init__(self, root):
        self.stream = (Path(root) / TIMELINE).open("w", encoding="utf-8", newline="")
        self.writer = csv.writer(self.stream, delimiter=";")
        self.writer.writerow(["track_id", "frame_number", "scene_id", "x1", "y1", "x2", "y2", "confidence"])

    def observe(self, person, number, width, height):
        x1, y1, x2, y2 = map(float, person["bbox"])
        box = [max(0, min(width, round(x1))), max(0, min(height, round(y1))),
               max(0, min(width, round(x2))), max(0, min(height, round(y2)))]
        self.writer.writerow([int(person["track_id"]), number, int(person["scene_id"]), *box, person.get("confidence", "")])

    def close(self):
        self.stream.close()


@lru_cache(maxsize=4)
def timeline(root):
    result = {}
    with (Path(root) / TIMELINE).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter=";"):
            tid, number = int(row["track_id"]), int(row["frame_number"])
            rows = result.setdefault(tid, [])
            if rows and rows[-1]["frame_number"] >= number:
                raise ReviewError("Tracking-Zeitstruktur ist nicht eindeutig.", 409)
            rows.append({"track_id": tid, "frame_number": number, "scene_id": int(row["scene_id"]),
                         "bbox": [float(row[k]) for k in ("x1", "y1", "x2", "y2")],
                         "confidence": float(row["confidence"]) if row["confidence"] else None})
    return result


def effective_tracks(metadata, review, root=None):
    splits = review.get("track_splits", {})
    originals = {int(t["track_id"]): t for t in metadata["tracks"]}
    if not isinstance(splits, dict) or any(k not in {str(tid) for tid in originals} for k in splits):
        raise ReviewError("Ungültige Track-Splits.", 409)
    result, used = [], set(originals)
    for source, original in originals.items():
        segments = splits.get(str(source))
        if segments is None:
            result.append({**original, "source_track_id": source, "is_split": False})
            continue
        if not isinstance(segments, list) or len(segments) < 2:
            raise ReviewError("Ein Split muss mindestens zwei Segmente enthalten.", 409)
        previous = None
        for segment in segments:
            try:
                tid, start, end = (segment[k] for k in ("track_id", "start_frame", "end_frame"))
                if any(type(v) is not int for v in (tid, start, end)) or tid in used or tid < 1 or start > end or (previous is not None and start <= previous):
                    raise ValueError()
                used.add(tid)
                previous = end
                result.append({**original, "track_id": tid, "source_track_id": source, "is_split": True,
                               "start_frame": start, "end_frame": end,
                               "start_s": (start - 1) / metadata["fps"], "end_s": (end - 1) / metadata["fps"]})
            except (KeyError, ValueError, TypeError) as exc:
                raise ReviewError("Ungültige Segmentgrenzen.", 409) from exc
        if segments[0]["start_frame"] != original["start_frame"] or segments[-1]["end_frame"] != original["end_frame"]:
            raise ReviewError("Track-Splits decken den Originaltrack nicht ab.", 409)
    if splits and root is not None:
        if not (Path(root) / TIMELINE).is_file():
            raise ReviewError("Die Zeitstruktur für gespeicherte Splits fehlt.", 409)
        frame_index = timeline(str(root))
        for source in map(int, splits):
            rows = frame_index.get(source, [])
            covered = []
            for track in (t for t in result if t["source_track_id"] == source):
                numbers = [r["frame_number"] for r in rows if track["start_frame"] <= r["frame_number"] <= track["end_frame"]]
                if not numbers or numbers[0] != track["start_frame"] or numbers[-1] != track["end_frame"]:
                    raise ReviewError("Segmentgrenze entspricht keinem Trackingframe.", 409)
                track["observation_count"] = len(numbers)
                covered.extend(numbers)
            if covered != [r["frame_number"] for r in rows]:
                raise ReviewError("Track-Splits müssen alle Trackingframes genau einmal abdecken.", 409)
    return result


def resolve_track(source, number, review):
    segments = review.get("track_splits", {}).get(str(source))
    if segments is None:
        return source
    for segment in segments:
        if segment["start_frame"] <= number <= segment["end_frame"]:
            return segment["track_id"]
    raise ReviewError("Beobachtung liegt außerhalb der Tracksegmente.", 409)


def apply_changes(root, metadata, state, changes):
    if not isinstance(changes, list):
        raise ReviewError("Ungültige Track-Änderungen.")
    if not changes:
        return state
    if not (Path(root) / TIMELINE).is_file():
        raise ReviewError("Dieser ältere Lauf hat kein vollständiges Frame-Protokoll. Für präzise Splits Tracking erneut ausführen.", 409)
    frames = timeline(str(root))
    result = copy.deepcopy(state)
    splits = result.setdefault("track_splits", {})
    next_id = result.get("next_segment_id", max((t["track_id"] for t in metadata["tracks"]), default=0) + 1)
    for change in changes:
        if not isinstance(change, dict):
            raise ReviewError("Ungültige Split-Änderung.")
        if change.get("action") == "undo_split" and set(change) == {"action", "source_track_id"}:
            source = change["source_track_id"]
            if type(source) is not int or str(source) not in splits:
                raise ReviewError("Kein Split für diesen Originaltrack vorhanden.")
            del splits[str(source)]
            continue
        if change.get("action") != "split" or set(change) != {"action", "track_id", "before_frame"} or type(change["track_id"]) is not int or type(change["before_frame"]) is not int:
            raise ReviewError("Split benötigt Track-ID und einen Frame als Beginn des rechten Segments.")
        tracks = {t["track_id"]: t for t in effective_tracks(metadata, result, root)}
        track = tracks.get(change["track_id"])
        if track is None:
            raise ReviewError("Tracksegment existiert nicht mehr. Bitte neu laden.", 409)
        source, cut = track["source_track_id"], change["before_frame"]
        numbers = [r["frame_number"] for r in frames[source] if track["start_frame"] <= r["frame_number"] <= track["end_frame"]]
        index = bisect.bisect_left(numbers, cut)
        if index == 0 or index == len(numbers) or numbers[index] != cut:
            raise ReviewError("Der Schnitt muss auf einem beobachteten Trackingframe liegen und zwei nichtleere Segmente erzeugen.")
        if type(next_id) is not int or next_id <= max(tracks, default=0):
            raise ReviewError("Ungültiger Segment-ID-Zähler.", 409)
        replacement = [{"track_id": next_id, "start_frame": numbers[0], "end_frame": numbers[index-1]},
                       {"track_id": next_id+1, "start_frame": numbers[index], "end_frame": numbers[-1]}]
        previous = splits.get(str(source), [{k: track[k] for k in ("track_id", "start_frame", "end_frame")}])
        splits[str(source)] = [new for old in previous for new in (replacement if old["track_id"] == track["track_id"] else [old])]
        next_id += 2
    result["next_segment_id"] = next_id
    effective_tracks(metadata, result, root)
    return result


def spaced(rows, limit=5):
    if len(rows) <= limit:
        return list(rows)
    first, last = rows[0]["frame_number"], rows[-1]["frame_number"]
    selected = set()
    for i in range(limit):
        target = first + i * (last-first) / (limit-1)
        selected.add(min((j for j in range(len(rows)) if j not in selected), key=lambda j: (abs(rows[j]["frame_number"] - target), j)))
    return [rows[i] for i in sorted(selected)]


def review_tracks(data, metadata, review):
    """Live step-1 projection; automatic files and completed identities stay frozen."""
    tracks = {t["track_id"]: {**t, "observations": [], "quality_face_count": 0, "split_options": []}
              for t in effective_tracks(metadata, review, data.root)}
    excluded = set(review["excluded_face_observations"])
    for source in data.tracks:
        for crop in data.review_crops(source, excluded):
            tid = resolve_track(source, crop["frame_number"], review)
            tracks[tid]["observations"].append({**crop, "track_id": tid, "source_track_id": source})
        for crop in data.evidence_by_track[source]:
            tracks[resolve_track(source, crop["frame_number"], review)]["quality_face_count"] += 1
    frames = timeline(str(data.root)) if (data.root / TIMELINE).is_file() else None
    for track in tracks.values():
        if frames is None:
            continue
        rows = [r for r in frames.get(track["source_track_id"], []) if track["start_frame"] <= r["frame_number"] <= track["end_frame"]]
        numbers = [r["frame_number"] for r in rows]
        track["observation_count"] = len(rows)
        # Face-free children get five body previews on demand, with no extra review JPEGs.
        if track["is_split"] and not track["quality_face_count"]:
            track["observations"] = [{"crop_id": -r["frame_number"], "track_id": track["track_id"], "source_track_id": track["source_track_id"],
                "frame_number": r["frame_number"], "timestamp_s": (r["frame_number"]-1)/metadata["fps"],
                "width": max(1, round(r["bbox"][2])-round(r["bbox"][0])), "height": max(1, round(r["bbox"][3])-round(r["bbox"][1])),
                "face_bbox": None, "face_id": None, "excluded": False, "evidence_status": "fallback", "preview_frame": True}
                for r in spaced(rows)]
        visible_frames = sorted({crop["frame_number"] for crop in track["observations"]})

        for frame_number in visible_frames[1:]:
            at = bisect.bisect_left(numbers, frame_number)
            if at > 0 and at < len(numbers) and numbers[at] == frame_number:
                track["split_options"].append({"before_frame": numbers[at], "left_end_s": (numbers[at-1]-1)/metadata["fps"],
                                            "right_start_s": (numbers[at]-1)/metadata["fps"]})
    return sorted(tracks.values(), key=lambda t: (t["source_track_id"], t["start_s"]))
