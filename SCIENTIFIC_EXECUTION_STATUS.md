# Scientific Execution Status

> Superseded for current decisions by `FINAL_DEPLOYMENT_STATUS.md`. The approved GFM path is ULTRA assessment behind the existing adapter; BioMedKG is rejected, and GFM does not block independent work. No user decision to select a replacement is pending.

**As of:** 2026-10-02  
**Scope:** Scientific blockers 1–7 only. Public deployment remains stopped.  
**Policy:** `OPTIMIZATION_POLICY.md`; objectives remain separate Pareto dimensions. No training or optimization was started.

## BLOCKED

### 1. ET-Flow checkpoint/access and Linux/CUDA execution

- **Finding:** ET-Flow inference code is available and the `drugs-o3` checkpoint exists in Zenodo v3 (100.7 MB). The newer v4 record contains scaffold data but no checkpoint. The checkpoint record has no license value; MIT licensing of the source code does not grant rights to the weights. The project has no provisioned Linux/CUDA runtime or verified cloud GPU session. The cloud deployment architecture remains unchanged.
- **Next action:** Obtain written checkpoint-use permission/license from the rights holder. Then provision the already specified Ubuntu 22.04 / Python 3.10 / CUDA 12.1 environment on an A10G/L4-class GPU, resolve and lock ET-Flow/PyTorch/PyG dependencies, and run batch-1 inference plus geometry and reproducibility checks. Do not download or use the checkpoint before rights clearance.

### 2. Target-conditioned molecular generation

- **Finding:** The pinned GP-MoLFormer checkpoint supports unconditional generation, scaffold prompting, and distribution/pair fine-tuning; it is not protein- or pocket-conditioned. Its current implementation correctly blocks target-conditioned claims. No target has been approved, and ChEMBL retrieval is incomplete: the existing NSCLC EGFR extraction is truncated at 10,000 of 58,847; Alzheimer’s APP and T2D KCNJ11 retrievals failed with HTTP 500. All three are provisional candidate targets only.
- **Next action:** Finish target ranking and target-specific assay extraction/quality review for all three diseases, then construct frozen leakage-resistant splits. Implement target-conditioned fine-tuning on the pinned GP-MoLFormer backbone with explicit target/pocket conditioning and train/evaluate it in cloud. Fragment control needs a validated constrained-decoding/conditioning implementation and its own tests; retain unsupported-operation failure states until then.

### 3. Target GFM/GNN model and benchmark

