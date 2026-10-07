"""Environment-backed runtime configuration shared by the API and workers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    data_dir: Path
    artifact_dir: Path
    state_db: Path
    storage_uri: str
    model_registry: Path
    model_cache_dir: Path
    log_level: str
    api_host: str
    api_port: int
    worker_queue: str
    worker_poll_seconds: float
    device: str
    api_token: str = ""

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        port = int(os.environ.get("SATORI_API_PORT", "8000"))
        poll = float(os.environ.get("SATORI_WORKER_POLL_SECONDS", "2"))
        if not 1 <= port <= 65535:
            raise ValueError("SATORI_API_PORT must be in [1, 65535]")
        if not 0.1 <= poll <= 300:
            raise ValueError("SATORI_WORKER_POLL_SECONDS must be in [0.1, 300]")
        queue = os.environ.get("SATORI_WORKER_QUEUE", "cpu").lower()
        if queue not in {"cpu", "gpu", "etflow", "docking"}:
            raise ValueError("SATORI_WORKER_QUEUE must be cpu, gpu, etflow, or docking")
        data = _path("SATORI_DATA_DIR", "data")
        artifacts = _path("SATORI_ARTIFACT_DIR", "artifacts")
        state = _path("SATORI_STATE_DB", str(artifacts / "state" / "jobs.sqlite3"))
        return cls(
            data, artifacts, state,
            os.environ.get("SATORI_STORAGE_URI", str(artifacts)),
            _path("SATORI_MODEL_REGISTRY", "model_registry.example.json"),
            _path("SATORI_MODEL_CACHE_DIR", "model-cache"),
            os.environ.get("SATORI_LOG_LEVEL", "INFO").upper(),
            os.environ.get("SATORI_API_HOST", "0.0.0.0"), port, queue, poll,
            os.environ.get("SATORI_DEVICE", "auto").lower(),
            os.environ.get("SATORI_API_TOKEN", ""),
        )
