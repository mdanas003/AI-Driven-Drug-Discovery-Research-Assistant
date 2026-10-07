# External free GPU guide

**Status:** No external provider was authenticated or used. AWS Free Tier GPU workers are prohibited. This guide does not promise availability or provider quotas.

## Human-started execution only

When an external no-cost GPU is available and its current terms permit the workload, the user starts the session through the provider’s normal login and UI. Colab, Kaggle, or another provider must be treated as a short-lived interactive execution environment, never as Satori’s always-on backend. Do not automate sign-in, evade session limits, keep a session alive, or treat a free session as guaranteed capacity.

Before a workload starts, verify the provider’s current usage policy, allowed data/license handling, accelerator availability, session duration, and storage persistence. Do not upload restricted datasets or weights where the provider terms disallow it. The user must explicitly authorize provider use if login/acceptance is required.

## Restart/resume requirements

The runner must receive an immutable job bundle with hashes and a short-lived scoped token; it may save resumable checkpoints only when the model/data license and storage terms permit. On interruption, the backend lease expires, retains completed artifact hashes and attempt lineage, and makes the job reclaimable. A resumed session verifies all hashes and resumes from the last valid checkpoint; it must not duplicate or overwrite completed stages silently.

## Current limitation

The repository has no remote GPU claim/lease/result endpoints. Therefore users cannot yet activate a free session to pull a queued Satori job or return its output. Do not manually mark job state as completed or treat local files from a notebook as backend results. This capability is **BLOCKED** pending implementation and validation of the runner protocol in `GPU_RUNNER_GUIDE.md`.

## Science remains unchanged

GFM/ULTRA evaluation, explicit protein/pocket-conditioned GP-MoLFormer, ET-Flow, GraphFDM, affinity, predictors and RL remain subject to existing data, licensing, split and validation gates. A free accelerator only supplies compute; it does not make an unavailable checkpoint authorized or make an unevaluated model scientifically ready.
