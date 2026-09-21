"""Tested attribute selection over existing clean crops only. No face-quality filter."""
import cv2
import numpy as np
from .review_artifacts import ReviewError
from .config import MAX_IMAGES_PER_PERSON, validate_parameter

MIN_PERSON_HEIGHT_RATIO = 0.15

PREFERRED_PERSON_HEIGHT_RATIO = 0.25

BORDER_MARGIN_RATIO = 0.02

PERSON_BLUR_IMAGE_SIZE = (224, 448)

WEIGHT_PERSON_BLUR = 0.50

WEIGHT_PERSON_SIZE = 0.30

WEIGHT_NOT_AT_BORDER = 0.20

def is_near_border(
    bbox: tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
) -> bool:
    x1, y1, x2, y2 = bbox

    margin_x = frame_width * BORDER_MARGIN_RATIO
    margin_y = frame_height * BORDER_MARGIN_RATIO

    return (
        x1 <= margin_x
        or y1 <= margin_y
        or x2 >= frame_width - margin_x
        or y2 >= frame_height - margin_y
    )

def normalize_values(
    values: list[float],
) -> list[float]:
    """
    Min-Max-Normalisierung auf den Bereich 0 bis 1.

    Wenn alle Werte innerhalb der Vergleichsgruppe identisch sind,
    erhalten alle den neutralen Wert 0.5.
    """
    if not values:
        return []

    minimum = min(values)
    maximum = max(values)

    if abs(maximum - minimum) < 1e-12:
        return [0.5] * len(values)

    return [
        (value - minimum) / (maximum - minimum)
        for value in values
    ]

def calculate_person_blur_score(
    person_crop: np.ndarray,
) -> float:
    """
    Berechnet die Schärfe des gesamten Personen-Crops.

    Vorgehen:
    1. Crop auf 224 x 448 skalieren
    2. in Graustufen umwandeln
    3. Laplacian berechnen
    4. Varianz des Laplacian bestimmen

    Ein höherer Wert steht normalerweise für mehr
    lokale Kanten und damit für einen schärferen Crop.
    """
    if (
        person_crop is None
        or person_crop.size == 0
    ):
        return 0.0

    resized = cv2.resize(
        person_crop,
        PERSON_BLUR_IMAGE_SIZE,
        interpolation=cv2.INTER_LINEAR,
    )

    gray = cv2.cvtColor(
        resized,
        cv2.COLOR_BGR2GRAY,
    )

    return float(
        cv2.Laplacian(
            gray,
            cv2.CV_64F,
        ).var()
    )

def score_candidates(
    candidates: list[dict],
) -> None:
    """
    Berechnet den finalen additiven Qualitäts-Score.

    50 % Schärfe des gesamten Personen-Crops
    30 % relative Personengröße
    20 % nicht am Bildrand

    Gesichtswerte und RF-DETR-Confidence fließen nicht
    in die Auswahl ein.
    """
    if not candidates:
        return

    # Laplacian-Werte können stark auseinanderliegen.
    # log1p reduziert den Einfluss extremer Ausreißer.
    log_blur_values = [
        float(
            np.log1p(
                max(
                    0.0,
                    candidate[
                        "person_blur_score"
                    ],
                )
            )
        )
        for candidate in candidates
    ]

    normalized_blur_values = (
        normalize_values(
            log_blur_values
        )
    )

    for (
        candidate,
        normalized_blur,
    ) in zip(
        candidates,
        normalized_blur_values,
    ):
        # Die Person muss bereits mindestens 15 % groß sein.
        # Ab 25 % gibt es für die Größenbewertung 1.0.
        size_score = min(
            candidate["height_ratio"]
            / PREFERRED_PERSON_HEIGHT_RATIO,
            1.0,
        )

        border_score = (
            0.0
            if candidate[
                "near_frame_border"
            ]
            else 1.0
        )

        selection_score = (
            WEIGHT_PERSON_BLUR
            * normalized_blur

            + WEIGHT_PERSON_SIZE
            * size_score

            + WEIGHT_NOT_AT_BORDER
            * border_score
        )

        candidate[
            "size_score"
        ] = size_score

        candidate[
            "normalized_person_blur"
        ] = normalized_blur

        candidate[
            "border_score"
        ] = border_score

        candidate[
            "selection_score"
        ] = selection_score

