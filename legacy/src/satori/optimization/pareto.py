from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParetoResult:
    index: int
    nondominated: bool
    dominators: tuple[int, ...]
    objective_values: dict[str, float]


def pareto_front(
    rows: Sequence[Mapping[str, float]], *, maximize: Sequence[str], minimize: Sequence[str] = ()
) -> list[ParetoResult]:
    """Return exact non-dominated status with per-row values and dominator indices.

    Missing, non-numeric and non-finite objective values are errors: candidates
    are never silently dropped or assigned a favorable imputed score.
    """
    objectives = tuple(maximize) + tuple(minimize)
    if not objectives or len(set(objectives)) != len(objectives):
        raise ValueError("Provide unique objectives with at least one maximize/minimize direction")
    normalized: list[tuple[float, ...]] = []
    for index, row in enumerate(rows):
        values: list[float] = []
        for name in maximize:
            value = row.get(name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"row {index} has missing/non-finite objective {name!r}")
            values.append(float(value))
        for name in minimize:
            value = row.get(name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"row {index} has missing/non-finite objective {name!r}")
            values.append(-float(value))
        normalized.append(tuple(values))

    results: list[ParetoResult] = []
    for i, candidate in enumerate(normalized):
        dominators = tuple(
            j for j, other in enumerate(normalized)
            if j != i and all(a >= b for a, b in zip(other, candidate))
            and any(a > b for a, b in zip(other, candidate))
        )
        results.append(ParetoResult(
            index=i,
            nondominated=not dominators,
            dominators=dominators,
            objective_values={name: float(rows[i][name]) for name in objectives},
        ))
    return results
