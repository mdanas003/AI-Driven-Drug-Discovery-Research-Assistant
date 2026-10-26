# Satori

Satori is a provenance-first research codebase for disease-target evidence, molecular design, multi-objective optimization, affinity modeling, and docking. Its outputs are research hypotheses, not experimental or clinical evidence.

## Project status

This repository is a local research prototype. It is **not deployed publicly**. Several advanced scientific stages remain blocked by incomplete target-specific data, model/checkpoint availability or rights, and missing validation protocols. An implemented interface or baseline is not evidence that a scientific model is trained or validated. See [current scientific status](docs/PROJECT_STATUS.md).

The approved disease contexts are NSCLC, Alzheimer’s disease, and type 2 diabetes mellitus. The approved architecture remains intact: explicit protein/pocket conditioning for target-conditioned generation, ULTRA assessment behind the GFM interface, GraphFDM as primary optimizer, RL as a separately reported baseline, and separate Pareto objectives.

## Quick start

Requires Python 3.11–3.13. Create an isolated environment and install the project’s chemistry and API extras:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[chemistry,ml,cloud-api,cloud-test]"
```

Run the tests:

```powershell
python -m unittest discover -s tests -v
```

The optional dependencies are separated in `pyproject.toml`; the pinned worker environments are under `requirements/`. GPU/model dependencies are not installed by the quick-start command.

## Target evidence ingestion

The sample configuration includes the three approved disease identifiers. For a live Open Targets retrieval, install the package in the project environment and run:

```powershell
$env:PYTHONPATH = "src"
python -m satori.cli ingest-targets --config config.example.json --output-dir data/raw/open-targets
```

Outputs and HTTP response caches go under `data/`, which is ignored by Git. Review the target-specific data policy before using retrieved records for training. Live data retrieval does not select a final target or establish training readiness.

## Local API development

Set a non-empty `SATORI_API_TOKEN` in the process environment, then run:

```powershell
$env:SATORI_API_TOKEN = "<local-development-token>"
uvicorn satori.api:app --host 127.0.0.1 --port 8000
```

`GET /health` is unauthenticated and reports service capabilities. Job submission and job/result retrieval require a Bearer token. The API queues work; a separate worker must be running. SQLite is single-host only. Do not expose this prototype directly to the public internet.

## Repository map

- `src/satori/` — data, chemistry, target, generation, optimization, affinity, docking, provenance, API, and worker modules.
- `tests/` — unit and contract tests; tests do not claim scientific model validation.
- `tools/` — data retrieval utilities.
- `requirements/` — pinned runtime dependency groups.
- `docs/` — architecture, scientific policies/status, development, deployment, and external-GPU notes.
- `Dockerfile.*` and `docker-compose.yml` — optional Linux deployment definitions; no AWS resources or public service are deployed.

## Key documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Scientific status and blockers](docs/PROJECT_STATUS.md)
- [Data specification](docs/science/DATASET_SPEC.md)
- [Optimization policy](docs/science/OPTIMIZATION_POLICY.md)
- [Model feasibility](docs/science/MODEL_FEASIBILITY.md)
- [Zero-cost deployment status](docs/deployment/ZERO_COST_DEPLOYMENT.md)
- [External GPU execution boundary](docs/deployment/EXTERNAL_GPU.md)
- [Development and dependency groups](docs/development/DEPENDENCIES.md)

## Scientific integrity

No model result, checkpoint, or evaluation metric is inferred from an adapter, placeholder, or smoke test. Blocked stages must stay blocked; baseline outputs must remain labeled as baselines. See the disease-specific objective and assay policy before proposing candidates.