- **Finding — BioMedKG FAILS the current compatibility gate.** The BioMedKG paper reports random 60:20:20 edge splits for PrimeKG++ and DrugBank DTI; it does not report disease/target-disjoint or time-held-out evaluation. Its pretraining graph is PrimeKG++, so target-ranking labels may already be encoded in pretraining; the released artifacts do not provide a per-target leakage audit. The Hugging Face model card is empty and labels the model MIT; the dataset card is also empty, while the paper explicitly uses DrugBank DTI and official DrugBank terms require an academic download application and a separate commercial license. Those repository labels do not establish the rights for every embedded upstream asset or derived checkpoint. Finally, the published dataset listing does not establish coverage of our MONDO disease IDs and exact target identifiers. The Hub viewer fails to load the mixed-schema CSV directory. No dataset or checkpoint files were downloaded for this review; the repository advertises a 1.49 GB dataset.
- **Architecture/task fit:** BioMedKG is a multimodal biomedical KG representation and link-prediction system, but compatibility with this project’s disease-to-target ranking use case is not demonstrated under the required leakage-resistant protocol. The project’s in-repo temporal relational GNN remains untrained and is not a substitute GFM. Open Targets evidence ranking remains a transparent baseline only.
- **Available candidate for your decision — ULTRA:** ULTRA is a general multi-relational KG link-prediction foundation model with public 2 MB checkpoints and MIT-licensed code. Its relation/entity-vocabulary transfer makes it a direct technical candidate for disease-to-target link prediction after mapping and a leakage-resistant biomedical benchmark; its generic pretraining does not establish biomedical accuracy, so it must be evaluated before use. [ULTRA repository](https://github.com/DeepGraphLearning/ULTRA)
- **Adjacent candidate — TxGNN:** TxGNN is a biomedical graph foundation model with pretrained weights and zero-shot disease support, but its documented tasks are drug indication/contraindication prediction, not disease-to-target ranking. It is not a drop-in GFM replacement for the current target-ranking task without adaptation and a separate leakage audit. [TxGNN project](https://zitniklab.hms.harvard.edu/projects/TxGNN/)
- **Next action:** Assess ULTRA as the primary candidate behind the GFM adapter. If it fails source-artifact licensing/provenance, biomedical coverage, identifier mapping, or leakage-resistant benchmark gates, keep GFM explicitly BLOCKED. Do not substitute TxGNN. Independent components continue where their own data and model gates permit.

### 4. GraphFDM implementation/execution

- **Finding:** GraphFDM is identified as *Graph Forward Distribution Matching for Molecular Inverse Design* (arXiv:2609.32056); the method has a full paper but no verified official implementation or checkpoint. No paper reproduction has been implemented or evaluated. The project now has a disease-scoped objective-vector interface with explicit maximize/minimize directions and no scalar weights. This does not implement GraphFDM. Target selection, assay datasets, and validated objective predictors remain incomplete, so optimizer training is not permitted.
- **Next action:** Implement a versioned paper reproduction against the paper’s stated graph-diffusion setup and benchmark, record any irreproducible details, and compare the paper-consistent diagnostics before connecting target-specific objectives. Train only after the target/data/split/predictor gates below pass; use the specified cloud GPU and report memory/runtime before scaling.

### 5. Affinity dataset, training, and evaluation

- **Finding:** The protein–ligand cross-attention architecture exists, but no curated, licensed complex-affinity dataset, frozen split, trained checkpoint, calibration, or evaluation result exists. ChEMBL target activity rows do not by themselves provide the prepared protein–ligand complex dataset required by this model. The existing affinity module has only interface/fixture validation.
- **Next action:** Define the licensed complex dataset and extraction manifest; curate structures and compatible affinity endpoints; freeze scaffold-, protein-sequence-cluster-, chronological-, and joint-leakage holdouts; then train/evaluate the cross-attention model in cloud with calibration and OOD reporting. Keep the ligand-only XGBoost model separately labeled as baseline.

### 6. ADMET, synthetic-feasibility, and OOD predictors

- **Finding:** No endpoint-specific ADMET predictor or validated synthetic-feasibility model has been selected, licensed, calibrated, or assessed for applicability domain. QED/SA descriptors are not substitutes for toxicity, ADMET, or route-feasibility predictors. No arbitrary toxicity or BBB thresholds have been added.
- **Next action:** Inventory candidate predictors with documented endpoint definitions, license, checkpoint, training domain, and external validation data; assess them on frozen disease-relevant holdouts, calibrate uncertainty, and publish applicability-domain criteria. Keep each unsupported objective `UNAVAILABLE`; do not start optimization until every objective channel used in a claim has a validated predictor.

### 7. Docking preparation and validation protocol

- **Finding:** Vina 1.2.7 is locally installed, but receptor/ligand preparation, selected target structures, chain/construct mapping, protonation policy, binding-site box, and validated protocol are absent. Current targets are provisional, so target-specific redocking readiness cannot be asserted.
- **Next action:** After target selection, identify suitable experimental structures and cognate ligands; implement deterministic receptor/ligand preparation (including preparation-tool version and parameters); redock cognate ligands and assess pose recovery and score controls per target before screening. Preserve a blocked result when no qualifying structure/control exists.

## CLOUD_REQUIRED

- A Linux/CUDA cloud execution environment is required for ET-Flow integration, target-conditioned generator fine-tuning, GFM/GNN training where warranted, GraphFDM reproduction/training, and affinity model training. No cloud GPU runtime was provisioned or used in this task. Use the exact environment and instance recommendations in `BLOCKER_RESOLUTION_PLAN.md` only after checkpoint rights, data gates, and cost/resource provisioning are available. Do not claim a cloud run from static Docker files or local fixtures.

## USER_DECISION_REQUIRED

- **Graph foundation model:** BioMedKG failed the compatibility gate. Choose whether to assess ULTRA as the direct disease-to-target link-prediction candidate, authorize a separately evaluated TxGNN adaptation, or defer GFM selection. No alternative has been selected. The explicit protein/pocket conditioning decision for GP-MoLFormer is resolved as recorded below.

## READY

- GP-MoLFormer conditioning decision resolved: protein/pocket conditioning is the required primary signal; target identity/activity may be auxiliary but cannot be the sole signal. The existing base checkpoint is not pocket-conditioned and remains blocked pending a conditioning pathway, pocket/complex data, frozen splits, and evaluation protocol.
- Separate Pareto objective-vector contract implemented in `src/satori/optimization/graphfdm.py` and bound to disease/target in the optimization job handler. It defines the approved common objective directions and adds CNS MPO/BBB suitability for Alzheimer’s. Channels that lack target data or validated predictors are explicitly marked pending; no scalar weights, unsupported thresholds, or favorable imputation are present. This is an interface/policy implementation only, not an executed optimizer or scientific result.
- Disease list remains NSCLC, Alzheimer’s disease, and T2D. Existing selected-target labels EGFR, APP, and KCNJ11 remain provisional. Current extraction state is recorded in `data/raw/chembl-target-activities/retrieval-summary.json`; it fails the target/assay readiness gate.

## Reproducibility and claim boundary

- No large-scale training, GraphFDM/RL optimization, checkpoint download, or public deployment was performed.
- Literature/source checks: [GraphFDM paper](https://arxiv.org/abs/2609.32056); [ET-Flow code](https://github.com/shenoynikhil/ETFlow); [ET-Flow checkpoint record v3](https://zenodo.org/records/14226681); [newer ET-Flow record v4](https://zenodo.org/records/16551316); [GP-MoLFormer model card](https://huggingface.co/ibm-research/GP-MoLFormer-Uniq); [BioMedKG repository](https://github.com/HySonLab/BioMedKG).
