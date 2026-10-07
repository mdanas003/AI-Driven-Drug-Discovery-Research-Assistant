# Satori AI Drug Discovery Platform — Implementation Plan

**Status:** User has authorized implementation of the approved scientific architecture; implementation is underway.  
**Basis:** `01_PROJECT_SPEC.md` through `07_CODEX_PLAN_PROMPT.md` in the supplied documentation pack, plus `Satori_AI_Drug_Discovery_Extreme_Implementation_Plan.md`.  
**Repository audit:** The workspace contains only `.git` and has no committed files, source tree, dependency manifest, tests, or existing implementation to preserve.

## 1. Objective and MVP

Build a locally runnable system that accepts one disease and emits ranked candidate molecules with target evidence, chemical properties, predicted activity/affinity, uncertainty/OOD status, and docking evidence. Preserve the seven-layer scientific pipeline: target prioritization → ligand data → molecular generation → optimization → triage → affinity prediction → docking.

The system must report computational predictions as such; it does not establish experimental biological validation, clinical efficacy, clinical safety, or therapeutic approval. A module is complete only when it runs, documents its interfaces and errors, has critical-path tests, produces reproducible outputs, and has evaluation where applicable.

**MVP acceptance:** reproducible disease/target and target/ligand ingestion; ranked targets with evidence; molecule generation, optimization and triage; affinity prediction; docking; ranked output with provenance; experiment records; and an end-to-end run on confirmed development hardware. If a required model cannot execute, report it as blocked; an interface or mock is not a functioning scientific component.

## 2. Architecture, repository, and module dependencies

Use a Python package with independently testable scientific modules and adapters around external data sources, heavyweight models, and docking tools. The orchestration layer depends on stable schemas/interfaces, not concrete model implementations. Keep research code separate from orchestration and deployment code. Design versioned inputs/outputs, errors, and provenance so future infrastructure can be added without committing to it in the prototype.

Suggested initial structure (create only as implementation is approved):

```text
README.md, project documentation, IMPLEMENTATION_PLAN.md
pyproject.toml, lockfile, .env.example, .gitignore
configs/                 base and component/experiment configuration
src/satori/schemas/      versioned target, ligand, candidate, run contracts
src/satori/data/         Open Targets, ChEMBL, UniProt, PDB, literature adapters
src/satori/chemistry/    standardization, validation, properties, rejection reasons
src/satori/targets/      graph, ranking, evidence retrieval and RAG adapters
src/satori/generation/   Transformer, conditioning and SE(3) flow adapters
src/satori/optimization/ GraphFDM/constrained flow and RL baseline
src/satori/triage/       chemistry rules, scoring, uncertainty/OOD, Pareto selection
src/satori/affinity/     baseline and protein–ligand model adapters
src/satori/docking/      preparation, Vina execution and pose validation
src/satori/pipeline/     stage orchestration, run state and ranking
src/satori/evaluation/   split creation, metrics and reports
tests/unit, tests/data, tests/models, tests/integration, tests/e2e
data/{raw,interim,processed,splits,structures,graphs,literature}/ (local, ignored)
artifacts/{models,generated,docking,reports}/ (local or configured store)
```

Dependency flow:

```text
config + schemas + provenance
  ├─> source adapters -> target evidence/graph -> target ranking -> TargetContext
  └─> ChEMBL -> deterministic chemistry processing -> versioned ligand datasets
TargetContext + ligand datasets -> generation -> optimization -> triage
triaged candidates + protein/pocket data -> affinity -> docking -> ranking
all stages -> pipeline run state, evaluation, logs and artifacts
```

Storage: begin with versioned local files and explicit manifests/hashes, with paths configurable. Do not introduce PostgreSQL, object storage, vector DB, MLflow server, distributed queues, Kubernetes, Terraform, monitoring, or microservices before need is demonstrated. A literature/vector index, if approved, is distinct from a mandatory production vector database. Database and persistence choices remain extensible behind interfaces.

## 3. Dependencies, data and reproducibility

No dependencies or versions are supplied by the repository. Candidate dependency families, subject to compatibility and license checks before pinning, are Python tooling; RDKit for molecular processing; graph/deep-learning and Transformers libraries; protein/structure and embedding utilities selected with the models; source clients or HTTP adapters for Open Targets, ChEMBL, UniProt, PDB and approved literature sources; Vina-compatible docking; and test, lint, format, type-check and configuration/logging tools. Separate core, ML, docking, API, and development extras where feasible. Verify supported OS, Python, accelerator/CUDA combinations, checkpoints, binary availability, download size, and license before adding dependencies or downloading assets. Lock exact versions after decisions and run a clean-environment installation check.

