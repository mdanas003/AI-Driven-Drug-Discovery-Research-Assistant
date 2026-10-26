"""Command line entry point: python -m satori "<SMILES>" ..."""

import sys

from satori.molecule import describe, lipinski, parse_smiles

EXAMPLES = {
    "aspirin": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    "ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    "cyclosporine": (
        "CCC1C(=O)N(CC(=O)N(C(C(=O)NC(C(=O)N(C(C(=O)NC(C(=O)NC(C(=O)N(C(C(=O)"
        "N(C(C(=O)N(C(C(=O)N(C(C(=O)N1)C(C(C)CC=CC)O)C)C(C)C)C)CC(C)C)C)CC(C)C)"
        "C)C)C)CC(C)C)C)C(C)C)CC(C)C)C)C"
    ),
}


def report(name: str, smiles: str) -> bool:
    """Print one molecule's properties and verdict. Returns False on bad input."""
    print(f"\n== {name} ==")
    try:
        mol = parse_smiles(smiles)
    except ValueError as err:
        print(f"  error: {err}")
        return False

    props = describe(mol)
    for key, value in props.items():
        print(f"  {key:<18} {value}")

    passes, violations = lipinski(props)
    print(f"  {'drug-like?':<18} {'PASS' if passes else 'FAIL'} (Lipinski Rule of Five)")
    for v in violations:
        print(f"    - violates {v}")
    return True


def main(argv: list[str]) -> int:
    molecules = {s: s for s in argv} if argv else EXAMPLES
    ok = [report(name, smiles) for name, smiles in molecules.items()]
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
