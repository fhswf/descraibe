from __future__ import annotations


class TrackIntervalAccumulator:
    """
    Speichert für jeden Track genau ein Zeitintervall.

    Ein Track beginnt mit seiner ersten Beobachtung und endet
    mit seiner letzten Beobachtung.

    Kurze Tracking-Aussetzer innerhalb desselben Tracks werden
    nicht als eigene Intervalle behandelt. Solange ByteTrack
    dieselbe Track-ID weiterführt, gehört alles zum selben Track.

    Erst verschiedene Tracks derselben realen Person führen später
    zu mehreren Appearance-Intervallen einer Person.
    """

    def __init__(self, fps: float) -> None:
        if fps <= 0:
            raise ValueError("fps muss größer als 0 sein.")

        self.fps = float(fps)
        self._tracks: dict[int, dict] = {}

    def observe(
        self,
        track_id: int,
        scene_id: int,
        frame_number: int,
    ) -> None:
        track_id = int(track_id)
        scene_id = int(scene_id)
        frame_number = int(frame_number)

        timestamp_s = (
            frame_number - 1
        ) / self.fps

        if track_id not in self._tracks:
            self._tracks[track_id] = {
                "track_id": track_id,
                "scene_id": scene_id,
                "start_frame": frame_number,
                "end_frame": frame_number,
                "start_s": timestamp_s,
                "end_s": timestamp_s,
                "observation_count": 1,
            }

            return

        track = self._tracks[track_id]

        track["end_frame"] = frame_number
        track["end_s"] = timestamp_s
        track["observation_count"] += 1

    def result(self) -> list[dict]:
        """
        Gibt die kompakten Track-Metadaten zurück.

        Frame-Grenzen stammen von den tatsächlich ausgewerteten Trackingframes,
        nicht von der Crop-Auswahl. Übersprungene Frames werden nicht ergänzt.
        """

        results = []

        for track_id in sorted(self._tracks):
            track = self._tracks[track_id]

            results.append(
                {
                    "track_id": int(
                        track["track_id"]
                    ),
                    "scene_id": int(
                        track["scene_id"]
                    ),
                    "start_s": float(
                        track["start_s"]
                    ),
                    "end_s": float(
                        track["end_s"]
                    ),
                    "observation_count": int(
                        track["observation_count"]
                    ),
                    "start_frame": int(track["start_frame"]),
                    "end_frame": int(track["end_frame"]),
                }
            )

        return results
