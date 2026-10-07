# Blocker Resolution Plan

**Prepared:** 2026-10-02  
**Scope:** Phases 1–7 scientific execution path. Phase 8 deployment is expressly deferred.  
**Diseases:** NSCLC (`MONDO_0005233`), Alzheimer’s disease (`MONDO_0004975`), and type 2 diabetes mellitus (`MONDO_0005148`).  
**Architecture constraint:** Preserve the approved temporal graph/GFM, target-conditioned GP-MoLFormer, ET-Flow, GraphFDM, affinity cross-attention, ADMET/synthesis, uncertainty/OOD and Vina components. A baseline remains a separate comparator and is never treated as a replacement.

## Classification key

- **CODEX CAN RESOLVE** — engineering, integration, evaluation protocol, or evidence gathering that can proceed without a scientific preference.
- **CLOUD GPU REQUIRED** — requires a compatible remote Linux/CUDA environment or more GPU capacity than the local RTX 3050 6 GB can reasonably provide.
- **USER SCIENTIFIC DECISION REQUIRED** — the project materials do not define a biological objective, endpoint, constraint, or model-acceptance choice that cannot be inferred from engineering evidence.
- **GENUINELY UNAVAILABLE** — an upstream artifact, checkpoint-use license, or target-specific evidence needed for a claim is not currently published or present. Do not imply that waiting, an adapter, or a newly written implementation closes this state.

## Findings that close stale blockers

These facts supersede the Phase 0 snapshots in the referenced status documents:

- The three-disease Open Targets pipeline and target-context/ligand data contracts are implemented and live-smoke-tested. The 30 ChEMBL rows are exploratory samples, **not** a disease benchmark or training set.
- PyTorch CUDA and the Transformers stack are installed. GP-MoLFormer-Uniq and its tokenizer are pinned and have completed real local CUDA inference. Its base checkpoint is not protein/pocket-conditioned; that remains a distinct task.
- AutoDock Vina v1.2.7 is installed and version-verified. The executable is no longer the docking blocker; prepared inputs and protocol validation are.
- The Phase 7 run ledger now writes JSON stage artifacts with hashes and persists partial/blocked states. Fixture tests do not constitute a scientific end-to-end result.

## Priority blocker register

### 1. ET-Flow execution and checkpoint

