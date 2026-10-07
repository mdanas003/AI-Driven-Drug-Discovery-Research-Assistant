# Development and dependency groups

Satori keeps optional stacks separate so a basic installation does not download CUDA frameworks or large model dependencies.

## Supported Python

The package declares Python `>=3.11,<3.14`. Use a virtual environment. The machine-specific environment audit was intentionally removed from the public project docs; hardware availability is not a project guarantee.

## Optional extras

| Extra | Purpose |
|---|---|
| `chemistry` | RDKit molecular parsing and descriptors |
| `ml` | PyTorch and NumPy graph/model components |
| `generation` | Transformers-based molecular generation |
| `etflow` | ET-Flow integration; separate upstream-compatible environment required |
| `affinity` | PyTorch affinity architecture and Biopython utilities |
| `retrieval` | Sentence-transformers retrieval components |
| `baseline` | Explicitly labeled ligand-only XGBoost baseline |
| AutoDock Vina | External executable; install separately and provide through configuration or `PATH` |
| `cloud-api` | FastAPI and Uvicorn |
| `cloud-storage` | Optional S3 adapter |
| `cloud-test` | HTTP client for API tests |

Pinned environment lists are in `requirements/`. The ET-Flow environment is isolated from the general GPU environment because its upstream Python, CUDA, PyTorch and PyG requirements differ.

## Install and test

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[chemistry,ml,cloud-api,cloud-test]"
python -m unittest discover -s tests -v
```

Add only the optional groups needed for a specific task. Do not install or download checkpoints as part of the basic test setup. GPU checkpoints and training dependencies require their own licensing, compatibility, size and evaluation gate.

## Local API

Set `SATORI_API_TOKEN` through the process environment, then run the API with Uvicorn. The worker uses the same runtime configuration; `SATORI_WORKER_QUEUE` selects `cpu`, `gpu`, `etflow`, or `docking`. The API token must not be committed or included in job JSON.
