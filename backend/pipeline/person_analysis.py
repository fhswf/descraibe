"""Assign detected faces to the current person tracks."""
from __future__ import annotations


def assign_faces_to_tracks(faces: list[dict], tracked_persons: list[dict]) -> dict[int, dict]:
    """Ordnet pro Analyseframe höchstens ein Gesicht einem Track zu."""
    candidates = []

    for face_index, face in enumerate(faces):
        fx1, fy1, fx2, fy2 = face["bbox"]
        face_cx = (fx1 + fx2) / 2.0
        face_cy = (fy1 + fy2) / 2.0

        for person in tracked_persons:
            x1, y1, x2, y2 = person["bbox"]
            if not (x1 <= face_cx <= x2 and y1 <= face_cy <= y2):
                continue

            person_width = max(1.0, float(x2 - x1))
            person_height = max(1.0, float(y2 - y1))
            expected_head_x = (x1 + x2) / 2.0
            expected_head_y = y1 + 0.20 * person_height

            score = (
                ((face_cx - expected_head_x) / person_width) ** 2
                + ((face_cy - expected_head_y) / person_height) ** 2
            )
            candidates.append((score, face_index, person))

    candidates.sort(key=lambda item: item[0])

    assignments: dict[int, dict] = {}
    used_tracks: set[int] = set()

    for _, face_index, person in candidates:
        track_id = int(person["track_id"])
        if face_index in assignments or track_id in used_tracks:
            continue
        assignments[face_index] = person
        used_tracks.add(track_id)

    return assignments
