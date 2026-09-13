from __future__ import annotations

import csv
import shutil
from pathlib import Path

import cv2
import numpy as np


class PersonCropWriter:
    """
    Speichert jede getrackte Personenbeobachtung als Personencrop.

    Struktur:

        person_analysis_v2/
            person_crops.csv
            person_crops/
                track_0001/
                    frame_00000001.jpg
                    frame_00000002.jpg
                    ...
                track_0002/
                    ...

    Jeder Crop bleibt dauerhaft seinem ursprünglichen Track
    und Frame zugeordnet.

    Dadurch können später:
    - komplette Tracks kontrolliert werden,
    - einzelne Zeitpunkte betrachtet werden,
    - Track-Splits vorgenommen werden,
    - Personenzuordnungen korrigiert werden.

    Die Dateien selbst müssen bei späteren Korrekturen
    nicht verschoben werden.
    """

    def __init__(
        self,
        output_dir: str | Path,
        fps: float,
        jpeg_quality: int = 90,
        clear_existing: bool = True,
    ) -> None:

        if fps <= 0:
            raise ValueError(
                "fps muss größer als 0 sein."
            )

        if not 0 <= jpeg_quality <= 100:
            raise ValueError(
                "jpeg_quality muss zwischen 0 und 100 liegen."
            )

        self.output_dir = Path(
            output_dir
        )

        self.crops_dir = (
            self.output_dir
            / "person_crops"
        )

        self.manifest_path = (
            self.output_dir
            / "person_crops.csv"
        )

        self.fps = float(
            fps
        )

        self.jpeg_quality = int(
            jpeg_quality
        )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Alte Testausgabe entfernen
        # -----------------------------------------------------
        #
        # Wenn dieselbe Analyse erneut gestartet wird,
        # sollen keine alten Crops aus einem vorherigen Lauf
        # übrig bleiben.
        #
        # Das betrifft nur:
        #
        # person_analysis_v2/person_crops/
        # person_analysis_v2/person_crops.csv
        #
        # Das Originalvideo oder andere Job-Dateien werden
        # NICHT verändert.
        # -----------------------------------------------------

        if clear_existing:
            if self.crops_dir.exists():
                shutil.rmtree(
                    self.crops_dir
                )

            if self.manifest_path.exists():
                self.manifest_path.unlink()

        self.crops_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # CSV-Manifest öffnen
        # -----------------------------------------------------

        self._manifest_file = open(
            self.manifest_path,
            "w",
            newline="",
            encoding="utf-8",
        )

        self._writer = csv.DictWriter(
            self._manifest_file,
            fieldnames=[
                "crop_id",
                "track_id",
                "scene_id",
                "frame_number",
                "timestamp_s",
                "x1",
                "y1",
                "x2",
                "y2",
                "person_confidence",
                "crop_path",
            ],
            delimiter=";",
        )

        self._writer.writeheader()

        self._crop_id = 0

    @property
    def crop_count(self) -> int:
        """
        Anzahl der erfolgreich gespeicherten Personencrops.
        """

        return self._crop_id

    def save(
        self,
        frame_bgr: np.ndarray,
        track_id: int,
        scene_id: int,
        frame_number: int,
        bbox,
        confidence: float | None = None,
    ) -> Path | None:
        """
        Schneidet die Bounding Box der getrackten Person
        aus dem vollständigen Videoframe aus und speichert
        diesen Ausschnitt als JPEG.

        Gibt den Pfad des gespeicherten Crops zurück.

        Falls die Bounding Box ungültig ist, wird kein Bild
        gespeichert und None zurückgegeben.
        """

        if (
            frame_bgr is None
            or frame_bgr.size == 0
        ):
            return None

        image_height, image_width = (
            frame_bgr.shape[:2]
        )

        x1, y1, x2, y2 = bbox

        # -----------------------------------------------------
        # Bounding Box auf gültigen Bildbereich begrenzen
        # -----------------------------------------------------

        x1 = max(
            0,
            min(
                image_width - 1,
                int(round(x1)),
            ),
        )

        y1 = max(
            0,
            min(
                image_height - 1,
                int(round(y1)),
            ),
        )

        x2 = max(
            0,
            min(
                image_width,
                int(round(x2)),
            ),
        )

        y2 = max(
            0,
            min(
                image_height,
                int(round(y2)),
            ),
        )

        if (
            x2 <= x1
            or y2 <= y1
        ):
            return None

        # -----------------------------------------------------
        # Personencrop erzeugen
        # -----------------------------------------------------

        person_crop = frame_bgr[
            y1:y2,
            x1:x2,
        ]

        if person_crop.size == 0:
            return None

        track_id = int(
            track_id
        )

        scene_id = int(
            scene_id
        )

        frame_number = int(
            frame_number
        )

        # -----------------------------------------------------
        # Track-Ordner
        # -----------------------------------------------------

        track_dir = (
            self.crops_dir
            / f"track_{track_id:04d}"
        )

        track_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Dateiname
        # -----------------------------------------------------

        crop_path = (
            track_dir
            / (
                f"frame_"
                f"{frame_number:08d}.jpg"
            )
        )

        # -----------------------------------------------------
        # JPEG speichern
        # -----------------------------------------------------

        success = cv2.imwrite(
            str(crop_path),
            person_crop,
            [
                cv2.IMWRITE_JPEG_QUALITY,
                self.jpeg_quality,
            ],
        )

        if not success:
            raise RuntimeError(
                "Personencrop konnte nicht gespeichert werden: "
                f"{crop_path}"
            )

        self._crop_id += 1

        # -----------------------------------------------------
        # Zeitpunkt berechnen
        # -----------------------------------------------------

        timestamp_s = (
            frame_number - 1
        ) / self.fps

        # Nur relativen Pfad in CSV speichern.
        # Dadurch bleibt der Job-Ordner verschiebbar.
        relative_path = (
            crop_path.relative_to(
                self.output_dir
            )
        )

        # -----------------------------------------------------
        # Metadaten in CSV schreiben
        # -----------------------------------------------------

        self._writer.writerow(
            {
                "crop_id": (
                    self._crop_id
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
                "x1": (
                    x1
                ),
                "y1": (
                    y1
                ),
                "x2": (
                    x2
                ),
                "y2": (
                    y2
                ),
                "person_confidence": (
                    float(confidence)
                    if confidence is not None
                    else ""
                ),
                "crop_path": (
                    relative_path.as_posix()
                ),
            }
        )

        return crop_path

    def close(self) -> None:
        """
        Schließt die CSV-Datei sauber.
        """

        if not self._manifest_file.closed:
            self._manifest_file.flush()
            self._manifest_file.close()