"""Step 6: learning from several proteins at once.

**The biology.** A drug works by sticking to a protein and stopping it doing
its job. EGFR is one of about 500 human proteins called kinases, and they
all share the same basic pocket: the place where ATP, the cell's fuel
molecule, normally binds. Because that pocket is similar across the family,
a molecule shaped to block one kinase often partly blocks others. So a
measurement against a *different* kinase is not noise — it is a weak clue
about EGFR.

**The computer science.** This is transfer learning. Step 5b showed that
every model we tried plateaued at the same score, and Step 5c showed that
cleaning the labels did not help either. What is left is that 8,450
molecules against one protein is simply too small a sample of chemistry.
Adding related tasks is the standard way out: the model sees more of the
input space, and the shared structure between tasks means some of what it
learns about one transfers to another.

**The danger, which is the real work here.** Combining tasks creates a new
way to cheat. The same molecule is often tested against many kinases. If a
molecule is in our test set for EGFR but its measurement against a mutant
EGFR sits in the training data, the model has effectively seen the answer.
It would score brilliantly and have learned nothing transferable. Measured
on our own data, 42% of the mutant rows are molecules that also appear in
the wild-type set, so this is the default outcome, not a remote risk.

Everything below exists to make that cheating impossible and then to prove
it was impossible.
"""

from dataclasses import dataclass, field

import numpy as np
from rdkit import DataStructs

from satori.model import Split


@dataclass
class Pool:
    """Rows from several targets, flattened into one table.

    One row is "this molecule, measured against this protein". The same
    molecule can appear many times with different `task` values, which is
    exactly the situation the leakage filter has to handle.
    """

    smiles: list[str]
    values: np.ndarray
    task: np.ndarray  # which protein each row refers to
    task_names: list[str]
    primary: int  # the protein we are judged on

    def __len__(self) -> int:
        return len(self.smiles)

    @property
    def is_primary(self) -> np.ndarray:
        return self.task == self.primary

    def indices_of(self, task_name: str) -> list[int]:
        task = self.task_names.index(task_name)
        return np.flatnonzero(self.task == task).tolist()


def build_pool(
    tables: dict[str, list[dict]],
    primary: str,
    column: str = "pchembl",
    task_column: str = "variant",
) -> Pool:
    """Flatten per-target tables into one pool.

    `tables` maps a file label to its rows. Rows carrying a `variant`
    column (as the mutant file does) are split into one task per variant,
    because a single changed amino acid can alter binding a thousandfold:
    those really are different proteins, not noise around one protein.
    """
    smiles: list[str] = []
    values: list[float] = []
    task_ids: list[int] = []
    task_names: list[str] = []

    for label, rows in tables.items():
        for row in rows:
            name = row.get(task_column) or label
            if name not in task_names:
                task_names.append(name)
            smiles.append(row["smiles"])
            values.append(float(row[column]))
            task_ids.append(task_names.index(name))

    if primary not in task_names:
        raise ValueError(f"primary task {primary!r} not among {task_names}")
    return Pool(
        smiles, np.array(values), np.array(task_ids), task_names, task_names.index(primary)
    )


def max_similarity_to(fingerprints: list, held_out: list) -> np.ndarray:
    """For each fingerprint, how close is the nearest held-out molecule?

    One row of comparisons at a time, so memory stays flat however large
    the pool grows.
    """
    if not held_out:
        return np.zeros(len(fingerprints))
    return np.array(
        [max(DataStructs.BulkTanimotoSimilarity(fp, held_out)) for fp in fingerprints]
    )


def too_close(fingerprints: list, held_out: list, cutoff: float) -> np.ndarray:
    """Which molecules are near enough to a held-out one to count as known?"""
    return max_similarity_to(fingerprints, held_out) >= cutoff


def honest_training_set(
    fingerprints: list, test: list[int], cutoff: float, candidates: list[int] | None = None
) -> list[int]:
    """Training rows that give away nothing about the test set.

    Drops any row whose molecule is within `cutoff` of any test molecule,
    across every task. This is stricter than holding out whole clusters:
    sphere-exclusion clustering only guarantees that members are close to
    their *centre*, so two molecules in different clusters can still be
    near neighbours of each other. Filtering against the test molecules
    themselves closes that gap.
    """
    held_out = [fingerprints[i] for i in test]
    excluded = set(test)
    pool = candidates if candidates is not None else range(len(fingerprints))
    keep = [i for i in pool if i not in excluded]
    blocked = too_close([fingerprints[i] for i in keep], held_out, cutoff)
    return [i for i, is_blocked in zip(keep, blocked) if not is_blocked]


@dataclass
class LeakageReport:
    """Proof that a training set was clean, or evidence that it was not."""

    worst_similarity: float
    offenders: int
    cutoff: float

    @property
    def clean(self) -> bool:
        return self.offenders == 0


def audit(fingerprints: list, train: list[int], test: list[int], cutoff: float) -> LeakageReport:
    """Check a finished split for leakage, after the fact.

    Run on every split, every time. A filter that is believed rather than
    checked is how a flattering number reaches a README.
    """
    similarities = max_similarity_to(
        [fingerprints[i] for i in train], [fingerprints[i] for i in test]
    )
    return LeakageReport(
        worst_similarity=round(float(similarities.max()), 3) if len(similarities) else 0.0,
        offenders=int((similarities >= cutoff).sum()),
        cutoff=cutoff,
    )


def with_task_feature(molecule_features: np.ndarray, pool: Pool) -> np.ndarray:
    """Add 'which protein is this?' to the molecule's own features.

    A one-hot column per task. It lets one model serve every protein while
    still being able to say "this molecule is potent against EGFR but not
    against CDK2", which a model given only the structure cannot express.

    Its limitation is worth knowing in advance: one-hot columns are
    equally distant from one another, so the model cannot tell that EGFR
    resembles its own L858R mutant more than a distant kinase. If pooling
    helps but weakly, replacing this with a measure of binding-site
    similarity is the next thing to try, not a bigger model.
    """
    one_hot = np.zeros((len(pool), len(pool.task_names)), dtype=molecule_features.dtype)
    one_hot[np.arange(len(pool)), pool.task] = 1
    return np.hstack([molecule_features, one_hot])


@dataclass
class Arm:
    """One side of the comparison: what it trained on, and how it scored."""

    name: str
    train: list[int] = field(default_factory=list)
    reports: list[LeakageReport] = field(default_factory=list)

    @property
    def all_clean(self) -> bool:
        return all(report.clean for report in self.reports)


def arms_for(
    pool: Pool,
    fingerprints: list,
    primary_split: Split,
    cutoff: float,
) -> tuple[Split, Split]:
    """Build the two training sets being compared, over one test set.

    Both are scored on exactly the same held-out molecules, and both are
    filtered by exactly the same rule. The only difference is whether rows
    from other proteins are allowed in. Without that symmetry the
    comparison would measure the filtering, not the pooling.
    """
    test = primary_split.test
    primary_rows = np.flatnonzero(pool.is_primary).tolist()

    single = honest_training_set(fingerprints, test, cutoff, candidates=primary_rows)
    multi = honest_training_set(fingerprints, test, cutoff)
    return (
        Split("single_task", single, test, f"{len(single):,} rows, one protein"),
        Split("multi_task", multi, test, f"{len(multi):,} rows across {len(pool.task_names)} proteins"),
    )
