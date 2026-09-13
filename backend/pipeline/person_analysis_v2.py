from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

from .persons.appearances import (
    TrackIntervalAccumulator,
)
from .persons.clustering import (
    run_clustering,
)
from .persons.config import (
    ANALYSIS_INTERVAL_SECONDS,
)
from .persons.detection import (
    RFDETRPersonDetector,
)
from .persons.face_detection import (
    RetinaFaceDetector,
)
from .persons.face_observations import (
    FaceObservationWriter,
)
from .persons.face_quality import (
    check_face_quality,
)
from .persons.face_recognition import (
    FaceMoERecognizer,
)
from .persons.person_crops import (
    PersonCropWriter,
)
from .persons.tracking import (
    BytePersonTracker,
    detect_scene_change_frames,
)


PROJECT_ROOT = (
    Path(__file__).resolve().parents[2]
)

MODEL_ROOT = (
    PROJECT_ROOT
    / "models"
)


# ============================================================
# Gesicht -> Track
# ============================================================


def assign_faces_to_tracks(
    faces: list[dict],
    tracked_persons: list[dict],
) -> dict[int, dict]:
    """
    Ordnet erkannte Gesichter den aktuell sichtbaren
    Personen-Tracks zu.

    Regeln:
    - Gesichtsmittelpunkt muss innerhalb der Person liegen.
    - Falls mehrere Personen infrage kommen, wird die
      erwartete Kopfposition berücksichtigt.
    - Pro Analyseframe:
        * ein Gesicht höchstens einem Track
        * ein Track höchstens einem Gesicht
    """

    candidates = []

    for face_index, face in enumerate(faces):

        (
            fx1,
            fy1,
            fx2,
            fy2,
        ) = face["bbox"]

        face_cx = (
            fx1 + fx2
        ) / 2.0

        face_cy = (
            fy1 + fy2
        ) / 2.0

        for person in tracked_persons:

            (
                x1,
                y1,
                x2,
                y2,
            ) = person["bbox"]

            if not (
                x1 <= face_cx <= x2
                and y1 <= face_cy <= y2
            ):
                continue

            person_width = max(
                1.0,
                float(x2 - x1),
            )

            person_height = max(
                1.0,
                float(y2 - y1),
            )

            expected_head_x = (
                x1 + x2
            ) / 2.0

            expected_head_y = (
                y1
                + 0.20
                * person_height
            )

            score = (
                (
                    (
                        face_cx
                        - expected_head_x
                    )
                    / person_width
                )
                ** 2
                +
                (
                    (
                        face_cy
                        - expected_head_y
                    )
                    / person_height
                )
                ** 2
            )

            candidates.append(
                (
                    score,
                    face_index,
                    person,
                )
            )

    candidates.sort(
        key=lambda item: item[0]
    )

    assignments: dict[
        int,
        dict,
    ] = {}

    used_tracks: set[int] = set()

    for (
        _score,
        face_index,
        person,
    ) in candidates:

        track_id = int(
            person["track_id"]
        )

        if face_index in assignments:
            continue

        if track_id in used_tracks:
            continue

        assignments[
            face_index
        ] = person

        used_tracks.add(
            track_id
        )

    return assignments


# ============================================================
# Personen aus geclusterten Tracks bauen
# ============================================================


