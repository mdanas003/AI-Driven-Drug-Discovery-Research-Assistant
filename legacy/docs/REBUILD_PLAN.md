# Satori — rebuild plan

**Date:** 2026-10-25 · **Status:** proposed, not approved
**Companion:** [TECH_STACK_RESEARCH.md](TECH_STACK_RESEARCH.md)

---

## 0. What we are building and how we will know it works

**Product:** an integrated, auditable target campaign — disease in, a ranked and defensible candidate chain out, every stage carrying its confidence state, data lineage and human decision record. Models are swappable inputs, not the product.

**Headline claim to be proven:**

> Using only evidence available before year *T*, Satori ranks targets that were *subsequently* clinically validated for that disease into the top *K*, across *N* diseases — and does so better than the free Open Targets association score alone.

That last clause is the whole thing. **The baseline is the product's existence test.**

### 0.1 The leakage trap — read this before anything else

Open Targets association scores **incorporate known-drug evidence as a datatype**. A target with an approved drug scores highly *because* it has an approved drug.

So a naive time-split is circular: rank 2018 targets with a score that already encodes the 2023 answer, and you "predict" what you were told. The benchmark would be meaningless, and any reviewer or technical diligence will find it in ten minutes.

Three controls, enforced in code, not discipline:

1. **Use the dated Open Targets release**, not the current API. The 2018 release, not today's data filtered to 2018.
2. **Strip the `known_drug` datatype** from every score used for ranking, at every cutoff. Report scores with and without it so the effect is visible.
3. **Assert no post-cutoff data enters a run.** Every record carries a source release date; the harness fails the run if any record post-dates the cutoff. This is a test, not a convention.

### 0.2 Kill criteria — agreed now, while it is cheap to be honest

- If the full chain does not beat the **known-drug-stripped Open Targets score** on Recall@50, the integration thesis is wrong and we stop and rethink. This is tested at the **end of Phase 2**, not at the end of the project.
- If a stage cannot reproduce its published benchmark, it ships disabled, not degraded.
- If the benchmark can only be made to work by tuning on the test diseases, it has failed. Hold out diseases from the start.

---

## 1. The architectural consequence of the time-split claim

This is the decision that shapes the foundation, and it cannot be retrofitted.

**Live REST APIs return current data. A time-split claim needs dated release archives.** These are different ingestion mechanisms, and the old codebase has only the first.

Every source therefore implements two paths:

```python
class SnapshotSource(Protocol):
    def live(self) -> Payload: ...                    # current state, for real campaigns
    def as_of(self, date: date) -> Payload: ...       # latest release <= date, for validation
    def releases(self) -> list[Release]: ...          # (id, date, uri, sha256)
```

Most sources support this natively — Open Targets publishes dated releases, ChEMBL is versioned (CHEMBL33/34/35…), UniProt and DepMap are release-tagged, PDB entries carry deposition dates, ClinicalTrials.gov records carry phase-transition dates.

**Every cached record is stamped with its source release date, not just a retrieval timestamp.** That one field is what makes the headline claim provable, and adding it later means re-ingesting everything.

### Ground truth

Labels come from **ClinicalTrials.gov phase transitions**, **ChEMBL `drug_mechanism` with `first_approval`**, and **Open Targets known-drug evidence with dates**. A positive is: *target X reached Phase II or beyond for disease Y in year Z > T*. Phase II is the threshold — Phase I says a molecule was safe, not that the target was right.

---

## 2. Project structure

