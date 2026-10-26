# Operations

**Current state:** no public deployment, AWS resources, or external GPU runner.

## Development

Install only the optional dependency groups needed. Run the unit suite with `python -m unittest discover -s tests -v`. For local API work, set a development `SATORI_API_TOKEN` in the process environment and keep Uvicorn bound to loopback. Do not expose the prototype directly to the internet.

## Job status semantics

- `queued`: accepted by a local queue and awaiting a worker.
- `running`: claimed by a worker.
- `completed`: handler returned a result; this does not imply scientific validation.
- `blocked`: required data, dependency, checkpoint, rights, or scientific protocol is unavailable.
- `failed`: unexpected execution error; inspect recorded logs and provenance.
- `cancelled`: explicitly cancelled.

The remote external-GPU waiting/lease lifecycle is not implemented. Do not manually mark jobs complete when a notebook finishes.

## Deployment gate

Before any AWS resource is created, verify the account-specific Free Tier status and exact $0 estimate. The current resource allowlist is empty. Keep GPU workers disabled. If a cost dimension is uncertain or nonzero, stop.

## Provenance and artifacts

Retain source revision, configuration, model/data/split hashes, seed, runtime capabilities, stage status, result hash, and errors. Missing or unauthorized checkpoints remain blocked. Preserve failed and blocked stage records; never translate them into success.