def build_persons(
    tracks: list[dict],
    track_to_person: dict[
        int,
        int,
    ],
) -> list[dict]:
    """
    Baut aus den geclusterten Tracks die automatisch
    erkannten Personen.

    Wichtig:
    Tracks ohne FaceMoE-basierte Identität werden hier
    NICHT als eigene Person erzeugt.

    Ein Track entspricht einem Zeitintervall.
    Eine Person kann mehrere Tracks und damit mehrere
    Erscheinungsintervalle besitzen.
    """

    grouped_tracks: dict[
        int,
        list[dict],
    ] = {}

    for track in tracks:

        track_id = int(
            track["track_id"]
        )

        if track_id not in track_to_person:
            continue

        person_id = int(
            track_to_person[
                track_id
            ]
        )

        grouped_tracks.setdefault(
            person_id,
            [],
        ).append(
            track
        )

    persons = []

    for person_id in sorted(
        grouped_tracks
    ):

        person_tracks = sorted(
            grouped_tracks[
                person_id
            ],
            key=lambda item: (
                float(
                    item["start_s"]
                ),
                int(
                    item["track_id"]
                ),
            ),
        )

        segments = []
        appearances = []

        for track in person_tracks:

            segment = {
                "track_id": int(
                    track["track_id"]
                ),
                "scene_id": int(
                    track["scene_id"]
                ),
                "start_s": float(
                    track["start_s"]
                ),
                "end_s": float(
                    track["end_s"]
                ),
            }

            segments.append(
                segment
            )

            appearances.append(
                {
                    "start_s": float(
                        track["start_s"]
                    ),
                    "end_s": float(
                        track["end_s"]
                    ),
                }
            )

        first_seen_ts = min(
            appearance["start_s"]
            for appearance
            in appearances
        )

        last_seen_ts = max(
            appearance["end_s"]
            for appearance
            in appearances
        )

        persons.append(
            {
                "person_id": int(
                    person_id
                ),
                "name": (
                    f"Person {person_id}"
                ),
                "function": "",
                "track_ids": [
                    int(
                        track[
                            "track_id"
                        ]
                    )
                    for track
                    in person_tracks
                ],
                "segments": segments,
                "appearances": appearances,
                "first_seen_ts": float(
                    first_seen_ts
                ),
                "last_seen_ts": float(
                    last_seen_ts
                ),
                "attributes": {},
            }
        )

    return persons


# ============================================================
# Track-Zuordnung speichern
# ============================================================