```
satori/
├── pyproject.toml                   # uv-managed, Python 3.12
├── docs/
│   ├── ARCHITECTURE.md
│   ├── VALIDATION_PROTOCOL.md       # the benchmark, frozen
│   ├── CLAIMS_POLICY.md             # what we may and may not say in output
│   └── science/{DATASET_SPEC,OPTIMIZATION_POLICY}.md
├── src/satori/
│   ├── core/
│   │   ├── types.py                 # Pydantic v2: Provenance, Confidence, Evidence
│   │   ├── status.py                # BLOCKED/UNAVAILABLE/TRUNCATED/COMPLETE — enforced in types
│   │   ├── hashing.py
│   │   └── errors.py
│   ├── http/
│   │   ├── client.py                # retry classification, release-stamped cache
│   │   ├── cache.py                 # content-addressed
│   │   └── ratelimit.py             # per-host token bucket
│   ├── sources/                     # one per data source, all SnapshotSource
│   │   ├── base.py  registry.py     # release catalog with checksums
│   │   ├── opentargets.py  chembl.py  uniprot.py
│   │   ├── reactome.py  string_db.py  depmap.py  gwas_catalog.py
│   │   ├── pdb.py  alphafold.py
│   │   └── clinicaltrials.py        # labels
│   ├── chem/
│   │   ├── standardize.py           # rdMolStandardize, pipeline version recorded
│   │   ├── descriptors.py  triage.py  splits.py
│   ├── stages/                      # pure functions, one per chain stage
│   │   ├── s01_disease.py … s16_clinical_context.py
│   ├── models/                      # swappable adapters — no business logic
│   │   ├── base.py                  # capability, version, licence, citation, benchmark
│   │   ├── boltz2.py  vina.py  p2rank.py  fpocket.py  admet_ai.py
│   │   └── registry.py              # fails closed when a checkpoint is absent
│   ├── compute/
│   │   ├── local.py
│   │   └── serverless.py            # Modal/RunPod, per-second GPU
│   ├── pipeline/                    # Dagster
│   │   ├── definitions.py  resources.py
│   │   ├── assets/                  # one asset per stage
│   │   └── partitions.py            # (disease × as_of_date) ← the key design choice
│   ├── campaign/
│   │   ├── model.py  decision.py  report.py
│   ├── validation/                  # the proof machinery — a package, not a test dir
│   │   ├── labels.py                # ground truth from CT.gov + ChEMBL approvals
│   │   ├── timesplit.py             # the as-of harness
│   │   ├── leakage.py               # strips known_drug; asserts no post-cutoff records
│   │   ├── baselines.py             # OT-score and random baselines
│   │   └── metrics.py               # Recall@K, MRR, enrichment, bootstrap CIs
│   ├── api/  cli/
├── benchmarks/
│   ├── definitions/                 # frozen: diseases, cutoffs, held-out set
│   └── results/                     # committed, dated, reproducible
├── tests/
└── infra/
```

### Four decisions worth defending

**Dagster partitions are `(disease × as_of_date)`.** Time-split stops being a special mode and becomes a dimension of every run. The same assets serve production campaigns (`as_of = today`) and validation runs (`as_of = 2018-01-01`). One code path, so validation can never drift from the product. This is the single highest-leverage structural choice in the plan.

**Dagster at all**, rather than hand-rolled orchestration. Software-defined assets give lineage, materialization history and hashing as framework primitives — the old repo's entire provenance apparatus was a hand-built version of this, and rebuilding it by hand is the largest avoidable cost here.

**`validation/` is shipped code, not a test directory.** The proof is a product feature; customers will re-run it.

**`stages/` are pure functions; Dagster assets wrap them.** Stages stay unit-testable without the orchestrator, and the orchestrator stays replaceable.

---

## 3. Phases

Ordered by **risk retired per week**, not by chain order. The existence test lands at the end of Phase 2.

### Phase 0 — Foundation and the harness *(large)*

Skeleton, `core/`, `http/` with release-stamped caching, the `SnapshotSource` contract, source release registry with checksums, Dagster scaffolding with the two-dimensional partitioning, and **`validation/` built before the thing it validates** — labels, leakage controls, metrics, and the two baselines.

*Done when:* the random and OT-score baselines produce a scored, reproducible benchmark table on the frozen disease set. No chain yet — just the ruler.

Building the ruler first is deliberate. It defines "done" for every later phase, and it makes the Phase 2 kill criterion executable rather than aspirational.

### Phase 1 — Stages 1–3, as-of capable *(medium)*

Disease → genes → proteins, against dated releases. First end-to-end time-split run.

*Done when:* the chain reproduces the OT-score baseline exactly when configured to use only that signal. Reproducing the baseline proves the harness is wired correctly before we try to beat it.

### Phase 2 — Stages 4–6, and the existence test *(large)*

Pathways (Reactome, STRING), tractability (Open Targets buckets — free, high-value, currently unused), validation evidence (DepMap, GWAS Catalog, HPA). Combined into a ranking.

*Done when:* **the chain beats the known-drug-stripped OT baseline on Recall@50 with a bootstrap confidence interval that excludes zero, on held-out diseases.**

This is the milestone that decides whether the company exists. Everything before it is infrastructure; everything after it is building on a proven thesis. If it fails, we have spent weeks rather than a year, and we will have learned something true.

