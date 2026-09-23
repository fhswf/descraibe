from __future__ import annotations

import csv
import json
import math
from pathlib import Path


class FaceObservationWriter:
    FIELDS = [
        "face_id", "source_track_id", "scene_id", "frame_number", "timestamp_s", "person_crop_path",
        "face_x1", "face_y1", "face_x2", "face_y2", "face_confidence", "face_usable", "excluded",
        "blur_score", "alignment_ok", "embedding_created", "landmarks", "face_crop_box", "frame_face_bbox",
    ]

    def __init__(self, output_dir: str | Path, fps: float) -> None:
        if fps <= 0:
            raise ValueError("fps muss größer als 0 sein.")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fps = float(fps)
        self.manifest_path = self.output_dir / "face_observations.csv"
        self._file = self.manifest_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.FIELDS, delimiter=";")
        self._writer.writeheader()
        self._face_id = 0

    @property
    def face_count(self) -> int:
        return self._face_id

    @staticmethod
    def _person_box(bbox, width: int, height: int) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = bbox
        return (max(0, min(width - 1, int(round(x1)))), max(0, min(height - 1, int(round(y1)))),
                max(0, min(width, int(round(x2)))), max(0, min(height, int(round(y2)))))

    def save(self, source_track_id: int, scene_id: int, frame_number: int, person_bbox, face_bbox,
             person_crop_path: str | Path | None, frame_width: int, frame_height: int,
             face_confidence: float, face_usable: bool, blur_score: float | None,
             landmarks=None, face_crop_box=None) -> int:
        px1, py1, px2, py2 = self._person_box(person_bbox, frame_width, frame_height)
        crop_width, crop_height = max(1, px2 - px1), max(1, py2 - py1)
        fx1, fy1, fx2, fy2 = face_bbox
        bbox = [
            max(0, min(crop_width - 1, int(round(fx1 - px1)))),
            max(0, min(crop_height - 1, int(round(fy1 - py1)))),
            max(0, min(crop_width - 1, int(round(fx2 - px1)))),
            max(0, min(crop_height - 1, int(round(fy2 - py1)))),
        ]
        self._face_id += 1
        crop_path = "" if person_crop_path is None else Path(person_crop_path).relative_to(self.output_dir).as_posix()
        self._writer.writerow({
            "face_id": self._face_id, "source_track_id": int(source_track_id), "scene_id": int(scene_id),
            "frame_number": int(frame_number), "timestamp_s": (int(frame_number) - 1) / self.fps,
            "person_crop_path": crop_path, "face_x1": bbox[0], "face_y1": bbox[1], "face_x2": bbox[2], "face_y2": bbox[3],
            "face_confidence": float(face_confidence), "face_usable": bool(face_usable), "excluded": False,
            "blur_score": "" if blur_score is None else float(blur_score), "alignment_ok": "", "embedding_created": "",
            "landmarks": json.dumps([[float(v) if math.isfinite(float(v)) else None for v in point] for point in landmarks]) if landmarks is not None else "null",
            "face_crop_box": json.dumps(list(map(int, face_crop_box))) if face_crop_box is not None else "null",
            "frame_face_bbox": json.dumps(list(map(float, face_bbox))),
        })
        return self._face_id

    def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            self._file.close()
