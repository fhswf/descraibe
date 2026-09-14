from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


class PersonCropWriter:
    """
    Speichert ausschließlich vom Aufrufer ausgewählte Personencrops.

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
        start_id: int = 0,
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

        self._crop_id = start_id
        self._start_id = start_id

    @property
    def crop_count(self) -> int:
        """
        Anzahl der erfolgreich gespeicherten Personencrops.
        """

        return self._crop_id - self._start_id

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

        success, encoded = cv2.imencode(
            ".jpg",
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
        # Python handles Windows Unicode/long paths that cv2.imwrite cannot.
        crop_path.write_bytes(encoded.tobytes())

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


class FallbackCropCollector:
    """Keep compact coordinates, never pixels; discard a track once usable face evidence exists.

    A second sequential decode writes at most five crops for each remaining track.
    Detection/tracking are not repeated. Memory is O(retained tracking observations)
    in small numeric tuples, not O(video frames) in image arrays.
    """

    def __init__(self):
        self.observations = defaultdict(list)
        self.with_faces = set()

    def observe(self, person: dict, frame_number: int) -> None:
        tid = int(person["track_id"])
        if tid not in self.with_faces:
            self.observations[tid].append((frame_number, int(person["scene_id"]),
                tuple(float(v) for v in person["bbox"]), person.get("confidence")))

    def face_succeeded(self, track_id: int) -> None:
        self.with_faces.add(track_id)
        self.observations.pop(track_id, None)

    def selected(self, limit: int = 5) -> dict[int, list[tuple]]:
        frames = defaultdict(list)
        for tid, rows in self.observations.items():
            numbers = [row[0] for row in rows]
            count = min(limit, len(rows))
            indices = set()
            for i in range(count):
                target = numbers[0] if count == 1 else numbers[0] + i * (numbers[-1] - numbers[0]) / (count - 1)
                # Distinct observations even when a track has long detection gaps.
                index = min((j for j in range(len(rows)) if j not in indices),
                            key=lambda j: (abs(numbers[j] - target), j))
                indices.add(index)
            for index in sorted(indices):
                number, scene, bbox, confidence = rows[index]
                frames[number].append((tid, scene, bbox, confidence))
        return frames

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
                    for tid, scene, bbox, confidence in selected[number]:
                        writer.save(frame, tid, scene, number, bbox, confidence)
                if progress_cb and (number % 300 == 0 or number == last):
                    progress_cb("Fallback-Personencrops werden gespeichert ...", number, last)
        finally:
            capture.release()
        return writer.crop_count - before
