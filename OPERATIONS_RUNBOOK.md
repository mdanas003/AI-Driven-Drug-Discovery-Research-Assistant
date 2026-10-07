# Operations runbook

**Current state:** AWS not deployed; external GPU runner not operational; no public Satori endpoint. Do not treat these procedures as already tested in AWS.

## Current safe checks

- Run the local test suite and capability checks on an operator machine only when requested; local development is not a production dependency.
- Read `ZERO_COST_DEPLOYMENT_STATUS.md` and `AWS_FREE_TIER_RESOURCE_ALLOWLIST.md` before any cloud work. The current allowlist is empty.
- Do not start a GPU worker, external provider session, or AWS resource automatically.

## After account authentication (read-only phase)

1. Inspect account plan/age, region, Free Tier offer status, actual and forecast usage, current resources, networking, storage, and all candidate quotas using the official console/API.
2. Calculate the exact expected bill for the concrete monthly workload, excluding promotional credits.
3. If any eligibility or cost dimension is uncertain or nonzero, stop. Do not deploy.
4. Only after a written $0 review may a separate deployment action be considered. Keep the allowlist fail-closed and GPU workers disabled.

## Intended user flow (not yet live)

1. Submit `/discover`, `/targets`, `/generate`, `/optimize`, or `/dock` asynchronously and receive a job ID.
2. Poll `GET /jobs/{job_id}` for queue, progress, provenance and status; retrieve terminal results from `/jobs/{job_id}/results`.
3. GPU work remains `QUEUED_WAITING_FOR_GPU` until a user-authorized external session claims it. Current API does not implement this state/protocol yet.
4. On runner termination, the lease should expire and a later authorized session can resume; this behavior is not yet implemented or validated.
5. Scientific failure is `BLOCKED` when prerequisites are missing and `FAILED` when execution errors. Never translate either state into `COMPLETED`.

## Start/stop and incident handling

- No AWS start/stop commands are provided because no resource is authorized.
- When any future approved resource is deployed, record its exact ID, region, monthly allowance, stop/delete operation, data retention impact and cleanup deadline in the allowlist before start.
- If billing or a nonzero forecast appears, stop further work and remove the specific resource only after checking whether deleting it also deletes required data. Do not create a replacement or upgrade the account.
- If an API token or worker credential is exposed, revoke it through the provider console and rotate it; never paste the new value into chat or Git.

## Scientific operations

Keep model-registry status, data/split hashes, run seeds, source revision, model/checkpoint hashes, license state, environment and all stage outcomes with each run. Checkpoints that are missing or unauthorized remain `BLOCKED`. RL does not replace GraphFDM; a model adapter is not a trained result. See `FINAL_DEPLOYMENT_STATUS.md` for exact outstanding scientific gates.
