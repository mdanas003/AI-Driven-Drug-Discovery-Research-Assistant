"""Explicit model artifact resolution; unavailable entries never trigger fallback."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from satori.errors import CheckpointUnavailable


class ModelArtifactRegistry:
    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path).expanduser().resolve()
        try:
            self.entries = json.loads(self.registry_path.read_text(encoding="utf-8"))["models"]
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise CheckpointUnavailable(f"Model registry unavailable or invalid: {self.registry_path}") from exc
        if not isinstance(self.entries, dict):
            raise ValueError("model registry 'models' must be an object")

    def describe(self, model_name: str) -> dict[str, Any]:
        try:
            return dict(self.entries[model_name])
        except KeyError as exc:
            raise CheckpointUnavailable(f"Model {model_name!r} is not registered") from exc

    def resolve(self, model_name: str, *, cache_dir: str | Path | None = None) -> Path:
        item = self.describe(model_name)
        if item.get("availability") != "available":
            raise CheckpointUnavailable(item.get("blocker") or f"{model_name} checkpoint is unavailable")
        artifact_uri = item.get("artifact_uri")
        if artifact_uri:
            parsed = urlparse(artifact_uri)
            if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
                raise CheckpointUnavailable(f"Unsupported model artifact URI: {artifact_uri}")
            from satori.storage import S3ArtifactStore
            key = parsed.path.strip("/")
            filename = Path(key).name
            if not filename or filename in {".", ".."}:
                raise CheckpointUnavailable(f"Invalid model artifact key: {key}")
            root = Path(cache_dir or Path.home() / ".cache" / "satori" / "models")
            path = S3ArtifactStore(f"s3://{parsed.netloc}").get_file(
                key, root / model_name / filename).resolve()
        elif item.get("artifact_path"):
            path = Path(item["artifact_path"]).expanduser().resolve()
        else:
            raise CheckpointUnavailable(f"{model_name} has no configured artifact_path or artifact_uri")
        if not path.exists() or (path.is_file() is False and path.is_dir() is False):
            raise CheckpointUnavailable(f"{model_name} checkpoint is missing: {path}")
        expected = item.get("sha256")
        if expected:
            hasher = hashlib.sha256()
            if path.is_dir():
                for child in sorted(child for child in path.rglob("*") if child.is_file()):
                    hasher.update(child.relative_to(path).as_posix().encode("utf-8") + b"\0")
                    with child.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            hasher.update(chunk)
            else:
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(chunk)
            digest = hasher.hexdigest()
            if digest.lower() != expected.lower():
                raise CheckpointUnavailable(f"{model_name} checkpoint hash mismatch")
        return path

    def remote_descriptor(self, model_name: str) -> dict[str, Any]:
        item = self.describe(model_name)
        if item.get("availability") != "remote-pinned" or not item.get("checkpoint_identifier"):
            raise CheckpointUnavailable(item.get("blocker") or f"{model_name} is not a remote-pinned artifact")
        return item
