# Cloud Deployment Procedure

This is a concrete, single-VM reference path. It does not deploy the service from this local Windows machine and does not claim scientific readiness. Deploy the API on a private listener/network; the sample binds port 8000 to loopback on the VM. Require a TLS/authentication proxy or VPN before remote access.

## 1. Provision a cloud host

Use an Ubuntu 22.04 LTS amd64 GPU VM. Reference: AWS EC2 `g5.xlarge` (4 vCPU, 16 GiB host RAM, one NVIDIA A10G with 22 GiB reported accelerator memory); provide a persistent 100 GiB or larger volume mounted for Docker and state. AWS currently lists this size/GPU in the [EC2 accelerator instance table](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html). Quotas, region availability, and price vary; check those in the cloud console before launching.

Attach a least-privilege VM workload identity for the target S3 bucket if using object storage. Do not create or commit static keys. Limit inbound network rules to operator/VPN or reverse-proxy sources; do not open port 8000 to the internet.

## 2. Prepare container runtime

1. Install a supported NVIDIA driver and Docker Engine following the cloud image/provider's supported procedure.
2. Install NVIDIA Container Toolkit on Ubuntu 22.04 using the [official guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). Restart Docker after configuring the NVIDIA runtime.
3. Confirm host `nvidia-smi` works and run:

   ```bash
   docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
   ```

4. Install Docker Compose v2 (the plugin). Docker Compose GPU device reservations are documented in the [Compose deployment spec](https://docs.docker.com/reference/compose-file/deploy/).

## 3. Place source and configure persistence

1. Retrieve the approved Git revision and record `git rev-parse HEAD`.
2. Copy only source/config/lock files. Do not place `.venv`, `.env`, `data/`, cached model weights, datasets, or untracked temporary artifacts in the build context. `.dockerignore` excludes local artifacts.
3. Create a persistent filesystem for `/opt/satori/artifacts`, `/opt/satori/data`, and `/opt/satori/model-cache`; ensure container UID 10001 can write there. The example Compose file creates Docker named volumes for single-host use. Back these volumes up.
4. `cp .env.example .env`, then edit non-secret storage paths and queue settings. Inject external-service secrets through VM secret manager/environment. Do not put them in request JSON.
5. Select storage mode:
   - Single VM: `SATORI_STORAGE_URI=/opt/satori/artifacts` (SQLite and files share durable host storage).
   - S3 object artifacts: `SATORI_STORAGE_URI=s3://<bucket>/<prefix>`; configure the VM role and keep `SATORI_STATE_DB` on persistent local block storage. SQLite remains single-host only.

## 4. Build and start

For CPU retrieval/API:

```bash
docker compose build api cpu-worker
docker compose up -d api cpu-worker
```

For the pinned general CUDA/PyTorch worker:

```bash
docker compose --profile gpu build gpu-worker
docker compose --profile gpu up -d api cpu-worker gpu-worker
```

For CPU docking, build/start the `docking` profile. For ET-Flow, first resolve the upstream Git commit and confirm checkpoint-use rights; then set `ETFLOW_GIT_COMMIT` to that immutable commit and build/start the separate `etflow` profile. ET-Flow cloud compatibility and checkpoint validation are not implied by a successful container build.

Observe startup and readiness:

```bash
docker compose ps
docker compose logs --tail=100 api cpu-worker gpu-worker
curl --fail http://127.0.0.1:8000/health
```

Only include `gpu-worker` in the logs command when its profile is running. `/health` reports framework/GPU detection but is not a scientific evaluation.

## 5. Submit and inspect a job

Replace the example disease ID with an approved Open Targets ID:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8000/targets \
  -H 'Content-Type: application/json' \
  -d '{"disease_id":"MONDO_0005233","limit":25}'
```

The `202` response gives `job_id` and `status_url`. Poll without holding the submission request open:

```bash
curl --fail http://127.0.0.1:8000/jobs/<job-id>
curl --fail http://127.0.0.1:8000/jobs/<job-id>/results
```

Do not submit training/generation/docking claims until target-data and scientific gates are resolved. `/optimize` currently produces a truthful `blocked` GraphFDM result. Generation can execute GP-MoLFormer if the pinned checkpoint can be resolved, but the result declares that it is not target-conditioned. Docking requires pre-prepared PDBQT artifacts and is explicitly unvalidated.

## 6. Record and operate

- Record all image digests, package locks, source revision, worker capability output, model/checkpoint hashes and dataset/split hashes.
- Confirm worker heartbeats and queue consumption using `GET /jobs/{id}` logs/status.
- Back up the SQLite state and artifact volumes; confirm S3 object lifecycle/versioning if selected.
- Monitor GPU memory/disk. The first model pull and Hugging Face cache are outside the image and require egress/storage.
- Stop a profile with `docker compose --profile gpu down`; do not remove volumes unless intentionally deleting data.
- Before multiple hosts, migrate SQLite queue state to a transactional managed DB/broker and point artifacts at durable object storage.

## Acceptance boundary

Container build, health, queue ingestion, status, artifacts and GPU visibility can establish deployment readiness only. They do not pass target ranking, assay-data, target conditioning, ET-Flow license, GraphFDM/RL, affinity, ADMET/OOD, docking preparation, or scientific-evaluation gates listed in `CLOUD_READINESS_REPORT.md`.
