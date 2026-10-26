# Satori — tech stack research and strategy

**Date:** 2026-10-24 · **Status:** research input for the rebuild decision, not an approved plan

My training data ends mid-2026, so everything below was web-researched today. Sources are listed at the end. **Several figures come from vendor blogs and aggregators that contradict each other — those are flagged inline and must be verified before you commit to them.**

---

## 1. Three findings that change the strategy

### 1.1 Boltz-2 collapses three of your stages into one model, under MIT licence

The most consequential release for this project. Boltz-2 does co-folding **and** binding-affinity prediction in a single model, reportedly reaching ~0.62–0.66 Pearson correlation on FEP+ benchmark subsets — approaching free-energy-perturbation accuracy at a tiny fraction of the compute. *(Two sources give different numbers for the same benchmark; check the paper.)*

Why this matters: your stages **7 (structure), 10 (docking), and 11 (affinity prediction)** were three separate problems with three separate blockers. Boltz-2 addresses all three, and **MIT licence means commercial use is permitted** — unlike AlphaFold 3, whose weights remain under a custom non-commercial licence.

This single fact retires the biggest 🔴 blocker in the earlier plan. Our own affinity model was blocked on licensed data, a frozen split, training, and calibration. We no longer need to train one.

Caveat: Boltz-2 reportedly **trails AF3 on structure accuracy**, particularly antibody–antigen and unseen antigens. For small-molecule work that matters less than for biologics.

Commercially-usable alternatives: **Protenix** (ByteDance, Apache-2.0, AF3 reproduction — superiority claims are self-reported), **OpenFold3**, **ESMFold**. **Chai-1's licence is disputed across sources** (Apache-2.0 vs proprietary+API) — verify directly before building on it.

### 1.2 Your proposed business model is already a funded company

This is the finding you most need before writing code.

**Tamarind Bio** raised a **$13.6M Series A**, hosts **200–300+ models**, and reports roughly **100 biotech customers including large pharma**. Its catalogue is exactly the list you'd pick: AlphaFold, Boltz, Chai, ESMFold, RFdiffusion, ProteinMPNN, DiffDock, GROMACS. Entry is a **free tier of ~10 jobs/month**, then paid. *(Paid pricing is inconsistent across sources — one lists $99/month, another $50,000/year. Only the free tier and "contact sales" are consistently supported. Treat both numbers as unverified.)*

"Host open models and charge per use" is a funded, occupied, no-code market with a meaningful head start. **If Satori's pitch is "we run Boltz for you," Satori loses.** The models are open-weight; running them is not defensible.

At the other end of the chain, target identification is enterprise-gated: **PandaOmics** (Insilico) and **BenevolentAI** both price as "custom," and BenevolentAI is described as partnership/licensing rather than self-service. Worth noting as a caution on target-ID claims generally: BenevolentAI's AI-identified target produced BEN-2293, which **failed its Phase 2 primary endpoints**.

**The gap between these two ends is where Satori fits.** Tamarind starts from *"I have a protein."* PandaOmics ends at *"here is a target."* Nobody runs disease → gene → protein → pathway → tractability → structure → pocket → candidate as **one auditable campaign with a decision record**. That is a different product from a model zoo, and it is the one your existing stages 1–3 work already points at.

### 1.3 Free GPU credits will not carry a public product

Researched honestly, the free tiers are demo volume:

| Provider | Free allowance | Reliability of figure |
|---|---|---|
| HF ZeroGPU | ~3.5–5 min/day (2 min unauthenticated) | sources disagree |
| Lightning AI | ~15 credits/mo ≈ 22 h on T4 | an older source claims 80 h — likely wrong |
| Kaggle | ~30 GPU-h/week | most consistent option |
| Colab | no published quota, "fluctuates" | Google's own wording |

One guide puts it plainly: permanent free inference tiers are **demo volume only**.

A Boltz-2 complex takes minutes of A100 time. ZeroGPU's daily allowance is a handful of runs. **Free credits are enough to build and validate the pipeline; they cannot serve users.** Your instinct — free during development, pass-through pricing at launch — is right, but the free phase must be scoped as *development*, not as a free user tier. Budget for real inference cost from the first external user.

---

## 2. Recommended stack, by layer

Licence column is the one that matters commercially. 🟢 free/CPU · 🟡 GPU needed · 🔴 still blocked