Data ingestion order:

1. Resolve the chosen disease identifier; collect Open Targets disease–target associations and evidence with source metadata.
2. Normalize target/gene/UniProt cross-references; retrieve UniProt sequence/annotations and available PDB or compatible structure references, chains and pocket information.
3. Build target evidence/graph and rank targets; retain evidence records and literature references. Fetch literature only after the corpus, source rights, retrieval approach, and citation behavior are decided.
4. For selected targets, retrieve ChEMBL compounds, target/assay/activity metadata, units, and pChEMBL where available.
5. Deterministically parse, sanitize, standardize, normalize, deduplicate and apply approved activity-selection rules. Preserve an explicit rejection reason for every rejected record.
6. Create dataset and split manifests before fitting models; train-only transforms are fitted only on training data.

Target records include internal target ID, gene symbol, UniProt ID, disease association, evidence score/source, pathways, structure references and literature references as available. Ligand records include molecule ID, canonical/standardized SMILES, InChI, target ID, assay/activity, units, pChEMBL where available, source and dataset version.

Every dataset records source version/date, processing code version, filter configuration, hash/version, and split seed. Every experiment records code commit, dataset/split versions, model/checkpoint version, full config/hyperparameters, seed, metrics, artifacts, runtime and hardware. Save model/data licenses and checkpoint provenance when applicable. Never report unmeasured performance.

## 4. Phases, exact order, tests, and evaluation

Each phase is gated by its exit criteria. Phase dependencies are sequential as listed; independent adapters within a phase may be developed concurrently after interfaces and user decisions are settled.

### Phase 0 — Decisions and environment audit

1. Resolve the blocked choices in §6 before selecting concrete model/checkpoint dependencies or asserting MVP feasibility.
2. Record OS, Python, CPU, RAM, GPU/VRAM, storage, CUDA/driver availability, Docker availability, network/data access constraints, and allowed training time/budget in a compute profile.
3. Verify candidate dependency/checkpoint availability, compatibility, licenses, storage/download requirements, and docking executable requirements.
4. Define configuration, logging, deterministic seeds, artifact paths, schemas and adapter/error contracts; create lockfile only after stack choices are approved.

**Tests/checks:** clean environment install; config validation; schema serialization/version checks; seed utility determinism; secret scanning/config does not require credentials in source. **Exit:** reproducible environment and feasible resource estimate or explicit blockers.

### Phase 1 — Data and provenance substrate

1. Implement source adapters and cached raw response recording for Open Targets, UniProt, PDB and ChEMBL; add literature only after source policy decision.
2. Normalize target and ligand records with source provenance and schema versions.
3. Implement deterministic molecule processing and rejection-reason reporting.
4. Implement dataset manifests, hashing, versioned outputs and split manifests.

**Tests:** fixture responses; source error/retry behavior; identifier mapping; invalid/sanitization failures; standardization; duplicates; activity filtering; rejection reasons; stable hashes/manifests. **Exit:** repeatable fixture-backed datasets with no silent record loss.

### Phase 2 — Target prioritization and evidence

1. Construct the approved graph schema and evidence records from ingested disease/target data.
2. Implement random and simple evidence/graph baselines.
3. Implement the approved graph foundation/GNN target ranker and benchmark protocol.
4. Add approved graph/vector retrieval, RAG and multi-hop evidence reasoning. Temporal/dynamic graph behavior is gated by the decision in §6.

**Tests:** graph schema and edge provenance; deterministic ranking; evidence traceability; retrieval citation/source linkage; baseline metric calculations; held-out evaluation isolation. **Evaluation:** Recall@K, Precision@K, MRR, Hits@K against random, evidence/simple graph baselines and selected advanced model. **Exit:** reproducible target ranking with supporting evidence and benchmark report.

### Phase 3 — Ligand datasets and protein context

1. Retrieve target-specific ChEMBL activity records and prepare approved train/validation/test partitions.
2. Prepare protein sequence, structures and binding pockets required by approved generation, affinity and docking models.
3. Define a target context object carrying target IDs, sequence/structure/pocket references and evidence; attach embeddings only when the selected components require them.

