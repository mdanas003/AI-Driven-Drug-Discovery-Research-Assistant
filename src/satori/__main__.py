"""Command line entry point.

    python -m satori describe "<SMILES>" ...      # one or more molecules
    python -m satori screen library.csv [options] # a whole CSV library
"""

import argparse
import sys

from satori.library import load_csv, rank, save_csv, screen
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


def cmd_describe(args: argparse.Namespace) -> int:
    molecules = {s: s for s in args.smiles} if args.smiles else EXAMPLES
    ok = [report(name, smiles) for name, smiles in molecules.items()]
    return 0 if all(ok) else 1


def cmd_screen(args: argparse.Namespace) -> int:
    try:
        rows = load_csv(args.csv)
    except (OSError, ValueError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1

    result = screen(rows)
    ranked = rank(result.compounds, drug_like_only=args.drug_like, top=args.top)

    print(f"Read {len(rows)} rows from {args.csv}")
    print(f"  valid and unique: {len(result.compounds)}")
    for name, reason in result.invalid:
        print(f"  skipped invalid:  {name} ({reason})")
    for name, original in result.duplicates:
        print(f"  skipped duplicate: {name} (same molecule as {original})")

    print(f"\n{'rank':>4}  {'name':<16} {'QED':>5}  {'MW':>8}  {'logP':>5}  Lipinski")
    for i, c in enumerate(ranked, start=1):
        p = c.props
        verdict = "PASS" if c.drug_like else "FAIL"
        print(
            f"{i:>4}  {c.name:<16} {p['qed']:>5.3f}  {p['molecular_weight']:>8.2f}"
            f"  {p['logp']:>5.2f}  {verdict}"
        )

    if args.out:
        if not ranked:
            print("\nNothing passed the filters, so no file was written.")
            return 1
        save_csv(ranked, args.out)
        print(f"\nSaved {len(ranked)} compounds to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="satori", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("describe", help="properties of one or more SMILES strings")
    p.add_argument("smiles", nargs="*", help="SMILES strings (default: built-in examples)")
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("screen", help="filter and rank a CSV library by QED")
    p.add_argument("csv", help="CSV file with 'name' and 'smiles' columns")
    p.add_argument("--drug-like", action="store_true", help="keep only Lipinski passes")
    p.add_argument("--top", type=int, help="keep only the best N")
    p.add_argument("--out", help="write the ranked results to this CSV")
    p.set_defaults(func=cmd_screen)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