def save_track_identities(
    output_path: Path,
    tracks: list[dict],
    track_to_person: dict[
        int,
        int,
    ],
) -> None:
    """
    Speichert für jeden Track den aktuellen
    Zuordnungsstatus.

    Tracks ohne FaceMoE-basierte Identität erhalten
    keine person_id.

    Es werden keine Embeddings gespeichert.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:

        writer = csv.writer(
            csv_file,
            delimiter=";",
        )

        writer.writerow(
            [
                "person_id",
                "track_id",
                "assignment_source",
            ]
        )

        for track in sorted(
            tracks,
            key=lambda item: int(
                item["track_id"]
            ),
        ):

            track_id = int(
                track["track_id"]
            )

            if track_id in track_to_person:

                writer.writerow(
                    [
                        int(
                            track_to_person[
                                track_id
                            ]
                        ),
                        track_id,
                        "facemoe_cluster",
                    ]
                )

            else:

                writer.writerow(
                    [
                        "",
                        track_id,
                        "unassigned_no_embedding",
                    ]
                )


# ============================================================
# Personenergebnis speichern
# ============================================================


def save_persons(
    output_path: Path,
    video_path: Path,
    tracks: list[dict],
    persons: list[dict],
    unassigned_tracks: list[dict],
) -> None:
    """
    Speichert das vollständige automatische
    Personenergebnis.

    Automatisch erkannte Personen und nicht zugeordnete
    Tracks werden getrennt gespeichert.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    unassigned_data = []

    for track in sorted(
        unassigned_tracks,
        key=lambda item: int(
            item["track_id"]
        ),
    ):

        unassigned_data.append(
            {
                "track_id": int(
                    track["track_id"]
                ),
                "scene_id": int(
                    track["scene_id"]
                ),
                "start_s": float(
                    track["start_s"]
                ),
                "end_s": float(
                    track["end_s"]
                ),
                "faces_assigned": int(
                    track.get(
                        "faces_assigned",
                        0,
                    )
                ),
                "faces_usable": int(
                    track.get(
                        "faces_usable",
                        0,
                    )
                ),
                "alignment_failures": int(
                    track.get(
                        "alignment_failures",
                        0,
                    )
                ),
                "embeddings_created": int(
                    track.get(
                        "embeddings_created",
                        0,
                    )
                ),
                "embedding_errors": int(
                    track.get(
                        "embedding_errors",
                        0,
                    )
                ),
            }
        )

    payload = {
        "video": video_path.name,
        "track_count": len(
            tracks
        ),
        "person_count": len(
            persons
        ),
        "unassigned_track_count": len(
            unassigned_data
        ),
        "persons": persons,
        "unassigned_tracks": (
            unassigned_data
        ),
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


# ============================================================
# Hauptanalyse
# ============================================================


def analyze_persons(
    video_path: str | Path,
    progress_cb=None,
) -> dict:
    """
    Führt die vollständige automatische
    Personenanalyse aus.

    Ablauf:

        Video
        ↓
        Szenenerkennung
        ↓
        RF-DETR Nano
        ↓
        ByteTrack
        ↓
        alle Personencrops speichern
        ↓
        RetinaFace alle 0,5 Sekunden
        ↓
        Face -> Track
        ↓
        Face Quality
        ↓
        Face Alignment
        ↓
        FaceMoE
        ↓
        Embeddings nur im RAM
        ↓
        Track-Clustering
        ↓
        automatische Personen

    Tracks ohne FaceMoE-Embedding werden NICHT
    automatisch einer Person zugeordnet.

    Sie bleiben als unassigned_tracks erhalten.

    FaceMoE-Embeddings werden niemals persistent
    gespeichert.
    """

    video_path = Path(
        video_path
    )

    if not video_path.is_file():

        raise FileNotFoundError(
            "Video nicht gefunden:\n"
            f"{video_path}"
        )

    video = cv2.VideoCapture(
        str(video_path)
    )

    if not video.isOpened():

        raise RuntimeError(
            "Video konnte nicht geöffnet werden:\n"
            f"{video_path}"
        )

    fps = float(
        video.get(
            cv2.CAP_PROP_FPS
        )
    )

    frame_count = int(
        video.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    if fps <= 0:

        video.release()

        raise RuntimeError(
            "Ungültige Framerate."
        )

    analysis_interval_frames = max(
        1,
        int(
            round(
                fps
                * ANALYSIS_INTERVAL_SECONDS
            )
        ),
    )

    analysis_output_dir = (
        video_path.parent
        / "person_analysis_v2"
    )

    analysis_output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print(
        "PERSONENANALYSE V2"
    )
    print(
        "=================="
    )
    print()

    print(
        f"Video: {video_path}"
    )

    print(
        f"FPS: {fps:.3f}"
    )

    print(
        f"Frames: {frame_count}"
    )

    print(
        "Gesichtsanalyse alle "
        f"{ANALYSIS_INTERVAL_SECONDS:.2f} s "
        f"({analysis_interval_frames} Frames)"
    )

    print(
        "Personencrops: "
        "jede getrackte Beobachtung"
    )

    print(
        "Face-Metadaten: "
        "ohne Bildduplikate"
    )

    print(
        "FaceMoE-Embeddings: "
        "nur im RAM"
    )

    print(
        "Tracks ohne FaceMoE: "
        "bleiben unassigned"
    )

    print(
        f"Ausgabe: "
        f"{analysis_output_dir}"
    )

    print()

    # --------------------------------------------------------
    # Szenenwechsel
    # --------------------------------------------------------

    print(
        "Szenenwechsel werden erkannt ..."
    )

    scene_change_frames = (
        detect_scene_change_frames(
            video_path
        )
    )

    print(
        "Szenenwechsel erkannt: "
        f"{len(scene_change_frames)}"
    )

    # --------------------------------------------------------
    # Modelle / Tracker
    # --------------------------------------------------------

    person_detector = (
        RFDETRPersonDetector()
    )

    person_tracker = (
        BytePersonTracker(
            frame_rate=fps
        )
    )

    face_detector = (
        RetinaFaceDetector(
            model_cache_dir=(
                MODEL_ROOT
                / "retinaface"
            )
        )
    )

    face_recognizer = (
        FaceMoERecognizer(
            model_root=(
                MODEL_ROOT
                / "facemoe"
            )
        )
    )

    # --------------------------------------------------------
    # Track-Zeiten
    # --------------------------------------------------------

    track_accumulator = (
        TrackIntervalAccumulator(
            fps=fps
        )
    )

    # --------------------------------------------------------
    # Personencrops
    # --------------------------------------------------------

    person_crop_writer = (
        PersonCropWriter(
            output_dir=(
                analysis_output_dir
            ),
            fps=fps,
            jpeg_quality=90,
            clear_existing=True,
        )
    )

    # --------------------------------------------------------
    # Face-Metadaten
    # --------------------------------------------------------

    face_observation_writer = (
        FaceObservationWriter(
            output_dir=(
                analysis_output_dir
            ),
            fps=fps,
            clear_existing=True,
        )
    )

    # --------------------------------------------------------
    # Statistiken
    # --------------------------------------------------------

    face_stats: dict[
        int,
        dict,
    ] = {}

    total_faces_detected = 0
    total_faces_assigned = 0
    total_faces_usable = 0
    total_alignment_failures = 0

    total_embeddings_created = 0
    total_embedding_errors = 0

    # --------------------------------------------------------
    # FaceMoE-Embeddings
    #
    # Ausschließlich RAM.
    # --------------------------------------------------------

    face_embedding_records: list[
        dict
    ] = []

    # --------------------------------------------------------
    # Rejected Faces
    #
    # Diese Face-Beobachtungen haben kein nutzbares
    # Embedding erhalten, werden aber für Same-Frame-
    # Cannot-Link berücksichtigt.
    # --------------------------------------------------------

    rejected_track_ids: list[
        int
    ] = []

    rejected_frame_numbers: list[
        int
    ] = []

    frame_number = 0

    try:

        while True:

            (
                success,
                frame_bgr,
            ) = video.read()

            if not success:
                break

            frame_number += 1

            # =================================================
            # 1. RF-DETR
            # =================================================

            persons = (
                person_detector.detect(
                    frame_bgr
                )
            )

            # =================================================
            # 2. ByteTrack
            # =================================================

            tracked_persons = (
                person_tracker.update(
                    persons,
                    scene_change=(
                        frame_number
                        in scene_change_frames
                    ),
                )
            )

            # =================================================
            # 3. Tracks + Personencrops
            # =================================================

            current_crop_paths: dict[
                int,
                Path,
            ] = {}

            for person in tracked_persons:

                track_id = int(
                    person[
                        "track_id"
                    ]
                )

                scene_id = int(
                    person[
                        "scene_id"
                    ]
                )

                track_accumulator.observe(
                    track_id=(
                        track_id
                    ),
                    scene_id=(
                        scene_id
                    ),
                    frame_number=(
                        frame_number
                    ),
                )

                crop_path = (
                    person_crop_writer.save(
                        frame_bgr=(
                            frame_bgr
                        ),
                        track_id=(
                            track_id
                        ),
                        scene_id=(
                            scene_id
                        ),
                        frame_number=(
                            frame_number
                        ),
                        bbox=(
                            person[
                                "bbox"
                            ]
                        ),
                        confidence=(
                            person.get(
                                "confidence"
                            )
                        ),
                    )
                )

                if crop_path is not None:

                    current_crop_paths[
                        track_id
                    ] = crop_path

            # =================================================
            # 4. RetinaFace alle 0,5 Sekunden
            # =================================================

            analyze_frame = (
                (
                    frame_number
                    - 1
                )
                % analysis_interval_frames
                == 0
            )

            if (
                analyze_frame
                and tracked_persons
            ):

                faces = (
                    face_detector.detect(
                        frame_bgr
                    )
                )

                total_faces_detected += len(
                    faces
                )

                # =============================================
                # 5. Face -> Track
                # =============================================

                assignments = (
                    assign_faces_to_tracks(
                        faces,
                        tracked_persons,
                    )
                )

                for (
                    face_index,
                    person,
                ) in assignments.items():

                    face = (
                        faces[
                            face_index
                        ]
                    )

                    track_id = int(
                        person[
                            "track_id"
                        ]
                    )

                    scene_id = int(
                        person[
                            "scene_id"
                        ]
                    )

                    total_faces_assigned += 1

                    if track_id not in face_stats:

                        face_stats[
                            track_id
                        ] = {
                            "faces_assigned": 0,
                            "faces_usable": 0,
                            "alignment_failures": 0,
                            "embeddings_created": 0,
                            "embedding_errors": 0,
                        }

                    stats = (
                        face_stats[
                            track_id
                        ]
                    )

                    stats[
                        "faces_assigned"
                    ] += 1

                    # =========================================
                    # 6. Face Quality
                    # =========================================

                    face_crop = (
                        face[
                            "crop"
                        ]
                    )

                    face_confidence = float(
                        face[
                            "confidence"
                        ]
                    )

                    (
                        is_usable,
                        quality_info,
                    ) = check_face_quality(
                        face_crop,
                        face_confidence,
                    )

                    blur_score = (
                        quality_info.get(
                            "blur_score"
                        )
                    )

                    aligned_crop = (
                        face[
                            "aligned_crop"
                        ]
                    )

                    alignment_ok = (
                        aligned_crop
                        is not None
                    )

                    # =========================================
                    # 7. Face-Metadaten
                    #
                    # Keine Face-Bildkopie.
                    # Kein Embedding.
                    # =========================================

                    person_crop_path = (
                        current_crop_paths.get(
                            track_id
                        )
                    )

                    face_id = None

                    if (
                        person_crop_path
                        is not None
                    ):

                        (
                            frame_height,
                            frame_width,
                        ) = (
                            frame_bgr.shape[:2]
                        )

                        face_id = (
                            face_observation_writer.save(
                                track_id=(
                                    track_id
                                ),
                                scene_id=(
                                    scene_id
                                ),
                                frame_number=(
                                    frame_number
                                ),
                                person_bbox=(
                                    person[
                                        "bbox"
                                    ]
                                ),
                                face_bbox=(
                                    face[
                                        "bbox"
                                    ]
                                ),
                                person_crop_path=(
                                    person_crop_path
                                ),
                                frame_width=(
                                    frame_width
                                ),
                                frame_height=(
                                    frame_height
                                ),
                                face_confidence=(
                                    face_confidence
                                ),
                                face_usable=(
                                    is_usable
                                ),
                                blur_score=(
                                    blur_score
                                ),
                                alignment_ok=(
                                    alignment_ok
                                ),
                            )
                        )

                    # =========================================
                    # 8. Quality-Statistik
                    # =========================================

                    if is_usable:

                        stats[
                            "faces_usable"
                        ] += 1

                        total_faces_usable += 1

                        if not alignment_ok:

                            stats[
                                "alignment_failures"
                            ] += 1

                            total_alignment_failures += 1

                    # =========================================
                    # 9. FaceMoE
                    # =========================================

                    embedding_created = False

                    if (
                        is_usable
                        and alignment_ok
                    ):

                        try:

                            embedding = (
                                face_recognizer.extract_embedding(
                                    aligned_crop
                                )
                            )

                        except Exception as error:

                            stats[
                                "embedding_errors"
                            ] += 1

                            total_embedding_errors += 1

                            print(
                                "FaceMoE-Fehler | "
                                f"Track {track_id} | "
                                f"Frame {frame_number} | "
                                f"{type(error).__name__}: "
                                f"{error}"
                            )

                        else:

                            face_embedding_records.append(
                                {
                                    "face_id": (
                                        face_id
                                    ),
                                    "track_id": (
                                        track_id
                                    ),
                                    "scene_id": (
                                        scene_id
                                    ),
                                    "frame_number": (
                                        frame_number
                                    ),
                                    "timestamp_s": (
                                        (
                                            frame_number
                                            - 1
                                        )
                                        / fps
                                    ),
                                    "embedding": (
                                        embedding
                                    ),
                                }
                            )

                            stats[
                                "embeddings_created"
                            ] += 1

                            total_embeddings_created += 1

                            embedding_created = True

                    # =========================================
                    # 10. Rejected Face für Cannot-Link
                    # =========================================

                    if not embedding_created:

                        rejected_track_ids.append(
                            track_id
                        )

                        rejected_frame_numbers.append(
                            frame_number
                        )

            # =================================================
            # Fortschritt
            # =================================================

            if progress_cb is not None:

                progress_cb(
                    frame_number,
                    frame_count,
                )

            if (
                frame_number
                % 500
                == 0
            ):

                print(
                    f"Frame "
                    f"{frame_number}/"
                    f"{frame_count}"
                )

    finally:

        video.release()

        person_crop_writer.close()

        face_observation_writer.close()

        face_recognizer.close()

    # ========================================================
    # Tracks fertigstellen
    # ========================================================

    tracks = (
        track_accumulator.result()
    )

    for track in tracks:

        track_id = int(
            track[
                "track_id"
            ]
        )

        stats = (
            face_stats.get(
                track_id,
                {
                    "faces_assigned": 0,
                    "faces_usable": 0,
                    "alignment_failures": 0,
                    "embeddings_created": 0,
                    "embedding_errors": 0,
                },
            )
        )

        track.update(
            stats
        )

    # ========================================================
    # RAM-Embeddings für Clustering vorbereiten
    # ========================================================

    if face_embedding_records:

        embeddings = np.stack(
            [
                record[
                    "embedding"
                ]
                for record
                in face_embedding_records
            ]
        ).astype(
            np.float32
        )

        embedding_frame_numbers = np.asarray(
            [
                record[
                    "frame_number"
                ]
                for record
                in face_embedding_records
            ],
            dtype=np.int32,
        )

        embedding_track_ids = np.asarray(
            [
                record[
                    "track_id"
                ]
                for record
                in face_embedding_records
            ],
            dtype=np.int32,
        )

    else:

        embeddings = np.empty(
            (
                0,
                512,
            ),
            dtype=np.float32,
        )

        embedding_frame_numbers = np.empty(
            0,
            dtype=np.int32,
        )

        embedding_track_ids = np.empty(
            0,
            dtype=np.int32,
        )

    rejected_track_ids_array = (
        np.asarray(
            rejected_track_ids,
            dtype=np.int32,
        )
    )

    rejected_frame_numbers_array = (
        np.asarray(
            rejected_frame_numbers,
            dtype=np.int32,
        )
    )

    # ========================================================
    # Identitätsclustering
    # ========================================================

    clustered_mapping = (
        run_clustering(
            embeddings=(
                embeddings
            ),
            frame_numbers=(
                embedding_frame_numbers
            ),
            track_ids=(
                embedding_track_ids
            ),
            rejected_track_ids=(
                rejected_track_ids_array
            ),
            rejected_frame_numbers=(
                rejected_frame_numbers_array
            ),
        )
    )

    clustered_track_ids = set(
        clustered_mapping
    )

    # ========================================================
    # Nicht zugeordnete Tracks
    #
    # Kein FaceMoE-Embedding -> keine automatische
    # Identitätsentscheidung.
    # ========================================================

    unassigned_tracks = [
        track
        for track in tracks
        if int(
            track[
                "track_id"
            ]
        )
        not in clustered_track_ids
    ]

    # ========================================================
    # Automatische Personen
    #
    # Nur Tracks mit FaceMoE-basierter Cluster-Zuordnung.
    # ========================================================

    track_to_person = dict(
        clustered_mapping
    )

    clustered_tracks = [
        track
        for track in tracks
        if int(
            track[
                "track_id"
            ]
        )
        in clustered_track_ids
    ]

    persons = (
        build_persons(
            tracks=(
                clustered_tracks
            ),
            track_to_person=(
                track_to_person
            ),
        )
    )

    # ========================================================
    # Ergebnisse speichern
    #
    # Keine Embeddings.
    # ========================================================

    track_identity_path = (
        analysis_output_dir
        / "track_identities.csv"
    )

    persons_path = (
        analysis_output_dir
        / "persons.json"
    )

    save_track_identities(
        output_path=(
            track_identity_path
        ),
        tracks=(
            tracks
        ),
        track_to_person=(
            track_to_person
        ),
    )

    save_persons(
        output_path=(
            persons_path
        ),
        video_path=(
            video_path
        ),
        tracks=(
            tracks
        ),
        persons=(
            persons
        ),
        unassigned_tracks=(
            unassigned_tracks
        ),
    )

    # ========================================================
    # Embeddings explizit aus RAM entfernen
    # ========================================================

    face_embedding_records.clear()

    del embeddings
    del embedding_frame_numbers
    del embedding_track_ids

    # ========================================================
    # Zusammenfassung
    # ========================================================

    print()
    print(
        "GESICHTSANALYSE"
    )
    print(
        "================"
    )
    print()

    print(
        "Gesichter erkannt: "
        f"{total_faces_detected}"
    )

    print(
        "Gesichtern Tracks zugeordnet: "
        f"{total_faces_assigned}"
    )

    print(
        "Qualitativ verwendbar: "
        f"{total_faces_usable}"
    )

    print(
        "Alignment fehlgeschlagen: "
        f"{total_alignment_failures}"
    )

    print()

    print(
        "FACEMOE"
    )
    print(
        "======="
    )
    print()

    print(
        "Embeddings erzeugt: "
        f"{total_embeddings_created}"
    )

    print(
        "Embedding-Fehler: "
        f"{total_embedding_errors}"
    )

    print(
        "Embeddings gespeichert: "
        "NEIN"
    )

    print()

    print(
        "AUTOMATISCHE PERSONEN"
    )
    print(
        "====================="
    )
    print()

    print(
        "Tracks insgesamt: "
        f"{len(tracks)}"
    )

    print(
        "Tracks mit FaceMoE-Embedding: "
        f"{len(clustered_track_ids)}"
    )

    print(
        "Nicht zugeordnete Tracks: "
        f"{len(unassigned_tracks)}"
    )

    print(
        "Automatisch erkannte Personen: "
        f"{len(persons)}"
    )

    print(
        "Track-Zuordnungen: "
        f"{track_identity_path}"
    )

    print(
        "Personenergebnis: "
        f"{persons_path}"
    )

    print()

    print(
        "PERSONENCROPS"
    )
    print(
        "============="
    )
    print()

    print(
        "Gespeicherte Personencrops: "
        f"{person_crop_writer.crop_count}"
    )

    print(
        "Crop-Verzeichnis: "
        f"{person_crop_writer.crops_dir}"
    )

    print(
        "Manifest: "
        f"{person_crop_writer.manifest_path}"
    )

    print()

    print(
        "FACE-METADATEN"
    )
    print(
        "=============="
    )
    print()

    print(
        "Gespeicherte Face-Beobachtungen: "
        f"{face_observation_writer.face_count}"
    )

    print(
        "Manifest: "
        f"{face_observation_writer.manifest_path}"
    )

    return {
        "video_path": str(
            video_path
        ),
        "tracks": tracks,
        "persons": persons,
        "unassigned_tracks": (
            unassigned_tracks
        ),
        "track_to_person": (
            track_to_person
        ),
        "output_dir": str(
            analysis_output_dir
        ),
        "persons_path": str(
            persons_path
        ),
        "track_identities_path": str(
            track_identity_path
        ),
    }


# ============================================================
# Konsolenausgabe
# ============================================================


def print_person_summary(
    result: dict,
) -> None:

    persons = (
        result[
            "persons"
        ]
    )

    unassigned_tracks = (
        result[
            "unassigned_tracks"
        ]
    )

    print()
    print(
        "PERSONEN"
    )
    print(
        "========"
    )
    print()

    for person in persons:

        track_text = ", ".join(
            str(track_id)
            for track_id
            in person[
                "track_ids"
            ]
        )

        appearance_text = ", ".join(
            (
                f"{appearance['start_s']:.2f}"
                f"–"
                f"{appearance['end_s']:.2f}"
            )
            for appearance
            in person[
                "appearances"
            ]
        )

        print(
            f"Person "
            f"{person['person_id']:03d} | "
            f"Tracks: {track_text} | "
            f"Zeiten: {appearance_text}"
        )

    print()
    print(
        "NICHT ZUGEORDNETE TRACKS"
    )
    print(
        "========================"
    )
    print()

    for track in unassigned_tracks:

        print(
            f"Track "
            f"{int(track['track_id']):03d} | "
            f"Szene "
            f"{int(track['scene_id'])} | "
            f"{float(track['start_s']):.2f}"
            f"–"
            f"{float(track['end_s']):.2f} s | "
            f"Faces "
            f"{int(track.get('faces_usable', 0))}/"
            f"{int(track.get('faces_assigned', 0))}"
        )


# ============================================================
# CLI
# ============================================================


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Neue descraibe-"
            "Personenanalyse."
        )
    )

    parser.add_argument(
        "video",
        type=Path,
        help=(
            "Pfad zur Videodatei"
        ),
    )

    args = (
        parser.parse_args()
    )

    result = (
        analyze_persons(
            video_path=(
                args.video
            )
        )
    )

    print_person_summary(
        result
    )


if __name__ == "__main__":
    main()