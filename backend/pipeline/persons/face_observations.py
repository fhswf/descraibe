from __future__ import annotations

import csv
import json
import math
from pathlib import Path


class FaceObservationWriter:
    """
    Speichert Metadaten zu den einem Track zugeordneten Gesichtern.

    Es werden KEINE zusätzlichen Review-Bilder gespeichert.

    Die spätere Oberfläche verwendet den bereits vorhandenen
    Personencrop und zeichnet anhand der hier gespeicherten
    Face-Koordinaten den Gesichtsrahmen dynamisch ein.

    Dadurch existiert jeder Personencrop nur einmal.
    """

    def __init__(
        self,
        output_dir: str | Path,
        fps: float,
        clear_existing: bool = True,
    ) -> None:

        if fps <= 0:
            raise ValueError(
                "fps muss größer als 0 sein."
            )

        self.output_dir = Path(
            output_dir
        )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.fps = float(
            fps
        )

        self.manifest_path = (
            self.output_dir
            / "face_observations.csv"
        )

        if (
            clear_existing
            and self.manifest_path.exists()
        ):
            self.manifest_path.unlink()

        self._manifest_file = open(
            self.manifest_path,
            "w",
            newline="",
            encoding="utf-8",
        )

        self._writer = csv.DictWriter(
            self._manifest_file,
            fieldnames=[
                "face_id",
                "track_id",
                "scene_id",
                "frame_number",
                "timestamp_s",
                "person_crop_path",
                "face_x1",
                "face_y1",
                "face_x2",
                "face_y2",
                "face_confidence",
                "face_usable",
                "blur_score",
                "alignment_ok",
                "embedding_created",
                "landmarks", "face_crop_box", "frame_face_bbox",
            ],
            delimiter=";",
        )

        self._writer.writeheader()

        self._face_id = 0

    @property
    def face_count(self) -> int:
        return self._face_id

    @staticmethod
    def _clip_person_box(
        bbox,
        frame_width: int,
        frame_height: int,
    ) -> tuple[int, int, int, int]:

        x1, y1, x2, y2 = bbox

        x1 = max(
            0,
            min(
                frame_width - 1,
                int(round(x1)),
            ),
        )

        y1 = max(
            0,
            min(
                frame_height - 1,
                int(round(y1)),
            ),
        )

        x2 = max(
            0,
            min(
                frame_width,
                int(round(x2)),
            ),
        )

        y2 = max(
            0,
            min(
                frame_height,
                int(round(y2)),
            ),
        )

        return x1, y1, x2, y2

    def save(
        self,
        track_id: int,
        scene_id: int,
        frame_number: int,
        person_bbox,
        face_bbox,
        person_crop_path: str | Path | None,
        frame_width: int,
        frame_height: int,
        face_confidence: float,
        face_usable: bool,
        blur_score: float | None,
        alignment_ok: bool | None = None,
        embedding_created: bool | None = None,
        landmarks=None,
        face_crop_box=None,
    ) -> int:
        """
        Speichert eine Gesichtsbeobachtung.

        Die Face-Bounding-Box wird in Koordinaten relativ zum
        gespeicherten Personencrop umgerechnet.

        Gibt die erzeugte face_id zurück.
        """

        track_id = int(
            track_id
        )

        scene_id = int(
            scene_id
        )

        frame_number = int(
            frame_number
        )

        px1, py1, px2, py2 = (
            self._clip_person_box(
                person_bbox,
                frame_width,
                frame_height,
            )
        )

        crop_width = max(
            1,
            px2 - px1,
        )

        crop_height = max(
            1,
            py2 - py1,
        )

        fx1, fy1, fx2, fy2 = (
            face_bbox
        )

        # ---------------------------------------------
        # Face-Koordinaten vom vollständigen Frame
        # in Koordinaten des Personencrops umrechnen.
        # ---------------------------------------------

        face_x1 = int(
            round(
                fx1 - px1
            )
        )

        face_y1 = int(
            round(
                fy1 - py1
            )
        )

        face_x2 = int(
            round(
                fx2 - px1
            )
        )

        face_y2 = int(
            round(
                fy2 - py1
            )
        )

        # ---------------------------------------------
        # Koordinaten auf Personencrop begrenzen
        # ---------------------------------------------

        face_x1 = max(
            0,
            min(
                crop_width - 1,
                face_x1,
            ),
        )

        face_y1 = max(
            0,
            min(
                crop_height - 1,
                face_y1,
            ),
        )

        face_x2 = max(
            0,
            min(
                crop_width - 1,
                face_x2,
            ),
        )

        face_y2 = max(
            0,
            min(
                crop_height - 1,
                face_y2,
            ),
        )

        self._face_id += 1

        timestamp_s = (
            frame_number - 1
        ) / self.fps

        # Rejected observations retain diagnostics, but require no JPEG.
        relative_crop_path = ""
        if person_crop_path is not None:
            relative_crop_path = Path(person_crop_path).relative_to(self.output_dir).as_posix()

        self._writer.writerow(
            {
                "face_id": (
                    self._face_id
                ),
                "track_id": (
                    track_id
                ),
                "scene_id": (
                    scene_id
                ),
                "frame_number": (
                    frame_number
                ),
                "timestamp_s": (
                    timestamp_s
                ),
                "person_crop_path": (
                    relative_crop_path
                ),
                "face_x1": (
                    face_x1
                ),
                "face_y1": (
                    face_y1
                ),
                "face_x2": (
                    face_x2
                ),
                "face_y2": (
                    face_y2
                ),
                "face_confidence": (
                    float(
                        face_confidence
                    )
                ),
                "face_usable": (
                    bool(
                        face_usable
                    )
                ),
                "blur_score": (
                    float(
                        blur_score
                    )
                    if blur_score
                    is not None
                    else ""
                ),
                "alignment_ok": "" if alignment_ok is None else bool(alignment_ok),
                "embedding_created": "" if embedding_created is None else bool(embedding_created),
                "landmarks": json.dumps([[float(v) if math.isfinite(float(v)) else None for v in point] for point in landmarks]) if landmarks is not None else "null",
                "face_crop_box": json.dumps(list(map(int, face_crop_box))) if face_crop_box is not None else "null",
                "frame_face_bbox": json.dumps(list(map(float, face_bbox))),
            }
        )

        return self._face_id

    def close(self) -> None:

        if not self._manifest_file.closed:
            self._manifest_file.flush()
            self._manifest_file.close()
