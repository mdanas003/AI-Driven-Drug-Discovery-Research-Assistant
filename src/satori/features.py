"""Ways of turning a molecule into numbers, so they can be compared fairly.

Step 5 used one representation: 2,048 on/off Morgan bits. It is not the
only choice, and the choice usually matters more than the model:

- **counts** instead of on/off. A molecule with six benzene rings and one
  with a single ring set the same bit, but different counts.
- **radius 3** (ECFP6) sees larger fragments than radius 2 (ECFP4).
- **physicochemical descriptors** add the whole-molecule properties from
  Step 1 (weight, logP, polar surface area), which no fragment bit knows.

Every featurizer returns one row per molecule, so any model can be run on
any representation and the comparison stays honest.
"""

from collections.abc import Callable

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator

from satori.molecule import describe

N_BITS = 2048


def _morgan(radius: int, counts: bool) -> Callable[[list[Chem.Mol]], np.ndarray]:
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=N_BITS)
    take = (
        generator.GetCountFingerprintAsNumPy if counts else generator.GetFingerprintAsNumPy
    )
    dtype = np.uint16 if counts else np.uint8

    def featurize(mols: list[Chem.Mol]) -> np.ndarray:
        rows = np.zeros((len(mols), N_BITS), dtype=dtype)
        for i, mol in enumerate(mols):
            rows[i] = take(mol)
        return rows

    return featurize


def descriptors(mols: list[Chem.Mol]) -> np.ndarray:
    """The Step 1 properties, as a numeric table."""
    return np.array([list(describe(mol).values()) for mol in mols], dtype=np.float32)


def _with_descriptors(base: Callable[[list[Chem.Mol]], np.ndarray]):
    def featurize(mols: list[Chem.Mol]) -> np.ndarray:
        return np.hstack([base(mols).astype(np.float32), descriptors(mols)])

    return featurize


# The representations the benchmark compares. "ecfp4" is Step 5's choice,
# kept first so every table has the old result as its reference row.
FEATURIZERS: dict[str, Callable[[list[Chem.Mol]], np.ndarray]] = {
    "ecfp4": _morgan(2, counts=False),
    "ecfp4_counts": _morgan(2, counts=True),
    "ecfp6_counts": _morgan(3, counts=True),
    "ecfp4_counts+descriptors": _with_descriptors(_morgan(2, counts=True)),
    "descriptors_only": descriptors,
}


def featurize(name: str, mols: list[Chem.Mol]) -> np.ndarray:
    if name not in FEATURIZERS:
        raise ValueError(f"unknown featurizer {name!r}; try one of {sorted(FEATURIZERS)}")
    return FEATURIZERS[name](mols)
