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

Run the tests:

```powershell
.venv\Scripts\python -m pytest -v
```

## Code map

- [`src/satori/molecule.py`](src/satori/molecule.py): read SMILES, compute properties, check Lipinski (Step 1).
- [`src/satori/library.py`](src/satori/library.py): load a CSV, screen, rank, save (Step 2).
- [`src/satori/__main__.py`](src/satori/__main__.py): the command line tool (`describe`, `screen`).
- [`examples/known_drugs.csv`](examples/known_drugs.csv): 16 rows of known drugs, including one duplicate and one broken row on purpose.
- [`tests/`](tests/): checks that the numbers and behaviour are right.

## Roadmap

1. **Molecules**: read one molecule, compute properties, check drug-likeness. *(done)*
2. **Many molecules**: load a CSV of compounds, filter and rank them, save the results. *(done)*
3. **Real data**: download known active compounds for one target (for example EGFR, a lung cancer target) from ChEMBL.
4. **Similarity search**: fingerprints, "find molecules similar to this drug".
5. **First ML model**: predict activity from structure with scikit-learn, using an honest train/test split.
6. **Targets**: which proteins matter for a disease (Open Targets).
7. **Later**: web UI, API, docking and 3D structure, generative models, GPU, deployment. Each one is added only when the step before it works.
