from __future__ import annotations

import os

import cv2
import torch
from rfdetr import RFDETRNano

from .config import (
    PERSON_CLASS_ID,
    RFDETR_CONFIDENCE_THRESHOLD,
)


def _resolve_device() -> str:
    requested_device = os.environ.get("AD_PERSON_DEVICE", "auto").strip().lower()
    if requested_device not in {"auto", "cpu", "cuda"}:
        raise ValueError("AD_PERSON_DEVICE must be 'auto', 'cpu', or 'cuda'.")
    if requested_device == "cpu":
        return "cpu"

    cuda_available = torch.cuda.is_available()
    if requested_device == "cuda" and not cuda_available:
        raise RuntimeError(
            "AD_PERSON_DEVICE=cuda, but PyTorch cannot access CUDA "
            f"(torch CUDA build: {torch.version.cuda or 'CPU-only'}, "
            f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '<unset>')}). "
            "Expose a GPU to the container or set AD_PERSON_DEVICE=auto."
        )

    if requested_device == "cuda" or cuda_available:
        return "cuda"
    return "cpu"


class RFDETRPersonDetector:
    def __init__(self) -> None:
        self.device = _resolve_device()

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
        return self.detect_batch([frame_bgr])[0]

    def detect_batch(self, frames_bgr) -> list[list[dict]]:
        """Detect people in a batch of frames with one RF-DETR model call."""
        if not frames_bgr:
            return []
        return self.detect_prepared_batch(self.prepare_batch(frames_bgr))

    @staticmethod
    def prepare_batch(frames_bgr):
        """Convert frames before taking the shared model lock."""
        return [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames_bgr]

    def detect_prepared_batch(self, frames_rgb) -> list[list[dict]]:
        """Run a prepared RGB batch through RF-DETR."""
        if not frames_rgb:
            return []
        batch_detections = self.model.predict(
            frames_rgb,
            threshold=RFDETR_CONFIDENCE_THRESHOLD,
            include_source_image=False,
        )
        if len(batch_detections) != len(frames_rgb):
            raise RuntimeError("RF-DETR gab nicht für jedes Batch-Bild Detektionen zurück.")
        return [self._person_detections(detections) for detections in batch_detections]

    @staticmethod
    def _person_detections(detections) -> list[dict]:
        detections = detections[detections.class_id == PERSON_CLASS_ID]
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
