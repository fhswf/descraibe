from __future__ import annotations

import cv2
import torch
from rfdetr import RFDETRNano

from .config import (
    PERSON_CLASS_ID,
    RFDETR_CONFIDENCE_THRESHOLD,
)


class RFDETRPersonDetector:
    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = RFDETRNano(
            device=self.device,
        )

        if self.device == "cuda":
            self.model.inference(
                compile=False,
                inplace=True,
                dtype="float32",
            )

        print(f"RF-DETR Nano läuft auf: {self.device}")

    def detect(self, frame_bgr) -> list[dict]:
        frame_rgb = cv2.cvtColor(
            frame_bgr,
            cv2.COLOR_BGR2RGB,
        )

        detections = self.model.predict(
            frame_rgb,
            threshold=RFDETR_CONFIDENCE_THRESHOLD,
        )

        detections = detections[
            detections.class_id == PERSON_CLASS_ID
        ]

        results = []

        for box, confidence in zip(
            detections.xyxy,
            detections.confidence,
        ):
            x1, y1, x2, y2 = box

            results.append(
                {
                    "bbox": (
                        int(round(x1)),
                        int(round(y1)),
                        int(round(x2)),
                        int(round(y2)),
                    ),
                    "confidence": float(confidence),
                }
            )

        return results