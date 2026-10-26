"""Small local vector index and a provider-neutral contract for future managed indexes.

This module never creates embeddings. Callers must supply vectors from the approved,
licensed embedding model and retain its model/revision in the record metadata.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from satori.provenance import write_json_atomic


@dataclass(slots=True)
class VectorRecord:
    record_id: str
    vector: list[float]
    metadata: dict[str, Any]


@dataclass(slots=True)
class VectorHit:
    record_id: str
    similarity: float
    metadata: dict[str, Any]


class VectorStore(Protocol):
    def upsert(self, records: list[VectorRecord]) -> None: ...
    def query(self, vector: list[float], *, limit: int = 10) -> list[VectorHit]: ...


class LocalJsonVectorStore:
    """Deterministic cosine index for development and small evidence collections."""
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: dict[str, VectorRecord] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = {row["record_id"]: VectorRecord(**row) for row in data.get("records", [])}

    @staticmethod
    def _validate(vector: list[float]) -> None:
        if not vector or any(not math.isfinite(float(value)) for value in vector):
            raise ValueError("vectors must contain finite values and have positive dimension")

    def upsert(self, records: list[VectorRecord]) -> None:
        with self._lock:
            incoming = dict(self._records)
            dimension = len(next(iter(incoming.values())).vector) if incoming else None
            for record in records:
                self._validate(record.vector)
                if dimension is None:
                    dimension = len(record.vector)
                if len(record.vector) != dimension:
                    raise ValueError("vector dimensions must match the existing index")
                if not record.record_id:
                    raise ValueError("record_id must be non-empty")
                incoming[record.record_id] = record
            self._records = incoming
            write_json_atomic(self.path, {"schema_version": "1.0", "records": [
                {"record_id": key, "vector": value.vector, "metadata": value.metadata}
                for key, value in sorted(incoming.items())]})

    def query(self, vector: list[float], *, limit: int = 10) -> list[VectorHit]:
        self._validate(vector)
        if limit < 1:
            raise ValueError("limit must be positive")
        norm = math.sqrt(sum(float(x) ** 2 for x in vector))
        if norm == 0:
            raise ValueError("query vector must have non-zero magnitude")
        hits: list[VectorHit] = []
        with self._lock:
            for record in self._records.values():
                if len(record.vector) != len(vector):
                    raise ValueError("query vector dimensions do not match index")
                other_norm = math.sqrt(sum(float(x) ** 2 for x in record.vector))
                similarity = (sum(float(a) * float(b) for a, b in zip(vector, record.vector)) /
                              (norm * other_norm)) if other_norm else 0.0
                hits.append(VectorHit(record.record_id, similarity, record.metadata))
        return sorted(hits, key=lambda hit: (-hit.similarity, hit.record_id))[:limit]
