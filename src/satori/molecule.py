"""Step 1: turn a molecule written as text into numbers we can reason about.

A molecule is written as a SMILES string, for example aspirin is
"CC(=O)OC1=CC=CC=C1C(=O)O". RDKit reads that text into a molecule object,
and from the object we compute a few classic properties that medicinal
chemists use to judge whether something could work as an oral drug.
"""

from rdkit import Chem, RDLogger
from rdkit.Chem import QED, Descriptors

# RDKit prints its own warnings for bad SMILES; we raise a clear error instead.
RDLogger.DisableLog("rdApp.*")


def parse_smiles(smiles: str) -> Chem.Mol:
    """Read a SMILES string into an RDKit molecule, or raise ValueError."""
    mol = Chem.MolFromSmiles(smiles) if smiles and smiles.strip() else None
    if mol is None:
        raise ValueError(f"Not a valid SMILES string: {smiles!r}")
    return mol


def canonical_smiles(mol: Chem.Mol) -> str:
    """One standard spelling per molecule, so the same molecule written two
    different ways ("OC(=O)C" and "CC(O)=O") compares equal."""
    return Chem.MolToSmiles(mol)


def describe(mol: Chem.Mol) -> dict[str, float]:
    """Compute basic drug-relevant properties of a molecule."""
    return {
        # How heavy the molecule is (g/mol). Big molecules struggle to be absorbed.
        "molecular_weight": round(Descriptors.MolWt(mol), 2),
        # Oil vs. water preference. Higher = more greasy (lipophilic).
        "logp": round(Descriptors.MolLogP(mol), 2),
        # Groups that can donate / accept hydrogen bonds (N-H, O-H / N, O atoms).
        "h_bond_donors": Descriptors.NumHDonors(mol),
        "h_bond_acceptors": Descriptors.NumHAcceptors(mol),
        # Single bonds that can twist freely. Many = floppy molecule.
        "rotatable_bonds": Descriptors.NumRotatableBonds(mol),
        # Polar surface area (square angstroms). Relates to crossing cell membranes.
        "tpsa": round(Descriptors.TPSA(mol), 2),
        "rings": Descriptors.RingCount(mol),
        # Quantitative Estimate of Drug-likeness (Bickerton 2012): a single
        # 0-1 score blending the properties above. Higher = more drug-like.
        "qed": round(QED.qed(mol), 3),
    }


# Lipinski's Rule of Five (1997): most oral drugs satisfy these limits.
LIPINSKI_LIMITS = {
    "molecular_weight": 500,
    "logp": 5,
    "h_bond_donors": 5,
    "h_bond_acceptors": 10,
}


def lipinski(props: dict[str, float]) -> tuple[bool, list[str]]:
    """Check the Rule of Five. One violation is tolerated; two or more fail."""
    violations = [
        f"{name} = {props[name]} (limit {limit})"
        for name, limit in LIPINSKI_LIMITS.items()
        if props[name] > limit
    ]
    return len(violations) <= 1, violations
