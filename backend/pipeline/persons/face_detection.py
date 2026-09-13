from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import onnxruntime as ort

from uniface.constants import RetinaFaceWeights
from uniface.detection import RetinaFace
from uniface.face_utils import face_alignment
from uniface.model_store import set_cache_dir

from .config import (
    FACE_ALIGNMENT_SIZE,
    FACE_MARGIN_RATIO,
    RETINAFACE_CONFIDENCE_THRESHOLD,
    RETINAFACE_DYNAMIC_SIZE,
    RETINAFACE_INPUT_SIZE,
    RETINAFACE_MAX_NUM,
    RETINAFACE_NMS_THRESHOLD,
    RETINAFACE_POST_NMS_TOPK,
    RETINAFACE_PRE_NMS_TOPK,
)


MODEL_NAME = RetinaFaceWeights.MNET_V2


def clip_box(
    box: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box

    x1 = max(
        0,
        min(
            image_width - 1,
            int(math.floor(x1)),
        ),
    )
    y1 = max(
        0,
        min(
            image_height - 1,
            int(math.floor(y1)),
        ),
    )
    x2 = max(
        x1 + 1,
        min(
            image_width,
            int(math.ceil(x2)),
        ),
    )
    y2 = max(
        y1 + 1,
        min(
            image_height,
            int(math.ceil(y2)),
        ),
    )

    return x1, y1, x2, y2


def crop_with_margin(
    image: np.ndarray,
    box: tuple[int, int, int, int],
    margin_ratio: float = FACE_MARGIN_RATIO,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    image_height, image_width = image.shape[:2]
    x1, y1, x2, y2 = box

    width = max(
        1.0,
        float(x2 - x1),
    )
    height = max(
        1.0,
        float(y2 - y1),
    )

    margin = (
        min(width, height)
        * margin_ratio
    )

    crop_box = clip_box(
        (
            x1 - margin,
            y1 - margin,
            x2 + margin,
            y2 + margin,
        ),
        image_width,
        image_height,
    )

    crop_x1, crop_y1, crop_x2, crop_y2 = (
        crop_box
    )

    crop = image[
        crop_y1:crop_y2,
        crop_x1:crop_x2,
    ].copy()

    return crop, crop_box


def normalize_landmarks(
    landmarks,
) -> np.ndarray:
    if landmarks is None:
        return np.full(
            (5, 2),
            np.nan,
            dtype=np.float32,
        )

    points = np.asarray(
        landmarks,
        dtype=np.float32,
    )

    if points.size != 10:
        return np.full(
            (5, 2),
            np.nan,
            dtype=np.float32,
        )

    return points.reshape(5, 2)


def align_face(
    image: np.ndarray,
    landmarks: np.ndarray,
) -> np.ndarray | None:
    if np.isnan(landmarks).any():
        return None

    aligned_image, _ = face_alignment(
        image,
        landmarks,
        image_size=FACE_ALIGNMENT_SIZE,
    )

    return aligned_image


class RetinaFaceDetector:
    def __init__(
        self,
        model_cache_dir: Path | None = None,
    ) -> None:
        if model_cache_dir is not None:
            model_cache_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            set_cache_dir(
                str(model_cache_dir)
            )

        available_providers = (
            ort.get_available_providers()
        )

        if (
            "CUDAExecutionProvider"
            in available_providers
        ):
            self.providers = [
                "CUDAExecutionProvider",
                "CPUExecutionProvider",
            ]
            self.device = "cuda"
        else:
            self.providers = [
                "CPUExecutionProvider"
            ]
            self.device = "cpu"

        self.model = RetinaFace(
            model_name=MODEL_NAME,
            confidence_threshold=(
                RETINAFACE_CONFIDENCE_THRESHOLD
            ),
            nms_threshold=(
                RETINAFACE_NMS_THRESHOLD
            ),
            input_size=(
                RETINAFACE_INPUT_SIZE
            ),
            providers=self.providers,
            dynamic_size=(
                RETINAFACE_DYNAMIC_SIZE
            ),
            pre_nms_topk=(
                RETINAFACE_PRE_NMS_TOPK
            ),
            post_nms_topk=(
                RETINAFACE_POST_NMS_TOPK
            ),
        )

        print(
            f"RetinaFace läuft auf: "
            f"{self.device}"
        )

    def detect(
        self,
        image: np.ndarray,
    ) -> list[dict]:
        if (
            image is None
            or image.size == 0
        ):
            return []

        image_height, image_width = (
            image.shape[:2]
        )

        faces = self.model.detect(
            image,
            max_num=RETINAFACE_MAX_NUM,
        )

        if faces is None:
            return []

        results = []

        for face in faces:
            box = np.asarray(
                face.bbox,
                dtype=np.float32,
            ).reshape(-1)

            if box.size != 4:
                continue

            x1, y1, x2, y2 = clip_box(
                (
                    float(box[0]),
                    float(box[1]),
                    float(box[2]),
                    float(box[3]),
                ),
                image_width,
                image_height,
            )

            landmarks = (
                normalize_landmarks(
                    face.landmarks
                )
            )

            face_crop, face_crop_box = (
                crop_with_margin(
                    image,
                    (x1, y1, x2, y2),
                )
            )

            crop_x1, crop_y1, _, _ = (
                face_crop_box
            )

            crop_landmarks = (
                landmarks.copy()
            )

            if not np.isnan(
                crop_landmarks
            ).any():
                crop_landmarks[:, 0] -= (
                    crop_x1
                )
                crop_landmarks[:, 1] -= (
                    crop_y1
                )

            aligned_crop = align_face(
                face_crop,
                crop_landmarks,
            )

            results.append(
                {
                    "bbox": (
                        x1,
                        y1,
                        x2,
                        y2,
                    ),
                    "confidence": float(
                        face.confidence
                    ),
                    "crop": face_crop,
                    "aligned_crop": (
                        aligned_crop
                    ),
                }
            )

        return results