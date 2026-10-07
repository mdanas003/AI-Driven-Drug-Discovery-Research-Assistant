# Worker Architecture

## Queueing and job lifecycle

The API writes an immutable payload/configuration/provenance snapshot into the SQLite job ledger and returns a UUID. Queue selection is explicit: `discover` and `targets` → `cpu`; `generate` and `optimize` → `gpu`; `dock` → `docking`; `etflow` → `etflow`. Separate worker processes set `SATORI_WORKER_QUEUE`. Jobs cannot be claimed by a worker from another queue.

Lifecycle: `queued → running → completed | blocked | failed`. `blocked` represents expected missing dependency/checkpoint/scientific prerequisites (`ComponentBlocked`, `CheckpointUnavailable`, `DependencyUnavailable`); unexpected errors become `failed` with type/message and traceback in logs. Each worker appends structured, UTC-stamped logs, updates progress at stage boundaries, records code revision, request config, runtime capabilities, result hash and result artifact pointer. The worker heartbeat powers container health checks.

Progress is deliberately coarse until each long-running scientific operation exposes its own progress callback. `0.05` means claimed, `0.15` means handler is executing, `0.9` means storing the completed output, `1.0` is terminal; it is not a percentage estimate of scientific work.

## Scientific handler boundaries

- Discovery and target retrieval call the existing Open Targets client and preserve target/evidence records.
- Generation calls pinned GP-MoLFormer. Results explicitly set `target_conditioned=false`; target/pocket inputs remain blocked by its existing module.
- Optimization calls GraphFDM's primary adapter. With current missing implementation/checkpoint/objective training, the job becomes `blocked`; it does not call RL as fallback.
- Docking calls Vina only on existing receptor/ligand PDBQT files and explicit box parameters. It labels the score `NOT_VALIDATED` until preparation and protocol evaluation are approved.
- ET-Flow calls its actual existing conformer adapter in a separately pinned image. Rights/checkpoint or environment failures surface as blocked.

The job handler is orchestration only. Model training/evaluation, target-specific policy, molecule preparation, and affinity claims remain in scientific modules and their established gates.

## Horizontal scaling and future queue

The current SQLite lease/queue is suitable only for a single VM sharing one persistent disk. It uses SQLite WAL and an atomic `BEGIN IMMEDIATE` claim; do not mount this SQLite database over network object storage or run multi-host writers. At multi-node scale, implement the same `JobRepository` contract with a managed relational database and a broker/queue (for example PostgreSQL plus a managed queue). Model artifacts and result blobs use the `ArtifactStore` interface. Vector records use the `VectorStore` protocol; the current durable local JSON cosine index is development-scale only, and no managed vector backend is selected.

Workers do not auto-resubmit jobs. Operators should retain terminal failure logs and explicitly resubmit after reviewing side effects. Publicly accessible multi-tenant use additionally requires authentication/authorization, resource quotas, cancellation semantics, worker leases/recovery and audit retention before deployment.
