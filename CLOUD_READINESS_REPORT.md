# Cloud Readiness Report

> Superseded for current deployment decisions by `FINAL_DEPLOYMENT_STATUS.md`. This earlier report predates bearer-token authentication and the final ULTRA decision. Its verification results remain historical.

**Prepared:** 2026-10-02  
**Scope:** Cloud deployment infrastructure and local/static validation. This is not a cloud deployment or scientific validation report.

## READY

- Linux container build definitions separate API, CPU, general CUDA/PyTorch, ET-Flow CUDA/PyG and CPU Vina workloads. Images pin primary frameworks/runtime packages, use non-root UID 10001, persistent environment paths and health checks. Model weights are not copied into the source image.
- FastAPI request endpoints enqueue jobs and return a job ID. `/jobs/{id}` returns status/progress/logs/provenance; `/jobs/{id}/results` reads the hashed artifact or returns blocker/failure details; `/health` reports capability information.
- A single-host SQLite queue uses atomic claims and queue isolation. CPU ingestion, GP-MoLFormer generation, GraphFDM optimization, ET-Flow, and Vina route to separate workers. The handlers call real project modules; known blockers propagate as `blocked`.
- Local filesystem and S3 artifact backends share an interface. A configurable registry enforces explicit availability/path/hash and raises `CheckpointUnavailable` rather than fallback. A vector-store protocol and persistent local cosine index exist; no embedding model is fabricated.
- Runtime configuration is environment-driven; secrets are rejected in job bodies and documented for provider secret managers. No Windows filesystem path is baked into the cloud code/images.
- Local tests cover API submission/health, config validation, capability shape, storage/hash/path traversal, registry resolution/failure, vector persistence, job lifecycle, worker startup/result/provenance, failure propagation and worker health.

## CLOUD_REQUIRED

- Build and run the images in Linux Docker; Docker Engine is unavailable on the local machine. Validate health checks and persistent volume permissions on the VM.
- Verify NVIDIA container runtime on an Ubuntu 22.04 GPU VM, then validate the pinned PyTorch 2.6.0+cu124 worker with a GPU smoke. Recommended integration reference: AWS EC2 `g5.xlarge`, 4 vCPU, 16 GiB RAM, one A10G reported as 22 GiB accelerator memory. It is not a guarantee that all training fits.
- Resolve ET-Flow's commit-pinned dependency image with matching Python 3.10, PyTorch 2.5.1+cu121, NumPy 1.26.4 and PyG compiled packages. Actual ET-Flow inference, VRAM profile and geometry evaluation require cloud execution.
- Resolve and hash each model/checkpoint artifact and pin final container image digests. GP-MoLFormer weights are remote-pinned and will populate the mounted Hugging Face cache; do not build them into the image.
- Validate S3 IAM role and artifact persistence with a real cloud bucket if S3 mode is selected. SQLite/job state remains on durable local block storage in the single-host topology.
- Cloud GPU training/inference for GFM/GNN, GP-MoLFormer fine-tuning, GraphFDM, RL baseline and protein-ligand affinity is a separate compute phase after data/model scientific gates.

## BLOCKED

- **Target/GFM:** exact approved foundation checkpoint is not identified; temporal graph implementation has not been scientifically ranked against a leakage-resistant benchmark.
- **ET-Flow:** runtime prepared, but checkpoint-use rights in the cited Zenodo record remain unresolved in the existing blocker plan; do not use the weights until cleared.
- **GraphFDM:** remains primary optimizer but no compatible implementation/checkpoint/objective-training path is defined. The API worker records blocked state; RL is not substituted.
- **RL:** distinct Pareto baseline, not yet trained; no baseline method/checkpoint or data gate.
- **GP-MoLFormer target conditioning:** current real model is unconditional/scaffold-prompted. Protein/pocket conditioning and validated fragment policy are not implemented by the base checkpoint.
- **Data/affinity/ADMET/OOD:** existing data are smoke samples, not training datasets; validated disease-target endpoint distributions, leakage-resistant splits, property predictors and calibration are not established. Do not train or emit validated outputs.
- **Docking:** Vina 1.2.7 runtime is available, but receptor/ligand preparation, pocket, validated scoring setup and evaluation protocol remain BLOCKED. Returned score is labelled not validated.
- **Managed vector retrieval:** only local vector storage interface/index is implemented. Cloud vector backend and licensed/validated embedding selection remain open.

## USER_DECISION_REQUIRED

- **None for this infrastructure phase.** The scientific choices already recorded in `OPTIMIZATION_POLICY.md` remain in force. The project has not been asked to expose an unauthenticated public endpoint, and this report does not make that decision for the user.

## DEPLOYMENT_GAPS

- Local Docker build/run and a cloud VM/GPU smoke were not possible or performed here. Static Dockerfile/config checks do not certify container image builds.
- Job submission and retrieval now require a configured bearer token; `/health` remains unauthenticated and exposes capability status only. API is still bound to loopback in Compose and has no TLS termination, tenant isolation, rate limits, request quotas, cancellation, or public abuse controls. Keep port 8000 private until a TLS/authentication gateway or VPN and the remaining operational controls are configured.
- SQLite is a one-host queue. Do not mount its database across hosts or on object storage. Add managed transactional job metadata/broker, worker leases/recovery and cancellation before horizontal scaling.
- Bind cloud data/checkpoint licenses, private-data retention and regional controls to actual selected sources/providers. Ensure S3 bucket policy, encryption/versioning/lifecycle and backup/recovery are configured.
- ET-Flow Docker build requires an immutable `ETFLOW_GIT_COMMIT`; a full lockfile/resolved image digest and execution test still need cloud CI. The model checkpoint's license blocker is scientific/legal and is not resolved by containerization.
- `POST /discover` and `/targets` perform Open Targets disease-target evidence retrieval. They do not perform final target selection, target-ranking validation, ChEMBL assay distribution analysis, or prove readiness for training.

## Verification performed

- Full local suite: **58 tests passed**; Python `compileall` passed; `pip check` reported no broken requirements. FastAPI/Uvicorn/HTTPX were installed as a small pinned test/runtime group after network approval; no model checkpoint was downloaded.
- Docker Compose `config --quiet` passed. Runtime paths were scanned; no hardcoded Windows-user paths were found. Docker Compose CLI is present, but the Docker engine is unavailable, so images were not built or run. The ET-Flow compose configuration used a placeholder commit only for static parsing; the Dockerfile rejects it for a real image build.
- No large checkpoint download, expensive training, or actual cloud provisioning was performed.
- External configuration references: [ET-Flow upstream environment](https://raw.githubusercontent.com/shenoynikhil/ETFlow/main/env.yml), [ET-Flow package metadata](https://raw.githubusercontent.com/shenoynikhil/ETFlow/main/pyproject.toml), [PyTorch version matrix](https://pytorch.org/get-started/previous-versions/), [AWS EC2 GPU sizes](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html), [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), and [Vina 1.2.7 releases](https://github.com/ccsb-scripps/AutoDock-Vina/releases).
