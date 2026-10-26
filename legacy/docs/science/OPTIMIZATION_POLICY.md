# Optimization Policy

**Status:** Scientific policy approved; optimization is gated on target selection, complete assay extraction, split construction, and predictor validation.  
**Scope:** GraphFDM is the primary optimizer. RL is retained and evaluated as a separately reported baseline.  
**Decision record:** This policy records the user's approved objective and chemistry-screening decisions. It does not claim that target ranking, predictor validation, or optimization has already occurred.

## 1. Disease contexts

The data and optimization pipeline must support all three disease contexts:

1. Non-small cell lung cancer (NSCLC)
2. Alzheimer's disease
3. Type 2 diabetes mellitus (T2D)

For each disease, the target must be selected from the approved target-prioritization process before its potency dataset is declared final. The genes in the existing smoke data are provisional contexts only: EGFR for NSCLC (`CHEMBL203`), APP for Alzheimer's (`CHEMBL2487`), and KCNJ11 for T2D (`CHEMBL1886`). They are not represented here as scientifically approved final targets.

## 2. Endpoint selection and potency labels

Derive endpoint selection from the selected target's actual ChEMBL data. Do not impose a global endpoint or mix incompatible assay modalities into one target.

Use this preference hierarchy, subject to assay comparability and adequate support:

1. pChEMBL-normalized binding/activity values when valid, uncensored or appropriately handled, and comparable in assay context.
2. Ki/Kd for direct binding when sufficiently populated.
3. IC50 for inhibition assays.
4. EC50 only when the target mechanism and assay design make EC50 biologically appropriate.

Keep distinct endpoint types, assay formats, mechanisms, and incompatible assay contexts in separate strata unless an explicit, documented normalization model justifies combining them. Preserve source activity type, units, relation/censoring, assay ID, assay type, BAO format/label, target ID, document/source IDs, and retrieval provenance. Convert concentration values to molar units before deriving p-scale values; do not treat censored `>`/`<` measurements as exact observations. Do not convert endpoints into a single common training label solely because they share a pChEMBL value.

For each selected disease target, report the complete extracted distribution before defining active/inactive labels: endpoint type, assay type/format, assay count, activity count, exact versus censored counts, units, pChEMBL availability, distinct compounds, target identity, and distribution summaries. Select target-specific activity thresholds from those distributions, assay semantics, and intended use; record rationale and sensitivity analyses. Preserve a continuous potency objective alongside any thresholded classification labels. No universal numeric potency threshold is approved.

## 3. Provisional smoke-data observations

The checked-in standardized ChEMBL smoke files contain only 10 records each. These counts are useful for validating data plumbing, not for endpoint choice, potency thresholds, target selection, or model fitting. All are one- or few-assay samples and are not complete ChEMBL target distributions.

| Disease smoke context (provisional) | ChEMBL target | Records | Observed endpoint types | pChEMBL present | Important assay/censoring context |
|---|---|---:|---|---:|---|
| NSCLC / EGFR | CHEMBL203 | 10 | IC50: 9; Ki: 1 | 7/10 | Six biochemical (`B`, single-protein) and four functional (`F`, cell-based); six assay IDs; one record has a non-exact relation. Do not pool IC50 and Ki, or biochemical and functional assays, by default. |
| Alzheimer's / APP | CHEMBL2487 | 10 | Ki: 10 | 6/10 | One biochemical single-protein assay (`CHEMBL649398`); six exact relations and four `>` censored relations. The censored observations are not exact potency labels. |
| T2D / KCNJ11 | CHEMBL1886 | 10 | EC50: 10 | 10/10 | One biochemical-assay record class with cell-based format (`CHEMBL884411`), potassium-channel opening in transfected cells. EC50 is context-specific and is usable only if appropriate to the selected mechanism. |

These figures were computed from `data/interim/chembl-smoke-standardized/*.jsonl`, reading endpoint and assay fields under each record's `source_record`. The standardized wrapper does not promote nested source fields to top-level fields. The provisional records provide no evidence that the listed genes are the final disease targets or that these endpoint distributions are representative. Re-extract after target selection and query the full relevant ChEMBL activity population.

## 4. Pareto objectives

Keep the objectives separate. GraphFDM must optimize a Pareto set/front; the RL baseline must use the same objective definitions and report the same objective vectors for fair comparison. Do not collapse objectives into a weighted scalar score at this stage. Any future scalarization requires a separate scientific decision and documented sensitivity analysis.

### NSCLC

- Maximize selected-target potency/affinity using the target-specific endpoint policy above.
- Maximize selectivity.
- Maximize QED/drug-likeness.
- Minimize synthetic difficulty (including SA score where applicable).
- Optimize ADMET using validated endpoint-specific predictors.
- Maximize novelty and chemical/scaffold diversity.
- Minimize predictive uncertainty and penalize out-of-domain (OOD) candidates.

### Alzheimer's disease

