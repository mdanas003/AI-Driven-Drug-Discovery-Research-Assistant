# Satori Cloud Architecture

## Scope

This deployment layer runs the existing Satori scientific modules as durable jobs. It does not claim that blocked or untrained scientific components are ready. GraphFDM remains the primary optimizer, RL remains a distinct baseline, and either worker records the existing blocker rather than substituting another model.

## Runtime shape

```text
Caller / future UI
        │ HTTPS (reverse proxy or private network; API has no built-in user auth)
        ▼
FastAPI API ── submit/status/results ── SQLite job ledger (single VM, persistent disk)
        │                                         │
        ├── local artifact store or S3            ├── CPU queue ── API/data worker
        ├── model registry/cache                   ├── GPU queue ── GNN/GP-MoLFormer/optimizer worker
        └── health/capability report               ├── ET-Flow queue ── isolated CUDA 12.1 worker
                                                  └── docking queue ── CPU Vina worker
```

The API only validates/enqueues requests. `JobRepository` is a SQLite-backed single-host queue with atomic queue claims, a monotonically updated progress field, timestamped logs, terminal `completed`/`blocked`/`failed` states, serialized request configuration, and provenance. Workers call the existing `satori.job_handlers` adapters, which in turn call existing scientific modules. Result payloads are content-hashed and stored as artifacts; the database retains the result artifact reference rather than large generated output bodies.

## Workload allocation

| Queue | Container | Workloads | Current boundary |
|---|---|---|---|
| `cpu` | API and CPU worker | API/orchestration, Open Targets data retrieval, preprocessing, graph construction, provenance | Can run without CUDA. Some retrieval/model paths still require configured services or artifacts. |
| `gpu` | CUDA 12.4/PyTorch worker | temporal GNN, GP-MoLFormer inference/fine-tuning, future GraphFDM/RL and protein-ligand training | GP-MoLFormer real pinned inference is wired; target-conditioned generation, GFM checkpoint and trained optimizer/affinity models remain blocked. |
| `etflow` | isolated CUDA 12.1/Python 3.10 worker | ET-Flow conformer inference | Upstream-compatible environment is separate. Checkpoint use rights and validation are still blocked. |
| `docking` | CPU worker with Vina 1.2.7 | Vina execution on already prepared PDBQT input | Receptor/ligand preparation, pocket and protocol validation remain scientific gates. |

The GPU and ET-Flow environments are kept separate because ET-Flow upstream currently pins NumPy 1.26.4 and CUDA 12.1/PyG dependencies while the main GPU image uses NumPy 2.2.4 and PyTorch 2.6.0/CUDA 12.4. ET-Flow's package metadata lists Python through 3.12; the image uses Python 3.10. The upstream environment dependencies are visible in its [environment file](https://raw.githubusercontent.com/shenoynikhil/ETFlow/main/env.yml) and [package metadata](https://raw.githubusercontent.com/shenoynikhil/ETFlow/main/pyproject.toml).

## Persistence and scaling boundary

- Development and single-VM reference deployment: local filesystem artifact store plus SQLite on the same persistent EBS volume.
- Object storage: `SATORI_STORAGE_URI=s3://bucket/prefix` selects the optional boto3-backed artifact store; standard AWS credential chains/IAM roles supply credentials. No keys are stored in config or job payloads.
- Vector retrieval: a vector-store protocol and durable local cosine index exist. It stores supplied vectors and provenance; it does not fabricate embeddings or include a cloud-managed vector database backend. The embedding model/index remains a separately selected scientific component.
- SQLite on one shared EBS filesystem is a one-host development/reference topology. Before multiple API/worker hosts or public multi-tenant service, replace the job repository with a managed relational database/queue and add authentication, authorization, tenant isolation, rate limits and operational monitoring. The persistence interfaces are intentionally separate from request handlers.
- Model weights are not in source images. They resolve from a revision-pinned upstream source or configured artifact cache; unresolved model checkpoints are recorded as blocked in the model registry.

## HTTP contract

`POST /discover`, `/targets`, `/generate`, `/optimize`, `/dock` (and `POST /etflow`) return `202` with a job ID. `GET /jobs/{job_id}` returns status/progress/logs/provenance; `GET /jobs/{job_id}/results` returns `409` until terminal and then includes result artifacts or the explicit blocker/failure. `GET /health` reports API and runtime capability status. Jobs do not run in the request process.

All five requested operation paths are implemented. Request JSON containing keys such as `api_key`, `secret`, `password`, `credential`, or `access_token` is rejected; secrets must be injected through an environment or secret manager. Do not expose port 8000 publicly without a trusted TLS/authentication proxy.

## Scientific status

The runtime can retrieve disease-target evidence and execute real GP-MoLFormer inference when the pinned model cache is available. Other job paths keep their real scientific limitations. See [CLOUD_READINESS_REPORT.md](CLOUD_READINESS_REPORT.md) and [MODEL_ARTIFACT_REGISTRY.md](MODEL_ARTIFACT_REGISTRY.md).
