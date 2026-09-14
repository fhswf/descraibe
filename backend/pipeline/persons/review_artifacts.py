"""Read the existing analysis outputs. No model imports or image generation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from functools import lru_cache
from pathlib import Path


FILES = ("persons.json", "track_identities.csv", "person_crops.csv", "face_observations.csv")


class ReviewError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def available(job_dir: str | Path) -> bool:
    from . import stage_state
    if stage_state.active(job_dir):
        return True
    root = Path(job_dir) / "person_analysis"
    return all((root / name).is_file() for name in FILES[:3])


def _number(value: object) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite number")
    return result


def _rows(data: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";"))


class Artifacts:
    def __init__(self, root: Path, identity_root: Path | None = None, staged: bool = False):
        self.root = root.resolve()
        self.staged = staged
        self.identity_id = identity_root.parent.name if identity_root else None
        self.tracking_id = root.parent.name if staged else None
        self.base_root = root.parents[2] if staged else root
        self.crop_roots = {}
        raw = {}
        for name in FILES:
            source = identity_root if staged and name in FILES[:2] else root
            raw[name] = (source / name).read_bytes() if source and (source / name).is_file() else b""
        if staged:
            raw["tracks.json"] = (root / "tracks.json").read_bytes()
            raw["identity_result.json"] = (identity_root / "identity_result.json").read_bytes() if identity_root else b""
            raw["extra_crops"] = (identity_root / "person_crops.csv").read_bytes() if identity_root else b""
        self.analysis_id = hashlib.sha256(b"\0".join(raw.values())).hexdigest()
        payload = json.loads(raw["persons.json"].decode("utf-8-sig")) if raw["persons.json"] else {"persons": [], "unassigned_tracks": []}
        self.identity_report = json.loads(raw["identity_result.json"]) if staged and identity_root else None
        self.used_splits = (self.identity_report or {}).get("track_splits", {})
        self.used_exclusions = (self.identity_report or {}).get("excluded_face_observations", [])
        successful_faces = {r["face_id"] for r in self.identity_report["observations"] if r["status"] == "success"} if self.identity_report else set()
        self.persons = {int(p["person_id"]): p for p in payload["persons"]}
        self.tracks: dict[int, dict] = {}
        if staged:
            for track in (self.identity_report or {}).get("tracks", json.loads(raw["tracks.json"])["tracks"]):
                self._add_track(track)
        else:
            for person in payload["persons"]:
                for segment in person["segments"]:
                    self._add_track(segment)
            for track in payload["unassigned_tracks"]:
                self._add_track(track)
        self.assignments: dict[int, int | None] = {}
        for row in _rows(raw["track_identities.csv"]):
            tid = int(row["track_id"])
            target = int(row["person_id"]) if row["person_id"] else None
            if tid in self.assignments or tid not in self.tracks or (target is not None and target not in self.persons):
                raise ValueError("invalid track assignment")
            self.assignments[tid] = target
        if staged and identity_root is None:
            self.assignments = {tid: None for tid in self.tracks}
        if set(self.assignments) != set(self.tracks):
            raise ValueError("incomplete track assignments")
        self.crops: dict[int, dict] = {}
        self.by_track: dict[int, list[dict]] = {tid: [] for tid in self.tracks}
        by_path = {}
        crop_sources = [(root, raw["person_crops.csv"])] + ([(identity_root, raw["extra_crops"])] if identity_root else [])
        for crop_root, crop_bytes in crop_sources:
            for row in _rows(crop_bytes):
                tid, cid = int(row["track_id"]), int(row["crop_id"])
                if staged and crop_root == root:
                    from .track_segments import resolve_track
                    tid = resolve_track(tid, int(row["frame_number"]), {"track_splits": self.used_splits})
                if tid not in self.tracks or cid in self.crops:
                    raise ValueError("invalid crop reference")
                relative = row["crop_path"].replace("\\", "/")
                crop = {
                    "crop_id": cid, "track_id": tid, "scene_id": int(row["scene_id"]),
                    "frame_number": int(row["frame_number"]), "timestamp_s": _number(row["timestamp_s"]),
                    "crop_path": ((crop_root.relative_to(self.base_root) / relative).as_posix()), "width": int(row["x2"]) - int(row["x1"]),
                    "height": int(row["y2"]) - int(row["y1"]), "face_bbox": None,
                }
                self.crops[cid] = crop
                self.crop_roots[cid] = crop_root
                self.by_track[tid].append(crop)
                if crop_root == root:
                    by_path[relative] = crop
        self.faces = []
        self.observations: dict[int, dict] = {}
        self.evidence_by_track = {tid: [] for tid in self.tracks}
        self.legacy_evidence = False
        for row in _rows(raw["face_observations.csv"]):
            crop = by_path.get(row["person_crop_path"].replace("\\", "/"))
            if crop is None:
                continue
            bbox = [int(float(row[key])) for key in ("face_x1", "face_y1", "face_x2", "face_y2")]
            crop["face_bbox"] = bbox
            usable = row["face_usable"].lower() in {"true", "1"}
            aligned = row["alignment_ok"].lower() in {"true", "1"}
            verified = "embedding_created" in row
            created = row.get("embedding_created", "").lower() in {"true", "1"}
            try:
                confidence = _number(row.get("face_confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0
            if (staged and usable) or (not staged and usable and aligned and (created or not verified)):
                fid = int(row["face_id"])
                if fid in self.observations:
                    raise ValueError("duplicate observation")
                evidence_status = ("facemoe" if fid in successful_faces else "retinaface") if staged else ("facemoe" if verified else "legacy_unverified")
                try:
                    blur_score = max(0, _number(row.get("blur_score") or 0))
                except (TypeError, ValueError):
                    blur_score = 0
                observation = {**crop, "face_id": fid, "evidence_status": evidence_status,
                               "blur_score": blur_score, "face_confidence": confidence}
                self.observations[fid] = observation
                self.evidence_by_track[crop["track_id"]].append(observation)
                self.legacy_evidence |= not staged and not verified
            self.faces.append({
                "face_id": int(row["face_id"]), "track_id": crop["track_id"],
                "scene_id": crop["scene_id"], "frame_number": crop["frame_number"],
                "timestamp_s": crop["timestamp_s"],
                "crop_path": "person_analysis/" + crop["crop_path"],
                "person_crop_path": "person_analysis/" + crop["crop_path"],
                "bbox": bbox, "face_bbox": bbox,
                "usable": row["face_usable"].lower() in {"true", "1"},
                "confidence": confidence,
                "alignment_ok": row["alignment_ok"].lower() in {"true", "1"},
                "embedding_created": created if verified else None,
            })
        for crops in self.by_track.values():
            crops.sort(key=lambda c: (c["frame_number"], c["crop_id"]))
        for rows in self.evidence_by_track.values():
            rows.sort(key=lambda c: (c["frame_number"], c["face_id"]))

    def _add_track(self, row: dict) -> None:
        tid = int(row["track_id"])
        if tid in self.tracks:
            raise ValueError("duplicate track")
        start, end = _number(row["start_s"]), _number(row["end_s"])
        if start > end:
            raise ValueError("invalid interval")
        self.tracks[tid] = {"track_id": tid, "scene_id": int(row["scene_id"]), "start_s": start, "end_s": end,
                            "start_frame": row.get("start_frame"), "end_frame": row.get("end_frame"),
                            "source_track_id": row.get("source_track_id", tid), "is_split": row.get("is_split", False)}

    def crop_file(self, crop_id: int) -> Path:
        crop = self.crops.get(crop_id)
        if crop is None:
            raise ReviewError("Personencrop nicht gefunden.", 404)
        path = (self.base_root / crop["crop_path"]).resolve()
        if not path.is_relative_to((self.crop_roots[crop_id] / "person_crops").resolve()) or not path.is_file():
            raise ReviewError("Personencrop nicht gefunden.", 404)
        return path

    def sample(self, track_id: int, limit: int = 8) -> list[dict]:
        if track_id not in self.tracks:
            raise ReviewError("Track nicht gefunden.", 404)
        rows = self.by_track[track_id]
        count = min(max(1, limit), 24, len(rows))
        if count == 0:
            return []
        indices = [len(rows) // 2] if count == 1 else [round(i * (len(rows) - 1) / (count - 1)) for i in range(count)]
        return [dict(rows[i]) for i in indices]

    def review_crops(self, track_id: int, excluded: set[int]) -> list[dict]:
        if track_id not in self.tracks:
            raise ReviewError("Track nicht gefunden.", 404)
        evidence = self.evidence_by_track[track_id]
        if self.staged and self.identity_id:
            evidence = [c for c in evidence if c["face_id"] not in excluded]
            preferred = [c for c in evidence if c["evidence_status"] == "facemoe"]
            evidence = preferred or evidence
            if len(evidence) > 5:
                evidence = [evidence[round(i * (len(evidence) - 1) / 4)] for i in range(5)]
        if evidence:
            return [{**c, "excluded": c["face_id"] in excluded} for c in evidence]
        excluded_crops = {c["crop_id"] for fid, c in self.observations.items() if fid in excluded}
        candidates = [c for c in self.by_track[track_id] if c["crop_id"] not in excluded_crops]
        if len(candidates) > 5:
            candidates = [candidates[round(i * (len(candidates) - 1) / 4)] for i in range(5)]
        return [{**c, "face_bbox": None, "face_id": None, "excluded": False,
                 "evidence_status": "fallback"} for c in candidates]


@lru_cache(maxsize=8)
def _cached(root: str, signature: tuple) -> Artifacts:
    return Artifacts(Path(root))


def load(job_dir: str | Path) -> Artifacts:
    from . import stage_state
    pointer = stage_state.active(job_dir)
    if pointer:
        tracking = stage_state.run_path(job_dir, pointer["tracking_run"], "tracking")
        identity = stage_state.run_path(job_dir, pointer["identity_run"], "identities") if pointer["identity_run"] else None
        return _cached_stage(str(tracking), str(identity) if identity else None)
    root = Path(job_dir) / "person_analysis"
    if not available(job_dir):
        raise ReviewError("Für diesen Job liegen noch keine vollständigen Track-Daten vor.", 409)
    try:
        signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None for p in (root / name for name in FILES))
        return _cached(str(root.resolve()), signature)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReviewError("Die Track-Artefakte konnten nicht gelesen werden.", 409) from exc


@lru_cache(maxsize=8)
def _cached_stage(tracking, identity):
    try:
        return Artifacts(Path(tracking), Path(identity) if identity else None, staged=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReviewError("Stufen-Artefakte konnten nicht gelesen werden.", 409) from exc


def load_tracking(job_dir):
    from . import stage_state
    pointer = stage_state.active(job_dir)
    if pointer is None:
        raise ReviewError("Tracking fehlt.", 409)
    return _cached_stage(str(stage_state.run_path(job_dir, pointer["tracking_run"], "tracking")), None)