def choose_track_representative(
    track_candidates: list[dict],
) -> dict:
    """
    Bewertet alle Beobachtungen eines Tracks und behält
    genau den Kandidaten mit dem höchsten Score.
    """
    score_candidates(
        track_candidates
    )

    representative = max(
        track_candidates,
        key=lambda candidate: (
            candidate["selection_score"],
            candidate["person_blur_score"],
            candidate["height_ratio"],
        ),
    )

    result = dict(representative)

    result[
        "track_selection_score"
    ] = representative[
        "selection_score"
    ]

    return result

def select_images(
    candidates_by_track: dict[
        int,
        list[dict],
    ],
    max_images: int,
) -> list[dict]:
    """
    Zweistufige Auswahl:

    1. Pro Track wird genau ein Repräsentant gewählt.
    2. Alle Track-Repräsentanten derselben Person werden
       erneut relativ zueinander bewertet.
    3. Maximal fünf Bilder werden behalten.
    """
    representatives = []

    for (
        track_id,
        track_candidates,
    ) in sorted(
        candidates_by_track.items()
    ):
        representative = (
            choose_track_representative(
                track_candidates
            )
        )

        representative[
            "selection_type"
        ] = "Track-Repräsentant"

        representatives.append(
            representative
        )

    # Zweite Bewertungsstufe:
    # Die Repräsentanten verschiedener Tracks derselben
    # Person werden erneut miteinander verglichen.
    score_candidates(
        representatives
    )

    representatives.sort(
        key=lambda candidate: (
            candidate["selection_score"],
            candidate["person_blur_score"],
            candidate["height_ratio"],
        ),
        reverse=True,
    )

    selected = representatives[
        :max_images
    ]

    # Für die Ausgabe wieder chronologisch sortieren.
    return sorted(
        selected,
        key=lambda item: item[
            "frame_number"
        ],
    )


def select_existing(data, frame_width, frame_height, max_images=MAX_IMAGES_PER_PERSON):
    """Wählt die vorhandenen aktuellen Personencrops ohne neue Bilder zu erzeugen."""
    validate_parameter("max_images", max_images)
    if frame_width <= 0 or frame_height <= 0:
        raise ReviewError("Frameabmessungen fehlen.", 409)
    people = {person_id: {} for person_id in data.persons}
    for track_id, crops in data.by_track.items():
        person_id = data.assignments[track_id]
        if person_id is None or data.tracks[track_id]["excluded"]:
            continue
        groups, seen = [[], []], set()
        for crop in crops:
            if crop["frame_number"] in seen:
                continue
            x1, y1, x2, y2 = crop["person_bbox"]
            height_ratio = (y2 - y1) / frame_height
            if height_ratio < MIN_PERSON_HEIGHT_RATIO:
                continue
            path = data.crop_file(crop["crop_id"])
            image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ReviewError(f"Vorhandener Crop {crop['crop_id']} ist nicht lesbar.", 409)
            seen.add(crop["frame_number"])
            candidate = {
                **crop, "identity_id": person_id, "bbox": crop["person_bbox"], "height_ratio": height_ratio,
                "near_frame_border": is_near_border(tuple(crop["person_bbox"]), frame_width, frame_height),
                "person_blur_score": calculate_person_blur_score(image),
            }
            groups[0 if crop["face_bbox"] is not None else 1].append(candidate)
        candidates = groups[0] or groups[1]
        if candidates:
            people[person_id][track_id] = candidates
    return {person_id: select_images(tracks, max_images) for person_id, tracks in sorted(people.items())}
