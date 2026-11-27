"""Face-sample selection and alignment helpers for persisted tracking crops."""
from __future__ import annotations

import json
import random
from pathlib import Path

import cv2
import numpy as np


MAX_FACE_SAMPLES_PER_TRACK = 5


def align_observation_face(image, face_row: dict, crop_row: dict, align_face):
    """Align a face using its saved person crop and tracking geometry."""
    face_image, origin_x, origin_y = extract_face_crop(image, face_row, crop_row)
    if face_image is None:
        return None
    person_x1, person_y1 = int(crop_row["x1"]), int(crop_row["y1"])
    points = np.asarray(json.loads(face_row["landmarks"]), dtype=np.float32)
    if points.shape != (5, 2):
        return None
    points -= np.asarray([person_x1 + origin_x, person_y1 + origin_y], dtype=np.float32)
    return align_face(face_image, points)


def extract_face_crop(image, face_row: dict, crop_row: dict):
    """Crop the stored RetinaFace margin region and return its crop origin."""
    face_x1, face_y1, face_x2, face_y2 = map(int, json.loads(face_row["face_crop_box"]))
    person_x1, person_y1 = int(crop_row["x1"]), int(crop_row["y1"])
    height, width = image.shape[:2]
    x1 = max(0, min(width - 1, face_x1 - person_x1))
    y1 = max(0, min(height - 1, face_y1 - person_y1))
    x2 = min(width, face_x2 - person_x1)
    y2 = min(height, face_y2 - person_y1)
    if x2 <= x1 or y2 <= y1:
        return None, 0, 0
    return image[y1:y2, x1:x2].copy(), x1, y1


def _sample_indices(count: int, limit: int = MAX_FACE_SAMPLES_PER_TRACK) -> list[int]:
    selected_count = min(count, limit)
    if selected_count <= 1:
        return [0] if count else []
    return [index * (count - 1) // (selected_count - 1) for index in range(selected_count)]


def select_temporal_observations(observations: list[dict], limit: int = MAX_FACE_SAMPLES_PER_TRACK) -> list[dict]:
    ordered = sorted(observations, key=lambda row: (int(row["frame_number"]), int(row["face_id"])))
    return [ordered[index] for index in _sample_indices(len(ordered), limit)]


class TrackingFaceSampleCollector:
    """Keep a deterministic, bounded reservoir of face images per track."""

    def __init__(self, limit: int = MAX_FACE_SAMPLES_PER_TRACK) -> None:
        self.limit = max(1, int(limit))
        self._tracks: dict[int, dict] = {}

    def observe(self, track_id: int, frame_number: int, face_id: int, image) -> None:
        track_id = int(track_id)
        state = self._tracks.setdefault(track_id, {
            "seen": 0, "rng": random.Random(track_id), "samples": [],
        })
        state["seen"] += 1
        sample = (int(frame_number), int(face_id), image.copy())
        if len(state["samples"]) < self.limit:
            state["samples"].append(sample)
            return
        slot = state["rng"].randrange(state["seen"])
        if slot < self.limit:
            state["samples"][slot] = sample

    def save(self, scene_dir: str | Path) -> dict[int, str]:
        scene_dir = Path(scene_dir)
        paths = {}
        for track_id, state in sorted(self._tracks.items()):
            for frame_number, face_id, image in sorted(state["samples"], key=lambda item: (item[0], item[1])):
                relative = Path("person_crops") / ".face_samples" / f"track_{track_id:04d}" / f"face_{frame_number:08d}_{face_id:06d}.png"
                target = scene_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(target), image):
                    raise RuntimeError("Gesichtsprobe konnte nicht gespeichert werden.")
                paths[face_id] = relative.as_posix()
        return paths


def load_aligned_face(root: str | Path, face_row: dict, crop_by_path: dict[str, dict]):
    """Align a selected observation from its saved tracking crop."""
    root = Path(root)
    person_crop_path = str(face_row.get("person_crop_path") or "").replace("\\", "/")
    sample_path = str(face_row.get("face_sample_path") or "").replace("\\", "/")
    if sample_path:
        source = (root / sample_path).resolve()
        if source.is_relative_to((root / "person_crops" / ".face_samples").resolve()) and source.is_file():
            image = cv2.imread(str(source), cv2.IMREAD_COLOR)
            if image is None:
                return None
            from .face_detection import align_face

            try:
                points = np.asarray(json.loads(face_row["landmarks"]), dtype=np.float32)
                if points.shape != (5, 2):
                    return None
                face_x1, face_y1, _face_x2, _face_y2 = map(int, json.loads(face_row["face_crop_box"]))
                points -= np.asarray([face_x1, face_y1], dtype=np.float32)
                return align_face(image, points)
            except Exception:
                return None
    crop_path = sample_path if sample_path in crop_by_path else person_crop_path
    crop_row = crop_by_path.get(crop_path)
    if crop_row is None:
        return None
    source = (root / crop_path).resolve()
    if not source.is_relative_to((root / "person_crops").resolve()):
        return None
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        return None
    from .face_detection import align_face

    try:
        return align_observation_face(image, face_row, crop_row, align_face)
    except Exception:
        return None
