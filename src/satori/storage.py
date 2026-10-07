"""Provider-neutral artifact interface with local and optional S3 implementations."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path, PurePosixPath
import shutil
from typing import Any
from urllib.parse import urlparse

from satori.provenance import sha256_bytes


class ArtifactStore(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str: ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes: ...

    def put_json(self, key: str, value: Any) -> dict[str, str]:
        data = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
        uri = self.put_bytes(key, data, content_type="application/json")
        return {"uri": uri, "sha256": sha256_bytes(data), "size_bytes": str(len(data))}

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key).decode("utf-8"))

    def get_file(self, key: str, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.get_bytes(key))
        return path

    def put_file(self, key: str, source: str | Path) -> dict[str, str]:
        raise NotImplementedError


class LocalArtifactStore(ArtifactStore):
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        relative = PurePosixPath(key)
        if relative.is_absolute() or not key or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("Artifact key must be a safe relative path")
        target = (self.root / Path(*relative.parts)).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Artifact key escapes the configured root")
        return target

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + f".{os.getpid()}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return str(destination)

    def put_file(self, key: str, source: str | Path) -> dict[str, str]:
        source_path = Path(source)
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + f".{os.getpid()}.tmp")
        import hashlib
        digest = hashlib.sha256()
        size = 0
        try:
            with source_path.open("rb") as src, temporary.open("wb") as dst:
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk); digest.update(chunk); size += len(chunk)
                dst.flush(); os.fsync(dst.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return {"uri": str(destination), "sha256": digest.hexdigest(), "size_bytes": str(size)}

    def get_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def get_file(self, key: str, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._resolve(key), path)
        return path

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()


class S3ArtifactStore(ArtifactStore):
    def __init__(self, uri: str):
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            raise ValueError("S3 storage URI must use s3://bucket[/prefix]")
        try:
            import boto3
        except ImportError as exc:
            from satori.errors import DependencyUnavailable
            raise DependencyUnavailable("S3 artifacts require installing the [cloud-storage] extra") from exc
        self.bucket = parsed.netloc
        self.prefix = parsed.path.strip("/")
        self.client = boto3.client("s3")

    def _key(self, key: str) -> str:
        path = PurePosixPath(key)
        if path.is_absolute() or not key or ".." in path.parts:
            raise ValueError("Artifact key must be a safe relative path")
        return "/".join(part for part in (self.prefix, str(path)) if part)

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data,
                               ContentType=content_type)
        return f"s3://{self.bucket}/{self._key(key)}"

    def put_file(self, key: str, source: str | Path) -> dict[str, str]:
        source_path = Path(source)
        import hashlib
        digest = hashlib.sha256()
        size = 0
        with source_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk); size += len(chunk)
        object_key = self._key(key)
        self.client.upload_file(str(source_path), self.bucket, object_key)
        return {"uri": f"s3://{self.bucket}/{object_key}", "sha256": digest.hexdigest(),
                "size_bytes": str(size)}

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        return response["Body"].read()

    def get_file(self, key: str, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, self._key(key), str(path))
        return path


def make_artifact_store(uri: str) -> ArtifactStore:
    if uri.startswith("s3://"):
        return S3ArtifactStore(uri)
    if uri.startswith("file://"):
        uri = urlparse(uri).path
    if "://" in uri:
        raise ValueError(f"Unsupported SATORI_STORAGE_URI scheme: {urlparse(uri).scheme}")
    return LocalArtifactStore(uri)
