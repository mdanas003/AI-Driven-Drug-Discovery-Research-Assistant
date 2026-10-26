# Project status

**Last verified local test suite:** 58 tests passed; Python compilation and dependency consistency checks passed.  
**Public deployment:** none.  
**Scientific training:** no large-scale training or candidate optimization is claimed.

## Implemented and locally tested

- Provenance-aware target/evidence and assay records, ChEMBL retrieval contracts, deterministic chemistry standardization, rejection reasons, and split manifest utilities.
- Time-aware relational and temporal graph model implementations, plus an explicit adapter boundary for a pretrained GFM. These architectures are not trained or scientifically benchmarked.
- Revision-pinned unconditional GP-MoLFormer inference path with output validation and scaffold checks. It does not perform protein/pocket conditioning.
- Disease-scoped separate Pareto objectives, GraphFDM adapter/blocker, affinity cross-attention architecture, explicit ligand-only baseline, Vina execution boundary, and auditable pipeline status handling.
- Authenticated asynchronous API/job contracts, single-host SQLite queue, worker separation, model registry and local/S3 artifact interfaces.

## Scientific blockers

- Disease-specific ChEMBL retrieval is incomplete or truncated; targets, assay endpoints, potency distributions and leakage-resistant splits are not ready for training.
- ULTRA remains the primary GFM candidate behind the adapter, but its biomedical data coverage, artifact provenance/licensing, identifier mapping and leakage-resistant benchmark gates have not passed. BioMedKG is rejected; TxGNN is not a fallback.
- Protein/pocket-conditioned GP-MoLFormer requires a valid conditioning implementation, paired data, and a trained/evaluated checkpoint.
- ET-Flow execution is blocked pending checkpoint-use rights and compatible runtime validation.
- GraphFDM is the primary optimizer, but there is no verified implementation/checkpoint or paper-consistent reproduction. RL remains a separate baseline.
- Endpoint-specific ADMET, synthesis feasibility and calibrated OOD predictors are not selected and validated.
- The protein–ligand affinity model has no curated licensed dataset, frozen leakage-resistant split, trained checkpoint, or calibration/evaluation.
- Docking structure preparation and protocol validation are incomplete; Vina scores are not measured affinity.

## Deployment blockers

- No AWS account eligibility, plan, usage quota, or region was verified. The AWS resource allowlist is empty and no resources were created.
- No public API/frontend is deployed. SQLite remains single-host. There is no external GPU claim/lease/heartbeat/upload protocol.
- AWS GPU workers are prohibited by the zero-cost policy. Heavy scientific GPU work requires local execution where feasible or separately authorized no-cost external GPU capacity; no paid fallback is permitted.

Scientific policies and datasets are specified in [`science/`](science/). Zero-cost deployment constraints are in [`deployment/ZERO_COST_DEPLOYMENT.md`](deployment/ZERO_COST_DEPLOYMENT.md).
