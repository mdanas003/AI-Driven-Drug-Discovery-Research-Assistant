# Step 6 — multi-task learning across the kinome

**Status:** plan, nothing built yet. Written before any code, so the success criterion cannot drift to match whatever we get.

## 1. Why this step, and why only now

Two earlier stages produced negative results, and together they narrowed the problem down to this one:

- **Step 5b** ran six model and representation combinations under one protocol. Bagged trees, boosted trees and a similarity kernel all landed at R² 0.60 ± 0.03. When independent approaches converge, the model class is not the constraint.
- **Step 5c** tested whether label noise was the constraint. Weighting by measurement quality changed nothing beyond the run-to-run spread, and training on only the clean 9% of labels was clearly *worse* (R² 0.447 against 0.532). Quantity beat cleanliness.

What remains is **coverage**: the model fails on chemical series it has never seen. 8,450 molecules against one protein is a thin slice of chemistry. The human kinome shares a conserved ATP-binding site, so a compound's behaviour against one kinase genuinely carries information about the others, and the same chemical series appears across many of them.

That makes "train across many targets" the one standing hypothesis with evidence behind it rather than enthusiasm.

## 2. The claim to be tested, and when we stop

> For a chemical series never seen in training, does adding other kinases' data improve prediction against EGFR?

**Primary metrics**, in order:
1. **Top-10% hit rate** — of the molecules the model ranks highest, what share are genuinely among the most potent. The decision-relevant number, and the one not capped by label noise.
2. **Spearman** — ranking quality overall.
3. R² and MAE, secondary. Step 5b showed absolute error is already inside the data's own 0.775 disagreement, so large gains here are not expected and would be grounds for suspicion rather than celebration.

**Success:** multi-task beats single-task on the identical held-out series by **more than the larger of the two run-to-run spreads**, across 5 repeats.

**Kill criterion:** if no target selection beats single-task by more than that spread, we write it up as a negative result and stop, exactly as in Step 5c. A plausible idea that fails cheaply is a good outcome; one that fails expensively after we have built a product on it is not.

## 3. The leakage trap, which is the whole difficulty

Single-task leakage had one route: a test molecule's close relatives sitting in training. Step 4's clustering closed it. Multi-task opens **two more**, and both would produce a flattering number.

| Route | What happens | Why it is fatal |
|---|---|---|
| **Same molecule, another target** | Molecule M is held out for EGFR, but M's CDK2 and ABL1 rows are in training | Kinase potencies correlate strongly for promiscuous inhibitors. The model can recover M's EGFR potency from having memorized M elsewhere — it has seen the answer, under a different label |
| **Close relative, another target** | M itself is excluded, but a molecule 0.9 similar to M remains in another target's training data | Exactly the leak Step 4 closed for one target, re-entering through the side door |
| **Different test set** | Multi-task scored on a different set of molecules than single-task | Then the comparison measures nothing, however rigorous each half is |

### The procedure, per repeat

1. Cluster the **EGFR** wild-type molecules at Tanimoto 0.6 — the 1,864 series from Step 4.
2. Hold out whole series until 20% of EGFR molecules are held out. This is the test set **T**, about 1,690 molecules, **identical for both models**.
3. **Single-task training:** EGFR rows not in T. This is exactly the Step 5 baseline, re-run, not quoted from memory.
4. **Multi-task training:** every row for every selected target, minus
   - every row whose molecule is in T, and
   - every row whose molecule is **within 0.6 Tanimoto of any molecule in T**, across all targets.
5. Train both, score both on T using EGFR labels only.

Step 4 of that list is the expensive-sounding part, and it is not: measured throughput is **14.5 million Tanimoto comparisons per second**, so filtering a million-molecule pool against 1,700 held-out molecules takes **about 2 minutes per repeat**. The rigorous version is affordable, so there is no excuse for an approximation.

### The leak is real, and it is large

Measured on the data already on disk, using the EGFR mutant set as the stand-in for "another target":

| | |
|---|---|
| Mutant rows whose molecule **also appears** in the wild-type set | **1,722 of 4,060 (42%)** |
| Mutant rows removed by the strict 0.6 similarity filter, for one repeat | 1,216 (30%) |
| Mutant rows surviving as genuine extra training data | 2,844 |

Without the filter, **42% of the extra rows would hand the model a molecule it is about to be tested on**, labelled with a strongly correlated potency against a near-identical protein. This is not a hypothetical risk to be mentioned in a limitations section; it is the default outcome of the obvious implementation, and it would produce a large, entirely spurious improvement.

