from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from satori.errors import DependencyUnavailable
from satori.provenance import sha256_bytes, write_json_atomic


@dataclass(slots=True)
class DatasetSplit:
    strategy: str
    seed: int
    train: list[str]
    validation: list[str]
    test: list[str]
    group_key: str | None = None

    def validate_disjoint(self) -> None:
        partitions = [set(self.train), set(self.validation), set(self.test)]
        if any(partitions[i] & partitions[j] for i in range(3) for j in range(i + 1, 3)):
            raise ValueError("Split partitions overlap.")


def _assign_groups(groups: dict[str, list[str]], *, seed: int,
                   fractions: tuple[float, float, float]) -> tuple[list[str], list[str], list[str]]:
    if abs(sum(fractions) - 1.0) > 1e-8 or min(fractions) < 0:
        raise ValueError("Split fractions must be non-negative and sum to one.")
    keys = list(groups)
    random.Random(seed).shuffle(keys)
    total = sum(len(groups[key]) for key in keys)
    limits = (total * fractions[0], total * (fractions[0] + fractions[1]))
    outputs: tuple[list[str], list[str], list[str]] = ([], [], [])
    counts = [0, 0, 0]
    for key in keys:
        bucket = 0 if counts[0] < limits[0] else (1 if counts[0] + counts[1] < limits[1] else 2)
        outputs[bucket].extend(groups[key])
        counts[bucket] += len(groups[key])
    return outputs


def molecule_split(rows: list[dict[str, Any]], *, strategy: str, seed: int = 17,
                   fractions: tuple[float, float, float] = (0.8, 0.1, 0.1),
                   id_field: str = "record_id", molecule_field: str = "molecule_id") -> DatasetSplit:
    """Create record partitions grouped so a molecule cannot appear across partitions."""
    if any(not row.get(id_field) for row in rows):
        raise ValueError(f"Every row needs a non-empty {id_field!r} field.")
    if len({str(row[id_field]) for row in rows}) != len(rows):
        raise ValueError(f"{id_field!r} values must uniquely identify rows.")
    if any(not row.get(molecule_field) for row in rows):
        raise ValueError(f"Every row needs non-empty {id_field!r} and {molecule_field!r} fields.")
    if strategy == "random":
        groups: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            groups[str(row[molecule_field])].append(str(row[id_field]))
        buckets = _assign_groups(groups, seed=seed, fractions=fractions)
        split = DatasetSplit(strategy, seed, *buckets, group_key=molecule_field)
    elif strategy == "scaffold":
        try:
            from rdkit import Chem
            from rdkit.Chem.Scaffolds import MurckoScaffold
        except ImportError as exc:
            raise DependencyUnavailable("Scaffold splits require the [chemistry] extra (RDKit).") from exc
        groups: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            molecule = Chem.MolFromSmiles(row.get("smiles") or "")
            if molecule is None:
                raise ValueError(f"Invalid molecule {row[id_field]!r}; reject it in preprocessing before splitting.")
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(mol=molecule, includeChirality=True)
            groups[scaffold or "acyclic:all"].append(str(row[id_field]))
        split = DatasetSplit(strategy, seed, *_assign_groups(groups, seed=seed, fractions=fractions),
                             group_key="bemis_murcko_scaffold")
    elif strategy == "temporal":
        if any(not row.get("date") for row in rows):
            raise ValueError("Temporal split requires a non-empty date for every record.")
        if abs(sum(fractions) - 1.0) > 1e-8 or min(fractions) < 0:
            raise ValueError("Split fractions must be non-negative and sum to one.")
        by_molecule: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_molecule[str(row[molecule_field])].append(row)
        dated_groups = sorted(by_molecule.items(), key=lambda pair: max(str(row["date"]) for row in pair[1]))
        n = len(dated_groups)
        train_end, val_end = int(n * fractions[0]), int(n * (fractions[0] + fractions[1]))
        partitions = (dated_groups[:train_end], dated_groups[train_end:val_end], dated_groups[val_end:])
        split = DatasetSplit(strategy, seed,
            *[[str(row[id_field]) for _, group in partition for row in group] for partition in partitions],
            group_key=f"{molecule_field} by latest date")
    else:
        raise ValueError("strategy must be 'random', 'scaffold', or 'temporal'")
    split.validate_disjoint()
    return split


def write_split_manifest(path: str | Path, split: DatasetSplit, *, dataset_hash: str,
                         source_version: str, metadata: dict[str, Any] | None = None) -> str:
    """Persist exact record assignments and a stable digest for reproducible evaluation."""
    assignments = {
        "train": sorted(split.train),
        "validation": sorted(split.validation),
        "test": sorted(split.test),
    }
    assignment_hash = sha256_bytes(json.dumps(
        assignments, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8"))
    write_json_atomic(path, {
        "split_schema_version": "1.0",
        "dataset_hash_sha256": dataset_hash,
        "source_version": source_version,
        "strategy": split.strategy,
        "seed": split.seed,
        "group_key": split.group_key,
        "record_counts": {name: len(ids) for name, ids in assignments.items()},
        "assignment_hash_sha256": assignment_hash,
        "assignments": assignments,
        "metadata": metadata or {},
    })
    return assignment_hash


def target_disjoint_split(rows: list[dict[str, Any]], *, seed: int = 17,
                          fractions: tuple[float, float, float] = (0.8, 0.1, 0.1),
                          target_field: str = "target_id", id_field: str = "record_id") -> DatasetSplit:
    if any(not row.get(id_field) or not row.get(target_field) for row in rows):
        raise ValueError(f"Every row needs non-empty {id_field!r} and {target_field!r} fields.")
    if len({str(row[id_field]) for row in rows}) != len(rows):
        raise ValueError(f"{id_field!r} values must uniquely identify rows.")
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        groups[str(row[target_field])].append(str(row[id_field]))
    split = DatasetSplit("target_disjoint", seed, *_assign_groups(groups, seed=seed, fractions=fractions),
                         group_key=target_field)
    split.validate_disjoint()
    return split