**ET-Flow environment / execution — CLOUD GPU REQUIRED.** The upstream repository is MIT-licensed and documents the `drugs-o3` model for conformer generation from SMILES. Its environment file specifies Linux-style Conda channels; Python `>=3.8`, NumPy `1.26.4`, PyTorch with `pytorch-cuda==12.1`, PyG, `pytorch-cluster`, Lightning, TorchMetrics, RDKit, Datamol, Pandas and SciPy. Use a separate Linux environment; do not contaminate the Windows/Python 3.13 project environment. The ET-Flow Python package declares support through Python 3.12 classifiers and the published environment does not validate the current Windows/Python 3.13 stack. [ET-Flow repository](https://github.com/shenoynikhil/ETFlow), [upstream environment](https://raw.githubusercontent.com/shenoynikhil/ETFlow/main/env.yml), [package metadata](https://raw.githubusercontent.com/shenoynikhil/ETFlow/main/pyproject.toml)

- **Exact cloud environment:** Ubuntu 22.04 x86-64; Python 3.10; CUDA 12.1 runtime; PyTorch + `pytorch-cuda=12.1`; NumPy 1.26.4; PyG and `pytorch-cluster` built for that exact Torch/CUDA pair; Lightning; TorchMetrics; RDKit; Datamol; Pandas; SciPy; `etflow` installed from a commit-pinned upstream checkout. Resolve once, export a Conda lock, and record the container image digest and package lock.
- **GPU:** an NVIDIA L4 or A10G with 24 GB VRAM is the recommended integration instance. The 100.7 MB model checkpoint suggests that batch-1 inference may fit on an 8–12 GB device, but the upstream project does not publish a minimum VRAM guarantee; verify peak memory using batch size 1 before expanding. Do not use the local Windows GPU as the supported ET-Flow environment.
- **Storage:** reserve 20 GB for the environment, cache, logs and small integration inputs. The `drugs-o3` checkpoint is 100.7 MB. Do not download the large raw GEOM training corpus for inference. The original Zenodo record’s checkpoint+split bundle is 359.4 MB, but only the checkpoint and a small test subset are needed for an inference smoke. [Zenodo checkpoint record](https://zenodo.org/records/14226681)
- **Steps:** (1) resolve/checkpoint-lock the upstream environment; (2) confirm permission for checkpoint use (license issue below); (3) install ET-Flow at a recorded source commit; (4) load `BaseFlow.from_default(model="drugs-o3")`; (5) run one known test molecule with three conformers; (6) validate atom count, finite coordinates, bond/angle/chirality geometry, reproducibility settings and wall time; (7) evaluate against the published GEOM-DRUGS split/RMSD procedure; (8) store the checkpoint hash, config, source commit, environment lock, seed and conformer artifacts in the Phase 7 ledger.
- **Scope boundary:** ET-Flow generates conformers for a supplied molecular graph. It does not replace GP-MoLFormer and is not joint graph/coordinate generation. The existing sequential composition is retained.

**`drugs-o3` checkpoint rights — GENUINELY UNAVAILABLE.** The checkpoint is published (100.7 MB) on the older Zenodo record, but the record shows no license value. The upstream code’s MIT license does not establish the weights’ license. No checkpoint use, redistribution or cloud copy is cleared by the public metadata. Obtain an explicit license/permission statement from the rights holder before using the weights. Until then, keep the component blocked; do not substitute another conformer model. [Zenodo rights metadata](https://zenodo.org/records/14226681)

**ET-Flow adapter composition and validation — CODEX CAN RESOLVE.** Preserve the current adapter contract; add graph-to-conformer artifacts, atom ordering, generated-coordinate checks and an explicit failure state. Do not mark this complete until actual `drugs-o3` inference and license clearance pass the gate above.

### 2. GraphFDM

**Method identity — CODEX CAN RESOLVE.** “GraphFDM” now maps to *Graph Forward Distribution Matching for Molecular Inverse Design*, arXiv:2609.32056, submitted 2026-09-25. It is a reward-conditioned graph-diffusion optimization method that matches a reward-tilted target distribution through the forward corruption process and adjusts graph-size as well as graph-structure distributions. This is the method to preserve; it is distinct from a generic reverse-step RL policy. [arXiv paper](https://arxiv.org/abs/2609.32056)

**Official GraphFDM code and pretrained checkpoint — GENUINELY UNAVAILABLE (as of this plan).** The arXiv submission has no linked source repository or model artifact, and no official package/checkpoint was located. The paper is only days old. Keep the GraphFDM adapter blocked as it is; do not rename the RL baseline, custom GNN, or any other flow model “GraphFDM.”

**Faithful research implementation — CODEX CAN RESOLVE.** The reward vector is now approved; implement the paper’s forward distribution matching equations against its stated graph-diffusion setup, with graph-size mass correction, online reward estimation, validity-preserving training, and paper-consistent diagnostics. Pin the arXiv version used and maintain a `paper-reproduction` status distinct from official upstream code/checkpoint. First reproduce a paper benchmark/property task; only then run a disease-target reward. If essential algorithm details are absent from the paper/supplement, record that subcomponent as unavailable instead of inventing a substitute.

**Cloud training.** Use a separate Ubuntu 22.04, Python 3.11 environment with a fully locked PyTorch CUDA stack, RDKit, and the graph/diffusion packages actually required by the paper implementation. Those exact graph package versions cannot be honestly pinned until the official code or the faithful implementation is selected. Reserve a 100 GB persistent volume for environment, generated graphs, checkpoints, logs and benchmark datasets; graph model/data sizes are not published for the current project. Use one A100 80 GB as the conservative training allocation; a 24–48 GB L4/L40S-class GPU is suitable for small-batch fine-tuning only after a measured peak-memory profile. These are planning allocations, not paper-reported minima. Save the base graph-diffusion checkpoint used, all reward-model versions, sample/replay artifacts, seed, and update schedule.

### 3. Reward/objective definition

**Disease-specific reward endpoints, objectives and constraints — RESOLVED by user decision.** The approved separate Pareto objective contract and target-specific endpoint-selection policy are recorded in `OPTIMIZATION_POLICY.md`. GraphFDM is primary; RL remains a separate baseline. No weighted scalar objective is approved.

**Implementation after approval — CODEX CAN RESOLVE.** Implement a versioned objective schema that stores the per-disease/per-target endpoint, units and direction; objective vs hard constraint; threshold/weight; uncertainty penalty; missing-model behavior; provenance; and rejection reason. Each score component remains visible. No failed/unknown ADMET model may become a favorable imputed value. Pareto selection remains available for genuine tradeoffs and does not invent scalar weights.

### 4. Leakage-resistant assay policy and splits

**Conservative assay ledger and split mechanics — CODEX CAN RESOLVE.** Resolve the engineering policy without asking for arbitrary thresholds:

1. Preserve every raw assay row and its source ID, assay type, relation (`=`, `<`, `>`), units, target, organism, publication date and processing decision.
2. Convert only directly comparable molar values with an exact relation to a p-activity value. Keep `Ki`, `Kd`, and `IC50` as separate endpoints/heads; do not pool binding and functional assay values. Preserve censored values for a censor-aware loss or exclude them from point metrics with a recorded reason. Never treat “no record” as an inactive negative.
3. For disease-target ranking, use positive-unlabeled ranking over the explicit candidate target universe. Do not sample unassociated targets as known negatives. Use publication/event-time cutoffs for prospective ranking and keep test-period evidence out of features.
4. For ligand/affinity evaluation, produce separate scaffold-disjoint, protein-sequence-cluster-disjoint, and chronological tests. In addition, build a joint holdout by assigning connected components over shared ligand scaffold and target sequence cluster; if that collapses the corpus, report the reduction and retain the separate stress tests rather than relaxing the constraints silently.
5. Freeze all partitions before tuning. Fit transforms, calibration and reward thresholds on train/validation only; hash exact assignments and dataset content. Report performance by disease, endpoint, assay family, target cluster and scaffold split.

The existing activity-policy and split-manifest code already has explicit decisions and molecule/scaffold/target/time grouping primitives. Codex can add sequence-cluster grouping, joint leakage-component assignments, censored-label handling, and tests. Small current smoke datasets do not meet minimum requirements for training or evaluation; run scalable source ingestion only after measuring the returned data volume and license.

**Disease-specific primary endpoints — policy approved, target data still pending.** The split algorithm is engineering; the endpoint policy is now set, but full target selection and complete ChEMBL assay distributions must be established before defining final labels.

### 5. Affinity model training and evaluation

**Model architecture — CODEX CAN RESOLVE.** Keep the implemented protein–ligand distance-aware cross-attention model as the approved research model and the Morgan/XGBoost implementation as a separately named baseline. Implement protein/ligand feature extraction, batching/masking, training, checkpoint metadata, calibration, and prediction artifact lineage. The random-tensor test only validates the forward/loss contract; there is no trained predictor now.

**Affinity model fit/evaluation — CLOUD GPU REQUIRED.** Use Ubuntu 22.04, Python 3.11, a lock-pinned PyTorch CUDA environment, RDKit, Biopython, structure parser/featurizer and (only if the implementation uses sparse graph ops) a matching PyG/`torch-cluster` build. Use an L4/A10G with 24 GB VRAM for the first small-batch run; reserve an A100 40–80 GB if protein–ligand complexes, cross-attention batches or the planned ensemble exceed measured memory. Reserve at least 100 GB persistent storage for structures, processed tensors, logs and checkpoints. Estimated custom model checkpoint is 0.1–1 GB; dataset storage is the dominant and currently unmeasured component.

- **Dataset gate:** curate experimental complex structures and affinity labels with per-record license/provenance. PDBbind v2020 is a viable established benchmark only under its access/use terms; it is not to be mirrored into this repository. A post-cutoff independent set such as the BDB2020+ construction in Leak-Proof PDBBind can serve as an external temporal test when permitted. Keep `pKd`, `pKi` and `pIC50` separate, do not pretend docking scores are affinity labels, and write the label curation/exclusion ledger.
- **Execution:** (1) freeze dataset, targets, structures and leakage splits; (2) validate atom/residue/chain alignment and input features; (3) train the cross-attention model on train only with heteroscedastic NLL; (4) select checkpoints on validation; (5) evaluate once on sealed scaffold-, target-cluster- and time-held-out tests; (6) report RMSE, MAE, Pearson, Spearman and concordance index with bootstrap confidence intervals; (7) persist predictions, uncertainty, dataset/split/model hashes and hardware/runtime.
- **Data access — GENUINELY UNAVAILABLE until licensed data is available.** The repository currently has only 30 exploratory ChEMBL records for three targets and no curated structure/affinity benchmark or license evidence. If PDBbind access is not available, Codex must identify an openly licensed matched-complex alternative and report its coverage before training; the small smoke sample is not a substitute.

### 6. Docking preparation and protocol

**Preparation software and validation workflow — CODEX CAN RESOLVE.** Vina v1.2.7 itself is installed locally. Use Meeko for supported receptor/ligand PDBQT preparation and Biopython/gemmi for structure/chain inspection; create a separate Python 3.11 chemistry/tool environment if Meeko dependency resolution conflicts with the project environment. Meeko documents receptor preparation from PDB/CIF and ligand conversion from SDF. [Meeko receptor CLI](https://apidocmeeko.readthedocs.io/en/latest/cli_rec_prep.html), [Meeko ligand preparation](https://github.com/forlilab/Meeko/blob/develop/docs/source/lig_prep_basic.rst), [Vina manual](https://vina.scripps.edu/manual/)

- Select structures by exact sequence/construct mapping, chain coverage, resolution and ligand occupancy. Prefer a co-crystal ligand at the intended site. Keep biologically relevant metals/cofactors and alternate conformations only under explicit preparation rules; record removed components.
- Derive the search box from the bound ligand centroid and documented padding. Do not infer a pocket from an arbitrary structure center. If no suitable co-crystal ligand/structure exists, mark docking `blocked: no validated pocket` for that target.
- Validate preparation by redocking the co-crystal ligand with the chosen Vina scoring mode and exhaustiveness; report pose RMSD and success at the prespecified 2 Å criterion, score, protonation method, box, Vina version and preparation log. Run a second known-complex control where possible. Only after the preparation gate passes, dock generated molecules. Treat scores as docking evidence, never experimental affinity.
- **Compute:** local CPU is sufficient for the initial redocking and small docking set; GPU is not required. For throughput, parallelize independent ligand runs with bounded CPU workers. No cloud GPU is required for Vina.

**Per-target co-crystal/pocket availability — GENUINELY UNAVAILABLE when no qualifying structure is found.** The three smoke-resolved target contexts had sequence/structure references but were explicitly not marked docking-ready. Codex can map and validate available structures; no protocol can manufacture a missing experimental pocket. Preserve per-target blocked states.

### 7. Uncertainty and OOD evaluation

**Evaluation/calibration code — CODEX CAN RESOLVE.** Retain the existing affinity heteroscedastic variance output. Add a separately identified five-seed ensemble for epistemic spread; calibrate regression intervals on validation using conformal residual quantiles; assess calibration and coverage only on untouched external/scaffold-, target-cluster- and temporal OOD sets. For target rankings, use disease-held-out and evidence-time-held-out tests; report risk–coverage/selective metrics. Measure OOD detection AUROC/AUPRC only when a defensible in-domain/OOD labeling rule exists. Do not turn an uncalibrated variance or embedding distance into “confidence.”

**Training/calibration runs — CLOUD GPU REQUIRED.** Reuse the affinity/graph environments above. Train ensemble members sequentially on one 24 GB L4/A10G where feasible; use A100 40–80 GB if peak memory or throughput requires it. No separate large checkpoint is needed for calibration, but preserve per-seed trained weights and calibration state. Required inputs are the frozen training/validation/test manifests and a trained model; neither calibrated uncertainty nor OOD performance can be claimed using the current smoke data.

## Remaining architecture blockers outside the priority order

### Target-prioritization GFM checkpoint — REVIEW COMPLETE; DECISION REQUIRED

**Initial candidate note, superseded by the completed review below.** BioMedKG was investigated as the candidate; it did not pass the compatibility gate.

**Current disposition:** See the completed BioMedKG review and user decision below.

**BioMedKG review — FAIL.** The paper uses random 60:20:20 edge splits rather than disease/target-disjoint or chronological splits; it uses PrimeKG++ for pretraining, with no per-target audit proving disease-target labels were excluded. The Hugging Face model and dataset cards are empty. Although Hub metadata labels the repository MIT, the work uses DrugBank DTI and official DrugBank terms describe limited academic access requiring an application and separate commercial licensing. This does not establish rights for every included upstream asset or derived checkpoint. Coverage of the three MONDO disease IDs and mapped target IDs is undocumented; the Hub dataset viewer fails to load the mixed-schema CSVs. The dataset is listed as 1.49 GB; no dataset/checkpoint files were downloaded. [BioMedKG paper](https://www.frontiersin.org/journals/systems-biology/articles/10.3389/fsysb.2025.1651930/full), [Hub dataset](https://huggingface.co/datasets/tienda02/BioMedKG), [DrugBank terms](https://trust.drugbank.com/drugbank-trust-center/drugbank-terms-of-service)

**Direct technical alternative for decision — ULTRA.** Its general KG link-prediction foundation model transfers across entity/relation vocabularies, with public 2 MB checkpoints and MIT-licensed code. It can score disease→target links after graph mapping, but generic pretraining is not biomedical validation; it still requires this project's temporal/positive-unlabeled evaluation. [ULTRA](https://github.com/DeepGraphLearning/ULTRA)

**Adjacent, non-drop-in alternative — TxGNN.** A biomedical graph foundation model for drug indication/contraindication and zero-shot disease inference, but not disease→target ranking. Using it requires an explicitly evaluated task adaptation; it is not equivalent without that work. [TxGNN](https://zitniklab.hms.harvard.edu/projects/TxGNN/)

**USER DECISION REQUIRED:** select whether to assess ULTRA, authorize a separate TxGNN adaptation, or defer GFM selection. No alternative has been selected. Stop target-ranking model work at this gate pending the decision.

### ADMET and synthetic-feasibility predictors

**Scientific policy approved; predictor validation remains required.** Use validated endpoint-specific ADMET/synthesis predictors only. Until validated predictors and supported thresholds exist, report each field as `not_evaluated`/`model_unavailable`; do not use a QED or SA heuristic as if it were a trained toxicity or synthesis model.

After endpoint approval, Codex can compare endpoint-specific checkpoints for license, validation domain and dependencies, then train/calibrate only where permitted data exist. **CLOUD GPU REQUIRED** for large model fine-tuning; compact endpoint inference may run locally once installed and benchmarked. No valid disease-specific checkpoint was identified in the repository.

### Graph + vector retrieval / LLM-RAG

**USER SCIENTIFIC DECISION REQUIRED, but not on the critical science path.** LLM/provider, data privacy boundary, literature licensing and citation policy are not specified. Phase 8 and LLM-backed user-facing retrieval remain deferred; no decision is requested now. A local retrieval-only index can be implemented by Codex once a licensed corpus and relevance test set are approved, without choosing an LLM.

## Resolution order and gates

1. **Data gate:** freeze disease-specific target selections, full assay distributions, endpoint strata, labels/objectives, and leakage-resistant split manifests under the approved policy in `OPTIMIZATION_POLICY.md`. Until then, disease-specific GraphFDM/RL reward training is blocked.
2. **ET-Flow:** obtain written checkpoint-use terms; then build/lock the Linux/CUDA 12.1 environment, run the real checkpoint smoke/equivariance and geometry tests, and integrate conformer artifacts.
3. **GraphFDM:** pin the arXiv v1 method and reproduce its paper task in the cloud environment; persist code/checkpoint provenance; compare only after matching the paper protocol. Official GraphFDM artifacts remain unavailable until released.
4. **Data/splits:** ingest enough provenance-tracked assay and target evidence; apply the conservative endpoint separation and leakage suite above; seal test manifests.
5. **Affinity + uncertainty:** prepare/authorize complex data; train cross-attention and five-seed ensemble in cloud; calibrate on validation; report sealed OOD results.
6. **Docking:** finish structure/chain/pocket mapping, Meeko preparation, cognate redocking controls and per-target readiness before screening generated structures.
7. **End-to-end scientific gate:** only then run the three disease-specific pipeline and emit either a ranked dataset with per-component provenance and uncertainty or a complete explicit blocker report.

**Phase 8 deployment stays stopped** until the scientific path above is defined and its Phase 7 gate produces a reproducible scientific result or a complete blocker report, per the user’s instruction.

## User decision status

### Decision 1 — disease-specific scientific objective contract — RESOLVED

The user approved separate Pareto objectives, target-specific ChEMBL endpoint selection, disease-specific objectives, chemistry screening gates, and restrictions against unsupported toxicity/BBB thresholds. See `OPTIMIZATION_POLICY.md` for the full contract. Numerical weights are not applicable because objectives must not be collapsed into a weighted scalar score.

### Decision 2 — BioMedKG and GFM alternative — REVIEW COMPLETE; USER DECISION REQUIRED

BioMedKG failed the leakage, license-provenance, and identifier-coverage gates. ULTRA is the direct technical candidate; TxGNN is adjacent and requires separately evaluated adaptation. Choose whether to assess ULTRA, authorize a TxGNN adaptation, or defer GFM selection. No alternative has been selected.

No Phase 8 decision is requested now. Cloud provider and spend authorization will only be requested if actual cloud provisioning is needed; this plan specifies provider-neutral instance requirements and does not provision resources.
