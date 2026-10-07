# Implementation Status

**As of:** 2026-10-02  
**State:** Phases 1–3 complete for data contracts and target/ligand context. Phase 4 has real pinned GP-MoLFormer inference on the RTX 3050; full exit remains blocked on ET-Flow execution and target-conditioned training. Phase 5 foundations are implemented; scientific optimization remains blocked on selected objective/reward models and artifacts.

## Current status

- Machine profile, disk budget, Python/GPU versions, and Windows/WSL/Docker availability are recorded in [ENVIRONMENT_AUDIT.md](ENVIRONMENT_AUDIT.md).
- Local core is installed in `.venv`: Python 3.13, RDKit 2026.3.6, NumPy 2.5.3, Pillow 12.3.0, PyTorch 2.14.1+cu130, Transformers 4.51.3, Safetensors 0.8.0 and Tokenizers 0.21.4. CUDA imports and live RTX execution were verified.
- The example configuration names all three selected diseases: NSCLC (`MONDO_0005233`), Alzheimer disease (`MONDO_0004975`), and type 2 diabetes mellitus (`MONDO_0005148`).
- Package groupings and size/platform constraints are in [DEPENDENCY_MATRIX.md](DEPENDENCY_MATRIX.md); per-model blockers and local/cloud fit are in [MODEL_FEASIBILITY.md](MODEL_FEASIBILITY.md).
- Required follow-up choices and staged recommendations are in [DECISION_REPORT.md](DECISION_REPORT.md).
- Open Targets live smoke ingestion completed at limit 3 for each disease: 3 target records per disease, each with a dataset manifest and deterministic content hash. Raw API responses are cached in `data/raw/http-cache`.
- Phase 1 includes exact raw JSON cache replay, retry classification, activity policy decisions, molecule rejection reporting, atomic JSONL/manifests, explicit split manifests, RCSB coordinate hashes, and per-disease config-driven ingestion.
- Phase 1 verification: 13 unit/fixture tests passed; compileall and CLI help succeeded; live three-disease API smoke pull succeeded.
- Phase 2: time-aware relational attention GNN + recurrent temporal snapshots implemented and CUDA-smoke-tested. Exact GFM remains blocked; no biological ranking fit/evaluation because benchmark and split policy are unresolved.
- Phase 3: live contexts resolved for EGFR, APP and KCNJ11; 30 ChEMBL raw activity rows retained and standardized with duplicate rows flagged, not discarded. No assay policy applied.
- Phase 4: revision-pinned IBM GP-MoLFormer-Uniq and tokenizer downloaded (about 374 MB combined). Real local CUDA inference returned 4/4 valid strings in an unconditional smoke; peak allocated VRAM ~217 MiB. Separate scaffold-prompt smoke returned 3/4 valid and 3/4 with the requested phenyl substructure. Invalid generations are preserved and flagged. This is not target-conditioned generation. Fragment control and protein/pocket conditioning remain blocked; ET-Flow is not installed/run on Windows/Python 3.13 and requires its separate compatible cloud toolchain.
- Phase 5: exact Pareto-front utility and auditable deterministic triage are available. GraphFDM and RL remain distinct; optimization is not run because reward endpoints, model/checkpoint choices and training data are unresolved. ADMET/synthesis/OOD predictions are not available.
- Phase 6: protein–ligand cross-attention forward/loss/uncertainty tensor contract verified with synthetic fixtures; no trained checkpoint or real prediction. Official Vina 1.2.7 Windows executable installed (1.23 MB), SHA-256 recorded, and version verified. Valid docking remains blocked on receptor/ligand preparation, binding pocket and protocol.
- Phase 7: restart-inspectable orchestration records run/config/code/runtime/stage status, retains completed stage results on explicit blockers, and passes fixture tests. No end-to-end scientific run is claimed.
- Phase 8: cloud-readiness infrastructure is implemented in the separate cloud API, SQLite job ledger, worker queues, artifact/vector interfaces, model registry and CPU/GPU/ET-Flow/docking Linux image definitions. Local Docker engine is unavailable, so images/cloud/GPU execution remain unverified. Public API authentication, managed multi-host job state, provider IAM/bucket policy and scientific blockers remain deployment gaps. Details are in `CLOUD_READINESS_REPORT.md` and the cloud deployment docs.
- Current test gate: 44 unit/fixture tests across Phases 1–7 pass; compileall passes. The real GP-MoLFormer smoke returned 75% validity, 100% scaffold retention among valid outputs, uniqueness 1.0 in this four-sample set, mean QED 0.268, and scaffold diversity 1.0. Novelty, synthetic accessibility, and 3D validity are explicitly unscored. These small smoke metrics are not scientific efficacy evaluation.

## Architecture status

Existing source contains data-source adapters, provenance/schema utilities, a temporal relational graph model, real GP-MoLFormer inference, ET-Flow conformer adapter, GraphFDM blocker interface, RDKit triage/Pareto utility, protein–ligand cross-attention architecture, XGBoost ligand-only baseline, evaluation utilities, installed Vina engine, and stage orchestration. Presence of an architecture does not mean it has been trained or scientifically validated.

The advanced architecture remains intact. Specifically, the target GFM and GraphFDM lack an exact identified reference/checkpoint; GP-MoLFormer base does not provide target/pocket conditioning; ETFlow is a conformer stage rather than joint graph/3D generation; ADMET/synthesis endpoints and model artifacts are unresolved; and affinity training, calibration, docking preparation and scientific evaluation data are not ready. Details and sources are in the feasibility report.

## Phase 2 status

The custom relational graph attention network and recurrent temporal model are implemented; the exact graph foundation model remains unavailable/unspecified and is not replaced by the custom GNN. A scientific ranking benchmark, negative-sampling policy and leakage split are still required before valid model fitting/evaluation.

## Next work gates

1. Preserve Phase 4's explicit model boundaries; provision a compatible Linux/CUDA cloud environment to execute ET-Flow and any target-conditioned fine-tuning.
2. Establish assay/activity inclusion and leakage-controlled per-disease split/benchmark policies before training or metric claims.
3. Continue implementing the reusable optimization, affinity, docking and orchestration contracts; keep scientific results blocked until their model/data/protocol prerequisites exist.