The strict filter costs 30% of the extra data. That is the price of a number worth believing.

### A test that must pass before any result is believed

Build the filter, then **assert it**: after constructing the multi-task training set, verify that no training molecule is within the cutoff of any test molecule. If that assertion ever fails, every number from the run is void. This goes in the test suite, not in a comment.

## 4. Which targets — staged, to find *where* transfer comes from

One number tells us whether it worked. Three tell us why.

| Setting | Targets | What it answers |
|---|---|---|
| **A. Mutants** | EGFR wild-type + the 13 mutant variants we already have | Does the nearest possible relative help? Needs no new download |
| **B. Tyrosine kinases** | EGFR + the tyrosine kinase branch | Does the close family help, where the binding site is most similar? |
| **C. Whole kinome** | EGFR + every kinase with enough data | Does distant kinase data help, or does it dilute? |

If transfer is real, the gain should fall off with kinome distance: A ≥ B ≥ C. If C beats A, the benefit is sheer data volume rather than biological relatedness, which is a different and interesting finding. Setting A runs today at no download cost, which makes it the first thing to try.

**Setting A is probably underpowered, and that is worth saying in advance.** After the leakage filter it adds about 2,844 rows to EGFR's 6,760 — a 42% increase in training data. Against a run-to-run spread of ±0.02 R², a gain that modest may be real and still undetectable. So Setting A is a plumbing test and a direction check, not the verdict: if it shows nothing, that does not refute the hypothesis, and the honest reading is "too small to tell". Only Settings B and C carry enough data to settle anything, which is also the order in which the download cost arrives.

## 5. Data: how much, how to get it, what it costs

Measured facts, not estimates:

- **The kinome:** 491 reviewed human protein kinases in UniProt, mapped to ChEMBL targets by accession.
- **Volume:** see §5.1 below, surveyed per target.
- **API throughput:** the EGFR download ran at roughly **3,300 usable rows per minute** (26,600 rows in 8 minutes). So 250,000 rows is about **75 minutes**; the whole kinome is a **several-hour** job.
- **API reliability, not throughput, is the binding constraint.** This is the finding that changed the plan, and it was learned the hard way. Two attempts to survey *just the row counts* for 451 targets — about 500 small requests, no bulk data — both failed:
  - Attempt 1 died after 10 minutes on three consecutive 60-second read timeouts.
  - Attempt 2, made politer (0.3s between calls, 120-second timeout, six retries, progress saved every 25 targets), **stalled for 13 hours** and then died with a connection reset mid-response.

  If 500 small requests cannot be completed reliably, then the hundreds of thousands needed for multi-target data are out of the question. No amount of retry logic fixes a server that will not answer.
- **Bulk download:** ChEMBL 37's SQLite release is **5.76 GB compressed**, roughly 25–30 GB extracted. The C: drive has **45 GB free**, so it fits with little room to spare. One download, then instant local SQL, pinned to a named release.

**Decision, revised: take the bulk route for Step 6.** The original plan was to use the API for a shortlist and keep the dump in reserve. The survey settled that: 13 hours spent failing to fetch *row counts* is the argument. Step 3's per-target API path stays as it is — it works well for one target and keeps the project runnable by anyone without a 6 GB download — but anything kinome-scale reads from the local dump.

Consequences worth noting now:

- **Disk must be checked first.** 45 GB free against ~35 GB needed. The extraction should go to a drive with room, and the archive should be deleted afterwards.
- **Provenance gets simpler, not harder.** A named release (`chembl_37`) is a stronger statement of "which data produced this result" than a retrieval timestamp against a live API.
- **The reproducibility story changes.** Step 3's results can be regenerated by anyone with internet; Step 6's will need the dump. The plan should ship the SQL queries and the derived per-target CSVs so that the expensive part need only happen once.

### The retry bug this uncovered

The survey's failure exposed a real defect in `satori/chembl.py`, now fixed. `get_json` retried only `ConnectionError` and `Timeout`. A response that stops mid-body arrives as `ChunkedEncodingError`, which is neither, so it propagated and killed the run — after 13 hours. Long jobs meet failure modes that short ones never show. The client now retries everything except an HTTP 4xx (where the request itself is wrong and a retry cannot help), and there are tests for each failure mode, including the mid-body truncation that caused this.

