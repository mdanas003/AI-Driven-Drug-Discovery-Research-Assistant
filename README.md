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

`fetch-chembl` downloads every IC50 measurement for a target, cleans the data, keeps one row per molecule (the **median** of its measurements) and labels it **active** if pChEMBL ≥ 6. It saves three files in `data/chembl/`:

| File | Contents |
|------|----------|
| `CHEMBL203_IC50_raw.csv`  | every downloaded measurement, kept so we never need to download again |
| `CHEMBL203_IC50.csv`      | one row per molecule: `name, pref_name, smiles, pchembl, n_measurements, spread, active` |
| `CHEMBL203_IC50.json`     | **provenance**: ChEMBL release, download date, threshold, and how many rows were dropped and why |

The provenance file matters. ChEMBL publishes a new release every few months, so "EGFR data" changes over time. A result is only reproducible if you know exactly which data produced it.

### What the real data looks like (ChEMBL 37, October 2026)

```
raw measurements:    26,600
  dropped  7,192  no pChEMBL value (inactive text, odd units, or not standardized)
  dropped  2,022  potential duplicate of another measurement
  dropped  1,255  not a binding/biochemical assay (cell assays are not comparable)
  dropped     47  no structure
kept measurements:   16,084
unique molecules:    10,381
actives (pChEMBL >= 6): 7,885 (76%)
```

The approved EGFR drugs are all in there: afatinib (8.5), dacomitinib (8.2), lapatinib (7.7), osimertinib (7.7), gefitinib (7.5) and erlotinib (7.4).

Lessons from real data:

- **40% of the raw measurements were unusable** for a clean comparison. Cleaning is not optional, and every rule we apply changes the answer, so the reasons are recorded.
- **We keep only binding assays.** The same molecule can measure 41 nM against the purified protein and 300 nM in living cells. Mixing the two would compare apples with oranges.
- **Measurements disagree.** Of the 3,127 molecules measured more than once, half have a spread of 0.87 log units or more (a seven-fold difference), and erlotinib's 77 measurements span 6.5 log units. That is why we take the median and record the `spread`.
- **76% "active" is not realistic.** Chemists mostly publish compounds that worked, so ChEMBL is biased toward actives. In a real screen, well under 1% of random molecules are active. Any model trained on this data will inherit that bias.

### Known limitations, to fix in later steps

- **Mutant EGFR is mixed with normal EGFR.** Many assays test cancer mutants (such as T790M, which osimertinib was designed to hit). That explains part of the large spread. We should separate them.
- **Salts and hydrates are not stripped.** 182 molecules have a `.` in their SMILES (for example dacomitinib is stored with a water molecule), which slightly distorts their calculated properties.
- **`screen` still ranks by QED only**, so it ignores the potency we just downloaded. The top-ranked molecules are drug-like, but not necessarily potent. Combining the two is what the next steps are for.

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
.venv\Scripts\python -m satori screen data\chembl\CHEMBL203_IC50.csv --drug-like --top 20
```

Run the tests:

```powershell
.venv\Scripts\python -m pytest -v
```

## Code map

- [`src/satori/molecule.py`](src/satori/molecule.py): read SMILES, compute properties, check Lipinski (Step 1).
- [`src/satori/library.py`](src/satori/library.py): load a CSV, screen, rank, save (Step 2).
- [`src/satori/chembl.py`](src/satori/chembl.py): download, clean and aggregate ChEMBL activity data (Step 3).
- [`src/satori/__main__.py`](src/satori/__main__.py): the command line tool (`describe`, `screen`, `fetch-chembl`).
- [`examples/known_drugs.csv`](examples/known_drugs.csv): 16 rows of known drugs, including one duplicate and one broken row on purpose.
- [`tests/`](tests/): checks that the numbers and behaviour are right.

## Roadmap

1. **Molecules**: read one molecule, compute properties, check drug-likeness. *(done)*
2. **Many molecules**: load a CSV of compounds, filter and rank them, save the results. *(done)*
3. **Real data**: download known active compounds for one target (EGFR, a lung cancer target) from ChEMBL. *(done)*
4. **Similarity search**: fingerprints, "find molecules similar to this drug".
5. **First ML model**: predict activity from structure with scikit-learn, using an honest train/test split.
6. **Targets**: which proteins matter for a disease (Open Targets).
7. **Later**: web UI, API, docking and 3D structure, generative models, GPU, deployment. Each one is added only when the step before it works.
