from __future__ import annotations

import numpy as np


TRACK_REFERENCE_SIZE = 5
SIMILARITY_THRESHOLD = 0.214
LINKAGE_METHOD = "average"


def normalize_embeddings(
    embeddings: np.ndarray,
) -> np.ndarray:
    embeddings = np.asarray(
        embeddings,
        dtype=np.float32,
    )

    if embeddings.ndim != 2:
        raise ValueError(
            "Embeddings müssen zweidimensional sein: "
            f"{embeddings.shape}"
        )

    norms = np.linalg.norm(
        embeddings,
        axis=1,
        keepdims=True,
    )

    if (
        np.any(~np.isfinite(norms))
        or np.any(norms <= 0)
    ):
        raise ValueError(
            "Ungültige Embeddings gefunden."
        )

    return (
        embeddings / norms
    ).astype(np.float32)


def select_track_references(
    track_embeddings: np.ndarray,
) -> np.ndarray:
    """
    Wählt maximal fünf zeitlich verteilte
    Referenz-Embeddings eines Tracks.
    """

    if (
        len(track_embeddings)
        <= TRACK_REFERENCE_SIZE
    ):
        return track_embeddings

    indices = np.linspace(
        0,
        len(track_embeddings) - 1,
        TRACK_REFERENCE_SIZE,
        dtype=int,
    )

    return track_embeddings[
        indices
    ]


def create_track_references(
    embeddings: np.ndarray,
    track_ids: np.ndarray,
) -> tuple[
    np.ndarray,
    dict[int, np.ndarray],
]:
    embeddings = normalize_embeddings(
        embeddings
    )

    unique_track_ids = np.unique(
        track_ids
    )

    track_references: dict[
        int,
        np.ndarray,
    ] = {}

    for track_id in unique_track_ids:

        track_embeddings = embeddings[
            track_ids == track_id
        ]

        track_references[
            int(track_id)
        ] = select_track_references(
            track_embeddings
        )

    return (
        unique_track_ids,
        track_references,
    )


def calculate_track_similarity(
    embeddings_a: np.ndarray,
    embeddings_b: np.ndarray,
) -> float:
    """
    Similarity zweier Tracks:

    Median aller paarweisen
    Cosine Similarities zwischen ihren
    Referenz-Embeddings.
    """

    similarity_matrix = (
        embeddings_a
        @ embeddings_b.T
    )

    return float(
        np.median(
            similarity_matrix
        )
    )


def create_track_distance_matrix(
    unique_track_ids: np.ndarray,
    track_references: dict[
        int,
        np.ndarray,
    ],
) -> np.ndarray:

    track_count = len(
        unique_track_ids
    )

    distance_matrix = np.zeros(
        (
            track_count,
            track_count,
        ),
        dtype=np.float32,
    )

    for i in range(
        track_count
    ):

        track_id_a = int(
            unique_track_ids[i]
        )

        embeddings_a = (
            track_references[
                track_id_a
            ]
        )

        for j in range(
            i + 1,
            track_count,
        ):

            track_id_b = int(
                unique_track_ids[j]
            )

            embeddings_b = (
                track_references[
                    track_id_b
                ]
            )

            similarity = (
                calculate_track_similarity(
                    embeddings_a,
                    embeddings_b,
                )
            )

            distance = (
                1.0 - similarity
            )

            distance_matrix[
                i,
                j,
            ] = distance

            distance_matrix[
                j,
                i,
            ] = distance

    return distance_matrix


def create_cannot_link_pairs(
    track_ids: np.ndarray,
    frame_numbers: np.ndarray,
    rejected_track_ids: np.ndarray,
    rejected_frame_numbers: np.ndarray,
    clustered_track_ids: np.ndarray,
) -> set[frozenset[int]]:
    """
    Erzeugt Cannot-Link-Beziehungen für Tracks,
    deren Gesichter im selben Analyseframe
    gleichzeitig beobachtet wurden.

    Auch Face-Beobachtungen, die kein Embedding
    erhalten haben, werden berücksichtigt.
    """

    all_track_ids = np.concatenate(
        [
            track_ids,
            rejected_track_ids,
        ]
    )

    all_frame_numbers = np.concatenate(
        [
            frame_numbers,
            rejected_frame_numbers,
        ]
    )

    valid_track_ids = {
        int(track_id)
        for track_id
        in clustered_track_ids
    }

    frame_to_tracks: dict[
        int,
        set[int],
    ] = {}

    for (
        track_id,
        frame_number,
    ) in zip(
        all_track_ids,
        all_frame_numbers,
    ):

        track_id = int(
            track_id
        )

        frame_number = int(
            frame_number
        )

        if (
            track_id
            not in valid_track_ids
        ):
            continue

        frame_to_tracks.setdefault(
            frame_number,
            set(),
        ).add(
            track_id
        )

    cannot_link_pairs: set[
        frozenset[int]
    ] = set()

    for tracks in (
        frame_to_tracks.values()
    ):

        tracks = sorted(
            tracks
        )

        for i in range(
            len(tracks)
        ):

            for j in range(
                i + 1,
                len(tracks),
            ):

                cannot_link_pairs.add(
                    frozenset(
                        (
                            tracks[i],
                            tracks[j],
                        )
                    )
                )

    return cannot_link_pairs


