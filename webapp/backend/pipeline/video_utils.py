"""video_utils.py – load video metadata and extract basic stats."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def get_video_stats(video_path: str) -> dict:
    """Return basic metadata about a video file using cv2.

    Returns a dict with keys: duration_s, fps, width, height, frame_count,
    size_bytes, filename.  Falls back gracefully when cv2 is unavailable.
    """
    import cv2

    p = Path(video_path)
    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {p}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()

    duration_s = (frame_count / fps) if fps > 0 else 0.0

    return {
        "filename": p.name,
        "duration_s": round(duration_s, 3),
        "fps": round(fps, 3),
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "size_bytes": p.stat().st_size,
    }


def get_duration_s(video_path: str) -> Optional[float]:
    """Return video duration in seconds, or None on failure."""
    try:
        stats = get_video_stats(video_path)
        return stats["duration_s"]
    except Exception:
        return None
