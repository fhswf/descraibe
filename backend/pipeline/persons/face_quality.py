from __future__ import annotations

import cv2
import numpy as np

from .config import (
    FACE_BLUR_THRESHOLD,
    FACE_QUALITY_IMAGE_SIZE,
)


def calculate_blur_score(
    image: np.ndarray,
) -> float:
    if (
        image is None
        or image.size == 0
    ):
        raise ValueError(
            "Ungültiger Gesichtsausschnitt."
        )

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )

    return float(
        cv2.Laplacian(
            gray,
            cv2.CV_64F,
        ).var()
    )


def check_face_quality(
    face_crop: np.ndarray,
    face_confidence: float | None = None,
) -> tuple[bool, dict]:
    if (
        face_crop is None
        or face_crop.size == 0
    ):
        raise ValueError(
            "Ungültiger Gesichtsausschnitt."
        )

    height, width = (
        face_crop.shape[:2]
    )

    resized_face = cv2.resize(
        face_crop,
        FACE_QUALITY_IMAGE_SIZE,
        interpolation=cv2.INTER_LINEAR,
    )

    blur_score = calculate_blur_score(
        resized_face
    )

    is_usable = (
        blur_score
        >= FACE_BLUR_THRESHOLD
    )

    return is_usable, {
        "width": int(width),
        "height": int(height),
        "blur_score": blur_score,
        "face_confidence": (
            float(face_confidence)
            if face_confidence is not None
            else None
        ),
    }