# Model Artifact Registry

The machine-readable source of model availability is [`../../model_registry.example.json`](../../model_registry.example.json). Copy it to the configured registry path and add concrete artifact paths/checksums only when the file is available and its license is recorded. `ModelArtifactRegistry.resolve()` requires `availability=available`, a local artifact path, and a matching SHA-256 when supplied; otherwise it raises `CheckpointUnavailable`. It never falls back.

| Component | Source/checkpoint | Environment | Current status |
|---|---|---|---|
| GP-MoLFormer-Uniq | Hugging Face model and tokenizer revisions are pinned in the example registry | Main GPU image or CPU; HF cache mounted | Unconditional/scaffold-prompt generation only; explicit protein/pocket conditioning requires a compatible implementation, data, and a trained/evaluated checkpoint. |
| ET-Flow `drugs-o3` | Upstream ETFlow; checkpoint on Zenodo record 14226681 | Separate Linux/Python 3.10/CUDA 12.1/PyTorch/PyG image | Cloud toolchain/checkpoint execution unverified; published checkpoint rights are unresolved in project blocker record. Do not use until cleared. |
| Temporal relational GNN | Source implementation in repository; no fitted artifact | Main GPU | Architecture code exists; disease-specific leakage-controlled benchmark and training checkpoint do not. |
| Target GFM | ULTRA is the primary candidate for assessment; exact artifact still requires provenance/license review | Model-specific | BLOCKED until the exact artifact, biomedical coverage, identifier mapping, and leakage-resistant benchmark pass. Do not substitute the temporal GNN or TxGNN. |
| GraphFDM | Approved primary optimizer, no compatible exact implementation/checkpoint | Main GPU once resolved | BLOCKED; worker preserves blocker. |
| RL | Separate Pareto baseline, no training artifact | Main GPU once resolved | BLOCKED; not GraphFDM replacement. |
| Protein-ligand cross-attention | Source architecture, no trained checkpoint | Main GPU | BLOCKED on sufficient assay/protein/ligand data, split, training and calibration. |
| ADMET/synthetic feasibility/OOD | No validated calibrated model selection | Per-model runtime after selection | BLOCKED; no invented toxicity limits or output scores. |
| AutoDock Vina | External official Vina release; executable not checked into Git | CPU | The adapter is tested; validated receptor prep, binding site and docking protocol remain BLOCKED. |

## Registration requirements

Every concrete model artifact record must include model/version, upstream source and immutable identifier, checkpoint SHA-256, download/cache location, framework/Python/CUDA/PyG matrix, license and license evidence, dataset/training split hashes where applicable, and status (`available`, `remote-pinned`, `untrained`, or `blocked`). Record resolved container image digest and lockfile alongside the model record. Do not check large weights into Git or embed them in Docker build contexts.
