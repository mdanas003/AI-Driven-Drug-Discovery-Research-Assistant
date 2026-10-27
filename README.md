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

| | Random split | Cluster split |
|---|---:|---:|
| R² (variation explained) | **0.698** | **0.594** |
| MAE (average error, pChEMBL) | 0.524 | 0.651 |
| Spearman (ranking quality) | 0.839 | 0.768 |
| MAE from always guessing the average | 1.095 | 1.124 |

Both beat "always guess the average", so the model genuinely learned something. But the random split flatters it, and only the cluster number says anything about a series nobody has made yet — which is the only question a real project asks.

### There is no single honest number

Here is the uncomfortable part. "Close relative" is a threshold we chose, and the score depends on it:

| Clustering cut-off | Chemical series | Series held out | Cluster-split R² | MAE | Flattery from the random split |
|---|---:|---:|---:|---:|---:|
| 0.6 (same series) | 1,864 | 449 | 0.594 | 0.651 | 0.104 R² |
| 0.4 (family resemblance) | 741 | 83 | 0.425 | 0.674 | 0.273 R² |
| 0.3 (loosely related) | 471 | 93 | 0.458 | 0.697 | 0.240 R² |

Loosening the definition of "related" makes the test harder and the model look worse — R² falls from 0.59 to about 0.43. But notice the bottom row: R² goes slightly *up* while MAE gets *worse*. That is not a real improvement. With only 83–93 series held out, which ones land in the test set starts to dominate the result, so the measurement itself becomes noisy. Running it with a different `--seed` would move these numbers around.

Two honest conclusions. There is **no single cut-off that makes one of these numbers *the* answer**, so a published R² with no stated split protocol tells you almost nothing. And a careful evaluation needs **repeats across seeds**, not one split — which this step does not yet do.

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
- [`src/satori/model.py`](src/satori/model.py): features, the two splits, training and scoring (Step 5).
- [`src/satori/__main__.py`](src/satori/__main__.py): the command line tool (`describe`, `screen`, `fetch-chembl`, `similar`, `cluster`, `train`, `predict`).
- [`examples/known_drugs.csv`](examples/known_drugs.csv): 16 rows of known drugs, including one duplicate and one broken row on purpose.
- [`tests/`](tests/): checks that the numbers and behaviour are right.

## Roadmap

1. **Molecules**: read one molecule, compute properties, check drug-likeness. *(done)*
2. **Many molecules**: load a CSV of compounds, filter and rank them, save the results. *(done)*
3. **Real data**: download known active compounds for one target (EGFR, a lung cancer target) from ChEMBL. *(done)*
4. **Similarity search**: fingerprints, "find molecules similar to this drug", and clustering. *(done)*
5. **First ML model**: predict activity from structure with scikit-learn, split by cluster so the score is honest. *(done)*
6. **Targets**: which proteins matter for a disease (Open Targets).
7. **Later**: web UI, API, docking and 3D structure, generative models, GPU, deployment. Each one is added only when the step before it works.
