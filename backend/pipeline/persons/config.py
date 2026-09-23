# backend/pipeline/persons/config.py

# RF-DETR
PERSON_CLASS_ID = 1
RFDETR_CONFIDENCE_THRESHOLD = 0.50

# ByteTrack
LOST_TRACK_BUFFER = 30
TRACK_ACTIVATION_THRESHOLD = 0.70
MINIMUM_CONSECUTIVE_FRAMES = 2
MINIMUM_IOU_THRESHOLD = 0.10
HIGH_CONF_DET_THRESHOLD = 0.60

# Tracking sampling; RetinaFace runs on every second sampled frame.
TRACKING_INTERVAL_SECONDS = 0.233

# RetinaFace
RETINAFACE_CONFIDENCE_THRESHOLD = 0.50
RETINAFACE_NMS_THRESHOLD = 0.40
RETINAFACE_INPUT_SIZE = (640, 640)
RETINAFACE_DYNAMIC_SIZE = False
RETINAFACE_PRE_NMS_TOPK = 5000
RETINAFACE_POST_NMS_TOPK = 750
RETINAFACE_MAX_NUM = 0

FACE_MARGIN_RATIO = 0.10
FACE_ALIGNMENT_SIZE = 112

# Face quality
FACE_QUALITY_IMAGE_SIZE = (112, 112)
FACE_BLUR_THRESHOLD = 5.0

# Defaults for the optional person settings; each run receives its own values.
SIMILARITY_THRESHOLD = 0.214
MAX_IMAGES_PER_PERSON = 5


def validate_parameter(name, value):
    """Validate before starting work, including direct Python callers."""
    import math
    from .review_artifacts import ReviewError

    valid = type(value) in (int, float) and math.isfinite(value)
    if name == "tracking_interval_seconds":
        valid = valid and 0 < value <= 10
        message = "Trackingabstand muss größer als 0 und höchstens 10 Sekunden sein."
    elif name == "similarity_threshold":
        valid = valid and -1 <= value <= 1
        message = "Clustering-Schwellenwert muss zwischen -1 und 1 liegen."
    elif name == "max_images":
        valid = type(value) is int and 1 <= value <= MAX_IMAGES_PER_PERSON
        message = "Die maximale Bilderzahl muss eine ganze Zahl von 1 bis 5 sein."
    else:
        raise ValueError(name)
    if not valid:
        raise ReviewError(message)
    return value
