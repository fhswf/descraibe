"""person_analysis.py – Person detection, tracking and attribute extraction (Step 06).

This module:
1. Detects faces in scene images using OpenCV DNN YuNet face detector
2. Extracts person regions (full body from face bounding box)
3. Detects name overlays (Bauchbinden) via Tesseract OCR
4. Tracks persons across frames using timecode + visual similarity
5. Extracts visual attributes (clothing colors, etc.)
6. Returns a persons_df DataFrame for prompt injection
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Environment / config ────────────────────────────────────────────────────────

_YU_NET_MODEL_PATH = os.environ.get(
    "YU_NET_MODEL_PATH",
    str(Path(__file__).parent.parent.parent / "models" / "face_detection_yunet_2023mar.onnx")
)
_TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "").strip() or None
_TESSERACT_LANG = os.environ.get("TESSERACT_LANG", "deu+eng").strip()


# ── Progress helpers ────────────────────────────────────────────────────────────

def _emit_progress(
    progress_cb: Optional[Callable[..., None]],
    message: str,
    current: Optional[int] = None,
    total: Optional[int] = None,
) -> None:
    if not progress_cb:
        return
    try:
        if current is None or total is None:
            progress_cb(message)
        else:
            progress_cb(message, current, total)
    except TypeError:
        progress_cb(message)


# ── YuNet face detector ─────────────────────────────────────────────────────────

class YuNetDetector:
    """OpenCV DNN-based YuNet face detector with graceful fallback."""

    _instance: Optional["YuNetDetector"] = None
    _model: Optional[Any] = None
    _model_size: Tuple[int, int] = (320, 320)
    _nms_threshold: float = 0.3
    _score_threshold: float = 0.5

    def __new__(cls) -> "YuNetDetector":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True

        model_path = Path(_YU_NET_MODEL_PATH)
        if not model_path.exists():
            logger.warning(
                "YuNet model not found at %s. Face detection will be skipped. "
                "Set YU_NET_MODEL_PATH or download from "
                "https://github.com/ShiqiYu/libfacedetection.train/tree/main/tasks/task1/onnx",
                model_path,
            )
            return False

        try:
            self._model = cv2.dnn.readNet(str(model_path))
            logger.info("YuNet face detector loaded from %s", model_path)
            return True
        except Exception as exc:
            logger.warning("Failed to load YuNet model: %s", exc)
            return False

    def detect(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Detect faces in an image.

        Returns list of dicts with keys: x, y, w, h, confidence.
        """
        if not self._ensure_model():
            return []

        h, w = image.shape[:2]

        # Prepare blob
        blob = cv2.dnn.blobFromImage(
            image, 1.0 / 255.0, self._model_size, (104, 117, 123), swapRB=True
        )
        self._model.setInput(blob)

        try:
            # YuNet outputs: detection (1xN or 1x7 depending on version)
            outputs = self._model.forward(self._model.getUnconnectedOutLayersNames())
            if isinstance(outputs, (list, tuple)):
                outputs = outputs[0] if len(outputs) == 1 else np.concatenate(outputs, axis=0)
        except Exception as exc:
            logger.warning("YuNet inference failed: %s", exc)
            return []

        detections: List[Dict[str, Any]] = []

        # Parse outputs (shape depends on model version; handle both formats)
        for i in range(outputs.shape[0] if len(outputs.shape) > 1 else outputs.shape[1]):
            if len(outputs.shape) == 2:
                row = outputs[i]
            else:
                row = outputs[:, i] if outputs.shape[0] < outputs.shape[1] else outputs[i]
                if row.shape[0] > 5:
                    row = row.flatten()

            if len(row) >= 5:
                confidence = float(row[14]) if len(row) > 14 else float(row[4])
                if confidence < self._score_threshold:
                    continue

                # Handle different output formats
                if len(row) >= 15:
                    # Full format: x1, y1, x2, y2, conf, ...
                    x1, y1, x2, y2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])
                else:
                    # Compact format: rel_x, rel_y, w, h, conf
                    rel_x, rel_y, bw, bh, conf = row[:5]
                    x1 = rel_x * w
                    y1 = rel_y * h
                    x2 = x1 + bw * w
                    y2 = y1 + bh * h

                x, y = max(0.0, min(float(x1), w - 1)), max(0.0, min(float(y1), h - 1))
                bw = max(1, int(min(float(x2 - x1), w - x)))
                bh = max(1, int(min(float(y2 - y1), h - y)))

                detections.append({
                    "x": int(x),
                    "y": int(y),
                    "w": bw,
                    "h": bh,
                    "confidence": confidence,
                })

        return detections


