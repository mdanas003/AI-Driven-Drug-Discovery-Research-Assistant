# Phase 0 Decision Report

**Date:** 2026-10-02  
**Decision scope:** Environment and feasibility only. No training, large model/data download, cloud provisioning, or implementation change to scientific model behavior.

## Resolved by the user

- Disease set is fixed; no further disease choice is needed: NSCLC, Alzheimer disease, and type 2 diabetes mellitus.
- Machine storage budget is now approximately 40 GB free; the latest audit measured 49,359,675,392 bytes free on C: (~46.0 GiB). The old 3.49 GB limit is retired.
- RTX 3050 with 6 GB VRAM remains the local GPU. Treat local machine as development/integration; use cloud GPU for heavy model training and inference workloads.
- Preserve the approved advanced components. Baselines stay separate and explicitly named.

## Phase 0 decisions applied

1. Disease configuration now contains three MONDO IDs: NSCLC `MONDO_0005233`, Alzheimer disease `MONDO_0004975`, and type 2 diabetes mellitus `MONDO_0005148`. The ontology mappings distinguish type 2 diabetes from broad diabetes and NSCLC from small-cell lung cancer. The IDs are recorded in `config.example.json`.
2. Data orchestration must execute disease-specific runs and retain one shared provenance-aware evidence graph. Keep each disease's labels, assay contexts, and evaluation partitions separable; cross-disease sharing is a later explicitly evaluated multi-task option, not implicit pooling. The example config now lists all three diseases, but current CLI commands accept a single `disease_id` per invocation; multi-disease iteration/orchestration remains implementation work and is not claimed as operational support yet.
3. Local foundation is a project `.venv` with RDKit 2026.3.6, NumPy 2.5.3, and Pillow 12.3.0. This passed import and trivial SMILES-parse smoke checks.
4. Do not install local PyTorch/CUDA or model-specific libraries until their resolved download closure and platform-specific extensions are sized and checked. The official PyTorch CUDA 13 wheel exists for CPython 3.13/Windows; ETFlow's upstream dependencies point to an isolated CUDA 12.1 Linux environment.
5. Do not start expensive training or bulk data ingestion in Phase 0. Establish dataset versions, licensing, endpoint coverage, target/assay policy and splits first.

## Status by requested label

- **READY:** host audit complete; local core Python/RDKit/NumPy environment established and verified; three-disease configuration represented; advanced architecture constraints documented.
- **CLOUD_REQUIRED:** serious training/fine-tuning for the GFM, GraphFDM (once specified), ETFlow model work, protein–ligand cross-attention, target-conditioned generator and larger LLM/RAG workloads. This is a deployment class, not a statement that cloud resources are provisioned.
- **BLOCKED:** exact GFM artifact, GraphFDM specification/artifact, ETFlow native Windows/Python 3.13 support, target-conditioned GP-MoLFormer capability/checkpoint, ADMET/synthesis predictor choices, trained affinity model/data, complete docking preparation, and validated/calibrated evaluation sets are absent or unresolved.
- **USER_DECISION_REQUIRED:** choose an LLM/provider and its license/privacy/evaluation policy before enabling LLM-backed RAG; choose/approve benchmark, activity/assay inclusion, negative sampling, leakage split, chemical standardization and triage thresholds before training or scientific candidate claims. These are required later-phase decisions, not blockers for the environment audit.

## Contradictions and unresolved technical decisions

- The project references “GFM” target prioritization but currently supplies a custom relational graph attention network with no foundation checkpoint. The latter is not equivalent to a pretrained graph foundation model.
- The stated “joint graph/3D generation” ambition is not met by the current GP-MoLFormer → ETFlow chain: GP-MoLFormer generates molecular strings/scaffolds while ETFlow generates conformers for an already specified molecule graph. A compatible joint topology-and-coordinate method/checkpoint remains unspecified.
- The selected GP-MoLFormer base is not target/pocket conditioned. The contract must retain a blocked target-conditioned path until a conditioning/fine-tuning method and data are validated.
- “GraphFDM” does not resolve to a specified objective, implementation, constraints, or checkpoint. RL can be developed only as a separately labeled baseline, never as its replacement.
- The architecture's support for three diseases is a pipeline requirement, not evidence of three usable chemical benchmark sets. Target association evidence and drug/assay activity evidence have different meanings; disease target association alone does not supply target-ligand labels.
- Exact target ranking benchmark/split, affinity assay/unit inclusion, negative sampling, chemical standardization and triage thresholds remain unresolved and gate valid training/evaluation.

## Next sequence

1. Inspect/validate live data endpoint mappings and disease evidence counts for the three configured IDs; capture source release/date and license metadata.
2. Specify label/assay inclusion, standardization, negative sampling, target-disjoint/scaffold/temporal split policies, and per-disease evaluation benchmarks before training.
3. Resolve PyTorch CUDA wheel dependency sizes; install it as a separate local GPU group only if useful for integration, then verify GPU visibility and bounded-memory behavior.
4. Select cloud GPU/runtime and build a separate locked Linux environment for ETFlow/PyG and training. Do not silently alter the approved model contracts to fit the local environment.
5. Resolve exact GFM and GraphFDM references, ADMET/synthesis models, RAG provider/model, and affinity dataset/checkpoint plan. Keep unresolved modules visibly blocked until evidence closes each blocker.

No additional user decision is needed to continue the environment/data feasibility work. The decisions listed above are only needed before their dependent scientific/model steps. This report does not approve training or candidate generation; implementation and expensive runs remain gated on the user's earlier approval requirement for the plan and on the listed data/model prerequisites.

## Current implementation-phase status (2026-10-02)

The implementation request is approved and active. Phase 1–3 data/context work is complete for contracts and smoke datasets. GP-MoLFormer base inference is now verified locally, but its outputs are unconditional; target/pocket conditioning is still **BLOCKED — USER DECISION REQUIRED** for the conditioning/fine-tuning method and still requires compatible training data/compute. ET-Flow execution and advanced training are **CLOUD_REQUIRED**. Phase 5 GraphFDM/RL optimization is blocked pending an identified GraphFDM implementation/checkpoint and approved multi-objective reward/endpoints. Phase 6 scientific affinity and docking remain blocked pending training data/checkpoint and validated receptor/ligand preparation. These are component blockers; baseline/interfaces remain explicitly distinct.

Phases 5–7 executable contracts and tests now exist. API/UI/container deployment in Phase 8 remains **BLOCKED — USER DECISION REQUIRED** because the approved phase plan calls its scope unresolved; Docker engine is also unavailable. No expensive scientific training or efficacy claim has been made.
