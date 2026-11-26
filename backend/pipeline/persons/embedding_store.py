"""Compact storage for the reference vectors used by identity clustering."""
from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

import numpy as np

EMBEDDING_DIMENSIONS = 512
TRACK_REFERENCE_SIZE = 5
MAGIC = b"DSCRREF1"
HEADER = struct.Struct("<8sII")  # magic, vector dimensions, track count
TRACK_HEADER = struct.Struct("<iH")  # track id, reference count


def write(path: str | Path, references: dict[int, np.ndarray]) -> None:
    """Write normalized 512d references as little-endian IEEE float16 rows."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(HEADER.pack(MAGIC, EMBEDDING_DIMENSIONS, len(references)))
            for track_id, vectors in sorted(references.items()):
                vectors = np.asarray(vectors, dtype=np.float32)
                if (type(track_id) is not int or track_id < 1 or vectors.ndim != 2
                        or vectors.shape[1] != EMBEDDING_DIMENSIONS or not 1 <= len(vectors) <= TRACK_REFERENCE_SIZE
                        or not np.isfinite(vectors).all()):
                    raise ValueError("Ungültige Referenz-Embeddings.")
                packed = np.asarray(vectors, dtype="<f2")
                if not np.isfinite(packed).all():
                    raise ValueError("Referenz-Embeddings liegen außerhalb des float16-Bereichs.")
                stream.write(TRACK_HEADER.pack(track_id, len(packed)))
                stream.write(packed.tobytes(order="C"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read(path: str | Path) -> dict[int, np.ndarray]:
    """Read and renormalize vectors to offset float16 quantization drift."""
    payload = Path(path).read_bytes()
    if len(payload) < HEADER.size:
        raise ValueError("Referenz-Embedding-Datei ist unvollständig.")
    magic, dimensions, track_count = HEADER.unpack_from(payload)
    if magic != MAGIC or dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError("Unbekanntes Referenz-Embedding-Format.")

    result = {}
    offset = HEADER.size
    for _ in range(track_count):
        if len(payload) - offset < TRACK_HEADER.size:
            raise ValueError("Referenz-Embedding-Datei ist unvollständig.")
        track_id, count = TRACK_HEADER.unpack_from(payload, offset)
        offset += TRACK_HEADER.size
        byte_count = count * dimensions * np.dtype("<f2").itemsize
        if (track_id < 1 or track_id in result or not 1 <= count <= TRACK_REFERENCE_SIZE
                or len(payload) - offset < byte_count):
            raise ValueError("Ungültige Referenz-Embedding-Zeile.")
        vectors = np.frombuffer(payload, dtype="<f2", count=count * dimensions, offset=offset)
        vectors = vectors.astype(np.float32).reshape(count, dimensions)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if not np.isfinite(vectors).all() or np.any(~np.isfinite(norms)) or np.any(norms <= 0):
            raise ValueError("Referenz-Embeddings sind ungültig.")
        result[track_id] = vectors / norms
        offset += byte_count
    if offset != len(payload):
        raise ValueError("Referenz-Embedding-Datei enthält zusätzliche Daten.")
    return result