Use the NSCLC objective set, and additionally:

- Optimize CNS/BBB suitability as explicit separate objectives.
- Include CNS MPO and validated BBB-related model outputs as separate objectives when predictors are validated.
- CNS MPO >= 4 may be used as a preferred screening objective; it is not proof of BBB penetration.
- Do not impose hard BBB thresholds unsupported by validated model outputs.

### Type 2 diabetes mellitus

- Maximize selected-target potency/affinity.
- Maximize selectivity.
- Maximize QED/drug-likeness.
- Minimize synthetic difficulty.
- Optimize oral-drug ADMET properties using validated predictors.
- Maximize novelty and chemical/scaffold diversity.
- Minimize predictive uncertainty and penalize OOD candidates.

### Shared additional objectives

- Maximize QED and novelty.
- Minimize SA score / predicted synthetic difficulty.
- Maintain scaffold and chemical diversity across the Pareto candidate set.
- Minimize predicted toxicity liabilities only when a predictor has validated, calibrated endpoints and appropriate applicability domain.
- Minimize model uncertainty and penalize OOD molecules.

Do not invent hard toxicity cutoffs for hERG, hepatotoxicity, mutagenicity, CYP inhibition, or other endpoints. Until a selected model defines a calibrated endpoint, validation population, and supported threshold, report its prediction/uncertainty as an exploratory objective or leave it unavailable; do not present it as a validated safety gate. The same principle applies to unsupported BBB thresholds.

## 5. Universal chemistry safety-screening gates

Apply these configurable medicinal-chemistry screening gates before a molecule enters optimization evaluation:

- RDKit-valid and chemically sanitized structure.
- No duplicate candidate under the documented canonicalization/identity policy.
- No PAINS or selected reactive-structure alerts under the selected and versioned medicinal-chemistry filter.
- Molecular weight <= 500 Da.
- HBD <= 5.
- HBA <= 10.
- logP <= 5.
- Rotatable bonds <= 10.
- TPSA <= 140 Å².

These are configurable chemistry triage limits, not claims of biological safety, clinical suitability, or absence of toxicity. Store filter/version, descriptors, and rejection reasons for every candidate. Thresholds must be editable in configuration and written into run provenance.

## 6. Data splits and leakage controls

Before fitting potency/property predictors or comparing optimizers, create and freeze leakage-resistant splits. Retain a random split only as a labeled diagnostic baseline. The primary evaluation must prevent chemical-series leakage through scaffold or stricter structure grouping, prevent duplicate/near-duplicate leakage, and account for assay/document/time structure where relevant. Keep target identity and disease context isolated where the evaluation claim requires generalization across targets. All split assignments must be generated deterministically from versioned input manifests and recorded seeds.

For assay data, split after identity normalization and duplicate resolution, and keep measurements for the same compound/scaffold group from crossing partitions. Avoid placing replicated measurements or records from one assay/document family on both sides of a split when that would leak assay-specific signal. Report endpoint-stratified results and the exact split policy; do not conceal sparse or unsupported strata by merging them.

## 7. Predictor validation and optimizer entry gates

Optimization must not start until all of the following have explicit evidence:

1. Final selected target and target-prioritization provenance for each disease.
2. Full target-specific ChEMBL activity extraction, quality filters, endpoint distributions, assay-context review, and sample counts.
3. Endpoint-specific continuous objectives and, only if supported, target-specific active/inactive thresholds.
4. Frozen leakage-resistant splits and a reproducible data manifest.
5. Property-predictor validation on the frozen splits, with calibration and applicability-domain/uncertainty analysis for every objective used.
6. Defined GraphFDM objective-vector interface and a separate RL baseline that consumes the same objective contract.

If any objective lacks a validated predictor, mark it `UNAVAILABLE` or `BLOCKED` for the relevant evaluation. Do not silently substitute another model, infer scientific validity from an adapter/mock, or report an optimizer as scientifically evaluated when objective channels are unavailable. GraphFDM remains the primary optimizer; RL remains a baseline and cannot replace it.

## 8. Reproducibility and reporting

For every data, predictor, and optimization run, record disease and selected target, ChEMBL release/retrieval timestamp, source IDs and response hashes, endpoint filters, assay strata, censoring treatment, structure standardization and filter versions, split manifest/hash and seed, model/checkpoint/version/license, objective-vector schema, configuration, software and hardware, random seeds, candidate lineage, and failure states. Report Pareto fronts and per-objective distributions, diversity, uncertainty/OOD status, and rejected/failed candidates. Keep unavailable, failed, and not-yet-run states distinct from negative biological results.

## 9. Current gate status

**Optimization status: BLOCKED pending scientific execution prerequisites.** The objective contract and screening limits are approved. The three smoke-data target contexts above are provisional only; full target prioritization and complete ChEMBL distributions are not yet established here. Do not launch GraphFDM or RL optimization until Section 7 is satisfied for the selected targets and objective predictors.
