"""image_extraction.py – SceneDetect + MidframeExtractor + gapfill (Step 05).

Fidelity notes (aligned with FINAL notebook step 05):
- Filenames encode the video timestamp as HH-MM-SS-mmm so gapfill can parse them.
- Long scenes (≥ short_scene_s) produce up to 3 frames (20 / 50 / 80 %).
- Short scenes produce 1 frame (50 %).
- Gapfill uses _extract_ts_from_filename() to build img→timestamp index and
  matches scene images to AD slots before extracting new frames.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Timestamp helpers ──────────────────────────────────────────────────────────

_TS_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{2})-(\d{3})$")


def _ts_str(seconds: float) -> str:
    """Convert seconds → 'HH-MM-SS-mmm' filename-safe timestamp string."""
    s = max(0.0, float(seconds))
    hh = int(s // 3600)
    mm = int((s % 3600) // 60)
    ss = int(s % 60)
    ms = min(999, int(round((s - int(s)) * 1000)))
    return f"{hh:02d}-{mm:02d}-{ss:02d}-{ms:03d}"


def _extract_ts_from_filename(path: str) -> Optional[float]:
    """Parse HH-MM-SS-mmm timestamp from a filename (scans backwards over underscore parts)."""
    parts = Path(path).stem.split("_")
    for part in reversed(parts):
        m = _TS_RE.match(part)
        if m:
            hh, mm, ss, ms = map(int, m.groups())
            return hh * 3600 + mm * 60 + ss + ms / 1000.0
    return None


# ── Save helper ────────────────────────────────────────────────────────────────

def _save_frame(frame: np.ndarray, out_path: Path, jpg_quality: int = 95, min_bytes: int = 5_000) -> None:
    """Encode and write a JPEG frame, raising RuntimeError on failure."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if frame is None:
        raise RuntimeError(f"Frame is None: {out_path}")
    if getattr(frame, "dtype", None) != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpg_quality])
    if not ok or buf is None:
        raise RuntimeError(f"cv2.imencode failed: {out_path}")
    out_path.write_bytes(buf.tobytes())
    if not out_path.exists() or out_path.stat().st_size < min_bytes:
        raise RuntimeError(f"Saved image too small/missing: {out_path}")
    logger.info(f"Saved frame: {out_path.name} ({out_path.stat().st_size} bytes)")


# ── MidframeExtractor ──────────────────────────────────────────────────────────