def detect_faces_in_image(image_path: str) -> List[Dict[str, Any]]:
    """Load an image and detect faces using YuNet."""
    img = cv2.imread(str(image_path))
    if img is None:
        logger.warning("Could not read image: %s", image_path)
        return []

    detector = YuNetDetector()
    return detector.detect(img)


# ── Person region extraction ────────────────────────────────────────────────────

def extract_person_region(
    image: np.ndarray,
    face_bbox: Dict[str, Any],
    extend_ratio: float = 1.8,
) -> np.ndarray:
    """Extract full-body region from face bounding box.

    Args:
        image: BGR image array
        face_bbox: dict with x, y, w, h
        extend_ratio: how much to extend vertically above and below face

    Returns:
        Cropped person region image (BGR), or empty array if invalid
    """
    h, w = image.shape[:2]
    fx, fy, fw, fh = int(face_bbox["x"]), int(face_bbox["y"]), int(face_bbox["w"]), int(face_bbox["h"])

    # Extend vertically
    extra_h = int(fh * extend_ratio)
    top = max(0, fy - extra_h)
    bottom = min(h, fy + fh + extra_h)

    # Keep face horizontally centered with some padding
    pad_x = int(fw * 0.3)
    left = max(0, fx - pad_x)
    right = min(w, fx + fw + pad_x)

    if bottom <= top or right <= left:
        return np.array([])

    return image[top:bottom, left:right]


# ── Name overlay detection (OCR) ────────────────────────────────────────────────

def detect_name_overlay(image_path: str) -> Optional[str]:
    """Detect name overlay text (Bauchbinden) in an image.

    Looks for horizontal text bars near the top or bottom of the frame,
    which is typical for news/broadcast name plates.

    Returns:
        Detected name text or None if not found.
    """
    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract not installed, skipping OCR")
        return None

    if _TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD

    img = cv2.imread(str(image_path))
    if img is None:
        return None

    h, w = img.shape[:2]

    # Focus on potential Bauchbinden regions (top 25% and bottom 15%)
    regions = [
        img[: int(h * 0.25), :],  # Top region
        img[int(h * 0.85):, :],   # Bottom region
    ]

    best_text = None
    best_confidence = 0.0

    for region in regions:
        if region.size == 0:
            continue

        # Convert to grayscale
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

        # Apply thresholding to make text stand out
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Get OCR data with confidence
        try:
            data = pytesseract.image_to_data(
                thresh,
                lang=_TESSERACT_LANG,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:
            logger.debug("Tesseract failed on region: %s", exc)
            continue

        # Look for text with reasonable confidence
        for i, conf in enumerate(data.get("conf", [])):
            conf_val = float(conf) if conf != "-1" else 0.0
            if conf_val < 40:
                continue

            text = "".join(
                c for c in data["text"][i] if c.isprintable()
            ).strip()

            # Filter out timestamps, watermarks, short strings
            if len(text) < 2:
                continue
            if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", text):  # timestamps
                continue
            if len(text) > 30:  # likely not a person name
                continue

            if conf_val > best_confidence:
                best_confidence = conf_val
                best_text = text

    return best_text


# ── Attribute extraction ────────────────────────────────────────────────────────

def _rgb_to_color_name(r: int, g: int, b: int) -> str:
    """Map RGB to a human-readable color name."""
    # Simple color mapping based on HSV ranges
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])

    # Grayscale
    if s < 30:
        if v > 200:
            return "weiß"
        elif v > 150:
            return "hellgrau"
        elif v > 100:
            return "grau"
        elif v > 50:
            return "dunkelgrau"
        else:
            return "schwarz"

    # Brown / Orange / Yellow
    if 5 <= h <= 45:
        if s > 150 and v > 150:
            return "orange"
        if s > 100:
            return "braun"
        return "dunkelbraun"

    # Yellow
    if 20 <= h <= 40 and s > 100:
        return "gelb"

    # Green
    if 40 <= h <= 85:
        if s > 150 and v > 150:
            return "grün"
        elif v > 100:
            return "dunkelgrün"
        return "olivgrün"

    # Cyan / Teal
    if 85 <= h <= 110:
        return "türkis"

    # Blue
    if 95 <= h <= 135:
        if v > 150 and s > 150:
            return "blau"
        elif v > 100:
            return "dunkelblau"
        return "navy"

    # Purple / Magenta
    if 135 <= h <= 175:
        return "violett"

    # Red / Pink
    if (h <= 10 or h >= 170) and s > 100:
        if v > 150 and s < 180:
            return "rosa"
        return "rot"

    return "bunt"


