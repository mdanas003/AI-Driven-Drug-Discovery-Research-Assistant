"""Execute existing scientific modules from durable jobs, preserving their real status."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

from satori.docking import VinaDockingEngine
from satori.generation.models import ETFlowConformerGenerator, GPMolFormerGenerator
from satori.optimization.graphfdm import GraphFDMOptimizer
from satori.runtime_config import RuntimeConfig


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"unsupported job result type: {type(value).__name__}")


def _discover(payload: dict[str, Any], config: RuntimeConfig) -> dict[str, Any]:
    from satori.data.sources import OpenTargetsClient
    disease_id = str(payload.get("disease_id", "")).strip()
    limit = int(payload.get("limit", 100))
    if not disease_id or limit < 1:
        raise ValueError("disease_id and positive limit are required")
    rows = OpenTargetsClient(cache_dir=config.data_dir / "raw" / "http-cache").disease_targets(
        disease_id, limit=limit)
    return {"operation": "Open Targets disease-target evidence retrieval", "disease_id": disease_id,
            "record_count": len(rows), "targets": _jsonable(rows),
            "scientific_status": "retrieved; target ranking/evaluation remains a separate gate"}


def _targets(payload: dict[str, Any], config: RuntimeConfig) -> dict[str, Any]:
    from satori.data.sources import OpenTargetsClient
    disease_id = str(payload.get("disease_id", "")).strip()
    limit = int(payload.get("limit", 100))
    if not disease_id or limit < 1:
        raise ValueError("disease_id and positive limit are required")
    rows = OpenTargetsClient(cache_dir=config.data_dir / "raw" / "http-cache").disease_targets(
        disease_id, limit=limit)
    return {"operation": "Open Targets candidate target retrieval", "disease_id": disease_id,
            "record_count": len(rows), "targets": _jsonable(rows),
            "scientific_status": "candidate evidence only; no final target selection is implied"}


def _generate(payload: dict[str, Any], config: RuntimeConfig) -> dict[str, Any]:
    import os
    from satori.generation.models import GenerationRequest
    from satori.model_registry import ModelArtifactRegistry
    required = ("target_id",)
    if any(not str(payload.get(key, "")).strip() for key in required):
        raise ValueError("target_id is required")
    request = GenerationRequest(
        target_id=str(payload["target_id"]), count=int(payload.get("count", 8)),
        seed=int(payload.get("seed", 17)), scaffold_smiles=payload.get("scaffold_smiles"),
        fragment_smiles=tuple(payload.get("fragment_smiles", ())),
        protein_sequence=payload.get("protein_sequence"), pocket_path=payload.get("pocket_path"),
        batch_size=int(payload.get("batch_size", 8)), max_length=int(payload.get("max_length", 202)))
    registry = ModelArtifactRegistry(config.model_registry)
    model = registry.remote_descriptor("gp_molformer_uniq")
    model_id, _, model_revision = model["checkpoint_identifier"].partition("@")
    tokenizer_id, _, tokenizer_revision = model["tokenizer_identifier"].partition("@")
    if not all((model_revision, tokenizer_id, tokenizer_revision)):
        from satori.errors import CheckpointUnavailable
        raise CheckpointUnavailable("GP-MoLFormer registry entry must pin model and tokenizer revisions")
    os.environ.setdefault("HF_HOME", str(config.model_cache_dir / "huggingface"))
    rows = GPMolFormerGenerator(
        device=None if config.device == "auto" else config.device,
        model_id=model_id, model_revision=model_revision,
        tokenizer_id=tokenizer_id, tokenizer_revision=tokenizer_revision).generate(request)
    return {"operation": "GP-MoLFormer molecular generation", "molecules": _jsonable(rows),
            "requested_count": request.count,
            "scientific_status": "real inference; this checkpoint is not protein/pocket conditioned",
            "target_conditioned": False}


def _optimize(payload: dict[str, Any], _config: RuntimeConfig) -> dict[str, Any]:
    from satori.optimization.graphfdm import OptimizationObjectives
    target_id = str(payload.get("target_id", "")).strip()
    disease_id = str(payload.get("disease_id", "")).strip()
    molecules = payload.get("molecules", [])
    if not target_id or not disease_id or not isinstance(molecules, list):
        raise ValueError("disease_id, target_id, and a molecules list are required")
    # GraphFDM remains the primary optimizer. Its explicit scientific blocker propagates.
    output = GraphFDMOptimizer(plugin=payload.get("plugin"),
                               checkpoint=payload.get("checkpoint")).optimize(
        molecules, target_id=target_id,
        objectives=OptimizationObjectives.for_disease(disease_id, target_id))
    return {"operation": "GraphFDM optimization", "molecules": output}


def _dock(payload: dict[str, Any], _config: RuntimeConfig) -> dict[str, Any]:
    receptor = Path(str(payload.get("receptor", ""))).expanduser().resolve()
    ligand = Path(str(payload.get("ligand", ""))).expanduser().resolve()
    if not receptor.is_file() or not ligand.is_file():
        from satori.errors import ComponentBlocked
        raise ComponentBlocked("Docking blocked: receptor and ligand must be staged PDBQT artifacts.")
    center = tuple(float(x) for x in payload.get("center", ()))
    size = tuple(float(x) for x in payload.get("size", ()))
    if len(center) != 3 or len(size) != 3 or any(x <= 0 for x in size):
        raise ValueError("center and size must be three values; box dimensions must be positive")
    output = Path(str(payload.get("output_pose", "artifacts/docking/pose.pdbqt"))).expanduser()
    result = VinaDockingEngine(str(payload.get("executable", "vina"))).dock(
        receptor, ligand, output, center, size,
        exhaustiveness=int(payload.get("exhaustiveness", 8)),
        modes=int(payload.get("modes", 9)))
    return {"operation": "AutoDock Vina", "result": _jsonable(result),
            "protocol_validation": "NOT_VALIDATED; score is a docking hypothesis, not measured affinity"}


def _etflow(payload: dict[str, Any], _config: RuntimeConfig) -> dict[str, Any]:
    from satori.model_registry import ModelArtifactRegistry
    model = ModelArtifactRegistry(_config.model_registry).describe("etflow_drugs_o3")
    if model.get("availability") != "available":
        from satori.errors import ComponentBlocked
        raise ComponentBlocked(model.get("blocker") or "ET-Flow checkpoint is not cleared for execution")
    smiles = payload.get("smiles")
    if not isinstance(smiles, list) or not smiles:
        raise ValueError("smiles must be a non-empty list")
    conformers = ETFlowConformerGenerator().generate(smiles, samples=int(payload.get("samples", 1)))
    return {"operation": "ET-Flow conformer generation", "conformers": _jsonable(conformers),
            "scientific_status": "inference completed; checkpoint licensing/validation must be separately cleared"}


HANDLERS: dict[str, Callable[[dict[str, Any], RuntimeConfig], dict[str, Any]]] = {
    "discover": _discover, "targets": _targets, "generate": _generate,
    "optimize": _optimize, "dock": _dock, "etflow": _etflow,
}
