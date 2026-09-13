from __future__ import annotations

from pathlib import Path

import numpy as np
import supervision as sv
from scenedetect import AdaptiveDetector, detect
from trackers import ByteTrackTracker

from .config import (
    HIGH_CONF_DET_THRESHOLD,
    LOST_TRACK_BUFFER,
    MINIMUM_CONSECUTIVE_FRAMES,
    MINIMUM_IOU_THRESHOLD,
    PERSON_CLASS_ID,
    TRACK_ACTIVATION_THRESHOLD,
)


def detect_scene_change_frames(video_path: Path) -> set[int]:
    scenes = detect(
        str(video_path),
        AdaptiveDetector(),
        start_in_scene=True,
    )

    return {
        scene_start.frame_num + 1
        for scene_start, _ in scenes[1:]
    }


class BytePersonTracker:
    def __init__(self, frame_rate: float) -> None:
        self.frame_rate = frame_rate
        self.scene_id = 1
        self.scene_track_id_map: dict[int, int] = {}
        self.next_global_track_id = 1
        self.tracker = self._create_tracker()

    def _create_tracker(self) -> ByteTrackTracker:
        return ByteTrackTracker(
            lost_track_buffer=LOST_TRACK_BUFFER,
            frame_rate=self.frame_rate,
            track_activation_threshold=TRACK_ACTIVATION_THRESHOLD,
            minimum_consecutive_frames=MINIMUM_CONSECUTIVE_FRAMES,
            minimum_iou_threshold=MINIMUM_IOU_THRESHOLD,
            high_conf_det_threshold=HIGH_CONF_DET_THRESHOLD,
        )

    def start_new_scene(self) -> None:
        self.scene_id += 1
        self.tracker = self._create_tracker()
        self.scene_track_id_map.clear()

    def update(
        self,
        persons: list[dict],
        scene_change: bool = False,
    ) -> list[dict]:

        if scene_change:
            self.start_new_scene()

        if persons:
            detections = sv.Detections(
                xyxy=np.asarray(
                    [person["bbox"] for person in persons],
                    dtype=np.float32,
                ),
                confidence=np.asarray(
                    [person["confidence"] for person in persons],
                    dtype=np.float32,
                ),
                class_id=np.full(
                    len(persons),
                    PERSON_CLASS_ID,
                    dtype=np.int32,
                ),
            )
        else:
            detections = sv.Detections.empty()

        tracked_detections = self.tracker.update(detections)

        if tracked_detections.tracker_id is None:
            return []

        tracked_persons = []

        for index, local_tracker_id in enumerate(
            tracked_detections.tracker_id
        ):
            local_tracker_id = int(local_tracker_id)

            if local_tracker_id < 0:
                continue

            if local_tracker_id not in self.scene_track_id_map:
                self.scene_track_id_map[local_tracker_id] = (
                    self.next_global_track_id
                )
                self.next_global_track_id += 1

            track_id = self.scene_track_id_map[local_tracker_id]

            x1, y1, x2, y2 = tracked_detections.xyxy[index]

            tracked_persons.append(
                {
                    "bbox": (
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2),
                    ),
                    "confidence": float(
                        tracked_detections.confidence[index]
                    ),
                    "track_id": track_id,
                    "scene_id": self.scene_id,
                }
            )

        return tracked_persons