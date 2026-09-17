"""Liest ausschließlich den aktuellen Zustand unter person_analysis/."""
from __future__ import annotations

import csv
import math
from collections import OrderedDict
from pathlib import Path
from threading import RLock

TRACKING_FILES = ("tracks.json", "tracking_frames.csv", "person_crops.csv", "face_observations.csv")
FILES = (*TRACKING_FILES, "persons.json", "attributes.json")


class ReviewError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def available(job_dir: str | Path) -> bool:
    root = Path(job_dir) / "person_analysis"
    return all((root / name).is_file() for name in TRACKING_FILES)


def _bool(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _optional_bool(value) -> bool | None:
    return None if value is None or str(value).strip() == "" else _bool(value)


def _number(value, default=0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


class Artifacts:
    def __init__(self, root: Path, include_persons: bool = True):
        from . import stage_state, track_segments

        self.root = root.resolve()
        self.track_state = stage_state.read_json(self.root / "tracks.json")
        self.tracking_revision = int(self.track_state["revision"])
        self.tracks = {track["track_id"]: track for track in track_segments.current_tracks(self.track_state, self.root)}
        self._tracks_by_source = {}
        for track in self.tracks.values():
            self._tracks_by_source.setdefault(track["source_track_id"], []).append(track)
        self.persons, self.assignments = {}, {track_id: None for track_id in self.tracks}
        self.identity_revision = self.assignment_revision = None
        if include_persons and (self.root / "persons.json").is_file():
            self._load_persons(stage_state.read_json(self.root / "persons.json"))
        self.analysis_id = f"tracking-{self.tracking_revision}"
        self.crops, self.by_track = {}, {track_id: [] for track_id in self.tracks}
        self.faces, self.observations = [], {}
        self.evidence_by_track = {track_id: [] for track_id in self.tracks}
        self._load_crops()
        self._load_faces()

    def _load_persons(self, payload: dict) -> None:
        if payload.get("tracking_revision") != self.tracking_revision or not isinstance(payload.get("persons"), list):
            raise ReviewError("Personenzuordnungen passen nicht zum aktuellen Tracking.", 409)
        self.identity_revision = int(payload.get("revision", 0))
        self.assignment_revision = int(payload.get("assignment_revision", self.identity_revision))
        used = set()
        for raw in payload["persons"]:
            person_id = int(raw["person_id"])
            if person_id < 1 or person_id in self.persons:
                raise ReviewError("Ungültige Personenzuordnungen.", 409)
            person = {
                "person_id": person_id, "name": str(raw.get("name") or f"Person {person_id}"),
                "description": str(raw.get("description") or ""), "function": str(raw.get("function") or ""),
                "track_ids": [int(value) for value in raw.get("track_ids", [])],
                "profile_crop_id": raw.get("profile_crop_id"),
            }
            for track_id in person["track_ids"]:
                if track_id not in self.tracks or track_id in used or self.tracks[track_id]["excluded"]:
                    raise ReviewError("Ungültige Personenzuordnungen.", 409)
                used.add(track_id)
                self.assignments[track_id] = person_id
            self.persons[person_id] = person

    def _resolve_track(self, source: int, frame: int) -> int:
        # The current tracks have already been validated once in __init__.
        for track in self._tracks_by_source.get(source, []):
            if track["start_frame"] <= frame <= track["end_frame"]:
                return track["track_id"]
        raise ReviewError("Beobachtung liegt außerhalb der aktuellen Tracksegmente.", 409)

    def _load_crops(self) -> None:
        for row in _rows(self.root / "person_crops.csv"):
            crop_id = int(row["crop_id"])
            source = int(row["source_track_id"])
            frame = int(row["frame_number"])
            track_id = self._resolve_track(source, frame)
            crop = {
                "crop_id": crop_id, "track_id": track_id, "source_track_id": source, "scene_id": int(row["scene_id"]),
                "frame_number": frame, "timestamp_s": _number(row["timestamp_s"]),
                "crop_path": row["crop_path"].replace("\\", "/"), "crop_type": row.get("crop_type") or "",
                "width": int(row["x2"]) - int(row["x1"]), "height": int(row["y2"]) - int(row["y1"]),
                "person_bbox": [int(row[key]) for key in ("x1", "y1", "x2", "y2")], "face_bbox": None,
            }
            self.crops[crop_id] = crop
            self.by_track[track_id].append(crop)
        for rows in self.by_track.values():
            rows.sort(key=lambda row: (row["frame_number"], row["crop_id"]))

    def _load_faces(self) -> None:
        crops_by_path = {crop["crop_path"]: crop for crop in self.crops.values()}
        for row in _rows(self.root / "face_observations.csv"):
            face_id, source, frame = int(row["face_id"]), int(row["source_track_id"]), int(row["frame_number"])
            track_id = self._resolve_track(source, frame)
            crop = crops_by_path.get(row.get("person_crop_path", "").replace("\\", "/"))
            bbox = [int(float(row[key])) for key in ("face_x1", "face_y1", "face_x2", "face_y2")]
            if crop is not None:
                crop["face_bbox"] = bbox
            face = {
                "face_id": face_id, "track_id": track_id, "source_track_id": source, "scene_id": int(row["scene_id"]),
                "frame_number": frame, "timestamp_s": _number(row["timestamp_s"]),
                "crop_id": crop["crop_id"] if crop else None, "crop_path": crop["crop_path"] if crop else None,
                "face_bbox": bbox, "usable": _bool(row.get("face_usable")), "excluded": _bool(row.get("excluded")),
                "confidence": _number(row.get("face_confidence")), "blur_score": max(0.0, _number(row.get("blur_score"))),
                "alignment_ok": _optional_bool(row.get("alignment_ok")),
                "embedding_created": _optional_bool(row.get("embedding_created")),
            }
            self.faces.append(face)
            if not face["usable"] or crop is None:
                continue
            observation = {
                **crop, "face_id": face_id, "face_bbox": bbox, "usable": True, "excluded": face["excluded"],
                "blur_score": face["blur_score"], "face_confidence": face["confidence"],
                "alignment_ok": face["alignment_ok"], "embedding_created": face["embedding_created"],
                "evidence_status": "facemoe" if face["embedding_created"] else "retinaface",
            }
            self.observations[face_id] = observation
            self.evidence_by_track[track_id].append(observation)
        for rows in self.evidence_by_track.values():
            rows.sort(key=lambda row: (row["frame_number"], row["face_id"]))

    def crop_file(self, crop_id: int) -> Path:
        crop = self.crops.get(int(crop_id))
        if crop is None:
            raise ReviewError("Personencrop nicht gefunden.", 404)
        path = (self.root / crop["crop_path"]).resolve()
        if not path.is_relative_to((self.root / "person_crops").resolve()) or not path.is_file():
            raise ReviewError("Personencrop nicht gefunden.", 404)
        return path

    @staticmethod
    def _sample(rows: list[dict], limit: int) -> list[dict]:
        limit = max(1, int(limit))
        if len(rows) <= limit:
            return [dict(row) for row in rows]
        if limit == 1:
            return [dict(rows[len(rows) // 2])]
        return [dict(rows[round(i * (len(rows) - 1) / (limit - 1))]) for i in range(limit)]

    def review_crops(self, track_id: int, limit: int = 5, include_excluded: bool = False) -> list[dict]:
        if track_id not in self.tracks:
            raise ReviewError("Track nicht gefunden.", 404)
        all_evidence = self.evidence_by_track[track_id]
        evidence = all_evidence if include_excluded else [row for row in all_evidence if not row["excluded"]]
        if evidence:
            facemoe = [row for row in evidence if row["embedding_created"]]
            return self._sample(facemoe or evidence, limit)
        excluded_crop_ids = set() if include_excluded else {row["crop_id"] for row in all_evidence if row["excluded"]}
        fallback = [{**crop, "face_id": None, "excluded": False, "evidence_status": "fallback"}
                    for crop in self.by_track[track_id] if crop["crop_id"] not in excluded_crop_ids]
        # Tracking and Identity may contain a fallback crop of the same frame.
        unique_frames = {crop["frame_number"]: crop for crop in fallback}
        return self._sample(list(unique_frames.values()), limit)

    def tracking_crops(self, track_id: int) -> list[dict]:
        """All quality-usable faces, including exclusions, independent of Identity."""
        evidence = self.evidence_by_track[track_id]
        if evidence:
            return [{**row, "evidence_status": "retinaface"} for row in evidence]
        return self.review_crops(track_id, limit=5, include_excluded=True)


def load(job_dir: str | Path) -> Artifacts:
    if not available(job_dir):
        raise ReviewError("Für diesen Job liegen noch keine vollständigen Tracking-Daten vor.", 409)
    try:
        return Artifacts(Path(job_dir) / "person_analysis", include_persons=True)
    except ReviewError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReviewError("Die Personenanalyse konnte nicht gelesen werden.", 409) from exc


def load_tracking(job_dir: str | Path) -> Artifacts:
    if not available(job_dir):
        raise ReviewError("Tracking fehlt.", 409)
    try:
        return Artifacts(Path(job_dir) / "person_analysis", include_persons=False)
    except ReviewError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReviewError("Die Tracking-Daten konnten nicht gelesen werden.", 409) from exc


def read_preview_frame(video_path: str | Path, frame_number: int):
    """Read a 1-based review frame; retry sequentially if seeking visibly fails.

    Reported positions cannot prove pixel accuracy for every codec/container.
    This is only used for previews, never for ML or persisted crop selection.
    """
    import cv2

    if frame_number < 1:
        raise ReviewError("Originalframe nicht verfügbar.", 404)
    capture = cv2.VideoCapture(str(video_path))
    try:
        try:
            if capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number - 1):
                ok, frame = capture.read()
                position = capture.get(cv2.CAP_PROP_POS_FRAMES)
                if ok and frame is not None and abs(position - frame_number) < 0.5:
                    return frame
        except cv2.error:
            pass
    finally:
        capture.release()

    # Reopen rather than relying on another seek to reset a problematic decoder.
    capture = cv2.VideoCapture(str(video_path))
    try:
        for _ in range(frame_number):
            if not capture.grab():
                raise ReviewError("Originalframe nicht verfügbar.", 404)
        ok, frame = capture.retrieve()
        if not ok or frame is None:
            raise ReviewError("Originalframe nicht verfügbar.", 404)
        return frame
    except cv2.error as exc:
        raise ReviewError("Originalframe nicht verfügbar.", 404) from exc
    finally:
        capture.release()


# Only read endpoints use these instances. Writers keep using fresh load() data.
# One current entry per job, at most four jobs; nothing is persisted to disk.
_preview_cache: OrderedDict = OrderedDict()
_preview_lock = RLock()


def _preview_signature(root: Path) -> tuple:
    result = []
    for name in (*TRACKING_FILES, "persons.json"):
        try:
            stat = (root / name).stat()
            result.append((stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino))
        except FileNotFoundError:
            result.append(None)
    return tuple(result)


def load_for_preview(job_dir: str | Path) -> Artifacts:
    """Read-only cached metadata; detect replacements, edits and deletions."""
    from . import track_segments

    root = (Path(job_dir) / "person_analysis").resolve()
    with _preview_lock:
        for _ in range(2):
            signature = _preview_signature(root)
            entry = _preview_cache.get(root)
            if entry is not None and entry[0] == signature:
                _preview_cache.move_to_end(root)
                return entry[1]
            _preview_cache.pop(root, None)
            track_segments.timeline.cache_clear()
            data = load(root.parent)
            if signature != _preview_signature(root):
                continue
            _preview_cache[root] = (signature, data)
            while len(_preview_cache) > 4:
                _preview_cache.popitem(last=False)
            return data
    raise ReviewError("Tracking-Daten wurden geändert. Bitte neu laden.", 409)
