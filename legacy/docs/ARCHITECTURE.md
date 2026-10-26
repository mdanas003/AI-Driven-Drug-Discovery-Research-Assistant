# Architecture

## Scope

Satori separates disease-target evidence collection, molecular data preparation, scientific models, orchestration, and artifact/provenance handling. This repository contains a research prototype and deployment definitions; it is not a live service.

## Runtime shape

```text
Client
  │
  ▼
FastAPI ── job ledger (SQLite, single host) ── CPU / GPU / ET-Flow / docking workers
  │                          │
  ├── health/status          └── hashed result artifacts + provenance
  └── model registry and local artifact storage
```

The API validates and queues requests. It does not wait for long-running model work. Workers claim jobs from their configured queue and call the corresponding scientific handler. Expected scientific prerequisites propagate as `blocked`; unexpected runtime exceptions become `failed`. Results retain the input/configuration snapshot, source revision, runtime capabilities and artifact hashes.

## Queues

| Queue | Operations | Current boundary |
|---|---|---|
| `cpu` | Open Targets evidence retrieval and CPU preprocessing | Evidence retrieval is not final target selection or training validation. |
| `gpu` | molecular generation and optimization adapters | The available GP-MoLFormer checkpoint is not protein/pocket conditioned; GraphFDM remains blocked. |
| `etflow` | ET-Flow conformer generation | Checkpoint rights and compatible execution/validation remain unresolved. |
| `docking` | AutoDock Vina on prepared PDBQT inputs | Structure preparation and docking protocol are not validated. |

GPU, ET-Flow, and docking containers are optional Compose profiles. They must not be enabled unless their runtime and scientific prerequisites are satisfied. In the zero-cost AWS plan, AWS GPU workers are prohibited.

## Persistence and scaling

The SQLite ledger uses atomic claims and is suitable only for a single host. Never share its database file across hosts or place it on object storage. `ArtifactStore` supports local files and an optional S3 implementation; no AWS storage is deployed. The model registry resolves explicit artifacts and fails closed when a checkpoint is unavailable. The local vector index stores supplied vectors and provenance; it does not generate embeddings.

Multi-host deployment needs a transactional job store/queue, worker lease and recovery semantics, authentication/authorization, quotas, cancellation, monitoring and durable artifact policy. Those components are not currently implemented as a verified hosted control plane.

## HTTP contract

- `POST /discover`, `/targets`, `/generate`, `/optimize`, `/dock`, `/etflow` accept jobs and return HTTP 202 with a job ID.
- `GET /jobs/{job_id}` returns status, progress, logs and provenance.
- `GET /jobs/{job_id}/results` returns terminal results or the recorded blocker/failure.
- `GET /health` reports service/runtime capabilities.

Job operations require a configured Bearer token. Health is unauthenticated and contains no local filesystem paths. Compose binds the API to loopback. The API has no public ingress or frontend.

## External GPU boundary

There is no remote GPU runner protocol yet: no external claim lease, heartbeat, restart recovery, or result upload endpoint. Free notebook sessions are not persistent workers. See [External GPU execution](deployment/EXTERNAL_GPU.md); do not mark an external run complete until that protocol is implemented and validated.
