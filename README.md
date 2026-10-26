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

### Lipinski's Rule of Five

In 1997 Christopher Lipinski noticed most oral drugs satisfy four limits (all multiples of five):

- molecular weight ≤ 500
- logP ≤ 5
- H-bond donors ≤ 5
- H-bond acceptors ≤ 10

A molecule with **at most one** violation is considered "drug-like". It is a rule of thumb, not a law: cyclosporine breaks it and is still an important drug.

## Run it

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

Try the built-in examples:

```powershell
.venv\Scripts\python -m satori
```

Or your own molecule:

```powershell
.venv\Scripts\python -m satori "CC(=O)NC1=CC=C(C=C1)O"
```

Run the tests:

```powershell
.venv\Scripts\python -m pytest -v
```

## Code map

- [`src/satori/molecule.py`](src/satori/molecule.py): read SMILES, compute properties, check Lipinski.
- [`src/satori/__main__.py`](src/satori/__main__.py): the command line tool.
- [`tests/test_molecule.py`](tests/test_molecule.py): checks that the numbers are right.

## Roadmap

1. **Molecules**: read one molecule, compute properties, check drug-likeness. *(done)*
2. **Many molecules**: load a CSV of compounds, filter and rank them, save the results.
3. **Real data**: download known active compounds for one target (for example EGFR, a lung cancer target) from ChEMBL.
4. **Similarity search**: fingerprints, "find molecules similar to this drug".
5. **First ML model**: predict activity from structure with scikit-learn, using an honest train/test split.
6. **Targets**: which proteins matter for a disease (Open Targets).
7. **Later**: web UI, API, docking and 3D structure, generative models, GPU, deployment. Each one is added only when the step before it works.