def clusters_can_merge(
    cluster_a: set[int],
    cluster_b: set[int],
    cannot_link_pairs: set[
        frozenset[int]
    ],
) -> bool:

    for track_a in cluster_a:

        for track_b in cluster_b:

            if (
                frozenset(
                    (
                        track_a,
                        track_b,
                    )
                )
                in cannot_link_pairs
            ):
                return False

    return True


def calculate_cluster_distance(
    cluster_a: set[int],
    cluster_b: set[int],
    track_id_to_index: dict[
        int,
        int,
    ],
    distance_matrix: np.ndarray,
) -> float:

    distances = []

    for track_a in cluster_a:

        index_a = (
            track_id_to_index[
                track_a
            ]
        )

        for track_b in cluster_b:

            index_b = (
                track_id_to_index[
                    track_b
                ]
            )

            distances.append(
                float(
                    distance_matrix[
                        index_a,
                        index_b,
                    ]
                )
            )

    if LINKAGE_METHOD == "average":
        return float(
            np.mean(
                distances
            )
        )

    if LINKAGE_METHOD == "complete":
        return float(
            np.max(
                distances
            )
        )

    raise ValueError(
        "Nicht unterstützte "
        "Linkage-Methode: "
        f"{LINKAGE_METHOD}"
    )


def cluster_tracks(
    distance_matrix: np.ndarray,
    unique_track_ids: np.ndarray,
    cannot_link_pairs: set[
        frozenset[int]
    ],
) -> np.ndarray:
    """
    Hierarchisches agglomeratives Clustering
    mit harter Same-Frame-Cannot-Link-Regel.
    """

    if len(
        unique_track_ids
    ) == 0:
        return np.array(
            [],
            dtype=np.int32,
        )

    if len(
        unique_track_ids
    ) == 1:
        return np.array(
            [1],
            dtype=np.int32,
        )

    distance_threshold = (
        1.0
        - SIMILARITY_THRESHOLD
    )

    track_id_to_index = {
        int(track_id): index
        for index, track_id
        in enumerate(
            unique_track_ids
        )
    }

    clusters = [
        {
            int(
                track_id
            )
        }
        for track_id
        in unique_track_ids
    ]

    while True:

        best_pair = None
        best_distance = None

        for i in range(
            len(clusters)
        ):

            for j in range(
                i + 1,
                len(clusters),
            ):

                cluster_a = (
                    clusters[i]
                )

                cluster_b = (
                    clusters[j]
                )

                if not clusters_can_merge(
                    cluster_a,
                    cluster_b,
                    cannot_link_pairs,
                ):
                    continue

                distance = (
                    calculate_cluster_distance(
                        cluster_a,
                        cluster_b,
                        track_id_to_index,
                        distance_matrix,
                    )
                )

                if (
                    distance
                    > distance_threshold
                ):
                    continue

                if (
                    best_distance is None
                    or
                    distance
                    < best_distance
                ):

                    best_distance = (
                        distance
                    )

                    best_pair = (
                        i,
                        j,
                    )

        if best_pair is None:
            break

        i, j = best_pair

        merged_cluster = (
            clusters[i]
            | clusters[j]
        )

        clusters.pop(
            j
        )

        clusters.pop(
            i
        )

        clusters.append(
            merged_cluster
        )

    # stabile IDs:
    # Cluster mit kleinstem Track zuerst
    clusters.sort(
        key=lambda cluster: min(
            cluster
        )
    )

    track_to_identity: dict[
        int,
        int,
    ] = {}

    for (
        identity_id,
        cluster,
    ) in enumerate(
        clusters,
        start=1,
    ):

        for track_id in cluster:

            track_to_identity[
                track_id
            ] = identity_id

    return np.asarray(
        [
            track_to_identity[
                int(track_id)
            ]
            for track_id
            in unique_track_ids
        ],
        dtype=np.int32,
    )


