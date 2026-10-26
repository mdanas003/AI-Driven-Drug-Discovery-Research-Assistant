"""Queue worker executable: `satori-worker` or `python -m satori.worker`."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from satori.capabilities import detect_capabilities
from satori.errors import CheckpointUnavailable, ComponentBlocked, DependencyUnavailable
from satori.job_handlers import HANDLERS
from satori.jobs import JobRepository
from satori.runtime_config import RuntimeConfig
from satori.storage import make_artifact_store


def _revision() -> str:
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=2, check=True).stdout.strip()
    except Exception:
        return "uncommitted"


def process_one(repo: JobRepository, cfg: RuntimeConfig, queue: str) -> bool:
    job = repo.claim(queue)
    if job is None:
        return False
    job_id = job["job_id"]
    repo.update(job_id, progress=0.05)
    repo.add_log(job_id, "info", "execution started", {"worker_queue": queue})
    provenance = dict(job["provenance"] or {})
    try:
        provenance.update({"code_revision": _revision(), "worker_queue": queue,
                           "started_at": job["started_at"], "job_config": job["config"],
                           "worker_runtime": detect_capabilities(),
                           "container_image_digest": os.environ.get("SATORI_IMAGE_DIGEST", "unknown")})
        if cfg.model_registry.is_file():
            provenance["model_registry_sha256"] = hashlib.sha256(
                cfg.model_registry.read_bytes()).hexdigest()
        handler = HANDLERS.get(job["kind"])
        if handler is None:
            raise ComponentBlocked(f"No scientific handler is registered for job kind {job['kind']!r}")
        if job["queue_name"] != queue:
            raise ComponentBlocked(f"Job requires queue {job['queue_name']!r}, received {queue!r}")
        repo.update(job_id, progress=0.15)
        result_data = handler(job["payload"], cfg)
        repo.update(job_id, progress=0.9)
        store = make_artifact_store(cfg.storage_uri)
        artifact = store.put_json(f"jobs/{job_id}/result.json", result_data)
        result = {"artifact": artifact, "artifact_key": f"jobs/{job_id}/result.json"}
        provenance["result_sha256"] = artifact["sha256"]
        provenance["finished_at"] = datetime.now(timezone.utc).isoformat()
        repo.update(job_id, status="completed", progress=1.0, result=result,
                    provenance=provenance)
        repo.add_log(job_id, "info", "execution completed", {"result_sha256": artifact["sha256"]})
    except (ComponentBlocked, CheckpointUnavailable, DependencyUnavailable) as exc:
        provenance["finished_at"] = datetime.now(timezone.utc).isoformat()
        repo.update(job_id, status="blocked", progress=1.0,
                    error={"type": type(exc).__name__, "message": str(exc)}, provenance=provenance)
        repo.add_log(job_id, "warning", "execution blocked", {"type": type(exc).__name__, "reason": str(exc)})
    except Exception as exc:
        provenance["finished_at"] = datetime.now(timezone.utc).isoformat()
        repo.update(job_id, status="failed", progress=1.0,
                    error={"type": type(exc).__name__, "message": str(exc)}, provenance=provenance)
        repo.add_log(job_id, "error", "execution failed", {"type": type(exc).__name__,
                       "message": str(exc), "traceback": traceback.format_exc(limit=20)})
    return True


def heartbeat(cfg: RuntimeConfig, queue: str) -> Path:
    path = cfg.state_db.parent / f"worker-{queue}.heartbeat"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    return path


def healthcheck(cfg: RuntimeConfig, queue: str) -> bool:
    path = cfg.state_db.parent / f"worker-{queue}.heartbeat"
    if not path.is_file():
        return False
    try:
        age = time.time() - path.stat().st_mtime
        return age <= float(os.environ.get("SATORI_WORKER_HEALTH_MAX_AGE", "90"))
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float)
    args = parser.parse_args()
    cfg = RuntimeConfig.from_env()
    queue = cfg.worker_queue
    if args.healthcheck:
        return 0 if healthcheck(cfg, queue) else 1
    repo = JobRepository(cfg.state_db)
    poll = args.poll_seconds if args.poll_seconds is not None else cfg.worker_poll_seconds
    if poll < 0.1:
        parser.error("poll interval must be >= 0.1 seconds")
    while True:
        heartbeat(cfg, queue)
        try:
            did_work = process_one(repo, cfg, queue)
        except Exception as exc:
            # Keep the worker alive across transient state-store faults; emit structured stderr.
            print(json.dumps({"level": "error", "message": "worker loop error",
                              "error_type": type(exc).__name__, "error": str(exc)}), file=sys.stderr)
            did_work = False
        if args.once:
            return 0
        if not did_work:
            time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
