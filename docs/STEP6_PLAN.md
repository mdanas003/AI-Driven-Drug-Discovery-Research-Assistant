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

---

## 9. Stage 6.1 log: what the plan got wrong

Written as it happened, because a plan that is quietly corrected is no longer a pre-registration.

### Disk: the 45 GB in §5 was stale

By the time the stage started, C: had **27 GB free**, not 45 — against the ~35 GB this needs. The download would have failed partway, and in the worst case filled the system drive.

Two things fixed it. D: has **94 GB free**, so the release lives at `D:\chembl_dump\` and not on C: at all. That also avoids a trap nobody had noticed: the project folder is inside OneDrive, so extracting a 30 GB database anywhere under it would have handed OneDrive 30 GB to sync.

**Lesson worth keeping:** §5 said "disk must be checked first" and the number in it was still four days old. A figure in a plan is a measurement with a date on it, not a constant.

### The UniProt mapping route was unnecessary

§5.1 planned to take UniProt's 491 reviewed human kinases and map them to ChEMBL targets by accession — two web services and a join, and the step whose cost justified the whole download.

The dump makes it free. ChEMBL ships its own protein family tree in `protein_classification`, reachable from a target through `target_components` and `component_class`. So:

| | Planned | Actual |
|---|---|---|
| Define the kinome | UniProt query, 491 kinases, map by accession | `WHERE pc.l3 = 'Protein Kinase'` |
| Define Setting B | separate tyrosine-kinase list | `WHERE pc.l4 = 'TK protein kinase group'` |
| Web requests | ~25 batched, plus failures | **zero** |

This is better than cheaper. The family assignment now comes from the same release as the measurements, so "which kinases" and "which data" cannot drift apart between runs, and the shortlist is reproducible from the release name alone.

### Download throughput, measured

One connection to EBI runs at **about 290 KB/s** — 80 MB in the first five minutes, which puts the 5.76 GB file at roughly **six hours**. A second connection to a different byte range ran at the same speed rather than splitting the first one's bandwidth, and the server advertises `Accept-Ranges: bytes`.

So the download is **six parallel ranged parts**, concatenated and then checked against ChEMBL's published SHA256 (`33c2037...c290d281`). Six, not sixteen, because this is a free public server. The checksum is what makes the trick safe to use: a misordered or short reassembly cannot match it, so the result is either verified or discarded. Expected time is **about 40 minutes**.

### What is not a correction

The §3 leakage procedure, the §4 staged settings and the §6 model order are unchanged. The result and its success criterion were fixed before any of this data existed, and nothing here touches them.

### Code written for this stage

- `src/satori/kinome.py` — read-only connection, the kinome and group queries, per-target extraction, and the shortlist floor.
- `tests/test_kinome.py` — a miniature ChEMBL with the real table and column names, so the SQL is tested without the 5.76 GB file. Includes a non-kinase (thrombin) that must never appear in a kinase query, and a check that the rows feed Step 3's `clean`/`aggregate` unchanged.
- `satori kinome-counts` and `satori kinome-extract`.

**The deliberate non-feature:** `activities_for` does no filtering. It emits the same sixteen columns under the same names the web API returns, and every judgement about what to keep stays in Step 3's `drop_reason`. Two code paths that each decide what counts as a trustworthy measurement will eventually disagree, and then a difference between Step 5's score and Step 6's would be our own two implementations arguing rather than a finding.

### The schema check earned its keep in the first minute

`protein_classification` has **no `l1..l8` columns**. The §9 table above, written before the file finished downloading, says `WHERE pc.l3 = 'Protein Kinase'`, and that query cannot run.

The real table is a parent/child tree with a `class_level` and, usefully, a denormalised full path on every node:

```
protein_class_id  parent_id  pref_name                  protein_class_desc
            1100          6  Protein Kinase             enzyme  kinase  protein kinase
            1285       1100  TK protein kinase group    enzyme  kinase  protein kinase  tk
             130       1285  Tyrosine protein kinase...  enzyme  kinase  protein kinase  tk  abl