**The fetch must be resumable, per target.** The survey run behind §5.1 made about 500 requests and hit two transient failures — a dropped TLS connection and a closed connection — both of which its retry logic absorbed. A multi-target download is an order of magnitude longer, so failures are a certainty, not a risk. Step 3's existing per-target cache already gives us the right granularity: each target's raw rows land in their own file, a re-run skips what is already on disk, and a failure costs one target rather than the whole job. No new mechanism needed, but the loop must be written to use it that way rather than holding everything in memory until the end.

### 5.1 What the survey established, and what it could not

**Established:**

| | |
|---|---|
| Reviewed human protein kinases in UniProt | **491** |
| Mapped to a human single-protein ChEMBL target by accession | **451** |

The mapping route works and is cheap: one UniProt query for the kinome, then ChEMBL target lookups by accession in batches of 20.

**Not established:** per-target measurement counts. Both attempts to collect them died in the API, as described above. So the shortlist in §4 cannot be drawn up yet, and **the first task of Stage 6.1 is to obtain these counts from the bulk dump** — one SQL query over `activities` joined to `assays` and `target_dictionary`, filtered to IC50 with a pChEMBL value, grouped by target. Seconds locally, against hours and two failures remotely.

Until then, the only volume figure we can rely on is EGFR's own: 26,600 raw IC50 measurements, 16,084 usable, 8,450 wild-type molecules. EGFR is one of the most heavily studied kinases, so it is close to an upper bound rather than typical — most of the 451 will have far less, and a good number will have too little to contribute anything.

## 6. Models, in the order that risks least

1. **Single-task baseline, re-run.** Not the remembered 0.59; the same code path, same splits, same repeats, so the comparison is like-for-like.
2. **Pooled gradient boosting with target identity.** Molecule features alongside a target indicator. Cheap, interpretable, and Step 5b showed boosting matches anything else here at a tenth of the cost. If pooling helps at all, this should show a hint of it.
3. **Shared representation with per-target outputs.** Only if (2) shows promise. This is where multi-task genuinely earns its reputation in the literature, because the shared representation is learned rather than bolted on, and it is the first point in this project where a neural network and a GPU would be justified by evidence rather than fashion.

### The trap in "profile features"

A tempting approach is to feed each molecule's measured potencies against *other* kinases in as features. It would work well and it would be misleading, because **those measurements do not exist for a molecule nobody has tested yet**. It answers a different question: "given this compound's screening profile, predict its EGFR potency" — useful for prioritising an already-screened collection, useless for a new structure.

If we build it, it ships as a separate, differently-labelled capability, never mixed into the virtual-screening numbers. This is the single easiest way for a multi-task result to be oversold, including by accident.

## 7. Work order

| Stage | Work | Settles |
|---|---|---|
| 6.0 | **Setting A on data already on disk** — the mutant set, leakage filter and all | Whether the plumbing is right, before any download. Costs nothing and risks nothing |
| 6.1 | Bulk dump, then per-target counts by SQL | What data exists, and the shortlist §4 needs |
| 6.2 | Extract the selected targets to release-stamped CSVs | Data on disk in the Step 3 format, reusable |
| 6.3 | The leakage-proof split, plus the assertion test | That any later number can be believed |
| 6.4 | Setting A (mutants), free and immediate | Whether transfer happens at all |
| 6.5 | Settings B and C | Where transfer comes from, and whether it is relatedness or volume |
| 6.6 | Write-up, positive or negative | The result, with its spreads and its protocol |

Each stage ends with something runnable and a number with its spread. No stage depends on the next one working.

## 8. What would make this plan wrong

Worth writing down now, so it is not rationalised later:

- **Target identity may be the wrong conditioning.** A one-hot indicator cannot express that EGFR is more like HER2 than like CDK2. If pooled training fails, the next thing to test is binding-site similarity as a feature, not a bigger model.
- **The test set stays small.** 1,690 molecules in about 450 series, and the Step 5 spread of ±0.02 R² is the floor for detecting any gain. A real but small improvement may be undetectable at this size, and we should say so rather than chase it with more seeds.
- **More data may dilute rather than help.** If EGFR's 8,450 rows become 1% of the training set, the model may fit the average kinase and do worse on EGFR. Per-target weighting is the obvious response, and would need the same honest treatment Step 5c gave label weighting.
- **The 6 GB download may not be worth it.** Stage 6.0 runs on data already here. If it shows no hint of transfer — remembering that it is underpowered and cannot refute the hypothesis by itself — then it is worth pausing to reconsider before spending the download and the disk. The cheapest stage comes first precisely so this decision can be made on evidence.
