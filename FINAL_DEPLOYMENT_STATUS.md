# Final deployment status

> Updated by `AWS_DEPLOYMENT_FINAL.md` and `ZERO_COST_DEPLOYMENT_STATUS.md` on 2026-10-03. AWS deployment remains at zero resources because account eligibility could not be authenticated; no public system or external GPU runner is live.

## READY

- **Local repository verification:** 58 tests passed with `python -m unittest discover -s tests -v`; `python -m compileall -q src tools tests` passed; `python -m pip check` reported no broken requirements.
- **Deployment definitions:** Docker Compose static configuration validated for the default CPU/API services and the GPU, ET-Flow, and docking profiles. This validates configuration parsing only; no image was built or run.
- **API contracts:** authenticated job submission/status/result routes and health response are covered by the passing tests. `SATORI_API_TOKEN` is required for job operations; health exposes capability status without local paths. API remains bound to loopback in Compose.
- **Scientific failure reporting:** worker/job interfaces preserve explicit blocked and failed states, provenance and artifacts. GraphFDM is not replaced by RL; RL remains the baseline. The Pareto objective vector remains separate and disease-scoped.
- **GFM decision applied:** BioMedKG remains rejected. ULTRA is the primary candidate behind the existing GFM adapter contract. The adapter fails closed when no registered implementation/checkpoint is configured; no GFM output is claimed.

## CLOUD_REQUIRED

- **Cloud infrastructure validation:** provision the approved Ubuntu 22.04 `g5.xlarge` reference host (4 vCPU, 16 GiB RAM, A10G), persistent storage, supported NVIDIA driver, Docker Engine, NVIDIA Container Toolkit, and Compose v2. Build the API/CPU worker and GPU worker images, run GPU visibility and health checks, submit/poll jobs, and verify worker heartbeats, persistent artifact hashes, restart behavior, and logs. These steps have not run because this environment has no AWS CLI, credentials, or provisioned host.
- **Secure API exposure:** add TLS termination and public or operator ingress in front of the loopback-bound API, configure DNS/security groups and secret-managed bearer token, then verify authenticated access and health externally. No public endpoint is currently deployed.
- **Object storage, if selected:** configure least-privilege instance role and bucket policy, encryption/versioning/lifecycle, then validate artifact upload/download/hash round-trip. No bucket or cloud identity is configured.
- **Scientific GPU execution, after data gates:** run ULTRA adapter integration and leakage-controlled benchmark; target/pocket-conditioned GP-MoLFormer data preparation and fine-tuning; ET-Flow Linux/CUDA compatibility and inference; GraphFDM paper-consistent reproduction; validated ADMET/synthesis/OOD models; protein–ligand affinity training; and measured end-to-end ranking. Do not start expensive training until each component’s data, checkpoint/license, splits and evaluation protocol are available.

## BLOCKED

- **Disease target data / target selection:** local ChEMBL retrieval is incomplete, with capped/truncated and failed target requests; smoke datasets remain present. There is not yet complete, quality-reviewed assay data for NSCLC, Alzheimer’s disease, or T2D. Consequently target selection, target-specific potency distributions/labels and leakage-resistant activity splits are not ready.
- **ULTRA GFM validation:** ULTRA is task-compatible as a general relational link-prediction candidate and is the primary candidate per the final decision. It has not passed biomedical coverage, input-vocabulary mapping, licensing/provenance for the exact selected artifact, or leakage-resistant disease-to-target benchmark gates. Keep GFM outputs BLOCKED; do not substitute TxGNN or the in-repo temporal GNN.
- **Protein/pocket-conditioned GP-MoLFormer:** the available pinned model is unconditional/scaffold-prompted. Explicit protein/pocket conditioning requires a compatible conditioning implementation, paired target/pocket–ligand training/evaluation data and a trained validated checkpoint; no such checkpoint/result exists.
- **ET-Flow:** source/runtime interface exists, but the selected `drugs-o3` checkpoint’s use rights are not established and Linux/CUDA execution has not been validated. Do not download/use the weights until checkpoint rights are cleared and exact runtime/dependencies are verified.
- **GraphFDM:** primary optimizer interface and separate Pareto objectives exist, but no verified compatible implementation/checkpoint or paper-consistent reproduction is available. Do not report optimization as completed; RL remains a separately labeled baseline.
- **ADMET, synthesis feasibility and calibrated OOD:** no selected licensed endpoint-specific predictor suite, validated thresholds, external validation or calibration set is established. QED/SA/descriptors do not constitute validated toxicity or synthetic-feasibility predictions.
- **Protein–ligand affinity:** no curated/licensed complex-affinity dataset, frozen leakage-resistant split, trained cross-attention checkpoint or calibration/evaluation exists. The architecture contract is not a validated predictor.
- **Docking:** Vina packaging/interface exists, but receptor/ligand preparation, disease-target structures/pockets and a validated docking protocol/benchmark are incomplete. A Vina score cannot be reported as validated affinity.
- **Public-ready frontend and operations:** no deployed frontend, external API endpoint, managed multi-host queue, cancellation, quotas/rate limits, monitoring or recovery drill has been verified. SQLite queue definitions are single-host only.

## USER_ACTION_REQUIRED

- **Enable the cloud stage:** provide an authorized AWS execution context (role/profile or credentials through the approved secure mechanism), region and permission to provision the reference host and persistent resources. No credentials were detected, and no AWS CLI is installed here, so provisioning/deployment could not be performed.
- **Expose the service:** provide or approve the deployment DNS name and ingress/TLS arrangement (for example, a domain and certificate or an operator VPN). Until then, keep the API private. The API token must be injected through cloud secret management and must not be committed or sent in job payloads.
- **ET-Flow checkpoint rights:** obtain written permission or a license covering use of the `drugs-o3` checkpoint. Source-code licensing alone does not establish checkpoint rights.