```

So the kinome is a path-prefix match rather than a column comparison, and the group name comes from a self-join back up to the level-4 ancestor. The *names* in the plan were right — `Protein Kinase` and `TK protein kinase group` both exist — only the access route was invented.

**The part worth learning from.** Fifteen tests passed against a miniature ChEMBL before the real file arrived, and the miniature had `l1..l4` columns *because that is what the code assumed*. A fixture built from the same mistaken belief as the code under test confirms the belief rather than testing it, and it does so with a green tick. Hand-built fixtures can only check internal consistency; only the real artefact can check the assumption. Hence the four `@needs_release` tests, which skip without the dump and are the ones that caught this.

The level-4 self-join is a `LEFT JOIN` on purpose: one target is classified as a protein kinase with no group beneath it, and it should count as a kinase rather than disappear from the kinome because a display label is missing.

## 10. Stage 6.1 result: the data exists, and there is a lot of it

One query, **26 seconds**, against two API attempts that failed over thirteen hours.

| | |
|---|---|
| Human single-protein kinases with usable IC50 data | **405** |
| Of those, tyrosine kinases (EGFR's own group) | 79 |
| Total molecule-rows available | **266,265** |
| EGFR alone, for comparison | 8,450 wild-type |

The nine Manning kinase groups are all represented, so Setting C genuinely spans the family rather than leaning on one branch.

### The data is extremely concentrated

| Floor on molecules | Setting C targets | molecules | Setting B targets | molecules |
|---:|---:|---:|---:|---:|
| none | 405 | 266,265 | 79 | 128,260 |
| 100 | **201** | **261,348** | **56** | **127,476** |
| 500 | 109 | 239,712 | 39 | 122,748 |
| 2,000 | 41 | 167,729 | 22 | 102,680 |

The top 10 targets hold 28% of all rows, the top 50 hold 69%, and the top 109 hold 90%.

### The floor: 100 molecules

Chosen because it is nearly free. It keeps **98.1%** of all available rows; the 204 targets below it contribute 1.9% between them while each adding a file, a one-hot column and a slice of similarity-filter time. Above 100 the floor starts costing real data — 500 gives up 10% — and below it buys almost nothing.

This is a judgement, so it is written down rather than left to whatever the data happened to contain. It is also not load-bearing: the concentration table shows every floor from 100 to 500 holds 90%+ of the rows, so the result should not depend on which one we picked. If it does, that is itself a finding.

### What Stage 6.1 settles about §4

Setting A was underpowered at **+2,844 rows (+42%)** against a ±0.02 R² detection floor, exactly as pre-registered, and it duly showed nothing. The scale has changed:

| Setting | Extra training rows | Multiple of EGFR's own data |
|---|---:|---:|
| A. Mutants (done, null) | 2,844 | 1.4× |
| **B. Tyrosine kinases** | ~119,000 | **15×** |
| **C. Whole kinome** | ~253,000 | **31×** |

Settings B and C are not underpowered. If pooling related-protein data helps at all, 15× and 31× is where it becomes visible — and if it still shows nothing at 31×, that is a real negative result about transfer in this data rather than a failure to measure.

### Reproducibility note

The derived CSVs are gitignored, like all of `data/`, so the repository ships the *queries* and not 266,265 rows of ChEMBL. `satori kinome-counts` and `satori kinome-extract --all-kinases --minimum 100` regenerate them from the named release, and the release is pinned by name and by the published SHA256 of its archive.

### Extracted, and reconciled against the API

| | targets | rows | distinct molecules |
|---|---:|---:|---:|
| EGFR alone (Step 5's training data) | 1 | 8,450 | 8,450 |
| Setting B: tyrosine kinases | 56 | 132,940 | 81,297 |
| Setting C: whole kinome | 201 | 268,677 | 177,410 |

201 files at a floor of 100 molecules, splitting into **514 distinct (protein, variant) tasks**, 247 with 50 rows or more.

**Rows are not chemistry.** A row is one (molecule, protein) pair, so a promiscuous inhibitor tested against twelve kinases contributes twelve rows and one structure. Against the hypothesis actually under test — that 8,450 molecules is too thin a sample of chemical space — the honest multiplier is the distinct-molecule one: Setting C adds **167,069 molecules EGFR has never seen, 21x** Step 5's variety, where the row count would have claimed 32x. §4's table said "~253,000 extra rows", which was true and the wrong unit.

**The extraction reconciles exactly with Step 3.** EGFR's wild-type set from the dump is 8,450 molecules, and the overlap with the file Step 3 downloaded from the live API is **100.00%, with zero molecules on either side that the other lacks.** Two entirely separate routes — a paginated REST API in 2026-10 and a SQL reconstruction over six joins against the 2026-05 release — returning identical sets. That is the check that licenses comparing Step 6's scores against Step 5's at all.

A smaller reconciliation worth recording, because it looked like a bug: the counts query reported 266,265 and the extraction wrote 268,677. Neither is wrong. The counts query counts `DISTINCT molregno` per target, while `aggregate` emits one row per (structure, variant) — so a molecule measured against both a normal protein and its mutant is one in the first and two in the second, while salt stripping collapses distinct ChEMBL ids onto one structure and pushes the other way. 25,247 of the extracted rows are non-wild-type.
