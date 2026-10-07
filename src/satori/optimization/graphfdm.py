from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from satori.errors import ComponentBlocked


@dataclass(frozen=True, slots=True)
class ObjectiveChannel:
    """One independently reported Pareto dimension; values are never scalar weights."""

    name: str
    direction: Literal["maximize", "minimize"]
    status: Literal["ready", "pending_data", "pending_model"]


@dataclass(frozen=True, slots=True)
class OptimizationObjectives:
    """Approved disease-specific objective vector, without scalarization or thresholds.

    Target endpoint names, predictor versions, and availability are bound only after
    target selection and predictor validation. The interface intentionally carries
    no default score, weight, or imputation for a missing scientific channel.
    """

    disease_id: str
    target_id: str
    channels: tuple[ObjectiveChannel, ...]

    @classmethod
    def for_disease(cls, disease_id: str, target_id: str) -> "OptimizationObjectives":
        if not disease_id.strip() or not target_id.strip():
            raise ValueError("disease_id and target_id must be non-empty")
        if disease_id not in {"MONDO_0005233", "MONDO_0004975", "MONDO_0005148"}:
            raise ValueError(f"Unsupported disease objective policy: {disease_id!r}")
        channels = [
            ObjectiveChannel("target_specific_potency_affinity", "maximize", "pending_data"),
            ObjectiveChannel("selectivity", "maximize", "pending_model"),
            ObjectiveChannel("qed", "maximize", "ready"),
            ObjectiveChannel("synthetic_difficulty", "minimize", "pending_model"),
            ObjectiveChannel("validated_admet_endpoints", "maximize", "pending_model"),
            ObjectiveChannel("novelty", "maximize", "ready"),
            ObjectiveChannel("scaffold_diversity", "maximize", "ready"),
            ObjectiveChannel("uncertainty_ood_penalty", "minimize", "pending_model"),
        ]
        if disease_id == "MONDO_0004975":
            channels.extend((
                ObjectiveChannel("cns_mpo", "maximize", "ready"),
                ObjectiveChannel("bbb_suitability", "maximize", "pending_model"),
            ))
        return cls(disease_id, target_id, tuple(channels))


class MoleculeOptimizer(Protocol):
    def optimize(self, molecules: list[str], *, target_id: str,
                 objectives: OptimizationObjectives) -> list[str]: ...


class GraphFDMOptimizer:
    """Research adapter; deliberately fails until a compatible GraphFDM implementation exists."""

    model_id = "graphfdm-constrained-flow"

    def __init__(self, plugin: str | None = None, checkpoint: str | None = None):
        self.plugin = plugin
        self.checkpoint = checkpoint

    def optimize(self, molecules: list[str], *, target_id: str,
                 objectives: OptimizationObjectives) -> list[str]:
        if target_id != objectives.target_id:
            raise ValueError("target_id must match the target bound to the objective vector")
        if not self.plugin or not self.checkpoint:
            raise ComponentBlocked(
                "GraphFDM execution blocked: the supplied architecture names no compatible implementation, "
                "checkpoint, objective training procedure, or validated plugin. No RL substitution was made."
            )
        raise ComponentBlocked(f"GraphFDM plugin {self.plugin!r} has no registered adapter implementation.")
