from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json_atomic(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_jsonl(path: str | Path, records: Iterable[Any]) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            for record in records:
                row = canonical_json(record) + b"\n"
                stream.write(row)
                digest.update(row)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest.hexdigest()


def write_dataset_manifest(path: str | Path, *, source: str, dataset_hash: str,
                           processing_version: str, filters: dict[str, Any],
                           split_seed: int | None = None, source_version: str | None = None,
                           record_count: int | None = None,
                           metadata: dict[str, Any] | None = None) -> None:
    write_json_atomic(path, {
        "manifest_schema_version": "1.0",
        "source": source,
        "source_version_or_date": source_version or datetime.now(timezone.utc).date().isoformat(),
        "processing_version": processing_version,
        "filter_configuration": filters,
        "dataset_hash_sha256": dataset_hash,
        "record_count": record_count,
        "split_seed": split_seed,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
