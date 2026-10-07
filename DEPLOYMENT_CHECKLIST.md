# Deployment Checklist

## Before building

- [ ] Use a private Linux GPU VM and a persistent encrypted volume; do not require Docker on Windows.
- [ ] Install a supported NVIDIA driver, Docker Engine and NVIDIA Container Toolkit; confirm `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` works. NVIDIA documents the Ubuntu 22.04 container setup and `--gpus all` flow [here](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
- [ ] Copy `.env.example` to `.env`; configure the persistent paths, queue, `HF_HOME`, and provider artifact URI. Keep `.env` untracked.
- [ ] Set least-privilege object-storage IAM policy if using S3; do not insert long-lived access keys into job payloads.
- [ ] Confirm model/checkpoint licenses and registry entries; ET-Flow `drugs-o3` rights are still an explicit blocker.
- [ ] Pick and record an immutable ET-Flow source commit before building that profile.

## Build and start a reference single-host deployment

1. On Ubuntu 22.04 amd64 with an NVIDIA A10G/L4-class GPU and adequate persistent storage, install Docker Engine and NVIDIA Container Toolkit using their current official instructions. Confirm the GPU test above.
2. Clone/copy this repository to the VM. Preserve the source revision; do not copy local `.venv`, raw downloads, large checkpoints, or `.env` into the source tree.
3. Create `.env` from `.env.example`. Paths must be writable by UID 10001. For the simple single-VM path set `SATORI_STORAGE_URI=/opt/satori/artifacts`; configure S3 URI and VM IAM role when outputs should persist independently of the VM.
4. Build/start API and CPU worker: `docker compose build api cpu-worker` then `docker compose up -d api cpu-worker`.
5. For the general GPU queue: `docker compose --profile gpu build gpu-worker` then `docker compose --profile gpu up -d api cpu-worker gpu-worker`. Verify GPU visibility in worker logs/capability metadata before submitting model jobs.
6. To build a separate docking worker, `docker compose --profile docking build docking-worker`; start it with `docker compose --profile docking up -d api cpu-worker docking-worker`. It uses the official Vina 1.2.7 Linux release executable and checks its reported version during build.
7. ET-Flow is separately gated. First confirm checkpoint-use license and source commit; set `ETFLOW_GIT_COMMIT` to the immutable 40-character commit, then run `docker compose --profile etflow build etflow-worker` and start the profile. Execute the known-molecule validation protocol in `BLOCKER_RESOLUTION_PLAN.md` before enabling scientific use.
8. Confirm `docker compose ps`, worker heartbeat health, and `curl http://127.0.0.1:8000/health`. Keep API port private. Add a TLS/authentication reverse proxy or VPN and allowlisted ingress before exposing it beyond trusted operators.
9. Submit a small live `/targets` retrieval job with an approved Open Targets disease ID. Poll `/jobs/{job_id}` and confirm result hash/artifact, source provenance and terminal state. Exercise `/optimize` only to confirm its explicit GraphFDM blocker until the scientific prerequisites are cleared.
10. Back up the SQLite database and local artifact volume, or verify object-storage retention/versioning. Record image digests, lockfiles, model-cache revisions and runtime capability report.

The reference instance `g5.xlarge` has 16 GiB host memory, 4 vCPU and one A10G with 22 GiB GPU memory per AWS's [EC2 instance specification](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html). This is for integration/inference validation, not a guarantee that every training workload fits. Scale GPU profile/instance and disk after measuring peak memory/data needs.

## Before public exposure

- [ ] Authentication, authorization, request quotas, cancellation, rate limiting, audit policy and abuse controls.
- [ ] Multi-host job backend/managed DB and durable cloud object-storage policy if scaling beyond one VM.
- [ ] API TLS termination, DNS, security groups, backups, monitoring/alerting, log redaction and recovery drills.
- [ ] Scientific target/data/split/model/protocol gates in the readiness report.
- [ ] Operational review of model/data licenses, privacy, retention and cloud region before shipping research datasets or model checkpoints.