class MidframeExtractor:
    """Detect scenes and extract representative frames (1 or 3 per scene).

    Frame selection strategy (aligned with FINAL notebook):
    - Short scenes (< short_scene_s): 1 frame at 50 %.
    - Long scenes (≥ short_scene_s): up to 3 frames at 20 %, 50 %, 80 %.
      Blurry frames are skipped.  If all are blurry, the 50 % frame is used.
    """

    def __init__(
        self,
        output_dir: str = "output_frames",
        threshold: float = 24.0,
        min_scene_length: int = 20,        # frames
        blur_threshold: float = 80.0,
        short_scene_s: float = 3.0,
        jpg_quality: int = 95,
        min_bytes: int = 5_000,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.threshold = float(threshold)
        self.min_scene_length = int(min_scene_length)
        self.blur_threshold = float(blur_threshold)
        self.short_scene_s = float(short_scene_s)
        self.jpg_quality = int(jpg_quality)
        self.min_bytes = int(min_bytes)

    # ── internal helpers ────────────────────────────────────────────────────

    def _is_blurry(self, frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var()) < self.blur_threshold

    def _read_frame_at(self, cap: cv2.VideoCapture, ts_s: float):
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(ts_s * float(fps))))
        ok, frame = cap.read()
        return bool(ok), frame

    # ── scene detection ─────────────────────────────────────────────────────

    def detect_scenes(self, video_path: str) -> list[tuple[float, float]]:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
        video = open_video(video_path)
        sm = SceneManager()
        sm.add_detector(ContentDetector(
            threshold=self.threshold,
            min_scene_len=self.min_scene_length,
        ))
        sm.detect_scenes(video)
        scenes = sm.get_scene_list()
        logger.info(f"Scene detection: found {len(scenes)} scenes.")
        return [(float(s[0].get_seconds()), float(s[1].get_seconds()))
                for s in scenes]

    # ── frame extraction ────────────────────────────────────────────────────

    def extract_frames(
        self,
        video_path: str,
        scene_timestamps: list[tuple[float, float]],
    ) -> list[str]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError("cv2.VideoCapture could not open video.")

        extracted: list[str] = []
        video_stem = Path(video_path).stem

        for scene_no, (start_s, end_s) in enumerate(scene_timestamps, start=1):
            start_s, end_s = float(start_s), float(end_s)
            dur = max(0.0, end_s - start_s)
            if dur <= 0:
                continue

            if dur < self.short_scene_s:
                positions = [(0.5, "mid")]
            else:
                positions = [(0.2, "start"), (0.5, "mid"), (0.8, "end")]

            frames_data: list[tuple[float, str, np.ndarray, bool]] = []
            for pos, pos_name in positions:
                ts = start_s + dur * pos
                ok, frame = self._read_frame_at(cap, ts)
                if not ok or frame is None:
                    continue
                is_blurry = self._is_blurry(frame)
                if is_blurry:
                    logger.info(f"Slot {scene_no}: Frame at {ts:.2f}s is blurry, skipping.")
                frames_data.append((ts, pos_name, frame, is_blurry))

            if not frames_data:
                continue

            if dur < self.short_scene_s:
                # Take first non-blurry; fall back to blurry
                non_blurry = [x for x in frames_data if not x[3]]
                best = non_blurry[0] if non_blurry else frames_data[0]
                ts, pos_name, frame, _ = best
                out_path = self.output_dir / (
                    f"{video_stem}_scene_{scene_no:04d}_{pos_name}_{_ts_str(ts)}.jpg"
                )
                _save_frame(frame, out_path, self.jpg_quality, self.min_bytes)
                extracted.append(str(out_path))
            else:
                # Save all non-blurry frames; if none, save the midpoint
                saved_any = False
                for ts, pos_name, frame, blurry in frames_data:
                    if blurry:
                        continue
                    out_path = self.output_dir / (
                        f"{video_stem}_scene_{scene_no:04d}_{pos_name}_{_ts_str(ts)}.jpg"
                    )
                    _save_frame(frame, out_path, self.jpg_quality, self.min_bytes)
                    extracted.append(str(out_path))
                    saved_any = True
                if not saved_any:
                    # Fallback: save mid regardless of blur
                    mid_data = next((x for x in frames_data if x[1] == "mid"), frames_data[0])
                    ts, pos_name, frame, _ = mid_data
                    out_path = self.output_dir / (
                        f"{video_stem}_scene_{scene_no:04d}_{pos_name}_{_ts_str(ts)}.jpg"
                    )
                    _save_frame(frame, out_path, self.jpg_quality, self.min_bytes)
                    extracted.append(str(out_path))

        cap.release()
        return extracted

    # ── public entrypoint ───────────────────────────────────────────────────

    def process_video(
        self,
        video_path: str,
        *,
        window_start_s: float = 0.0,
        window_end_s: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> tuple[list[str], list[tuple[float, float]]]:
        if progress_cb:
            progress_cb("Detecting scenes…")
        scenes = self.detect_scenes(video_path)

        # Window filter
        if window_start_s or window_end_s:
            ws = float(window_start_s or 0.0)
            we = float(window_end_s) if window_end_s else 1e18
            if we <= ws:
                raise ValueError(f"Invalid window: end <= start ({ws} .. {we})")
            scenes = [
                (max(s0, ws), min(s1, we))
                for s0, s1 in scenes
                if not (s1 < ws or s0 > we)
            ]

        if progress_cb:
            progress_cb(f"Extracting frames from {len(scenes)} scenes…")
        images = self.extract_frames(video_path, scenes)
        return images, scenes


# ── Gapfill ────────────────────────────────────────────────────────────────────

_PREFER_OFFSETS = [0.0, -0.25, 0.25, -0.5, 0.5, -0.9, 0.9]


def gapfill_images_for_ad_slots(
    video_path: str,
    ad_slots_df: pd.DataFrame,
    existing_images: list[str],
    output_dir: str,
    blur_threshold: float = 80.0,
    prefer_offsets_s: Optional[list[float]] = None,
    *,
    window_start_s: Optional[float] = None,
    window_end_s: Optional[float] = None,
) -> tuple[list[str], pd.DataFrame]:
    """Map existing scene images to AD slots; extract new frames for uncovered slots.

    Returns:
        all_images: deduplicated list of all image paths (scene + gapfill)
        slot_map_df: DataFrame with columns [slot, slot_start_s, slot_end_s,
                                              img_ts_s, img_path, source]
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if ad_slots_df is None or not isinstance(ad_slots_df, pd.DataFrame) or ad_slots_df.empty:
        raise ValueError("ad_slots_df is missing or empty.")

    required = {"start_s", "end_s"}
    missing = required - set(ad_slots_df.columns)
    if missing:
        raise KeyError(f"ad_slots_df missing columns: {missing}")

    df = ad_slots_df.copy()
    if "slot" not in df.columns:
        df["slot"] = range(1, len(df) + 1)

    for c in ("slot", "start_s", "end_s"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["slot", "start_s", "end_s"])
    df = df[df["end_s"] > df["start_s"]].sort_values("slot").reset_index(drop=True)
    if df.empty:
        raise ValueError("ad_slots_df has no valid slots after cleaning.")

    # Optional window filter
    if window_start_s is not None or window_end_s is not None:
        ws = float(window_start_s or 0.0)
        we = float(window_end_s) if window_end_s is not None else 1e18
        df = df[~((df["end_s"] < ws) | (df["start_s"] > we))].reset_index(drop=True)
        if df.empty:
            raise ValueError("No slots within requested time window.")

    # Build image → timestamp index from filenames
    img_rows: list[dict] = []
    for p in (existing_images or []):
        ts = _extract_ts_from_filename(p)
        if ts is None:
            continue
        img_rows.append({"img_path": str(p), "img_ts_s": float(ts), "source": "scene"})
    imgs_df = pd.DataFrame(img_rows) if img_rows else pd.DataFrame(
        columns=["img_path", "img_ts_s", "source"]
    )

    if prefer_offsets_s is None:
        prefer_offsets_s = _PREFER_OFFSETS

    # Open video for gapfill frame extraction
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("cv2.VideoCapture could not open video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    def _is_blurry(frame: np.ndarray) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var()) < float(blur_threshold)

    def _read_at(ts_s: float):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(ts_s * fps)))
        ok, frame = cap.read()
        return bool(ok), frame

    video_stem = Path(video_path).stem
    added: list[str] = []
    slot_map: list[dict] = []

    for _, r in df.iterrows():
        slot_id = int(r["slot"])
        s0 = float(r["start_s"])
        s1 = float(r["end_s"])

        # Find existing scene images whose timestamp falls inside this slot
        in_slot = (
            imgs_df[(imgs_df["img_ts_s"] >= s0) & (imgs_df["img_ts_s"] <= s1)]
            if not imgs_df.empty
            else pd.DataFrame()
        )

        if not in_slot.empty:
            for _, im in in_slot.sort_values("img_ts_s").iterrows():
                slot_map.append({
                    "slot": slot_id,
                    "slot_start_s": s0,
                    "slot_end_s": s1,
                    "img_ts_s": float(im["img_ts_s"]),
                    "img_path": str(im["img_path"]),
                    "source": "scene",
                })
            continue  # slot covered by existing scene image

        # Gapfill: try blur-retrying offsets from midpoint
        mid = (s0 + s1) / 2.0
        chosen: Optional[tuple[float, np.ndarray]] = None

        for off in prefer_offsets_s:
            ts = max(s0, min(s1, mid + float(off)))
            ok, frame = _read_at(ts)
            if not ok or frame is None:
                continue
            if _is_blurry(frame):
                continue
            chosen = (ts, frame)
            break

        if chosen is None:
            # Final fallback: use midpoint regardless of blur
            ok, frame = _read_at(mid)
            if ok and frame is not None:
                chosen = (mid, frame)

        if chosen is not None:
            ts, frame = chosen
            out_name = f"{video_stem}_slot_{slot_id:04d}_gapfill_{_ts_str(ts)}.jpg"
            out_path = out_dir / out_name
            _save_frame(frame, out_path)

            added.append(str(out_path))
            # Add to index so later slots can reuse this image if it overlaps
            new_row = pd.DataFrame([{
                "img_path": str(out_path),
                "img_ts_s": float(ts),
                "source": "gapfill",
            }])
            imgs_df = pd.concat([imgs_df, new_row], ignore_index=True)

            slot_map.append({
                "slot": slot_id,
                "slot_start_s": s0,
                "slot_end_s": s1,
                "img_ts_s": float(ts),
                "img_path": str(out_path),
                "source": "gapfill",
            })

    cap.release()
    logger.info(f"Gapfill complete: mapped {len(slot_map)} slots to images, extracted {len(added)} new gapfill frames.")

    # Deduplicate all_images preserving order
    seen: set[str] = set()
    all_images: list[str] = []
    for p in (list(existing_images or []) + added):
        if p and p not in seen:
            seen.add(p)
            all_images.append(p)

    slot_map_df = pd.DataFrame(slot_map)
    if not slot_map_df.empty:
        slot_map_df = slot_map_df.sort_values(
            ["slot", "img_ts_s"], ascending=[True, True]
        ).reset_index(drop=True)

    return all_images, slot_map_df