| # | Stage | Primary choice | Licence | Compute |
|---|---|---|---|---|
| 1–2 | Disease → genes | Open Targets Platform GraphQL; MONDO/EFO | open | 🟢 |
| 3 | Proteins | UniProtKB REST; ESM-2/ESM-C embeddings | open / check ESM-3 terms | 🟢/🟡 |
| 4 | Pathways | Reactome ContentService, STRING, GO, WikiPathways | open | 🟢 |
| 5 | Tractability | Open Targets tractability buckets, ChEMBL target class | open | 🟢 |
| 6 | Target validation evidence | DepMap, GWAS Catalog, Human Protein Atlas | open | 🟢 |
| 7 | Structure | **Boltz-2**; Protenix / OpenFold3; AlphaFold DB lookup | MIT / Apache-2.0 | 🟡 |
| 8 | Pocket | P2Rank (MIT), fpocket (GPL — check), holo-ligand pockets | mixed | 🟢 |
| 9 | Molecules — retrieval | ChEMBL, PubChem, ZINC-22, COCONUT, Enamine REAL | open | 🟢 |
| 9 | Molecules — generation | Flow-matching SBDD (OMTRA, LDDM, PocketVE) | per-repo, verify | 🟡 |
| 10 | Docking | Vina/smina (CPU), gnina/DiffDock-L (GPU), or **Boltz-2 co-fold** | open | 🟢/🟡 |
| 11 | Affinity | **Boltz-2 affinity head**; OpenFE for FEP where justified | MIT | 🟡 |
| 12 | Virtual screening | composition of 9+10+11 | — | 🟡 |
| 13 | Lead opt — deterministic | mmpdb, R-group, Free-Wilson (RDKit) | open | 🟢 |
| 13 | Lead opt — generative | REINVENT4, SynFlowNet | Apache-2.0, verify | 🟡 |
| 14 | ADMET | ADMET-AI (TDC-benchmarked), Chemprop | open | 🟢 |
| 15 | Toxicity | ProTox, Tox21 via DeepChem | open | 🟢 |
| 16 | Clinical context | ClinicalTrials.gov API, OT known-drugs | open | 🟢 |

### Notes on the generative layer

You asked specifically what is newer than VAE/GAN/graph/diffusion/transformer. The answer from current literature: **flow matching has largely overtaken diffusion** for pocket-conditioned design. OMTRA (multi-task flow matching) reports SOTA on pocket-conditioned de-novo design and docking — though the paper itself notes that gains from large-scale pretraining and multi-task training are **modest**. PocketVE pushes variance-exploding diffusion; LDDM and PocketXMol are unified models covering generation and docking in one network.

The more important trend than architecture: **synthesizability-aware generation**. LDDM is explicitly framed as *synthesizable* SBDD. The known failure mode of 3D generative chemistry is producing molecules that score well and cannot be made — and one review notes high docking scores can be misleading when poses are strained. A generator that only emits synthesizable molecules is worth more than a marginally better architecture.

I found nothing on Bayesian flow networks for SBDD in current results; if that direction interests you it needs its own search.

**Recommendation: do not build generation early.** It is the stage with the worst validated-result-per-effort ratio, and it is where overclaiming is easiest.

---

## 3. Platform architecture

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 | the entire scientific ecosystem |
| Dependencies | `uv` | fast, lockfile-native |
| Schemas | **Pydantic v2** | validation at every boundary; the current dataclasses can't enforce the status vocabulary |
| Orchestration | **Dagster** | software-defined assets give lineage, materialization history and hashing **as a framework primitive** — this maps 1:1 onto the provenance requirement instead of hand-rolling it |
| API | FastAPI | already in use, correct choice |
| Database | Postgres + SQLAlchemy | SQLite is single-host; multi-user needs this |
| Artifacts | S3-compatible (MinIO local, R2/B2 in prod) | content-addressed, cheap egress |
| Data versioning | DVC or LakeFS | dataset snapshots that survive ChEMBL releases |
| **GPU execution** | **Modal or RunPod serverless** | **per-second billing, zero idle cost — this is what makes pass-through pricing work.** Verify Modal's current free tier directly; my search returned nothing on it |
| Frontend | Next.js + React | |
| Result analytics | DuckDB | fast local querying over campaign outputs |
| Tracing | OpenTelemetry | |

**The Dagster recommendation is the one I'd defend hardest.** The whole provenance apparatus in the current repo — stage hashing, manifests, run records — is a hand-built version of what Dagster assets give you for free, with a lineage UI included. Rebuilding that by hand is the single largest avoidable cost in this project.

Serverless GPU is the other structural choice: it makes cost **per job**, which is exactly the unit you'd bill on.

---

## 4. What to sell — recommendation

**Not best-in-class predictions.** The frontier models are open-weight and change every few months. Competing on model quality means re-competing continuously against teams with more GPU, and your output would be a commodity the moment the next checkpoint drops.

**Not a hosted model zoo.** That is Tamarind's business, with $13.6M, ~100 customers, and 200+ models already running.