**Tests:** target/activity linkage, units/assay filters, split disjointness, structure/chain mapping, absent-structure handling, context schema. **Exit:** versioned target datasets and usable protein context or explicit per-target blocker.

### Phase 4 — Molecular generation

1. Implement the selected GP-MoLFormer/Transformer adapter and checkpoint loading.
2. Implement approved target conditioning and scaffold/fragment conditioning.
3. Implement the selected SE(3)-equivariant flow component and define whether it is sequential, coupled or complementary to the Transformer.
4. Validate generated graph/SMILES, valence, duplicates, 3D coordinates and geometry; save generation metadata and model version.

**Tests:** checkpoint/interface errors; conditioning contracts; deterministic seeded sampling where supported; invalid graph/SMILES handling; duplicate and geometry validation; equivariance checks appropriate to the selected model. **Evaluation:** validity, uniqueness, novelty, diversity, QED, SA, property distributions, scaffold diversity and 3D validity. **Exit:** actual selected models execute; adapter-only mocks do not satisfy this phase.

### Phase 5 — Optimization and triage

1. Specify multi-objective rewards and constraint handling from approved objectives.
2. Implement GraphFDM/constrained flow optimization and the RL baseline behind separate adapters.
3. Add deterministic chemistry alerts, QED/Lipinski and SA filters, then approved activity/selectivity, ADMET, synthetic-feasibility and uncertainty/OOD scoring.
4. Add Pareto selection with individual objective values and per-candidate survival/rejection reasons.

**Tests:** reward component calculations; constraints; filter boundaries and rejection reasons; OOD/uncertainty output schema; Pareto dominance and ties; no use of test data in reward/threshold tuning. **Evaluation:** unoptimized vs GraphFDM vs RL; objective improvement, violations, validity, novelty/diversity loss and Pareto size/quality. **Exit:** reproducible candidate funnel with reasons and comparison report.

### Phase 6 — Affinity prediction and docking

1. Implement an approved classical affinity baseline and selected protein–ligand GNN/cross-attention model; do not silently replace the selected research model.
2. Implement protein preparation, pocket/grid configuration, ligand preparation and selected AutoDock Vina-compatible execution.
3. Persist prediction uncertainty/model version, docking score/pose, structure/pocket and preparation metadata, tool version and runtime.

**Tests:** model input/output contracts; train/test molecule, scaffold, temporal and target separation as selected; metric calculations; preparation failures; Vina invocation and version capture; pose validity and failure isolation. **Evaluation:** affinity RMSE, MAE, Pearson/Spearman and concordance index where appropriate under leakage-resistant splits; docking score distributions, pose validity, candidate ranking and predictor agreement/disagreement. **Exit:** held-out report and reproducible docking artifacts. Docking is independent computational evidence, not experimental affinity validation.

### Phase 7 — Orchestration, ranking, integration

1. Integrate stages in pipeline order using versioned contracts.
2. Record run ID, disease, config hash/version, code commit, dataset/model versions, seed, timestamps, stage results and errors.
3. Make stages restartable; persist explicit partial/failed states, including docking failure without corrupting earlier results.
4. Rank candidates while exposing individual evidence/metrics, Pareto status and provenance rather than an unexplained aggregate score.

**Tests:** mocked external/model adapters for deterministic early end-to-end integration; stage order/state transitions/restarts; failure and retry handling; provenance completeness; real-tool smoke path on tiny fixtures when resources are available. **End-to-end measures:** generated, valid, unique, novel, filter survival, affinity/docking/synthetic-feasibility distributions, Pareto candidates, runtime and compute cost. **Exit:** one disease run produces a ranked dataset or a complete explicit blocker report.

### Phase 8 — Deployment and later stages

The original architecture prefers local execution and permits Docker Compose after the scientific pipeline works; the added extreme-plan document requests rapid API/UI and containerized deployment. Keep API/UI/container scope blocked until the user resolves its MVP status. If approved, first expose run submission/status and target/candidate retrieval, then a results view with structures, properties, evidence, uncertainty and clear computational-prediction labeling; package the local vertical pipeline with a single documented launch path. Do not let deployment report scientific components as complete when they are mocks or unavailable.

