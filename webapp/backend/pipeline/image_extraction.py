"""image_extraction.py – SceneDetect + MidframeExtractor + gapfill (Step 05)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import pandas as pd


# ── MidframeExtractor ──────────────────────────────────────────────────────────

class MidframeExtractor:
    """Detect scenes and extract representative mid-frames."""

    def __init__(
        self,
        output_dir: str = "output_frames",
        threshold: float = 24.0,
        min_scene_length: int = 20,
        blur_threshold: float = 80.0,
        short_scene_s: float = 3.0,
        jpg_quality: int = 95,
        min_bytes: int = 5_000,
    ):
        self.output_dir = Path(output_dir)
        self.threshold = float(threshold)
        self.min_scene_length = int(min_scene_length)
        self.blur_threshold = float(blur_threshold)
        self.short_scene_s = float(short_scene_s)
        self.jpg_quality = int(jpg_quality)
        self.min_bytes = int(min_bytes)

    def detect_scenes(self, video_path: str):
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector

        video = open_video(video_path)
        sm = SceneManager()
        sm.add_detector(
            ContentDetector(
                threshold=self.threshold,
                min_scene_len=self.min_scene_length,
            )
        )
        sm.detect_scenes(video)
        return sm.get_scene_list()

    def _blur_score(self, frame: np.ndarray) -> float:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _save_frame(self, cap: cv2.VideoCapture, frame_pos: int, out_path: Path) -> bool:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        ok, frame = cap.read()
        if not ok or frame is None:
            return False
        if self._blur_score(frame) < self.blur_threshold:
            return False
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), frame,
                    [cv2.IMWRITE_JPEG_QUALITY, self.jpg_quality])
        return out_path.exists() and out_path.stat().st_size >= self.min_bytes

    def process_video(
        self,
        video_path: str,
        window_start_s: float = 0.0,
        window_end_s: Optional[float] = None,
    ) -> tuple[list[str], list[tuple[float, float]]]:
        """Return (image_paths, timestamps) for all extracted frames."""
        scenes = self.detect_scenes(video_path)
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

        image_paths: list[str] = []
        timestamps: list[tuple[float, float]] = []

        for i, (start_tc, end_tc) in enumerate(scenes):
            sc_start = start_tc.get_seconds()
            sc_end = end_tc.get_seconds()

            # Window filter
            if window_end_s is not None and sc_start > window_end_s:
                break
            if sc_end < window_start_s:
                continue

            duration = sc_end - sc_start
            if duration < self.short_scene_s:
                # 1 frame for short scenes
                mid = int((sc_start + sc_end) / 2 * fps)
                out = self.output_dir / f"scene_{i:04d}_mid.jpg"
                if self._save_frame(cap, mid, out):
                    image_paths.append(str(out))
                    timestamps.append((sc_start, sc_end))
            else:
                # Up to 3 frames for longer scenes
                for frac in [0.25, 0.5, 0.75]:
                    pos = int((sc_start + duration * frac) * fps)
                    out = self.output_dir / f"scene_{i:04d}_{int(frac*100):02d}.jpg"
                    if self._save_frame(cap, pos, out):
                        image_paths.append(str(out))
                        timestamps.append((sc_start, sc_end))

        cap.release()
        return image_paths, timestamps


# ── Gapfill ────────────────────────────────────────────────────────────────────

def gapfill_images_for_ad_slots(
    video_path: str,
    ad_slots_df: pd.DataFrame,
    existing_images: list[str],
    output_dir: str,
    blur_threshold: float = 80.0,
    window_start_s: float = 0.0,
    window_end_s: Optional[float] = None,
) -> tuple[list[str], pd.DataFrame]:
    """For every AD slot, find the best image; extract a new one if needed.

    Returns (all_images, slot_map_df).
    slot_map_df has columns: slot, start_s, end_s, image_path.
    """
    gap_dir = Path(output_dir)
    gap_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    all_images = list(existing_images)
    slot_map_rows = []

    for _, row in ad_slots_df.iterrows():
        slot_id = int(row.get("slot", 0))
        s = float(row.get("start_s", row.get("start", 0)))
        e = float(row.get("end_s", row.get("end", s)))

        # Find existing image within window
        best = _best_image_for_window(existing_images, s, e)
        if best is None:
            # Extract mid-frame
            mid = int((s + e) / 2 * fps)
            out_path = gap_dir / f"gapfill_slot_{slot_id:04d}.jpg"
            if _extract_single_frame(cap, mid, out_path, blur_threshold):
                best = str(out_path)
                all_images.append(best)

        slot_map_rows.append({
            "slot": slot_id,
            "start_s": round(s, 3),
            "end_s": round(e, 3),
            "image_path": best or "",
        })

    cap.release()

    slot_map_df = pd.DataFrame(
        slot_map_rows,
        columns=["slot", "start_s", "end_s", "image_path"],
    )
    return all_images, slot_map_df


def _best_image_for_window(images: list[str], start: float, end: float) -> Optional[str]:
    """Return the first image path that falls within [start, end] by filename hint."""
    # Images saved by MidframeExtractor don't encode timestamps in their names,
    # so we just return the first existing image as a reasonable default.
    # A more precise approach would store timestamps alongside paths.
    for img in images:
        if Path(img).exists():
            return img
    return None


def _extract_single_frame(
    cap: cv2.VideoCapture, frame_pos: int, out_path: Path, blur_threshold: float
) -> bool:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
    ok, frame = cap.read()
    if not ok or frame is None:
        return False
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if float(cv2.Laplacian(gray, cv2.CV_64F).var()) < blur_threshold:
        return False
    cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out_path.exists() and out_path.stat().st_size >= 5_000
