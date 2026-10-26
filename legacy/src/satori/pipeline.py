from __future__ import annotations

import hashlib
import dataclasses
import json
import math
import platform
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable

from satori.errors import SatoriError
from satori.provenance import sha256_bytes, write_json_atomic
from satori.schemas import PipelineRun, utc_now


class Pipeline:
    """Stage runner that persists success/failure/blocker state at every boundary."""

    stage_order = ("target_discovery", "ligand_data", "generation", "optimization",
                   "triage", "affinity", "docking", "ranking")

    def __init__(self, artifact_dir: str | Path):
        self.artifact_dir = Path(artifact_dir)

    def create_run(self, disease_id: str, config: dict[str, Any], seed: int) -> PipelineRun:
        config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        try:
            revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                      text=True, check=True).stdout.strip()
            dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                                        text=True, check=True).stdout.strip())
            code_commit = revision + ("+dirty" if dirty else "")
        except (OSError, subprocess.CalledProcessError):
            code_commit = "uncommitted"
        return PipelineRun(str(uuid.uuid4()), disease_id, seed, config_hash, code_commit)

    def execute(self, run: PipelineRun, stages: dict[str, Callable[[dict[str, Any]], Any]],
                context: dict[str, Any] | None = None) -> PipelineRun:
        values = context or {}
        run.status = "running"
        self._save(run)
        for name in self.stage_order:
            if name not in stages:
                run.blockers.append(f"{name}: no implementation was registered")
                run.stages.append({"name": name, "status": "blocked", "ended_at": utc_now()})
                run.status = "blocked"
                self._save(run)
                break
            started = utc_now()
            try:
                stage_value = stages[name](values)
                artifact = self._jsonable(stage_value)
                stage_bytes = json.dumps(artifact, indent=2, sort_keys=True,
                                         ensure_ascii=False).encode("utf-8")
                stage_path = self.artifact_dir / "runs" / run.run_id / "stages" / f"{name}.json"
                write_json_atomic(stage_path, artifact)
                values[name] = stage_value
                run.stages.append({"name": name, "status": "succeeded", "started_at": started,
                                   "ended_at": utc_now(),
                                   "output_artifact": str(stage_path.relative_to(self.artifact_dir)),
                                   "output_sha256": sha256_bytes(stage_bytes)})
            except SatoriError as exc:
                run.blockers.append(f"{name}: {exc}")
                run.stages.append({"name": name, "status": "blocked", "started_at": started,
                                   "ended_at": utc_now(), "error": str(exc)})
                run.status = "blocked"
                self._save(run)
                break
            except Exception as exc:
                run.stages.append({"name": name, "status": "failed", "started_at": started,
                                   "ended_at": utc_now(), "error_type": type(exc).__name__, "error": str(exc)})
                run.status = "failed"
                self._save(run)
                break
            self._save(run)
        else:
            run.status = "completed"
        self._save(run)
        return run

    def _save(self, run: PipelineRun) -> None:
        write_json_atomic(self.artifact_dir / "runs" / run.run_id / "run.json", {
            "run": run.__dict__ if hasattr(run, "__dict__") else {
                field: getattr(run, field) for field in run.__dataclass_fields__
            },
            "runtime": {"python": platform.python_version(), "platform": platform.platform()}
        })

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return cls._jsonable(dataclasses.asdict(value))
        if isinstance(value, dict):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._jsonable(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Pipeline stage output contains a non-finite number")
            return value
        raise TypeError(f"Pipeline stage output is not JSON serializable: {type(value).__name__}")
