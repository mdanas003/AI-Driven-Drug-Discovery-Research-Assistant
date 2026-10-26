"""Step 2: work with a whole library of molecules instead of one at a time.

A "library" is just a list of compounds, usually stored as a CSV file with
a name and a SMILES column. Screening it means: read every row, throw out
rows that are broken or duplicated, compute properties for the rest, then
filter and rank them so the most promising ones come first.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from satori.molecule import canonical_smiles, describe, lipinski, parse_smiles


@dataclass
class Compound:
    name: str
    smiles: str
    canonical: str
    props: dict[str, float]
    drug_like: bool
    violations: list[str]


@dataclass
class ScreenResult:
    compounds: list[Compound] = field(default_factory=list)
    # (name, reason) for rows we could not read.
    invalid: list[tuple[str, str]] = field(default_factory=list)
    # (name, name of the earlier row it duplicates).
    duplicates: list[tuple[str, str]] = field(default_factory=list)


def load_csv(path: str | Path) -> list[tuple[str, str]]:
    """Read (name, smiles) pairs from a CSV with 'name' and 'smiles' columns."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"name", "smiles"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing column(s) {sorted(missing)}")
        return [(row["name"].strip(), row["smiles"].strip()) for row in reader]


def evaluate(name: str, smiles: str) -> Compound:
    """Compute everything we know about one molecule. Raises ValueError."""
    mol = parse_smiles(smiles)
    props = describe(mol)
    drug_like, violations = lipinski(props)
    return Compound(name, smiles, canonical_smiles(mol), props, drug_like, violations)


def screen(rows: list[tuple[str, str]]) -> ScreenResult:
    """Evaluate every row, setting aside invalid and duplicate molecules."""
    result = ScreenResult()
    seen: dict[str, str] = {}  # canonical SMILES -> first name seen
    for name, smiles in rows:
        try:
            compound = evaluate(name, smiles)
        except ValueError as err:
            result.invalid.append((name, str(err)))
            continue
        if compound.canonical in seen:
            result.duplicates.append((name, seen[compound.canonical]))
            continue
        seen[compound.canonical] = name
        result.compounds.append(compound)
    return result


def rank(
    compounds: list[Compound], drug_like_only: bool = False, top: int | None = None
) -> list[Compound]:
    """Sort by QED (best first), optionally keeping only Lipinski passes."""
    kept = [c for c in compounds if c.drug_like or not drug_like_only]
    kept.sort(key=lambda c: c.props["qed"], reverse=True)
    return kept[:top] if top else kept


def save_csv(compounds: list[Compound], path: str | Path) -> None:
    """Write ranked compounds to CSV, one row per molecule."""
    if not compounds:
        raise ValueError("No compounds to save.")
    prop_names = list(compounds[0].props)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "name", "smiles", *prop_names, "drug_like", "violations"])
        for i, c in enumerate(compounds, start=1):
            writer.writerow(
                [i, c.name, c.canonical, *c.props.values(), c.drug_like, "; ".join(c.violations)]
            )
