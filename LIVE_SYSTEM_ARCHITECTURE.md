# Satori live system architecture

**Live deployment status:** none. The diagram below describes the approved target topology, not an operating system.

```text
Public client
    │
    ▼
AWS control plane (only after account-specific $0 verification)
    ├── authenticated API / health
    ├── asynchronous job state and queue
    └── minimal result/provenance storage
         │
         ├── CPU jobs → CPU executor, if explicitly verified at $0
         └── GPU jobs → QUEUED_WAITING_FOR_GPU
                            │
                            └── user-started, temporary external GPU session
                                (only when available/authorized)
```

## Current implementation versus intended deployment

- Existing FastAPI routes provide job submission, status, results and health with bearer-token protection on job operations. Compose binds the API to loopback; no public ingress/frontend exists.
- Existing job repository is SQLite/single-host, not a verified public/serverless queue. It has no external runner claim lease or result-upload API.
- GPU worker services exist as optional Compose profiles but must stay disabled for this zero-cost plan.
- Existing workers do not yet report `QUEUED_WAITING_FOR_GPU` or reclaim leases after a provider session ends.
- Storage and model registry abstractions exist locally; no AWS bucket, database, queue, or registry is deployed.
- Scientific components report genuine blockers; no AWS GPU or external GPU provider has run them.

## Required deployment gates

1. Complete authenticated, read-only AWS account audit and maintain an empty allowlist unless exact $0 eligibility and usage are verified.
2. Validate the lightweight control-plane architecture against the actual approved resources, including frontend/public access, auth, job persistence, provenance, quota handling and all ingress/storage/transfer costs.
3. Implement and test external GPU claim/lease/heartbeat/restart/result-upload protocol.
4. Obtain user authorization for a provider session when the provider requires login or accepting terms.
5. Execute end-to-end tests without claiming scientific success for blocked stages.

The user’s PC and RTX 3050 are not part of this system architecture and must not be required for normal operation.