### Phase 3 — Stages 7–8, GPU enters *(large)*

Structure via Boltz-2 (MIT) with AlphaFold DB and RCSB lookup; preparation via PDBFixer/Meeko; pockets via P2Rank and fpocket with cross-method agreement as a confidence signal. Serverless GPU through `compute/serverless.py`, billed per second.

*Gate:* redock a known co-crystallized ligand into its own prepared receptor, RMSD < 2 Å. Low-pLDDT AlphaFold pockets cannot reach `docking_ready` — this is the most common quiet failure in structure-based work.

*Time-split note:* structures must respect the cutoff too. A 2022 PDB deposition is not available to a 2018 run.

### Phase 4 — Stages 9–12 *(large)*

Libraries (ChEMBL, PubChem, ZINC-22, COCONUT), standardization, triage, conformers. Docking via Vina/smina on CPU or Boltz-2 co-folding on GPU. Affinity via **Boltz-2's affinity head** — this is where the old repo's untrainable affinity model is replaced by something that exists and is licensed.

*Gate:* decoy enrichment (DUD-E/DEKOIS), reporting EF1% and AUC. A docking setup that fails enrichment ships labelled as failing.

### Phase 5 — Stages 14–15 *(medium)*

ADMET-AI and Chemprop; ProTox/Tox21. Every prediction ships with training distribution, validation metric and applicability-domain verdict. **No invented cutoffs** for hERG, hepatotoxicity, mutagenicity, CYP or BBB — predictions are exploratory objectives, never pass/fail safety gates.

*Gate:* reproduce each model's published benchmark on its own public test set before enabling it.

### Phase 6 — Stage 13 and the campaign product *(medium)*

Deterministic optimization (mmpdb, R-group, Free-Wilson) and separate Pareto objectives — no scalarization. The **decision record**: reviewer, timestamp, rationale, dossier hash; `selected_target_id` never auto-filled. `satori verify` replays a campaign offline from recorded hashes so a reviewer can *execute* the provenance claim.

This is the phase that produces the thing a startup actually sells.

### Phase 7 — Generative tier *(unscheduled)*

De-novo generation, generative optimization. Flow-matching SBDD has overtaken diffusion, and **synthesizability-aware generation** matters more than architecture — a generator that only emits makeable molecules beats a marginally better one. Worst validated-result-per-effort ratio in the chain, and the easiest place to overclaim. Not before Phase 6 ships.

### Stage 16 — never produced

Satori retrieves trial and approval records as **context**. It does not produce clinical validation. The chain's terminal output is a prioritized, auditable research hypothesis for experimental testing.

---

## 4. Compute and cost

Development runs on free tiers — Kaggle (~30 GPU-h/week) is the most reliable, Lightning (~22 h/month) and ZeroGPU (minutes/day) supplement. **These are development allowances, not a user tier.** Phase 3 is the first phase needing GPU, which buys time to measure real per-run cost before any user depends on it.

Production uses **serverless GPU with per-second billing** so cost is per job — the same unit you bill on. Measure Boltz-2 per-complex cost in Phase 3 and publish it internally; it is the unit economics and nothing else is knowable without it.

---

## 5. Claims policy, enforced in code

`docs/CLAIMS_POLICY.md` and `core/status.py` make these structural rather than editorial:

- Boltz-2 affinity is a **prediction with a published correlation**, not a measured Kd. Ships with its benchmark number and applicability domain.
- Docking scores are **not affinity**, regardless of scoring function.
- `BLOCKED` / `UNAVAILABLE` appear in output, never silently omitted.
- Satori **never auto-selects a target**. It ranks; a human decides; Satori records.
- Generated molecules are hypotheses; unsynthesizable ones are labelled.
- No prediction becomes a boolean safety verdict.

Standing check: open the report and confirm a reader who has never read `docs/science/` cannot mistake any of it for validated science.

---

## 6. What to settle before Phase 0

1. Boltz-2's real FEP+ correlation, from the paper
2. **Chai-1's licence** — sources directly contradict each other
3. Modal/RunPod current free tier and per-second pricing
4. The frozen benchmark set: which diseases, which cutoff years, which held out
5. Whether Open Targets dated releases reach back far enough for the chosen cutoffs — **this gates the headline claim** and should be checked first
6. fpocket's licence if the product is commercial
7. Whether a newer co-folding model supersedes Boltz-2
