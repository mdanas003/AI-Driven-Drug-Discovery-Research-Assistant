# External GPU execution

## Policy

Temporary external free-GPU sessions may be used only when available, permitted by the provider’s current terms, and explicitly authorized where provider login/terms require it. Do not automate authentication, bypass quotas/session limits, keep sessions alive, or use these platforms as persistent workers. The user’s personal PC and RTX 3050 must not be required for normal Satori operation. AWS GPU workers and paid GPU fallbacks are prohibited.

## Current status

An external worker is **not implemented or validated**. The current API/SQLite service has no external job-claim lease, heartbeat, result-upload endpoint, or interrupted-session recovery. Do not represent a notebook or adapter as an operational runner.

## Required runner protocol

Before external GPU use, implement and test:

1. Short-lived, queue-scoped worker authorization.
2. Atomic job claims with expiring leases and attempt lineage.
3. Immutable job bundles containing source revision, configuration, input hashes, model registry state and provenance.
4. Runtime capability detection; no assumed accelerator model.
5. Progress/lease renewal and interruption-safe checkpoints where licenses permit.
6. Content-hashed artifact/result upload and idempotent terminal transition.
7. Reclaim after session termination without overwriting completed stages.

Required statuses are `QUEUED_WAITING_FOR_GPU`, `RUNNING`, `COMPLETED`, `BLOCKED`, and `FAILED`. A missing GPU leaves work waiting or unavailable; it must never synthesize a result. Provider-specific implementation and end-to-end verification remain blocked.
