# Satori

A computational drug discovery project, built one small, working step at a time.

The earlier, much larger version of this project lives in [`legacy/`](legacy/). We will bring ideas back from it only when each one makes sense on its own.

## Step 1: what is a molecule to a computer?

Drug discovery on a computer starts with one question: *given a molecule, what is it like, and could it be a pill?*

### SMILES: molecules as text

A computer needs molecules written as text. The standard way is **SMILES**:

| Molecule  | SMILES                          |
|-----------|---------------------------------|
| Aspirin   | `CC(=O)OC1=CC=CC=C1C(=O)O`      |
| Caffeine  | `CN1C=NC2=C1C(=O)N(C(=O)N2C)C`  |
| Ibuprofen | `CC(C)CC1=CC=C(C=C1)C(C)C(=O)O` |

Letters are atoms (`C` carbon, `N` nitrogen, `O` oxygen), `=` is a double bond, brackets `( )` are side branches, and matching digits (`C1 ... C1`) close a ring.

### The properties we compute

We use [RDKit](https://www.rdkit.org/), the standard open-source chemistry toolkit.

| Property           | Meaning |
|--------------------|---------|
| `molecular_weight` | How heavy the molecule is (g/mol). Very large molecules are hard for the gut to absorb. |
| `logp`             | Oil vs. water preference. Too greasy and it won't dissolve; too watery and it won't cross cell membranes. |
| `h_bond_donors`    | Number of N–H and O–H groups that can donate a hydrogen bond. |
| `h_bond_acceptors` | Number of N and O atoms that can accept a hydrogen bond. |
| `rotatable_bonds`  | Bonds that twist freely. Lots of them means a floppy molecule. |
| `tpsa`             | Polar surface area. Predicts how easily it passes through membranes. |
| `rings`            | Number of rings in the structure. |
| `qed`              | Quantitative Estimate of Drug-likeness: one 0–1 score blending the properties above (higher is more drug-like). |

### Lipinski's Rule of Five

In 1997 Christopher Lipinski noticed most oral drugs satisfy four limits (all multiples of five):

- molecular weight ≤ 500
- logP ≤ 5
- H-bond donors ≤ 5
- H-bond acceptors ≤ 10

A molecule with **at most one** violation is considered "drug-like". It is a rule of thumb, not a law: cyclosporine breaks it and is still an important drug.

## Step 2: screening a library of molecules

Real projects look at thousands or millions of molecules, not one. A **library** is a list of compounds, usually a CSV file with a `name` and a `smiles` column (see [`examples/known_drugs.csv`](examples/known_drugs.csv)). **Screening** it means:

1. **Read** every row.
2. **Set aside broken rows.** Real data always has typos and unreadable SMILES. We report them instead of crashing.
3. **Remove duplicates.** The same molecule can be written as different SMILES strings: `CC(=O)OC1=CC=CC=C1C(=O)O` and `OC(=O)C1=CC=CC=C1OC(C)=O` are both aspirin. We convert each one to a **canonical SMILES** (one standard spelling per molecule) and compare those.
4. **Filter**, for example keep only Lipinski passes.
5. **Rank**, here by QED, best first.
6. **Save** the ranked list to a new CSV.

Two lessons from the example library:

- **Atorvastatin** (Lipitor), one of the best-selling drugs ever, fails Lipinski. Its calculated logP is an *estimate* (6.31), higher than the measured value. Filters remove real drugs too.
- **Metformin**, the first-line diabetes drug, ranks near the bottom on QED. A drug-likeness score is not a measure of whether a drug works.

So in Satori, filters and scores are tools for **prioritizing** what to look at first, never proof that a molecule is good or bad.

## Step 3: real experimental data from ChEMBL

So far every number was *calculated*. Now we use *measured* data.

- A **target** is the protein a drug acts on. Our first target is **EGFR** (epidermal growth factor receptor). Mutations in EGFR drive many non-small-cell lung cancers, and drugs like gefitinib, erlotinib and osimertinib block it.
- **[ChEMBL](https://www.ebi.ac.uk/chembl/)** is a free database of lab results pulled from scientific papers: "compound X was tested against protein Y and had potency Z". EGFR is `CHEMBL203`.
- **IC50** is the concentration of a compound needed to block half of the protein's activity. Lower is more potent.
- **pChEMBL** puts that on a simple scale: `-log10(IC50 in molar)`. pChEMBL 6 = 1 µM, 7 = 100 nM, 9 = 1 nM. Higher is more potent, and each +1 is **ten times** more potent.

`fetch-chembl` downloads every IC50 measurement for a target, cleans the data, splits it by which form of the protein was tested, keeps one row per molecule (the **median** of its measurements) and labels it **active** if pChEMBL ≥ 6. It saves four files in `data/chembl/`:

| File | Contents |
|------|----------|
| `CHEMBL203_IC50_raw.csv`       | every downloaded measurement, kept so we never need to download again |
| `CHEMBL203_IC50_wild_type.csv` | the normal protein, one row per molecule |
| `CHEMBL203_IC50_mutant.csv`    | the mutant forms, with a `variant` column saying which |
| `CHEMBL203_IC50.json`          | **provenance**: ChEMBL release, download date, threshold, and how many rows were dropped and why |

Each molecule row is `name, pref_name, smiles, variant, pchembl, n_measurements, spread, active`.

The provenance file matters. ChEMBL publishes a new release every few months, so "EGFR data" changes over time. A result is only reproducible if you know exactly which data produced it.

### Cleaning: what we throw away, and why

```
raw measurements:    26,600
  dropped  7,192  no pChEMBL value (inactive text, odd units, or not standardized)
  dropped  2,022  potential duplicate of another measurement
  dropped  1,255  not a binding/biochemical assay (cell assays are not comparable)
  dropped     47  no structure
kept measurements:   16,084
```

**40% of the raw measurements were unusable** for a fair comparison. Cleaning is not optional, and every rule changes the answer, so the counts are recorded.

We keep only **binding assays**, measured against the purified protein. The same molecule measured 41 nM against purified EGFR and 300 nM in living cells; mixing the two would compare apples with oranges.

We also **strip salts and hydrates**. Drugs are often stored with a counter-ion or water attached, written in SMILES as separate pieces joined by a dot (dacomitinib is stored as the drug `.O`, plus a water molecule). Only the drug binds the protein, so we keep the largest piece. A useful side effect: a drug and its salt form have different ChEMBL IDs but the same stripped structure, so they now merge into one row with both their measurements.

### Why mutants must be kept separate

A mutation is a single changed amino acid in the protein. `T790M` means position 790 changed from threonine to methionine. One such change can alter how tightly a drug binds by a thousandfold, so in practice these are **different proteins**. ChEMBL names the mutation in a dedicated field for newer assays and only in the free-text description for older ones, so we read both.

| | Molecules | Active (pChEMBL ≥ 6) |
|---|---|---|
| Normal (wild-type) EGFR | 8,450 | 6,113 (72%) |
| Mutant EGFR (13 variants) | 4,060 | 3,573 (88%) |

The most-measured mutants are `L858R+T790M` (1,805 molecules), `L858R` (619) and `C797S+L858R+T790M` (574).

Splitting them apart makes the history of EGFR drugs visible in the data:

| Drug | Normal EGFR | L858R | T790M | L858R+T790M | C797S+L858R+T790M |
|------|------------:|------:|------:|------------:|------------------:|
| Gefitinib (1st generation)   | 7.69 | 8.96 | 5.76 | 5.99 | 6.51 |
| Afatinib (2nd generation)    | 8.50 | 9.40 | 8.58 | 7.75 | 6.67 |
| Osimertinib (3rd generation) | 6.85 | 8.91 | 8.27 | 8.41 | 6.94 |

Read it as a story, remembering that +1 means ten times more potent:

- **Gefitinib** works well on normal EGFR and on `L858R`, the mutation that drives many lung cancers. Then tumours acquire `T790M` and gefitinib loses about a thousandfold of its potency (8.96 → 5.99). That is drug resistance, and it is the clinical reality: patients relapse.
- **Osimertinib** was designed for exactly that problem. It is *more* potent on the resistant double mutant (8.41) than on the normal protein (6.85). Being weaker on normal EGFR is deliberate: normal EGFR is in healthy skin and gut, so hitting it causes the rash and diarrhoea that limit the older drugs.
- **`C797S`** is where osimertinib's own potency collapses (8.41 → 6.94). That is the next resistance mutation, and finding drugs for it is an open research problem today.

If we had left these mixed together, every one of those numbers would have been averaged into mush. This is why the step was worth doing before any modelling.

### The data is still biased, and that matters

- **Measurements disagree.** Of the 1,229 wild-type molecules measured more than once, half have a spread of 0.68 log units or more. Gefitinib's 54 wild-type measurements span 5.36 log units. Different labs, assay conditions and protein batches genuinely differ, so we keep the median and record the `spread` so it is never invisible.
- **72–88% "active" is not realistic.** Chemists mostly publish compounds that worked, so ChEMBL is biased toward actives. In a real screen, well under 1% of molecules are active. Any model trained on this data inherits that bias, and the mutant set is the more biased of the two: people test mutants with drugs already known to work on them.
- **`screen` still ranks by QED only**, so it ignores the potency we just downloaded. Combining structure with measured activity is what the next steps are for.

## Step 4: fingerprints, similarity and clustering

The oldest useful idea in medicinal chemistry is that **similar molecules tend to have similar activity**. To use it, a computer needs a way to measure "similar".

### Fingerprints

A **fingerprint** turns a molecule into a long row of yes/no bits. We use **Morgan fingerprints**, also called **ECFP4**: look at every atom, take in the neighbourhood around it out to two bonds away, and switch on a bit for each distinct neighbourhood found. The result is 2,048 bits saying which chemical fragments the molecule contains.

### Tanimoto similarity

Comparing two fingerprints is then simple arithmetic:

```
similarity = shared bits / bits set in either molecule
```

This is the **Tanimoto** coefficient, from 0.0 to 1.0. As a rough guide:

| Score | Meaning |
|-------|---------|
| 1.0 | identical fingerprints |
| above 0.7 | clearly the same chemical series |
| 0.4 – 0.7 | a family resemblance |
| below 0.3 | unrelated |

Gefitinib and erlotinib, two EGFR drugs that look alike to a chemist, score **0.41**. Gefitinib and ethanol score **0.03**.

Salts no longer matter here: because structures are stripped first (Step 3), a drug and its hydrochloride salt score exactly 1.0.

### Finding neighbours

```powershell
.venv\Scripts\python -m satori similar GEFITINIB data\chembl\CHEMBL203_IC50_wild_type.csv --top 8
```

The query can be a SMILES string or any name in the library. Searching all 8,450 wild-type molecules takes about 3 seconds:

```
rank  similarity  name             pChEMBL
   1       0.919  CHEMBL14699         8.00
   2       0.857  CHEMBL4448162       9.00
   3       0.857  CHEMBL299672        7.15
   4       0.844  CHEMBL291514        7.10
   5       0.818  CHEMBL4858176       4.60
...
Median pChEMBL of these 8 neighbours: 7.58  (whole library: 6.96, difference +0.62)
```

That last line is the similarity principle being tested rather than assumed. These neighbours really are more potent than the library as a whole. Run the same search for osimertinib in the mutant file and the difference comes out **negative**: the principle is a useful prior, not a law, so Satori prints which way the data fell instead of claiming the win.

### Activity cliffs: where the principle breaks

Look at ranks 1 and 5 above. Both are gefitinib with a single atom changed:

| Molecule | Change from gefitinib | pChEMBL |
|---|---|---|
| Gefitinib | — | 7.69 |
| `CHEMBL14699` | one CH₂ shorter in the linker | 8.00 |
| `CHEMBL4858176` | morpholine oxygen → selenium | 4.60 |

The selenium version is **0.818 similar and roughly 1,200 times less potent**. This is an **activity cliff**: a tiny structural change falling off a potency cliff. Cliffs are exactly where models trained on similarity fail, and they are common. (Honest caveat: that number comes from a single measurement, where Step 3 warned that labs disagree.)

### Clustering: how many *different* molecules do we really have?

8,450 molecules does not mean 8,450 ideas. Most come from papers exploring one scaffold with small variations.

```powershell
.venv\Scripts\python -m satori cluster data\chembl\CHEMBL203_IC50_wild_type.csv
```

```
1,864 clusters
784 of them a single molecule on its own
largest holds 164 molecules
```

So the real diversity is roughly **1,900 chemical series**, not 8,450 molecules. This matters enormously for Step 5: if a model is trained on part of a 164-molecule series and tested on the rest, it scores brilliantly while having learned nothing transferable. Honest testing has to split by cluster, not by molecule.

Clustering uses **sphere exclusion**: walk the molecules in order, let each unclaimed one found a cluster, and give it every unclaimed molecule within the cutoff. Satori walks the most potent molecules first, so each cluster centre is a compound worth looking at. It only ever holds one row of comparisons in memory, which matters because a full distance matrix for 8,450 molecules would be 36 million numbers.

## Step 5: the first model, and how to not fool yourself

Now Satori makes a *prediction* rather than a measurement or a calculation. Given a molecule's fingerprint, predict its pChEMBL value.

```powershell
.venv\Scripts\python -m satori train data\chembl\CHEMBL203_IC50_wild_type.csv --save data\models\egfr_wt.joblib
.venv\Scripts\python -m satori predict data\models\egfr_wt.joblib "<SMILES>"
```

The model is a **random forest**: hundreds of decision trees, each trained on a different random slice of the data, averaging their answers. It takes about 80 seconds on 8,450 molecules.

The model is the easy half. Knowing whether its score means anything is the hard half, and that depends entirely on how the data is split.

### The same model, measured two ways

**Random split** holds out 20% of molecules. **Cluster split** holds out whole chemical series from Step 4, so nothing in the test set has a close relative in training.

Every number below is the **average of 5 repeats** with its standard deviation. One split gives one number, and that number moves depending on which molecules happened to land in the test set; repeating the experiment is the only way to know how much it moves.

| | Random split | Cluster split |
|---|---:|---:|
| R² (variation explained) | 0.712 ± 0.018 | **0.588 ± 0.019** |
| MAE (average error, pChEMBL) | 0.515 ± 0.013 | **0.654 ± 0.022** |
| Spearman (ranking quality) | 0.846 ± 0.010 | **0.778 ± 0.013** |
| MAE from always guessing the average | 1.120 ± 0.017 | 1.139 ± 0.027 |

Both beat "always guess the average", so the model genuinely learned something. The random split flatters it by 0.124 R² — **six times the run-to-run spread**, so that gap is real and not luck. Only the cluster number says anything about a series nobody has made yet, which is the only question a real project asks.

### There is no single honest number

Here is the uncomfortable part. "Close relative" is a threshold we chose, and the score depends on it:

| Clustering cut-off | Series | Held out | Cluster-split R² | Flattery from the random split |
|---|---:|---:|---:|---:|
| 0.6 (same series) | 1,864 | 449 | 0.588 ± 0.019 | 0.124 R² |
| 0.4 (family resemblance) | 741 | 83 | 0.413 ± 0.071 | 0.299 R² |

Loosening the definition of "related" makes the test harder and the model look worse, R² falling from 0.59 to 0.41. Look at the spread, though: it grows four-fold, because only 83 series are held out and which ones land in the test set starts to dominate. **The stricter test is the more honest one and the less reliable one at the same time**, and without repeats that would have been invisible.

So there is no cut-off that makes one of these *the* answer, which is why a published R² with no stated split protocol and no spread tells you almost nothing.

### What the numbers mean in practice

- **MAE 0.65** means the typical prediction is out by about **4.5-fold in potency**. Good enough to sort a list into "probably worth making" and "probably not". Useless for predicting that a compound will be exactly 10 nM.
- **Spearman 0.77** says the *ranking* is better than the absolute values, which is lucky: ranking is what a project needs when choosing what to synthesize next.
- A saved model stores its cluster-split scores, and `predict` prints them before every prediction, so a number from this model cannot be quoted without its error bar:

```
Model predicts pchembl, trained on 8,450 molecules
  on unseen chemical series it was out by 0.65 on average (R2 0.594)

  COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1   predicted 7.66 +/- 0.65
  CC(=O)OC1=CC=CC=C1C(=O)O                         predicted 5.32 +/- 0.65
```

That first molecule is gefitinib, measured at 7.69, and the model says 7.66. **This proves nothing**: gefitinib is in the training data. Predicting a molecule you trained on is the oldest way to fool yourself, and it is why the table above exists. Aspirin, which should do nothing to EGFR, is predicted weak at 5.32, which is at least the right direction.

### Everything still wrong with this model

- **It inherits the publication bias of Step 3.** 72% of its training data is active, where a real screen is under 1% active. It has barely seen what a genuinely dead compound looks like.
- **Its targets are medians of measurements that disagree** by 0.68 log units on average. Part of the remaining error is the data's, not the model's, and no model can beat the noise in its labels.
- **Fingerprints cannot see activity cliffs.** The gefitinib/selenium pair from Step 4 are 0.82 similar and 1,200-fold apart in potency; this model will confidently predict they are alike.
- **Every prediction carries the same error bar.** A random forest can report the spread across its trees, which would say when a molecule is far from anything it has seen. That belongs in a later step.
- **It knows nothing about the protein.** It has learned which molecular fragments correlate with potency against wild-type EGFR, and would need retraining from scratch for any other target.

## Step 5b: is 0.59 any good? A fair fight between models

Before adding anything new, the obvious question: is a random forest the wrong model? Would gradient boosting, or a kernel method, or a graph neural network do better?

```powershell
.venv\Scripts\python -m satori benchmark data\chembl\CHEMBL203_IC50_wild_type.csv
```

Same clusters, same splits, same repeats, same metrics, one table. A model only wins if it wins by more than the run-to-run spread.

| Model | Features | R² | MAE | Spearman | Top 10% | Time |
|---|---|---:|---:|---:|---:|---:|
| Gradient boosting | ECFP6 counts | 0.601 ± 0.035 | 0.642 | 0.785 | 0.46 | 11s |
| Gradient boosting | ECFP4 counts + descriptors | 0.599 ± 0.030 | 0.643 | 0.785 | 0.47 | 10s |
| Random forest | ECFP4 bits *(Step 5)* | 0.598 ± 0.017 | 0.650 | 0.781 | 0.46 | 120s |
| Random forest | ECFP4 counts | 0.597 ± 0.016 | 0.650 | 0.781 | 0.44 | 126s |
| Tanimoto SVR | ECFP4 bits | 0.597 ± 0.030 | **0.638** | 0.784 | **0.49** | 10s |
| Gradient boosting | ECFP4 counts | 0.596 ± 0.034 | 0.643 | 0.781 | 0.45 | 12s |
| Gradient boosting | 8 descriptors only | 0.291 ± 0.033 | 0.877 | 0.556 | 0.28 | 3s |
| Ridge (a straight line) | ECFP4 counts | 0.181 ± 0.031 | 0.896 | 0.651 | 0.35 | 2s |

### What this settles

**The top six are a tie.** Three model families with completely different assumptions — bagged trees, boosted trees, a similarity kernel — all land at R² 0.60 ± 0.03, as does every representation we tried. When independent approaches converge on the same number, the ceiling is in the data, not the model. This is the evidence for expecting a graph neural network to tie as well: at 8,450 molecules on one target, architecture is not the bottleneck.

**The two that lose, lose for informative reasons.** Ridge at 0.18 proves the task is genuinely non-linear, so fingerprints need a model that can combine bits. Descriptors-only at 0.29 proves structure matters: you get roughly half the R² from eight whole-molecule numbers, so "right size and greasiness" is a real part of the signal, but only a part.

**The practical win is cost, not accuracy.** Gradient boosting reaches the same answer in 11 seconds that the forest takes 120 seconds to reach. `train --model gradient_boosting` is a tenfold saving for free.

**The Tanimoto SVR quietly wins where it counts.** Statistically tied on R², but it has the best MAE (0.638) and the best top-10% hit rate (0.49). Comparing whole molecules the way a chemist does is a better fit for this task than treating 2,048 bits as independent features.

### The ceiling, measured

`fetch-chembl` now records how well the data agrees with itself, over the 2,075 molecules measured more than once:

| | |
|---|---|
| Two measurements of the same molecule differ by | **0.775** log units on average |
| Median difference | 0.59 |
| Differ by more than 10-fold | 29% |

**The best model's error (0.638) is smaller than the disagreement between two real lab measurements (0.775).** The model is already more self-consistent than the data it learned from. Absolute accuracy is finished on these labels, and any paper reporting MAE far below this on ChEMBL data has either leaked its test set or quietly filtered to easy compounds.

### So where is the real headroom?

Not in the model class. Three candidates:

1. **Ranking, which is not capped the same way.** Of the molecules the best model ranks in its top 10%, **49% are genuinely among the most potent** — five times better than picking at random. This is the number a user acts on, and Spearman 0.78 still has room.
2. **Better labels.** Weighting or filtering by measurement count and spread might raise the ceiling itself, rather than chasing it. Step 5c tests this.
3. **More data, not deeper models.** One target is where every architecture saturates. Multi-task learning across many kinases is where the next real gain should live.

## Step 5c: the label-quality hypothesis, and why it failed

If labels disagree by 0.775 and the model is out by 0.64, the obvious move is to trust the better-measured molecules more. In our data, 85% of molecules were measured exactly once, and only 761 of 8,450 have two or more measurements agreeing within 1.0 log.

```powershell
.venv\Scripts\python -m satori labels data\chembl\CHEMBL203_IC50_wild_type.csv
```

Two experiments, kept deliberately apart, because mixing them is how a changed yardstick gets mistaken for a better model.

**Experiment 1 — identical training, change only what we score on.** If the error is the data's fault, scoring against labels we can check should reduce it.

| Scored on | R² | MAE | Top 10% |
|---|---:|---:|---:|
| every label | 0.566 ± 0.022 | 0.671 ± 0.010 | 0.43 |
| confident labels only | 0.532 ± 0.154 | 0.684 ± 0.065 | 0.28 |

**It did not.** The error moved by −0.013 MAE, well inside the ±0.065 spread. Label noise is not what limits this model.

**Experiment 2 — identical confident test set, change only what the model sees.**

| Trained on | R² | MAE | Top 10% |
|---|---:|---:|---:|
| all labels, unweighted | 0.532 ± 0.154 | 0.684 ± 0.065 | 0.28 |
| all labels, weighted by count (√n) | 0.535 ± 0.160 | 0.679 ± 0.083 | 0.28 |
| all labels, weighted by agreement | 0.534 ± 0.149 | 0.683 ± 0.071 | 0.27 |
| all labels, weighted by both | 0.554 ± 0.142 | 0.672 ± 0.072 | 0.27 |
| **confident labels only (761)** | **0.447 ± 0.117** | **0.759 ± 0.053** | 0.41 |

No weighting scheme beat plain unweighted labels by more than the spread. And training on only the clean 9% was clearly **worse**: R² 0.447 against 0.532.

### What we learned by being wrong

- **8,450 noisy labels beat 761 clean ones.** Throwing away imperfect data to feel rigorous made the model worse. Quantity won.
- **The binding constraint is coverage, not noise.** The model's error comes from being asked about chemical series it has never seen, not from wobble in the numbers it trained on. A median of several measurements already cancels much of the random error; what it cannot do is teach the model about unfamiliar chemistry.
- **We cannot even measure the ceiling precisely.** Scoring on the confident subset leaves about 230 molecules, and the spread explodes from ±0.022 to ±0.154 R². Any claim about label noise on this data, ours included, rests on thin evidence. That is worth remembering whenever a paper quotes a noise floor.
- **One number went the other way.** Training on confident labels only scored better on the top-10% hit rate (0.41 against 0.28). That is almost certainly because its training data and the test set are then drawn from the same narrow slice, not because it learned more. A single metric moving against the others is a prompt to be suspicious, not to celebrate.

This cost an afternoon and killed a plausible idea before anything got built on top of it. The result also points the next step more firmly: if more data beats cleaner data, then **multi-task learning across many targets** is the thing to do, and that is now an evidence-backed decision rather than a hunch.

## Step 6.0: learning from several proteins, and a correction to Step 5

### The biology, briefly

A drug works by sticking to a protein and stopping it working. EGFR is one of about 500 human **kinases** — molecular switches that tag other proteins with a phosphate group, using ATP (the cell's fuel) as the source. In cancer a mutated kinase gets stuck "on" and keeps telling the cell to divide.

Every kinase has the same basic pocket, the place ATP normally binds. So a molecule shaped to plug one kinase's pocket often partly plugs another's. **A measurement against a different kinase is therefore a weak clue about EGFR**, not noise. That is the biological claim this step tests.

### The computer science

This is **transfer learning**: train on related tasks so the model sees more of the input space. Each row becomes "this molecule, against this protein", and the protein is encoded as 14 extra columns where exactly one is set — a **one-hot** encoding. One model then serves all 14 proteins while still being able to say "potent against wild-type EGFR, weak against T790M".

```powershell
.venv\Scripts\python -m satori multitask data\chembl\CHEMBL203_IC50_wild_type.csv --also data\chembl\CHEMBL203_IC50_mutant.csv
```

### The leak that had to be closed first

Pooling proteins creates a way to cheat that single-task work does not have:

> Gefitinib is in the EGFR test set. Gefitinib's measurement against the T790M mutant is in the training set. The model has seen the answer.

**42% of the mutant rows are molecules that also appear in the wild-type set**, so this is what the obvious implementation does by default. Every training row within 0.6 Tanimoto of *any* test molecule is therefore removed, across all proteins, and the finished split is then **audited**: if anything slipped through, the command refuses to print scores. The test suite includes a deliberately leaky split to prove the audit fails when it should, because a guard never seen to fail cannot be trusted when it passes.

### Result: no effect, and we said in advance that we would not be able to tell

| Arm | Training rows | R² | MAE | Spearman | Top 10% |
|---|---:|---:|---:|---:|---:|
| Single protein | 4,103 | 0.428 ± 0.031 | 0.802 ± 0.025 | 0.666 | 0.30 |
| 14 proteins | 6,947 | 0.426 ± 0.030 | 0.810 ± 0.026 | 0.662 | 0.31 |

Every difference is **inside the run-to-run spread**: −0.002 R² against a spread of 0.031. The verdict is **undecided, not refuted** — [the plan](docs/STEP6_PLAN.md) predicted this stage would be underpowered, so a null result here carries no information about the hypothesis. Three explanations remain live and this experiment cannot separate them: too little extra data, mutants of one protein being too similar to add much, or the one-hot encoding being unable to express that wild-type EGFR resembles its own mutants more than a distant kinase.

### The finding that actually matters: Step 5 was leaking

Single-task R² here is **0.428**. Step 5 reported **0.588** for the same model on the same molecules. The difference is the filter:

| Protocol | Training rows | What it guarantees |
|---|---:|---|
| Step 5: hold out whole clusters | 6,760 | test molecules' *cluster-mates* are absent |
| Step 6.0: also drop near misses | 4,103 | nothing within 0.6 of a test molecule survives, anywhere |

**The strict filter removes a further 2,657 rows — 39% of the training set.** Those molecules sat in a *different* cluster yet were still within 0.6 similarity of a test molecule.

This is a property of sphere-exclusion clustering that is easy to miss: it guarantees members are close to their cluster **centre**, and says nothing about molecules in neighbouring clusters. Two molecules 0.59 similar can sit in different clusters, so "hold out whole clusters" does not mean "hold out everything similar".

Two causes are mixed in that 0.588 → 0.428 drop, and this run cannot separate them: the harder test removes leakage (more honest), and the smaller training set weakens the model (an artifact of the method). Both push the same way.

So the right conclusion is not "0.588 was a lie" but something Step 5 already warned about, now shown sharply:

**The score depends on how novel the test chemistry is, and we now have two points on that curve.**

| Question being asked | Protocol | R² |
|---|---|---:|
| A new series, but relatives may exist in our files | whole clusters held out | 0.59 |
| Genuinely novel chemistry, nothing close in training | strict 0.6 filter | 0.43 |

Both are real. The first describes the common case of exploring around a known scaffold; the second describes scaffold-hopping into new territory. A single quoted R² without its protocol is close to meaningless, which is why Satori prints the protocol every time.

## Run it

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Describe the built-in examples, or your own molecule:

```powershell
.venv\Scripts\python -m satori describe
.venv\Scripts\python -m satori describe "CC(=O)NC1=CC=C(C=C1)O"
```

Screen a library: rank all of it, or keep only the top 5 drug-like molecules and save them:

```powershell
.venv\Scripts\python -m satori screen examples\known_drugs.csv
.venv\Scripts\python -m satori screen examples\known_drugs.csv --drug-like --top 5 --out data\top5.csv
```

(`data/` is ignored by Git, so it is a good place for results.)

Download and clean real EGFR data from ChEMBL (needs internet the first time; later runs reuse the saved copy unless you add `--refresh`), then screen it:

```powershell
.venv\Scripts\python -m satori fetch-chembl CHEMBL203
.venv\Scripts\python -m satori screen data\chembl\CHEMBL203_IC50_wild_type.csv --drug-like --top 20
```

Find the molecules most similar to a drug, or group the library into chemical series:

```powershell
.venv\Scripts\python -m satori similar GEFITINIB data\chembl\CHEMBL203_IC50_wild_type.csv
.venv\Scripts\python -m satori cluster data\chembl\CHEMBL203_IC50_wild_type.csv
```

Run the tests:

```powershell
.venv\Scripts\python -m pytest -v
```

## Code map

- [`src/satori/molecule.py`](src/satori/molecule.py): read SMILES, compute properties, check Lipinski (Step 1).
- [`src/satori/library.py`](src/satori/library.py): load a CSV, screen, rank, save (Step 2).
- [`src/satori/chembl.py`](src/satori/chembl.py): download, clean and aggregate ChEMBL activity data (Step 3).
- [`src/satori/similarity.py`](src/satori/similarity.py): fingerprints, Tanimoto similarity, clustering (Step 4).
- [`src/satori/model.py`](src/satori/model.py): the two splits, repeated training and scoring (Step 5).
- [`src/satori/features.py`](src/satori/features.py): the molecular representations being compared (Step 5b).
- [`src/satori/benchmark.py`](src/satori/benchmark.py): the model line-up and the fair-fight protocol (Step 5b).
- [`src/satori/labels.py`](src/satori/labels.py): label confidence, training weights, split restriction (Step 5c).
- [`src/satori/multitask.py`](src/satori/multitask.py): pooling proteins, the leakage filter and its audit (Step 6.0).
- [`src/satori/__main__.py`](src/satori/__main__.py): the command line tool (`describe`, `screen`, `fetch-chembl`, `similar`, `cluster`, `train`, `benchmark`, `labels`, `multitask`, `predict`).
- [`examples/known_drugs.csv`](examples/known_drugs.csv): 16 rows of known drugs, including one duplicate and one broken row on purpose.
- [`tests/`](tests/): checks that the numbers and behaviour are right.

## Roadmap

1. **Molecules**: read one molecule, compute properties, check drug-likeness. *(done)*
2. **Many molecules**: load a CSV of compounds, filter and rank them, save the results. *(done)*
3. **Real data**: download known active compounds for one target (EGFR, a lung cancer target) from ChEMBL. *(done)*
4. **Similarity search**: fingerprints, "find molecules similar to this drug", and clustering. *(done)*
5. **First ML model**: predict activity from structure with scikit-learn, split by cluster so the score is honest. *(done)*
5b. **Model bake-off**: prove the model class is not the bottleneck, and measure the data's own ceiling. *(done)*
5c. **Label quality**: test whether trusting better-measured labels helps. It does not; quantity wins. *(done)*
6.0. **Multi-task plumbing**: pool EGFR's mutants, with a leakage filter and audit. No effect, as predicted — and it exposed that Step 5's split was leaking. *(done)*
6.1. **Multi-task at scale**: the whole kinome from ChEMBL's bulk release, where the data is large enough to settle the question. See [the plan](docs/STEP6_PLAN.md).
7. **Targets**: which proteins matter for a disease (Open Targets).
8. **Later**: web UI, API, docking and 3D structure, generative models, GPU, deployment. Each one is added only when the step before it works.
