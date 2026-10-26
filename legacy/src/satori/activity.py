from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from satori.schemas import ActivityDecision, LigandRecord


@dataclass(frozen=True, slots=True)
class ActivityPolicy:
    """Explicit, serializable activity inclusion criteria; there are no hidden defaults."""

    policy_id: str
    allowed_types: tuple[str, ...] = ()
    allowed_units: tuple[str, ...] = ()
    allowed_relations: tuple[str, ...] = ()
    min_pchembl: float | None = None
    max_pchembl: float | None = None

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must be non-empty")
        if self.min_pchembl is not None and self.max_pchembl is not None:
            if self.min_pchembl > self.max_pchembl:
                raise ValueError("min_pchembl cannot exceed max_pchembl")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def apply_activity_policy(
    records: Iterable[LigandRecord], policy: ActivityPolicy
) -> tuple[list[LigandRecord], list[ActivityDecision]]:
    """Select activities while returning a decision row for every input record."""
    accepted_records: list[LigandRecord] = []
    decisions: list[ActivityDecision] = []
    for record in records:
        reason: str | None = None
        relation = record.provenance.get("relation")
        if policy.allowed_types and record.activity_type not in policy.allowed_types:
            reason = "ACTIVITY_TYPE_NOT_ALLOWED"
        elif policy.allowed_units and record.activity_units not in policy.allowed_units:
            reason = "ACTIVITY_UNITS_NOT_ALLOWED"
        elif policy.allowed_relations and relation not in policy.allowed_relations:
            reason = "ACTIVITY_RELATION_NOT_ALLOWED"
        elif policy.min_pchembl is not None and record.pchembl_value is None:
            reason = "MISSING_PCHEMBL_FOR_MINIMUM"
        elif policy.min_pchembl is not None and record.pchembl_value < policy.min_pchembl:
            reason = "PCHEMBL_BELOW_MINIMUM"
        elif policy.max_pchembl is not None and record.pchembl_value is None:
            reason = "MISSING_PCHEMBL_FOR_MAXIMUM"
        elif policy.max_pchembl is not None and record.pchembl_value > policy.max_pchembl:
            reason = "PCHEMBL_ABOVE_MAXIMUM"
        accepted = reason is None
        decisions.append(ActivityDecision(
            molecule_id=record.molecule_id,
            assay_id=record.assay_id,
            accepted=accepted,
            reason=reason,
            activity_type=record.activity_type,
            activity_value=record.activity_value,
            activity_units=record.activity_units,
            pchembl_value=record.pchembl_value,
            policy_id=policy.policy_id,
        ))
        if accepted:
            accepted_records.append(record)
    return accepted_records, decisions