After a functioning MVP, consider persistent DB/object storage, workflow queues, MLflow, CI/CD, cloud deployment, Kubernetes, Terraform, monitoring, retraining, drift monitoring and multi-disease scaling based on demonstrated requirements.

**Tests if deployment is approved:** API schema/validation and error responses; health/status; pipeline lifecycle; UI result completeness; container clean build and local end-to-end smoke test. **Exit:** deployable local interface reproduces the same versioned pipeline results.

## 5. Risks, failure modes, and mitigations

- **Model/checkpoint uncertainty:** named research directions do not identify exact implementations or weights. Verify availability, terms, interfaces and resource use before integrating; label unavailable execution explicitly.
- **Compute mismatch:** 3D generation, foundation models, optimization and affinity training may exceed local GPU/RAM/time. Profile and estimate before downloads/training; report component-specific resource blockers without silent downgrades.
- **Data quality and provenance:** heterogeneous evidence, assays, units, target mappings and structure chains can mislead ranking. Preserve raw references, normalized values, assay rules and rejection reasons.
- **Leakage:** random splits may inflate results through scaffold, target, temporal or near-duplicate leakage. Choose split per model, document it before tuning, keep test data sealed, and fit learned transforms on training only.
- **Scientific proxy mismatch:** predicted affinity, docking, ADMET and synthetic feasibility are proxies. Expose individual metrics and uncertainty; do not claim efficacy or experimental confirmation.
- **Generation/3D mismatch:** Transformer molecular strings and SE(3) coordinate generation may have incompatible representations or training assumptions. Resolve their composition and validation contract before implementation.
- **RAG evidence quality:** literature access, licensing, temporal scope, citation identity, chunking and retrieval evaluation are unspecified. Preserve source IDs and distinguish retrieved evidence from model inference.
- **External source/tool failure:** network/API limits, schema changes, unavailable PDB structures or docking binaries can interrupt runs. Cache raw inputs, version adapters, make failures explicit and stage-local.
- **Scope and schedule risk:** “same-day” rapid deployment in the added plan is not substantiated by compute, model, data or dependency information. Treat schedule as unestimated until Phase 0 is complete.
- **Overbuilt infrastructure:** API/UI, vector stores and production services can consume effort before scientific feasibility. Gate them on the scope decision and working local pipeline.

Early integration tests can mock external APIs, checkpoints and docking executables, but must label outputs as fixtures/mocks. Mocks validate interfaces and failure handling only; they cannot satisfy scientific MVP acceptance or support performance claims.

## 6. Contradictions and decisions requiring the user

Every unresolved item below is `BLOCKED — USER DECISION REQUIRED`. Keep it blocked in status/reporting until explicitly resolved; do not infer a choice from the attached implementation plan.