def _dominant_color(image: np.ndarray, region: str = "bottom_half") -> Optional[str]:
    """Extract dominant color name from an image region."""
    if image.size == 0 or image.shape[0] < 10 or image.shape[1] < 10:
        return None

    h, w = image.shape[:2]

    # Focus on different regions based on what we're analyzing
    if region == "top":
        region_img = image[: h // 2, :]
    elif region == "bottom":
        region_img = image[h // 2 :, :]
    elif region == "bottom_half":
        region_img = image[h // 2 :, :]
    else:
        region_img = image

    # Resize for faster k-means
    small = cv2.resize(region_img, (50, 50))

    # Reshape to pixel list
    pixels = small.reshape(-1, 3).astype(np.float32)

    # Simple dominant color via histogram in HSV
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
    hist = hist.flatten()
    dominant_h = int(np.argmax(hist))

    # Convert back to RGB for color name
    dummy = np.uint8([[[dominant_h, 200, 200]]])
    dummy_bgr = cv2.cvtColor(dummy, cv2.COLOR_HSV2BGR)[0][0]
    r, g, b = int(dummy_bgr[2]), int(dummy_bgr[1]), int(dummy_bgr[0])

    return _rgb_to_color_name(r, g, b)


def extract_person_attributes(
    image: np.ndarray,
    face_bbox: Dict[str, Any],
    person_region: np.ndarray,
) -> Dict[str, Any]:
    """Extract visual attributes from a person region."""
    attributes: Dict[str, Any] = {}

    if person_region.size == 0:
        return attributes

    # Clothing colors
    if person_region.shape[0] >= 20:
        top_color = _dominant_color(person_region, region="top")
        bottom_color = _dominant_color(person_region, region="bottom")
        if top_color:
            attributes["top_color"] = top_color
        if bottom_color:
            attributes["bottom_color"] = bottom_color

    # Overall dominant color
    overall_color = _dominant_color(person_region, region="bottom_half")
    if overall_color:
        attributes["dominant_color"] = overall_color

    # Face-based age proxy (confidence as proxy)
    attributes["face_confidence"] = float(face_bbox.get("confidence", 0.0))

    return attributes


# ── Person tracking ─────────────────────────────────────────────────────────────

def _compute_iou(bbox1: Dict[str, Any], bbox2: Dict[str, Any]) -> float:
    """Compute Intersection over Union between two bounding boxes."""
    x1 = max(bbox1["x"], bbox2["x"])
    y1 = max(bbox1["y"], bbox2["y"])
    x2 = min(bbox1["x"] + bbox1["w"], bbox2["x"] + bbox2["w"])
    y2 = min(bbox1["y"] + bbox1["h"], bbox2["y"] + bbox2["h"])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    inter = (x2 - x1) * (y2 - y1)
    area1 = bbox1["w"] * bbox1["h"]
    area2 = bbox2["w"] * bbox2["h"]
    union = area1 + area2 - inter

    return inter / union if union > 0 else 0.0


def _face_region_color(image: np.ndarray, face_bbox: Dict[str, Any]) -> Tuple[float, float, float]:
    """Get mean color of face region for visual similarity."""
    x, y, w, h = int(face_bbox["x"]), int(face_bbox["y"]), int(face_bbox["w"]), int(face_bbox["h"])
    h_img, w_img = image.shape[:2]

    # Sample a smaller region inside the face
    x1, y1 = max(0, x + w // 4), max(0, y + h // 4)
    x2, y2 = min(w_img, x + 3 * w // 4), min(h_img, y + 3 * h // 4)

    if x2 <= x1 or y2 <= y1:
        return (0.0, 0.0, 0.0)

    face_region = image[y1:y2, x1:x2]
    mean_color = cv2.mean(face_region)
    return (mean_color[0], mean_color[1], mean_color[2])


def _color_distance(c1: Tuple[float, float, float], c2: Tuple[float, float, float]) -> float:
    """Euclidean distance between two BGR colors."""
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


class Person:
    """Represents a tracked person across video frames."""

    def __init__(
        self,
        person_id: int,
        first_seen_ts: float,
        name: Optional[str] = None,
    ):
        self.person_id = person_id
        self.name = name
        self.first_seen_ts = first_seen_ts
        self.last_seen_ts = first_seen_ts
        self.appearances: List[Dict[str, Any]] = []
        self.attributes: Dict[str, Any] = {}
        self.description: str = ""
        self._face_colors: List[Tuple[float, float, float]] = []

    def add_appearance(
        self,
        timestamp_s: float,
        image_path: str,
        face_bbox: Dict[str, Any],
        person_region: np.ndarray,
        attributes: Dict[str, Any],
    ) -> None:
        self.appearances.append({
            "timestamp_s": timestamp_s,
            "image_path": image_path,
            "face_bbox": face_bbox,
        })
        self.last_seen_ts = timestamp_s

        # Merge attributes (prefer first non-None values)
        for key, value in attributes.items():
            if key not in self.attributes or self.attributes[key] is None:
                self.attributes[key] = value

    def update_color(self, color: Tuple[float, float, float]) -> None:
        self._face_colors.append(color)
        if len(self._face_colors) > 5:
            self._face_colors.pop(0)

    def mean_color(self) -> Tuple[float, float, float]:
        if not self._face_colors:
            return (0.0, 0.0, 0.0)
        return tuple(sum(colors) / len(self._face_colors) for colors in zip(*self._face_colors))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "person_id": self.person_id,
            "name": self.name,
            "first_seen_ts": self.first_seen_ts,
            "last_seen_ts": self.last_seen_ts,
            "appearances_count": len(self.appearances),
            "attributes": self.attributes,
            "description": self.description,
        }


def track_persons_across_frames(
    detections_by_image: List[Dict[str, Any]],
) -> List[Person]:
    """Match detected persons across images using timecode + visual similarity.

    Args:
        detections_by_image: List of dicts with keys: image_path, timestamp_s, faces

    Returns:
        List of Person objects with assigned IDs
    """
    persons: List[Person] = []
    next_person_id = 1

    IOU_THRESHOLD = 0.3
    COLOR_THRESHOLD = 80.0  # BGR Euclidean distance

    for detection in detections_by_image:
        image_path = detection["image_path"]
        timestamp_s = detection["timestamp_s"]
        faces = detection["faces"]

        if not faces:
            continue

        # Load image for color extraction
        img = cv2.imread(str(image_path))
        if img is None:
            continue

        # Try to match each face to existing persons
        unmatched_faces = []
        for face_bbox in faces:
            matched = False
            face_color = _face_region_color(img, face_bbox)

            for person in persons:
                # Check temporal overlap (person can only be in consecutive frames)
                if timestamp_s - person.last_seen_ts > 30.0:  # 30s gap = different person
                    continue

                # Check visual similarity
                person_color = person.mean_color()
                if _color_distance(face_color, person_color) > COLOR_THRESHOLD:
                    continue

                # Check IoU with last appearance
                if person.appearances:
                    last_bbox = person.appearances[-1]["face_bbox"]
                    if _compute_iou(face_bbox, last_bbox) < IOU_THRESHOLD:
                        continue

                # Matched!
                person_region = extract_person_region(img, face_bbox)
                attributes = extract_person_attributes(img, face_bbox, person_region)
                person.add_appearance(timestamp_s, image_path, face_bbox, person_region, attributes)
                person.update_color(face_color)
                matched = True
                break

            if not matched:
                unmatched_faces.append((face_bbox, face_color))

        # Create new persons for unmatched faces
        for face_bbox, face_color in unmatched_faces:
            person = Person(next_person_id, timestamp_s)
            person_region = extract_person_region(img, face_bbox)
            attributes = extract_person_attributes(img, face_bbox, person_region)
            person.add_appearance(timestamp_s, image_path, face_bbox, person_region, attributes)
            person.update_color(face_color)

            # Try to detect name from this frame
            name = detect_name_overlay(image_path)
            if name:
                person.name = name
                person.description = f"{name}"

            persons.append(person)
            next_person_id += 1

    # Post-process: build descriptions
    for person in persons:
        attrs = person.attributes
        color_parts = []
        if attrs.get("top_color"):
            color_parts.append(f"{attrs['top_color']}es Oberteil")
        if attrs.get("bottom_color"):
            color_parts.append(f"{attrs['bottom_color']}e Hose/dunkle Hose")

        if color_parts:
            person.description = f"{person.name or f'Person {person.person_id}'}: {', '.join(color_parts)}"
        elif person.name:
            person.description = person.name
        else:
            person.description = f"Person {person.person_id}"

    logger.info("Tracked %d unique persons across %d images", len(persons), len(detections_by_image))
    return persons


# ── Timestamp helpers (shared with image_extraction) ────────────────────────────

_TS_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{2})-(\d{3})$")


def _extract_ts_from_filename(path: str) -> Optional[float]:
    """Parse HH-MM-SS-mmm timestamp from a filename."""
    parts = Path(path).stem.split("_")
    for part in reversed(parts):
        m = _TS_RE.match(part)
        if m:
            hh, mm, ss, ms = map(int, m.groups())
            return hh * 3600 + mm * 60 + ss + ms / 1000.0
    return None


# ── Main entry point ────────────────────────────────────────────────────────────

def analyze_persons(
    scene_images: List[str],
    progress_cb: Optional[Callable[..., None]] = None,
) -> pd.DataFrame:
    """Analyze persons in scene images.

    Args:
        scene_images: List of image file paths (with HH-MM-SS-mmm timestamps in names)
        progress_cb: Optional callback for progress updates

    Returns:
        DataFrame with columns: person_id, name, first_seen_ts, last_seen_ts,
        appearances_count, attributes (JSON), description
    """
    _emit_progress(progress_cb, "Detecting persons in images…", 0, len(scene_images))

    detections_by_image: List[Dict[str, Any]] = []

    for idx, img_path in enumerate(scene_images):
        timestamp_s = _extract_ts_from_filename(img_path) or 0.0
        faces = detect_faces_in_image(img_path)

        detections_by_image.append({
            "image_path": img_path,
            "timestamp_s": timestamp_s,
            "faces": faces,
        })

        if (idx + 1) % 10 == 0 or idx == len(scene_images) - 1:
            _emit_progress(
                progress_cb,
                f"Detecting faces in image {idx + 1}/{len(scene_images)}…",
                idx + 1,
                len(scene_images),
            )

    _emit_progress(progress_cb, "Tracking persons across frames…")
    persons = track_persons_across_frames(detections_by_image)

    # Build DataFrame
    rows = []
    for person in persons:
        rows.append({
            "person_id": person.person_id,
            "name": person.name,
            "first_seen_ts": person.first_seen_ts,
            "last_seen_ts": person.last_seen_ts,
            "appearances_count": len(person.appearances),
            "attributes": json.dumps(person.attributes),
            "description": person.description,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("first_seen_ts").reset_index(drop=True)

    _emit_progress(progress_cb, f"Person analysis complete: {len(persons)} persons detected", len(scene_images), len(scene_images))
    return df