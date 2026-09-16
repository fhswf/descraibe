from __future__ import annotations

import csv
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

FIELDS = [
    "crop_id", "source_track_id", "scene_id", "frame_number", "timestamp_s",
    "x1", "y1", "x2", "y2", "person_confidence", "crop_type", "crop_path",
]


def _clip_bbox(bbox, width: int, height: int) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(width - 1, int(round(x1))))
    y1 = max(0, min(height - 1, int(round(y1))))
    x2 = max(0, min(width, int(round(x2))))
    y2 = max(0, min(height, int(round(y2))))
    return None if x2 <= x1 or y2 <= y1 else (x1, y1, x2, y2)


def _encode_crop(frame: np.ndarray, bbox, quality: int) -> tuple[bytes, tuple[int, int, int, int]] | None:
    if frame is None or frame.size == 0:
        return None
    clipped = _clip_bbox(bbox, frame.shape[1], frame.shape[0])
    if clipped is None:
        return None
    x1, y1, x2, y2 = clipped
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    ok, encoded = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("Personencrop konnte nicht codiert werden.")
    return encoded.tobytes(), clipped


def read_manifest(root: str | Path) -> list[dict]:
    path = Path(root) / "person_crops.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def write_manifest(root: str | Path, rows: list[dict]) -> None:
    path = Path(root) / "person_crops.csv"
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PersonCropWriter:
    def __init__(self, output_dir: str | Path, fps: float, jpeg_quality: int = 95) -> None:
        if fps <= 0:
            raise ValueError("fps muss größer als 0 sein.")
        self.output_dir = Path(output_dir)
        self.crops_dir = self.output_dir / "person_crops"
        self.manifest_path = self.output_dir / "person_crops.csv"
        self.fps = float(fps)
        self.jpeg_quality = int(jpeg_quality)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.crops_dir, ignore_errors=True)
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.manifest_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS, delimiter=";")
        self._writer.writeheader()
        self._crop_id = 0

    @property
    def crop_count(self) -> int:
        return self._crop_id

    def save(self, frame_bgr: np.ndarray, source_track_id: int, scene_id: int, frame_number: int,
             bbox, confidence: float | None = None, crop_type: str = "face_evidence",
             filename_prefix: str = "frame") -> Path | None:
        result = _encode_crop(frame_bgr, bbox, self.jpeg_quality)
        if result is None:
            return None
        encoded, (x1, y1, x2, y2) = result
        source_track_id, scene_id, frame_number = int(source_track_id), int(scene_id), int(frame_number)
        track_dir = self.crops_dir / f"track_{source_track_id:04d}"
        track_dir.mkdir(parents=True, exist_ok=True)
        path = track_dir / f"{filename_prefix}_{frame_number:08d}.jpg"
        path.write_bytes(encoded)
        self._crop_id += 1
        self._writer.writerow({
            "crop_id": self._crop_id, "source_track_id": source_track_id, "scene_id": scene_id,
            "frame_number": frame_number, "timestamp_s": (frame_number - 1) / self.fps,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "person_confidence": "" if confidence is None else float(confidence),
            "crop_type": crop_type, "crop_path": path.relative_to(self.output_dir).as_posix(),
        })
        return path

    def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            self._file.close()


class FallbackCropCollector:
    """Behält nur kompakte Trackingdaten und speichert höchstens fünf Crops je Track."""
    def __init__(self):
        self.observations = defaultdict(list)
        self.with_faces = set()

    def observe(self, person: dict, frame_number: int) -> None:
        track_id = int(person["track_id"])
        if track_id not in self.with_faces:
            self.observations[track_id].append((
                int(frame_number), int(person["scene_id"]), tuple(float(v) for v in person["bbox"]), person.get("confidence")
            ))

    def face_succeeded(self, track_id: int) -> None:
        self.with_faces.add(int(track_id))
        self.observations.pop(int(track_id), None)

    def selected(self, limit: int = 5) -> dict[int, list[tuple]]:
        by_frame = defaultdict(list)
        for track_id, rows in self.observations.items():
            if not rows:
                continue
            count = min(limit, len(rows))
            indices = set()
            for i in range(count):
                target = rows[0][0] if count == 1 else rows[0][0] + i * (rows[-1][0] - rows[0][0]) / (count - 1)
                index = min((j for j in range(len(rows)) if j not in indices), key=lambda j: (abs(rows[j][0] - target), j))
                indices.add(index)
            for index in sorted(indices):
                number, scene, bbox, confidence = rows[index]
                by_frame[number].append((track_id, scene, bbox, confidence))
        return by_frame

    def save(self, video_path: Path, writer: PersonCropWriter, progress_cb=None) -> int:
        selected = self.selected()
        self.observations.clear()
        if not selected:
            return 0
        capture = cv2.VideoCapture(str(video_path))
        before = writer.crop_count
        try:
            if not capture.isOpened():
                raise RuntimeError("Video konnte für Fallback-Crops nicht geöffnet werden.")
            last = max(selected)
            for number in range(1, last + 1):
                if not capture.grab():
                    raise RuntimeError(f"Fallback-Frame {number} konnte nicht gelesen werden.")
                if number in selected:
                    ok, frame = capture.retrieve()
                    if not ok:
                        raise RuntimeError(f"Fallback-Frame {number} konnte nicht dekodiert werden.")
                    for track_id, scene, bbox, confidence in selected[number]:
                        writer.save(frame, track_id, scene, number, bbox, confidence, "tracking_fallback", "fallback")
                if progress_cb and (number % 300 == 0 or number == last):
                    progress_cb("Fallback-Personencrops werden gespeichert ...", number, last)
        finally:
            capture.release()
        return writer.crop_count - before


