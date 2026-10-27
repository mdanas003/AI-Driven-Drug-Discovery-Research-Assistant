"""Label quality: not every measurement deserves equal trust.

Step 5b showed that absolute accuracy is capped by how much the lab data
disagrees with itself. But that disagreement is not spread evenly. A
molecule measured once, by one group, with no way to check it, sits in the
same table as one measured fifty times in close agreement, and so far they
have counted exactly the same.

Two things follow:

1. **A cleaner test set gives a truer score.** If we score only on
   molecules whose labels we trust, the remaining error is the model's
   rather than the data's. That number is the one worth improving.
2. **Training might do better with weights.** Trusting the well-measured
   molecules more could help the model, or the lost data could hurt more
   than the noise does. That is a question to measure, not to assume.

Both need the same precaution: the *test* set decides what the score
means, so an experiment that changes the test set is answering a
different question from one that changes the training set.
"""

from dataclasses import dataclass

import numpy as np

from satori.model import Split

DEFAULT_MIN_MEASUREMENTS = 2
DEFAULT_MAX_SPREAD = 1.0

# How to turn confidence into a training weight.
WEIGHT_SCHEMES = ("equal", "count", "agreement", "both")


@dataclass
class Quality:
    """How much a label is worth trusting."""

    n_measurements: int
    spread: float

    @property
    def confident(self) -> bool:
        return self.is_confident()

    def is_confident(
        self,
        min_measurements: int = DEFAULT_MIN_MEASUREMENTS,
        max_spread: float = DEFAULT_MAX_SPREAD,
    ) -> bool:
        """Measured more than once, and the measurements agree."""
        return self.n_measurements >= min_measurements and self.spread <= max_spread


def quality_of(row: dict) -> Quality:
    """Read label quality from a `fetch-chembl` row."""
    return Quality(int(row.get("n_measurements") or 1), float(row.get("spread") or 0.0))


def confident_indices(
    rows: list[dict],
    min_measurements: int = DEFAULT_MIN_MEASUREMENTS,
    max_spread: float = DEFAULT_MAX_SPREAD,
) -> list[int]:
    return [
        i
        for i, row in enumerate(rows)
        if quality_of(row).is_confident(min_measurements, max_spread)
    ]


def weights(rows: list[dict], scheme: str = "both") -> np.ndarray:
    """Per-molecule training weights.

    "count": the average of n measurements is more reliable than one
        measurement, by roughly the square root of n.
    "agreement": measurements that disagree widely describe their molecule
        less precisely, so their average deserves less trust.
    "both": multiply the two.
    "equal": the Step 5 behaviour, kept as the reference.
    """
    if scheme not in WEIGHT_SCHEMES:
        raise ValueError(f"unknown weight scheme {scheme!r}; try one of {list(WEIGHT_SCHEMES)}")

    qualities = [quality_of(row) for row in rows]
    by_count = np.array([np.sqrt(q.n_measurements) for q in qualities])
    by_agreement = np.array([1.0 / (1.0 + q.spread) for q in qualities])
    chosen = {
        "equal": np.ones(len(rows)),
        "count": by_count,
        "agreement": by_agreement,
        "both": by_count * by_agreement,
    }[scheme]
    # Normalized to average 1, so weighting changes the balance between
    # molecules without changing the effective size of the training set.
    return chosen / chosen.mean()


def restrict(
    split: Split,
    train_allowed: set[int] | None = None,
    test_allowed: set[int] | None = None,
) -> Split:
    """Narrow a split to the molecules allowed on each side.

    Restricting the test side changes what the score *means*; restricting
    the training side changes what the model *sees*. Keeping them separate
    is what makes the two experiments comparable.
    """
    train = [i for i in split.train if train_allowed is None or i in train_allowed]
    test = [i for i in split.test if test_allowed is None or i in test_allowed]
    notes = []
    if train_allowed is not None:
        notes.append(f"training narrowed to {len(train):,}")
    if test_allowed is not None:
        notes.append(f"scored on {len(test):,} confident labels")
    return Split(
        split.name,
        train,
        test,
        "; ".join([split.explanation, *notes]),
    )
