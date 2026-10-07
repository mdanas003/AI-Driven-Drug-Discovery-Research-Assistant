# Dependency Matrix — Phase 0

Classification describes intended deployment. A package in the matrix is not installed unless marked **installed**. Keep each optional or GPU toolchain in a separate extra/environment so unsupported compiled dependencies cannot destabilize the core environment.

| Class | Components | Status / platform notes |
|---|---|---|
| **LOCAL-CORE** | CPython 3.13; stdlib HTTP/JSON/hashlib; RDKit 2026.3.6; NumPy 2.5.3; Pillow 12.3.0 | Installed in repo `.venv`; Windows CPython 3.13 wheels resolved. Suitable for chemistry/data ingestion and CPU preprocessing. |
| **LOCAL-GPU** | PyTorch 2.14.1+cu130; Transformers 4.51.3; Safetensors 0.8.0; Tokenizers 0.21.4 | Installed and verified on RTX 3050 CUDA. GP-MoLFormer pinned inference completed successfully. PyG custom ops remain uninstalled due separate compatibility risk. 6 GB VRAM supports bounded inference and small experiments, not large-scale training. |
| **CLOUD-GPU** | Linux/Python 3.11–3.12; pinned PyTorch/CUDA; PyG/torch-cluster; ETFlow; GFM/GraphFDM training; cross-attention affinity training; target-conditioned molecular fine-tuning | Preferred environment for large generation, fine-tuning and training. ETFlow's upstream environment uses PyTorch/CUDA 12.1 and NumPy 1.26.4; isolate it from the local Python 3.13 environment. Use a locked, reproducible cloud image once provider and GPU are chosen. |
| **OPTIONAL** | sentence-transformers + local MiniLM; FAISS/vector DB; XGBoost baseline; Vina 1.2.7; Meeko/protein preparation; scikit-learn metrics; LLM/RAG provider | Official Vina Windows x86-64 executable (1,233,920 bytes) is in `tools/vina`; version verified. Engine available locally, but scientific use awaits validated PDBQT preparation and binding-site protocol. No selected LLM or vector index is installed. |
| **BLOCKED** | Exact GFM checkpoint; GraphFDM implementation/checkpoint; target-conditioned GP-MoLFormer training recipe/checkpoint; local ETFlow native Windows/Py3.13 toolchain; validated ADMET/synthesis models; protein–ligand trained checkpoint; disease-specific benchmark and assay/split policy | Missing artifact, unresolved package/platform compatibility, or absent validated data/training specification. Preserve plugin contracts; do not substitute a simpler model and claim equivalence. |

## Size/compatibility checkpoints

- RDKit official PyPI currently provides a CPython 3.13 Windows x86-64 wheel (25.0 MB); installed with NumPy and Pillow as the only base scientific dependencies. [RDKit PyPI](https://pypi.org/project/rdkit/)
- PyTorch CUDA 13.0 closure was installed and verified: the PyTorch wheel was approximately 1,991 MB; CUDA runtime imports and live RTX inference succeeded. [PyTorch CUDA 13.0 wheel index](https://download.pytorch.org/whl/cu130/torch/)
- ETFlow upstream environment pins Python-compatible scientific versions and CUDA 12.1; upstream package metadata does not establish Python 3.13 Windows support. Keep ETFlow in Linux cloud environment unless a dedicated compatibility validation proves otherwise. [ETFlow environment](https://github.com/shenoynikhil/ETFlow/blob/main/env.yml), [ETFlow package metadata](https://github.com/shenoynikhil/ETFlow/blob/main/pyproject.toml)
- AutoDock Vina has upstream Windows releases, but installing the engine alone does not provide receptor/ligand preparation, binding-site selection, or validated docking. [Vina v1.2.7 release](https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7)

## Install sequence

1. **Done:** isolated `.venv`, RDKit + NumPy + Pillow; imports and trivial SMILES parse verified.
2. **Done:** installed PyTorch CUDA 13.0 and Transformers stack; verified real pinned GP-MoLFormer inference.
3. Install retrieval, docking, PyG, and model-specific packages only when their contracts/data are ready; separate incompatible environments.
4. Build cloud lock/container for ETFlow and expensive training after cloud GPU selection; no cloud resources are provisioned in Phase 0.
