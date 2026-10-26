from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class EvidenceRecord:
    disease_id: str
    target_id: str
    score: float
    source: str
    evidence_type: str = "association"
    retrieved_at: str = field(default_factory=utc_now)
    event_time: str | None = None
    source_record_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TargetRecord:
    target_id: str
    gene_symbol: str | None = None
    uniprot_id: str | None = None
    disease_id: str | None = None
    evidence: list[EvidenceRecord] = field(default_factory=list)
    sequence: str | None = None
    structure_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass(slots=True)
class TargetContext:
    disease_id: str
    target_id: str
    gene_symbol: str | None = None
    uniprot_id: str | None = None
    sequence: str | None = None
    sequence_sha256: str | None = None
    chembl_target_id: str | None = None
    structure_ids: list[str] = field(default_factory=list)
    structure_status: str = "unresolved"
    sequence_status: str = "unresolved"
    ligand_data_status: str = "unresolved"
    affinity_ready: bool = False
    docking_ready: bool = False
    blockers: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass(slots=True)
class LigandRecord:
    molecule_id: str
    smiles: str | None
    inchikey: str | None = None
    target_id: str | None = None
    assay_id: str | None = None
    activity_type: str | None = None
    activity_value: float | None = None
    activity_units: str | None = None
    pchembl_value: float | None = None
    source: str = "ChEMBL"
    source_version: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass(slots=True)
class MoleculeDecision:
    molecule_id: str
    accepted: bool
    reason: str | None
    canonical_smiles: str | None = None
    inchikey: str | None = None
    properties: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ActivityDecision:
    molecule_id: str
    assay_id: str | None
    accepted: bool
    reason: str | None
    activity_type: str | None
    activity_value: float | None
    activity_units: str | None
    pchembl_value: float | None
    policy_id: str


@dataclass(slots=True)
class StandardizedLigandRecord:
    source_record: LigandRecord
    accepted: bool
    rejection_reason: str | None
    canonical_smiles: str | None
    standardized_inchikey: str | None
    duplicate_structure: bool
    properties: dict[str, float] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass(slots=True)
class TriageDecision:
    molecule_id: str
    accepted: bool
    reason: str | None
    candidate: "CandidateRecord | None" = None


@dataclass(slots=True)
class CandidateRecord:
    molecule_id: str
    smiles: str
    target_id: str
    properties: dict[str, float] = field(default_factory=dict)
    generation_model: str | None = None
    affinity: float | None = None
    affinity_uncertainty: float | None = None
    ood_score: float | None = None
    docking_score: float | None = None
    docking_pose_path: str | None = None
    pareto_status: bool | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"


@dataclass(slots=True)
class PipelineRun:
    run_id: str
    disease_id: str
    seed: int
    config_hash: str
    code_commit: str
    status: str = "created"
    created_at: str = field(default_factory=utc_now)
    stages: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def to_jsonable(record: Any) -> dict[str, Any]:
    return asdict(record)
