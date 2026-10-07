# Satori Drug Discovery Platform

Satori is a modular research pipeline for target prioritization, ligand processing, molecular generation, optimization, triage, affinity prediction and docking. Its outputs are computational hypotheses, not experimental or clinical claims.

## Environment

The development machine runs Python 3.13.1 and has an NVIDIA RTX 3050 Laptop GPU (6 GB VRAM); the updated C: budget was approximately 40 GB free at Phase 0. The project `.venv` contains RDKit 2026.3.6, NumPy 2.5.3, Pillow 12.3.0, PyTorch 2.14.1+cu130, Transformers 4.51.3, Safetensors and Tokenizers. The pinned GP-MoLFormer model/tokenizer are cached locally. ET-Flow's Linux/CUDA 12.1 toolchain remains separate and cloud-required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Three-disease target ingestion

The example configuration contains NSCLC, Alzheimer disease, and type 2 diabetes mellitus. Ingestion writes separate disease datasets and manifests:

```powershell
$env:PYTHONPATH = "src"
python -m satori.cli ingest-targets --config config.example.json --output-dir data/raw/open-targets
```

Raw JSON API responses are cached under `data/raw/http-cache` and can be replayed offline by the source-client API. Dataset outputs use deterministic JSONL serialization and SHA-256 manifests. Per-source failures are explicit. External API access and model weight downloads require network access. Never put credentials in tracked configuration.

## Capabilities and scientific status

- Versioned target, evidence, ligand and candidate records; atomic datasets; dataset and split manifests.
- Open Targets disease-to-target, UniProt, ChEMBL and RCSB PDB adapters.
- RDKit molecule standardization, deterministic duplicate handling and explicit rejection reasons.
- Time-aware relational graph attention and recurrent temporal architecture, revision-pinned GP-MoLFormer local inference, ET-Flow conformer adapter, GraphFDM blocker boundary, auditable chemistry triage and Pareto-front selection, cross-attention affinity architecture, XGBoost ligand-only baseline, Vina execution boundary, split utilities and evaluation metrics.

The verified GP-MoLFormer base is unconditional; scaffold prompting is recorded and the returned structures are explicitly checked for scaffold retention. The base is not target/pocket conditioned, fragment constraints are blocked, and the ET-Flow stage has not run locally. See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for phase gates and scientific blockers.

An adapter or architecture is not evidence that a model has been downloaded, trained, validated, or evaluated. Exact model blockers and phase status are tracked in `IMPLEMENTATION_STATUS.md` and `MODEL_FEASIBILITY.md`. Training and candidate generation require validated, provenance-preserving data and explicit assay/split policies.

## Cloud runtime preparation

Cloud deployment scaffolding is in [CLOUD_ARCHITECTURE.md](CLOUD_ARCHITECTURE.md), with the reference procedure in [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md). It provides FastAPI job submission, a single-host durable SQLite queue, CPU/GPU/ET-Flow/docking worker images, local/S3 artifacts, vector-store interfaces, and an explicit model registry. Containers are Linux-only build targets and do not require Docker on the development machine.

The API runtime is an optional extra: `pip install -e ".[cloud-api]"`. Start locally for development with `uvicorn satori.api:app --host 127.0.0.1 --port 8000`; start a CPU worker with `python -m satori.worker` and `SATORI_WORKER_QUEUE=cpu`. For production, follow the private-network/security steps in `CLOUD_DEPLOYMENT.md`. SQLite is single-host only. No scientific component is upgraded to complete by the existence of an endpoint/worker.
