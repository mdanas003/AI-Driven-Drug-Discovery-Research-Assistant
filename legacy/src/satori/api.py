"""Thin asynchronous job-submission API. Install with `pip install .[cloud-api]`."""
from __future__ import annotations

import hmac
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Request, status
except ImportError as exc:
    from satori.errors import DependencyUnavailable
    raise DependencyUnavailable("The API requires installing the [cloud-api] extra") from exc

from satori.capabilities import detect_capabilities
from satori.jobs import JobRepository
from satori.runtime_config import RuntimeConfig
from satori.storage import make_artifact_store

app = FastAPI(title="Satori Research API", version="0.1.0",
              description="Research workflow job submission and status; not a clinical service")


def _runtime(request: Request) -> tuple[RuntimeConfig, JobRepository]:
    if not hasattr(request.app.state, "runtime_config"):
        cfg = RuntimeConfig.from_env()
        request.app.state.runtime_config = cfg
        request.app.state.job_repository = JobRepository(cfg.state_db)
    return request.app.state.runtime_config, request.app.state.job_repository


def _queue(kind: str) -> str:
    return {"discover": "cpu", "targets": "cpu", "generate": "gpu",
            "optimize": "gpu", "dock": "docking", "etflow": "etflow"}[kind]


def _safe_config(cfg: RuntimeConfig) -> dict[str, Any]:
    return {"data_dir": str(cfg.data_dir), "artifact_dir": str(cfg.artifact_dir),
            "storage_uri": cfg.storage_uri, "model_registry": str(cfg.model_registry),
            "model_cache_dir": str(cfg.model_cache_dir), "device": cfg.device}


def _authorize(request: Request) -> None:
    cfg, _ = _runtime(request)
    if not cfg.api_token:
        raise HTTPException(503, "API authentication is not configured")
    authorization = request.headers.get("authorization", "")
    scheme, separator, supplied = authorization.partition(" ")
    if (not separator or scheme.casefold() != "bearer" or not supplied
            or not hmac.compare_digest(supplied, cfg.api_token)):
        raise HTTPException(401, "valid bearer token required",
                            headers={"WWW-Authenticate": "Bearer"})


def _reject_secrets(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(term in normalized for term in ("secret", "password", "credential", "api_key", "access_token")):
                raise HTTPException(422, f"Credentials must be provided through environment/secret management, not {path}.{key}")
            _reject_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secrets(item, f"{path}[{index}]")


def _submit(kind: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _authorize(request)
    cfg, repo = _runtime(request)
    _reject_secrets(payload)
    provenance = {"runtime": detect_capabilities(), "api_version": "0.1.0",
                  "scientific_architecture": "approved; no automatic baseline substitution"}
    job = repo.create(kind, _queue(kind), payload, _safe_config(cfg), provenance)
    return {"job_id": job["job_id"], "kind": kind, "queue": job["queue_name"],
            "status": job["status"], "status_url": f"/jobs/{job['job_id']}"}


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    _runtime(request)
    return {"status": "ok", "service": "satori-api", "capabilities": detect_capabilities()}


def _endpoint_for(kind: str):
    async def endpoint(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        return _submit(kind, body, request)
    endpoint.__name__ = "submit_" + kind
    return endpoint


for _kind in ("discover", "targets", "generate", "optimize", "dock", "etflow"):
    app.add_api_route("/" + _kind, _endpoint_for(_kind), methods=["POST"],
                      status_code=status.HTTP_202_ACCEPTED, name="submit_" + _kind)


@app.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    _authorize(request)
    _, repo = _runtime(request)
    job = repo.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@app.get("/jobs/{job_id}/results")
def get_results(job_id: str, request: Request) -> dict[str, Any]:
    _authorize(request)
    cfg, repo = _runtime(request)
    job = repo.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job["status"] not in {"completed", "blocked", "failed"}:
        raise HTTPException(409, "job has no terminal result yet")
    result_data = None
    if job["status"] == "completed" and job["result"]:
        result_data = make_artifact_store(cfg.storage_uri).get_json(job["result"]["artifact_key"])
    return {"job_id": job_id, "status": job["status"], "result": result_data,
            "artifact": job["result"].get("artifact") if job["result"] else None,
            "error": job["error"], "logs": job["logs"], "provenance": job["provenance"]}