def refresh_identity_fallbacks(video_path: str | Path, root: str | Path, tracks: list[dict],
                               track_ids: set[int], fps: float, progress_cb=None) -> int:
    """Ersetzt nur die aktuell benötigten Identity-Fallback-Crops."""
    from .track_segments import spaced, timeline

    root, video_path = Path(root), Path(video_path)
    rows = read_manifest(root)
    kept = [row for row in rows if row.get("crop_type") != "identity_fallback"]
    old_paths = {row["crop_path"] for row in rows if row.get("crop_type") == "identity_fallback"}
    next_id = max((int(row["crop_id"]) for row in rows), default=0)
    by_id = {track["track_id"]: track for track in tracks}
    frames = timeline(str(root))
    selected = defaultdict(list)
    for track_id in sorted(track_ids):
        track = by_id[track_id]
        candidates = [row for row in frames.get(track["source_track_id"], [])
                      if track["start_frame"] <= row["frame_number"] <= track["end_frame"]]
        for row in spaced(candidates):
            selected[row["frame_number"]].append((track, row))

    temp = Path(tempfile.mkdtemp(prefix=".identity_crops_", dir=root))
    generated, new_paths = [], set()
    capture = cv2.VideoCapture(str(video_path))
    try:
        if selected and not capture.isOpened():
            raise RuntimeError("Video konnte für Identity-Fallback-Crops nicht geöffnet werden.")
        last = max(selected, default=0)
        for number in range(1, last + 1):
            if not capture.grab():
                raise RuntimeError(f"Fallback-Frame {number} konnte nicht gelesen werden.")
            if number not in selected:
                continue
            ok, frame = capture.retrieve()
            if not ok:
                raise RuntimeError(f"Fallback-Frame {number} konnte nicht dekodiert werden.")
            for track, row in selected[number]:
                encoded = _encode_crop(frame, row["bbox"], 95)
                if encoded is None:
                    continue
                image, (x1, y1, x2, y2) = encoded
                relative = Path("person_crops") / f"track_{track['source_track_id']:04d}" / f"identity_{number:08d}.jpg"
                temp_path = temp / relative
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_bytes(image)
                next_id += 1
                generated.append({
                    "crop_id": next_id, "source_track_id": track["source_track_id"], "scene_id": row["scene_id"],
                    "frame_number": number, "timestamp_s": (number - 1) / fps,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "person_confidence": "" if row["confidence"] is None else row["confidence"],
                    "crop_type": "identity_fallback", "crop_path": relative.as_posix(),
                })
                new_paths.add(relative.as_posix())
            if progress_cb and (number % 300 == 0 or number == last):
                progress_cb("Identity-Fallback-Crops werden gespeichert ...", number, last)

        for row in generated:
            source = temp / row["crop_path"]
            target = root / row["crop_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
        write_manifest(root, kept + generated)
        for relative in old_paths - new_paths:
            (root / relative).unlink(missing_ok=True)
        return len(generated)
    finally:
        capture.release()
        shutil.rmtree(temp, ignore_errors=True)


def remove_identity_fallbacks(root: str | Path) -> None:
    root = Path(root)
    rows = read_manifest(root)
    removed = [row for row in rows if row.get("crop_type") == "identity_fallback"]
    if not removed:
        return
    write_manifest(root, [row for row in rows if row.get("crop_type") != "identity_fallback"])
    for row in removed:
        (root / row["crop_path"]).unlink(missing_ok=True)