**Sell the campaign.** The defensible unit is a **target campaign**: one disease in, a ranked and auditable chain out, every stage carrying its confidence state, its data lineage, and its human decision record. Three reasons:

1. **Nobody occupies it.** The model-runner market starts after target selection; the target-ID market stops before structure. The join is empty.
2. **It compounds with use.** A model's advantage evaporates on the next release. A campaign history, a decision record, and a reproducible audit trail accumulate and are costly to migrate away from.
3. **It is what gets scrutinized.** Investor diligence, IP filings, regulatory submissions, and reviewers all ask *"where did this come from and who decided it?"* — a question no model answers and every drug programme must.

The models stay **swappable inputs**. When Boltz-3 ships, you upgrade an adapter; your product doesn't change.

**First wedge inside that:** disease → tractable, structurally-ready target, with the full evidence trail. It uses stages 1–8, needs little GPU, is the part Tamarind doesn't touch, and is the half the existing codebase already has real work in.

---

## 5. The honesty constraints do not relax

Higher ambition raises the stakes rather than lowering the bar:

- **Boltz-2's affinity output is a prediction with a published correlation, not a measured Kd.** It ships with its benchmark number and its applicability domain, every time.
- **Docking scores remain not-affinity**, even with a better scoring function behind them.
- **No invented cutoffs** for hERG, hepatotoxicity, mutagenicity, CYP or BBB.
- **Generated molecules are hypotheses**, and unsynthesizable generated molecules are labelled as such.
- **Satori never auto-selects a target.** It ranks; a human decides; Satori records.
- **Stage 16 is not a software output.** Satori retrieves trial and approval records as *context*. BEN-2293 is the standing reminder of what an AI-identified target is worth before Phase 2 reads out.

---

## 6. Verify before committing

My search returned contradictory or missing data on these. Do not plan around them unverified:

1. Boltz-2's actual FEP+ correlation — from the paper, not vendor blogs
2. **Chai-1's real licence** — sources directly contradict each other
3. Modal's current free tier and per-second GPU pricing
4. Tamarind's real paid pricing ($99/mo vs $50k/yr is a 500× spread)
5. fpocket's licence, if the product is commercial
6. Whether Boltz-2 or a newer co-folding model is current — an arXiv preprint claims "Pearl-2026.1.dev" beats both AF3 and Boltz-2, with openness and independent validation unestablished
7. Real per-run GPU cost for Boltz-2 at your expected complex size — this is your unit economics and nothing else matters until it's known

---

## Sources

- [Boltz-2 vs AlphaFold3 vs Chai-1 (2026)](https://www.biotech.today/compare/boltz2-vs-alphafold3-vs-chai1-structure-affinity)
- [OpenFold3 vs Boltz 2 vs AlphaFold 3](https://blackthorn.ai/blog/protein-engineering-with-ai/)
- [AlphaFold 3 vs Boltz-2 vs ESMFold](https://purna.ai/blog/alphafold-vs-boltz-vs-esmfold/)
- [Few-step Cofolding with All-Atom Flow Maps](https://arxiv.org/pdf/2606.08375)
- [OMTRA: Multi-Task Generative Model for SBDD](https://arxiv.org/html/2512.05080)
- [LDDM: Unified 3D Generative Model for Synthesizable SBDD](https://github.com/LPDI-EPFL/lddm)
- [PocketVE](https://arxiv.org/pdf/2609.08101)
- [Generative AI in structure-based drug discovery](https://link.springer.com/article/10.1186/s12915-026-02575-x)
- [Tamarind Bio raises $13.6M](https://www.biopharmatrend.com/news/tamarind-bio-raises-136m-to-run-200-ai-and-simulation-models-in-a-no-code-platform-for-bench-scientists-1505/)
- [Tamarind Bio Series A (GEN)](https://www.genengnews.com/topics/artificial-intelligence/tamarind-bio-secures-13-6m-series-a-to-make-ai-more-accessible-for-biology/)
- [Free GPU Cloud Credits: 9 Programs That Changed in 2026](https://www.spheron.network/blog/free-gpu-cloud-credits-2026/)
- [Google Colab Alternatives: 8 GPU Clouds Compared](https://www.spheron.network/blog/google-colab-alternatives-8-gpu-clouds-compared-2026/)
- [9 Best Target Identification AI Tools (2026)](https://lifebit.ai/blog/target-identification-ai-tools/)
- [AI Drug Discovery: What's Working, What's Failing in 2026](https://www.buildmvpfast.com/blog/ai-drug-discovery-clinical-trials-pharma-2026)
- [Insilico Pharma.AI analysis](https://intuitionlabs.ai/articles/insilico-pharma-ai-drug-discovery)
