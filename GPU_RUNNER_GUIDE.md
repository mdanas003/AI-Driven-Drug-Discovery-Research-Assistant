# GPU runner guide

**Status:** RUNNER NOT IMPLEMENTED OR VALIDATED. This guide specifies the safe execution contract; it does not claim Colab/Kaggle compatibility, job pickup, artifact upload, or model results.

## Execution contract

External GPU sessions are user-started and temporary. A runner may use only a provider’s normal documented notebook/session workflow, may not keep sessions alive, evade quotas, or run as a persistent backend. The Satori public/control plane must remain functional when there is no GPU. AWS GPU workers remain disabled.

For a production runner, the backend must expose authenticated, auditable operations to:

1. Claim a GPU-required job with an expiring lease and attempt number.
2. Download an immutable, hashed job bundle: source revision, exact configuration, inputs/data references, model registry descriptors, allowed checkpoint references, and provenance seed.
3. Verify bundle hashes and model licenses/availability before loading anything. Missing or unauthorized artifacts return `BLOCKED`.
4. Run only the requested scientific handler; preserve scientific blockers and do not substitute a baseline.
5. Periodically renew the lease and checkpoint restartable intermediate state where license/storage policy allows.
6. Upload bounded, content-hashed result/provenance artifacts; atomically transition the job to `COMPLETED`, `BLOCKED`, or `FAILED`.
7. Allow an expired lease to be reclaimed after termination, recording attempt lineage and preserving prior artifacts.

## Current code boundary

The existing API accepts jobs and the local SQLite worker supports CPU/GPU queues, but there is no remote worker claim/lease/heartbeat/result-upload API or hosted artifact endpoint. A remote notebook cannot safely obtain and complete a queued job against the current contract. Implement and test those endpoints before treating a runner as operational. Do not send the global API token to a notebook; use short-lived, queue-scoped worker credentials when that control plane exists.

## Provider workflow

The user must sign in to a free GPU provider directly, select an available runtime, review that provider’s current terms/quotas, and explicitly start a session. The runner must detect actual accelerator/runtime capabilities at launch rather than assume a GPU type. It must exit cleanly when no GPU is present. No provider account or authorization has been used for this task.

## Supported status transitions (required)

`QUEUED_WAITING_FOR_GPU` → `RUNNING` (valid lease) → `COMPLETED`, `BLOCKED`, or `FAILED`. An expired/terminated runner must leave the job reclaimable and must never leave it falsely completed. Existing jobs currently use `queued/running/completed/blocked/failed/cancelled`; the new waiting and lease states have not been implemented.

## Validation required before use

- Protocol tests for concurrent claims, expired lease recovery, idempotent result upload, unauthorized claims, oversized uploads and interrupted transfer.
- Reproducibility check from an immutable source revision and exact model/data hashes.
- Provider-specific tests in an explicitly authorized temporary session.
- End-to-end provenance and artifact download/hash verification.

Until those gates pass, GPU jobs must remain queued or explicitly blocked; no mock runner may report scientific completion.
