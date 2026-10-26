# Model feasibility and execution status

This document describes model interfaces and evidence available in the repository. Estimates are planning ranges, not measured benchmarks, unless explicitly labeled as a local smoke result. No model is considered scientifically validated because its code or adapter exists.

## Target prioritization and retrieval

| Component | Intended role | Current state and gate |
|---|---|---|
| ULTRA | Primary GFM candidate for disease-to-target link prediction | Existing GFM interface fails closed when no implementation/checkpoint is registered. ULTRA is the selected candidate for assessment, not a validated biomedical model. Its exact artifact provenance/licensing, biomedical coverage, identifier mapping and leakage-resistant benchmark must pass before producing rankings. BioMedKG is rejected; TxGNN is not a substitute. |
| Temporal relational GNN | Dynamic/temporal GNN component | Architecture and temporal snapshot utilities exist; no scientific training/evaluation checkpoint exists. It remains distinct from the GFM. |
| Graph + vector retrieval | Evidence and literature retrieval | A local vector-store interface exists. No validated biomedical embedding corpus, licensed literature index or retrieval evaluation is included. |
| LLM/RAG | Optional evidence synthesis | No provider/model/checkpoint is configured. Keep disabled until a compatible licensed model, privacy boundary and citation/evaluation plan are available. Retrieval results must retain source citations. |

## Molecular generation and geometry

| Component | Requirements and approximate resources | Current state and gate |
|---|---|---|
| GP-MoLFormer-Uniq | Pinned Transformers model/tokenizer; approximately 374 MB weights/tokenizer on disk. The prior local smoke used about 217 MiB peak allocated VRAM for small-batch unconditional inference; this is not a training estimate. | Unconditional and scaffold-prompt inference are implemented. No protein/pocket conditioning exists in the available checkpoint. Explicit protein/pocket conditioning needs paired data, implementation, training and evaluation. Do not use target ID as the sole condition. |
| Scaffold/fragment conditioning | Base generator plus validated constrained decoding or fine-tuned artifact; additional model/storage needs are not yet measured. | Scaffold prompts are checked after generation; arbitrary fragment control remains unsupported. Unsupported constraints must fail explicitly. |
| ET-Flow | Upstream Linux/CUDA/PyTorch/PyG toolchain and `drugs-o3` checkpoint. Exact checkpoint size and inference VRAM have not been verified here; reserve multiple GB for environment/cache until measured. | Adapter and separate container definition exist. Checkpoint-use rights and runtime/geometry evaluation remain blocked. ET-Flow supplies conformers for an existing molecular graph; it is not joint graph/3D topology generation. |

## Optimization and property models

| Component | Intended role | Current state and gate |
|---|---|---|
| GraphFDM | Primary multi-objective molecular optimizer | Separate disease-specific Pareto objective definitions and a fail-closed adapter exist. No verified compatible implementation/checkpoint or paper-consistent reproduction is available. Keep optimization blocked. |
| RL | Explicitly labeled baseline | It remains separate from GraphFDM and cannot replace it. No validated policy, reward model or training result is included. |
| ADMET/toxicity | Endpoint-specific prediction objectives | No licensed model suite, calibrated endpoints, external validation or supported hard thresholds are established. Do not invent toxicity limits. |
| Synthetic feasibility | Route/feasibility objective | SA score can be computed as a heuristic; it is not a validated synthesis-route predictor. A validated route model and evaluation data are not selected. |
| Uncertainty/OOD | Calibration and out-of-domain penalty | Evaluation interfaces exist, but calibrated predictors and held-out validation data are absent. Do not emit calibrated uncertainty or validated OOD claims. |

## Affinity and docking

| Component | Requirements | Current state and gate |
|---|---|---|
| Protein–ligand cross-attention | Curated/licensed complex-affinity data, leakage-resistant protein/ligand splits, trained weights and calibration | Architecture and synthetic tensor/loss tests exist; there is no trained checkpoint or validated affinity prediction. Ligand-only XGBoost remains a separately labeled baseline. |
| AutoDock Vina | External compatible executable; prepared receptor/ligand PDBQT, binding site and documented parameters | The adapter and result capture are tested. Vina is not vendored. Receptor/ligand preparation and retrospective protocol validation are incomplete. Scores are hypotheses, not measured affinity. |

## Compute boundary

Local testing and small inference smoke checks do not establish training capacity. The approved zero-cost policy prohibits AWS GPU use and paid GPU fallback. Heavy GPU work must wait for scientifically ready data/checkpoints and run only on local hardware if feasible or an explicitly authorized no-cost external GPU session. Free external sessions are temporary; the repository currently has no remote claim/lease/result-upload runner.

## Shared scientific gates

Before training or candidate ranking, each disease needs selected targets, sufficient target-specific activity data, endpoint-stratified quality review, leakage-resistant frozen splits, licensed model artifacts, and validated predictors. The full data and assay rules are in [DATASET_SPEC.md](DATASET_SPEC.md); approved objective definitions are in [OPTIMIZATION_POLICY.md](OPTIMIZATION_POLICY.md).