def check_cannot_link_violations(
    identity_labels: np.ndarray,
    unique_track_ids: np.ndarray,
    cannot_link_pairs: set[
        frozenset[int]
    ],
) -> list[
    tuple[int, int]
]:

    track_to_identity = {
        int(track_id):
        int(identity_id)
        for (
            track_id,
            identity_id,
        )
        in zip(
            unique_track_ids,
            identity_labels,
        )
    }

    violations = []

    for pair in (
        cannot_link_pairs
    ):

        track_a, track_b = tuple(
            pair
        )

        if (
            track_to_identity[
                track_a
            ]
            ==
            track_to_identity[
                track_b
            ]
        ):

            violations.append(
                (
                    track_a,
                    track_b,
                )
            )

    return violations


def run_clustering(
    embeddings: np.ndarray,
    frame_numbers: np.ndarray,
    track_ids: np.ndarray,
    rejected_track_ids: np.ndarray,
    rejected_frame_numbers: np.ndarray,
) -> dict[int, int]:
    """
    Führt das getestete FaceMoE-
    Identitätsclustering aus.

    Rückgabe:

        {
            track_id: identity_id,
            ...
        }

    Es werden keine Embeddings gespeichert.
    """

    if not (
        len(embeddings)
        == len(frame_numbers)
        == len(track_ids)
    ):
        raise ValueError(
            "Embeddings, Frame-Nummern "
            "und Track-IDs haben "
            "unterschiedliche Längen."
        )

    if (
        len(rejected_track_ids)
        != len(
            rejected_frame_numbers
        )
    ):
        raise ValueError(
            "Rejected Track-IDs und "
            "Frame-Nummern haben "
            "unterschiedliche Längen."
        )

    if len(embeddings) == 0:

        print()
        print(
            "IDENTITÄTSCLUSTERING"
        )
        print(
            "===================="
        )
        print(
            "Keine FaceMoE-Embeddings "
            "vorhanden."
        )

        return {}

    (
        unique_track_ids,
        track_references,
    ) = create_track_references(
        embeddings,
        track_ids,
    )

    distance_matrix = (
        create_track_distance_matrix(
            unique_track_ids,
            track_references,
        )
    )

    cannot_link_pairs = (
        create_cannot_link_pairs(
            track_ids=track_ids,
            frame_numbers=frame_numbers,
            rejected_track_ids=(
                rejected_track_ids
            ),
            rejected_frame_numbers=(
                rejected_frame_numbers
            ),
            clustered_track_ids=(
                unique_track_ids
            ),
        )
    )

    identity_labels = (
        cluster_tracks(
            distance_matrix=(
                distance_matrix
            ),
            unique_track_ids=(
                unique_track_ids
            ),
            cannot_link_pairs=(
                cannot_link_pairs
            ),
        )
    )

    violations = (
        check_cannot_link_violations(
            identity_labels=(
                identity_labels
            ),
            unique_track_ids=(
                unique_track_ids
            ),
            cannot_link_pairs=(
                cannot_link_pairs
            ),
        )
    )

    if violations:

        raise RuntimeError(
            f"{len(violations)} "
            "Cannot-Link-Regeln wurden "
            "verletzt: "
            f"{violations}"
        )

    track_to_identity = {
        int(track_id):
        int(identity_id)
        for (
            track_id,
            identity_id,
        )
        in zip(
            unique_track_ids,
            identity_labels,
        )
    }

    print()
    print(
        "IDENTITÄTSCLUSTERING FERTIG"
    )
    print(
        "============================"
    )
    print()

    print(
        "Tracks mit Embeddings: "
        f"{len(unique_track_ids)}"
    )

    print(
        "Referenz-Embeddings "
        "pro Track: maximal "
        f"{TRACK_REFERENCE_SIZE}"
    )

    print(
        "Track-Similarity: "
        "Median der paarweisen "
        "Cosine Similarities"
    )

    print(
        f"Linkage: "
        f"{LINKAGE_METHOD}"
    )

    print(
        "Similarity-Threshold: "
        f"{SIMILARITY_THRESHOLD:.3f}"
    )

    print(
        "Same-Frame "
        "Cannot-Link-Paare: "
        f"{len(cannot_link_pairs)}"
    )

    print(
        "Verletzte "
        "Cannot-Link-Regeln: "
        f"{len(violations)}"
    )

    print(
        "Face-basierte Identitäten: "
        f"{len(np.unique(identity_labels))}"
    )

    return track_to_identity