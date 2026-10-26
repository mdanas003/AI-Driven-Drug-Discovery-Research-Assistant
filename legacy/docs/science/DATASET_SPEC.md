# Target-specific disease activity dataset specification

**Purpose.** Build auditable, target-specific ChEMBL activity datasets for the NSCLC, Alzheimer's disease, and T2D target-prioritization workflow. These datasets support evidence review and feasibility assessment. They do not authorize potency-threshold adoption, affinity-model training, GraphFDM training, or RL optimization by themselves.

## Disease–target evidence pipeline

1. Query Open Targets Platform GraphQL for the top 100 associated targets for each MONDO disease identifier: NSCLC `MONDO_0005233`, Alzheimer's `MONDO_0004975`, T2D `MONDO_0005148`.
2. Preserve the platform association score and every returned datatype score. Rank candidates in source order by association score; deterministic tie ordering is target Ensembl ID. This is a transparent evidence-ranking baseline, not a trained or externally validated graph foundation model.
3. Resolve leading candidate Ensembl IDs through UniProtKB. Continue only with an unambiguous reviewed human protein accession for exact ChEMBL mapping; preserve unmapped/ambiguous states.
4. Map through ChEMBL target components and accept only an exact human `SINGLE PROTEIN` target. Preserve the ChEMBL mapping response and target ID.
5. Inspect the complete activity total count for every mapped candidate in the mapped top-15 set. Retrieve raw activities and compound structures for mapped candidates among the top 10 disease evidence ranks, up to 10,000 activity rows per target. Record complete versus truncated retrieval explicitly.

## Raw record contract

Retain, where supplied by ChEMBL: molecule ChEMBL ID, canonical input SMILES, ChEMBL target ID, assay ID, standard endpoint/type, measured standard value, standard units, relation operator, pChEMBL, activity/document IDs, assay type, assay description, BAO endpoint/format/label, target identifiers, and the complete source activity JSON. Do not discard activity rows for missing structures, missing endpoints, censored relations, or repeated compounds; preserve them and assign usability/rejection state during deterministic processing.

Exact raw HTTP responses are content-addressed and checksum-verified in `data/raw/http-cache`. Dataset manifests contain response request/response hashes, timestamps, source URLs, row counts, target mapping, extraction cap/completeness, and the raw dataset SHA-256. Per-record source activity IDs link rows to the retained ChEMBL payload; target-wide request references are stored once in the sidecar manifest rather than repeated in every row.

## Deterministic standardization and quality states

- Parse and sanitize input structures with the pinned RDKit environment; remove explicit hydrogens; emit canonical isomeric SMILES and InChIKey.
- Keep all distinct assay measurements even when several rows map to the same standardized structure. Mark repeated standardized structures; resolve replicate/assay grouping only in later endpoint-specific modeling.
- Explicit structure rejections: `MISSING_SMILES`, `INVALID_SMILES`, or a named standardization failure. Keep rejected source rows in the standardized output with reason.
- Activity readiness is separate from structure validity. Report endpoint, value, units, relation, assay metadata and pChEMBL availability. Exact measurements, left/right-censored measurements, missing values, unsupported units, and incompatible assay contexts are counted separately.
- The configurable physicochemical/PAINS/reactive chemistry gates in [`OPTIMIZATION_POLICY.md`](OPTIMIZATION_POLICY.md) are candidate triage policy, not assertions of biological safety and not silent filters on ChEMBL training data.

## Endpoint strata and potency labels

Choose endpoints from the actual selected-target ChEMBL distribution under [`OPTIMIZATION_POLICY.md`](OPTIMIZATION_POLICY.md): valid comparable pChEMBL; then direct-binding Ki/Kd; inhibition IC50; mechanism-appropriate EC50. Keep distinct endpoints, assay formats, and mechanisms separate unless documented assay normalization supports combination. Preserve censoring. Report per-target/per-stratum counts and distribution statistics before proposing a target-specific threshold. No universal potency cutoff is allowed.

## Leakage-resistant splits

Do not create training/evaluation splits until target selection and sufficient target-specific activity data have passed review. Then split after structure normalization and duplicate identity resolution, keeping standardized compounds and scaffold/series groups from crossing partitions; additionally group assay/document replicates where they could leak assay-specific signal. Freeze a deterministic split manifest with seed, data hash, strategy, assignments, and endpoint-stratified counts. A random split may be reported only as a diagnostic baseline. If data are too sparse for a stratum, report it as non-evaluable instead of pooling incompatible endpoints.

## Dataset status semantics

- `COMPLETE`: retrieved rows equal the ChEMBL-reported activity total for the query scope; this does not imply scientific suitability.
- `TRUNCATED`: retrieval hit the configured cap before the reported total; analysis is partial and must be labeled.
- `BLOCKED`: target mapping, retrieval, provenance, or structure coverage prevents the requested downstream use.
- `PROVISIONAL`: evidence-ranked candidate only; target selection is not approved.
- `READY_FOR_REVIEW`: enough auditable observations exist to review the target/endpoint, not a declaration that training is approved.
- `READY_FOR_TRAINING`: permitted only after target/endpoint approval, sufficient data quality, leakage-resistant split, and validated predictors satisfy their evaluation gate.

No status should be upgraded on the basis of an adapter, mock, smoke sample, or row count alone.
