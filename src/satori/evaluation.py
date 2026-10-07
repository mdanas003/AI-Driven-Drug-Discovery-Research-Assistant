from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def ranking_metrics(ranked_ids: Sequence[str], relevant_ids: set[str], *, k: int = 10) -> dict[str, float]:
    if k < 1:
        raise ValueError("k must be positive")
    if len(ranked_ids) != len(set(ranked_ids)):
        raise ValueError("Ranked identifiers must be unique")
    top = list(ranked_ids[:k])
    hits = [index + 1 for index, identifier in enumerate(top) if identifier in relevant_ids]
    return {
        f"precision_at_{k}": len(hits) / max(1, k),
        f"recall_at_{k}": len(hits) / max(1, len(relevant_ids)),
        "mrr": 1.0 / hits[0] if hits else 0.0,
        f"hits_at_{k}": float(bool(hits)),
    }


def evaluate_target_rankings(
    rankings: dict[str, Sequence[str]],
    relevant_ids: set[str],
    *,
    benchmark_id: str,
    dataset_hash_sha256: str,
    split_manifest_hash_sha256: str,
    ks: Sequence[int] = (5, 10, 20),
) -> dict[str, Any]:
    """Evaluate named rankers against fixed held-out relevance labels with lineage."""
    if not benchmark_id.strip() or not dataset_hash_sha256 or not split_manifest_hash_sha256:
        raise ValueError("Evaluation requires benchmark, dataset hash, and split-manifest hash")
    if not relevant_ids:
        raise ValueError("Target ranking benchmark must contain at least one relevant target")
    if not rankings:
        raise ValueError("At least one ranking is required")
    if not ks or any(k < 1 for k in ks) or len(set(ks)) != len(ks):
        raise ValueError("ks must contain unique positive integers")
    metrics: dict[str, dict[str, float]] = {}
    for model_id, ranking in sorted(rankings.items()):
        if not model_id.strip():
            raise ValueError("Every ranker needs a non-empty model ID")
        values: dict[str, float] = {}
        for k in ks:
            values.update(ranking_metrics(ranking, relevant_ids, k=k))
        metrics[model_id] = values
    return {
        "evaluation_schema_version": "1.0",
        "benchmark_id": benchmark_id,
        "dataset_hash_sha256": dataset_hash_sha256,
        "split_manifest_hash_sha256": split_manifest_hash_sha256,
        "relevant_target_count": len(relevant_ids),
        "rankers": metrics,
    }


def affinity_metrics(observed: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    if len(observed) != len(predicted) or not observed:
        raise ValueError("Observed/predicted arrays must have equal, non-zero length.")
    n = len(observed)
    errors = [float(y) - float(p) for y, p in zip(observed, predicted)]
    mae = sum(abs(error) for error in errors) / n
    rmse = math.sqrt(sum(error * error for error in errors) / n)
    mean_y, mean_p = sum(observed) / n, sum(predicted) / n
    numerator = sum((y - mean_y) * (p - mean_p) for y, p in zip(observed, predicted))
    denominator = math.sqrt(sum((y - mean_y) ** 2 for y in observed) *
                            sum((p - mean_p) ** 2 for p in predicted))
    pearson = numerator / denominator if denominator else 0.0
    concordant = prediction_ties = comparable = 0
    for i in range(n):
        for j in range(i + 1, n):
            actual = observed[i] - observed[j]
            estimate = predicted[i] - predicted[j]
            if actual == 0:
                continue
            comparable += 1
            if estimate == 0:
                prediction_ties += 1
            elif actual * estimate > 0:
                concordant += 1
    return {"mae": mae, "rmse": rmse, "pearson": pearson,
            "concordance_index": (concordant + 0.5 * prediction_ties) / comparable if comparable else 0.0}


def generation_metrics(smiles: Sequence[str], training_smiles: set[str] | None = None) -> dict[str, Any]:
    try:
        from rdkit import Chem
        from rdkit.Chem import QED
    except ImportError as exc:
        from satori.errors import DependencyUnavailable
        raise DependencyUnavailable("Generation metrics require the [chemistry] extra (RDKit).") from exc
    valid: list[str] = []
    qed: list[float] = []
    scaffolds: set[str] = set()
    from rdkit.Chem.Scaffolds import MurckoScaffold
    for smiles_value in smiles:
        molecule = Chem.MolFromSmiles(smiles_value)
        if molecule is None:
            continue
        canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
        valid.append(canonical)
        qed.append(float(QED.qed(molecule)))
        scaffolds.add(MurckoScaffold.MurckoScaffoldSmiles(mol=molecule, includeChirality=True))
    unique = set(valid)
    novelty = (len(unique - training_smiles) / len(unique)) if unique and training_smiles is not None else None
    return {"validity": len(valid) / max(1, len(smiles)), "uniqueness": len(unique) / max(1, len(valid)),
            "novelty": novelty, "novelty_status": "evaluated" if training_smiles is not None else "BLOCKED_NO_TRAINING_REFERENCE",
            "mean_qed": sum(qed) / max(1, len(qed)),
            "scaffold_diversity": len(scaffolds) / max(1, len(unique)),
            "synthetic_accessibility": None, "three_d_validity": None}