1. **BLOCKED — USER DECISION REQUIRED — Prototype disease:** the project says begin with one disease but names none. Select disease name and canonical identifier.
2. **BLOCKED — USER DECISION REQUIRED — D1 Target prioritization:** choose concrete pretrained/trainable model and checkpoint, graph schema, objective, negative sampling, benchmark and expected compute. GFM/GNN is a research direction, not an implementation choice.
3. **BLOCKED — USER DECISION REQUIRED — Temporal/dynamic graph scope:** the architecture says streaming/dynamic capability “where justified”; the added plan makes dynamic/temporal GNN a first-class requirement. Decide whether temporal behavior is MVP, later stage, or excluded pending justification.
4. **BLOCKED — USER DECISION REQUIRED — RAG and retrieval scope:** the architecture selects RAG/graph evidence; the added plan mandates LLM multi-hop reasoning and graph/vector hybrid retrieval. Select MVP depth, literature sources, embedding/retrieval components, citation requirements, licensing policy and evaluation; decide whether vector retrieval is required for MVP.
5. **BLOCKED — USER DECISION REQUIRED — D2 Molecular generator:** select exact GP-MoLFormer/Transformer implementation/checkpoint, scaffold/fragment conditioning representation, SE(3)-equivariant flow implementation, component composition (sequential/coupled/complementary), and training/fine-tuning strategy.
6. **BLOCKED — USER DECISION REQUIRED — D3 Optimization:** select GraphFDM implementation, objective/reward formulation, constraints, training procedure and RL baseline configuration.
7. **BLOCKED — USER DECISION REQUIRED — D4 Affinity:** resolve the conflict between the protein–ligand GNN/Transformer direction and the older XGBoost prototype choice. Choose MVP baseline and final research model separately; define protein/ligand representation, dataset and split. The added plan says classical ML may only be a baseline; this does not itself resolve the original decision.
8. **BLOCKED — USER DECISION REQUIRED — D5 Leakage policy:** choose split strategy per model and specify scaffold, temporal, target-disjoint and molecule-disjoint controls as appropriate.
9. **BLOCKED — USER DECISION REQUIRED — D6 Compute and budget:** record CPU, GPU/VRAM, RAM, storage, maximum training time, cloud budget, OS and relevant accelerator stack. No hardware profile was available in the repository audit.
10. **BLOCKED — USER DECISION REQUIRED — Data policy:** choose activity types/units/assay inclusion and aggregation rules, standardization policy, source versions/dates and evidence aggregation. Specify treatment of absent target structures.
11. **BLOCKED — USER DECISION REQUIRED — ADMET and synthesis models:** select concrete models/checkpoints, supported endpoints and evaluation data; define whether they are MVP requirements or later additions where the source docs do not specify exact models.
12. **BLOCKED — USER DECISION REQUIRED — Acceptance gates:** set configurable, empirically justified validity, novelty/property, uncertainty and candidate-count gates. Do not treat the proposed ≥98% validity gate as established scientific quality.
13. **BLOCKED — USER DECISION REQUIRED — API/UI/container MVP scope:** original docs defer infrastructure and allow Docker Compose after the core pipeline; the added plan requires a deployable API/UI path and advocates early Compose. Decide whether API, UI and containerized single-command deployment are required for MVP, and which interface is in scope.
14. **BLOCKED — USER DECISION REQUIRED — Storage/experiment tracking:** select local file formats and whether an experiment-tracking library is needed for MVP. The original documents require reproducible tracking but defer MLflow infrastructure; the added plan proposes MLflow or an equivalent abstraction.
15. **BLOCKED — USER DECISION REQUIRED — Schedule claim:** “same-day” execution is asserted by the added plan but cannot be evaluated without decisions 1–14, dependency/checkpoint verification and compute profiling. No delivery estimate is approved by the source documentation.

## 7. Source-document inconsistencies and interpretation

- The model register explicitly identifies exact target model, generator, optimization, affinity, leakage and compute as unresolved; the extreme plan states the conceptual architecture is fixed and insists the full advanced components remain first-class. Preserve those research directions, while treating concrete implementations, feasibility, and any increased scope as blocked decisions.
- Affinity’s GNN/Transformer direction conflicts with the older XGBoost prototype suggestion. Retain classical ML as a possible baseline, but do not select the MVP/final model without D4.
- Dynamic graphs are conditional in the architecture but mandatory in the extreme plan. See decision 3.
- Literature RAG is selected directionally, but the extreme plan expands it to LLM multi-hop reasoning, graph/vector hybrid retrieval and a literature corpus without naming sources or models. See decision 4.
- The original plan says local modular pipeline first, with Compose after it works, and defers FastAPI/infrastructure; the extreme plan asks for an API/UI deployment path and rapid Compose deployment. See decision 13.
- Both documents identify advanced generation and GraphFDM, but neither supplies confirmed checkpoints, compatible implementations or training feasibility. No dependency availability is confirmed by an empty repository.
- A ≥98% validity gate is proposed but must be configurable and justified experimentally; it is not a scientific acceptance claim.
- The seven-stage order places triage before affinity and docking; preserve it. Any proposal to use docking or affinity scores inside optimization/triage rewards must be explicitly specified and evaluated before implementation to avoid an ambiguous feedback loop.

## 8. Assumptions and plan controls

- Default to one locally runnable disease pipeline and file-based versioned datasets/artifacts while keeping interfaces extensible.
- Treat all named model families/tools as research directions until exact implementation, checkpoint, license, compatibility and compute are verified.
- Keep API/UI, containers, vector DB, MLflow server and production infrastructure out of MVP until their blocked scope decisions are resolved; the scientific pipeline remains the primary MVP.
- Allow deterministic fixtures/mocks for early interface and integration tests, never as evidence that a model or end-to-end scientific component works.
- Do not begin implementation until this plan is reviewed and approved, all decisions required for the intended implementation phase are resolved, and the compute/dependency audit supports that phase.
