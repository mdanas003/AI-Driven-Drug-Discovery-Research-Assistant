from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from satori.activity import ActivityPolicy, apply_activity_policy
from satori.chemistry import standardize_activity_records
from satori.data.sources import ChEMBLClient, OpenTargetsClient, RCSBClient, UniProtClient
from satori.provenance import write_dataset_manifest, write_jsonl
from satori.schemas import LigandRecord, TargetRecord
from satori.splits import molecule_split, target_disjoint_split, write_split_manifest
from satori.targets.context import resolve_target_context


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _diseases_from_config(path: Path) -> list[dict[str, str]]:
    config = json.loads(path.read_text(encoding="utf-8"))
    diseases = config.get("diseases")
    if not isinstance(diseases, list) or not diseases:
        raise ValueError("Config must contain a non-empty 'diseases' list")
    result: list[dict[str, str]] = []
    keys: set[str] = set()
    ids: set[str] = set()
    for disease in diseases:
        key = str(disease.get("key", "")).strip()
        disease_id = str(disease.get("open_targets_id", "")).strip()
        if not key or not disease_id:
            raise ValueError("Each configured disease needs non-empty key and open_targets_id")
        if Path(key).name != key or key in {".", ".."}:
            raise ValueError(f"Disease key is not a safe file name: {key!r}")
        if key in keys or disease_id in ids:
            raise ValueError("Disease config contains duplicate keys or disease IDs")
        keys.add(key)
        ids.add(disease_id)
        result.append({"key": key, "name": str(disease.get("name") or key), "disease_id": disease_id})
    return result


def _ingest_target(disease: dict[str, str], output: Path, limit: int) -> dict[str, Any]:
    records = OpenTargetsClient().disease_targets(disease["disease_id"], limit=limit)
    for record in records:
        record.metadata["configured_disease_key"] = disease["key"]
        record.metadata["configured_disease_name"] = disease["name"]
    digest = write_jsonl(output, (asdict(row) for row in records))
    write_dataset_manifest(str(output) + ".manifest.json", source="Open Targets",
                           dataset_hash=digest, processing_version="0.2.0",
                           filters={"disease_id": disease["disease_id"], "limit": limit},
                           record_count=len(records), metadata={"disease_key": disease["key"],
                                                               "disease_name": disease["name"]})
    return {"disease_id": disease["disease_id"], "count": len(records),
            "sha256": digest, "path": str(output)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="satori")
    sub = parser.add_subparsers(dest="command", required=True)
    targets = sub.add_parser("ingest-targets", help="Fetch target associations for one or more diseases")
    selection = targets.add_mutually_exclusive_group(required=True)
    selection.add_argument("--disease-id", help="Open Targets disease ID")
    selection.add_argument("--config", type=Path, help="Config containing a diseases list")
    targets.add_argument("--limit", type=int, default=100)
    targets.add_argument("--output", type=Path, help="Output JSONL for --disease-id")
    targets.add_argument("--output-dir", type=Path, help="Directory for per-disease JSONL when using --config")

    ligands = sub.add_parser("fetch-ligands", help="Fetch target activities from ChEMBL")
    ligand_source = ligands.add_mutually_exclusive_group(required=True)
    ligand_source.add_argument("--chembl-target-id", help="ChEMBL target ID")
    ligand_source.add_argument("--contexts", type=Path,
                               help="TargetContext JSONL; fetch separately for every ChEMBL-linked target")
    ligands.add_argument("--limit", type=int, default=1000)
    ligands.add_argument("--output", type=Path, help="Output JSONL for --chembl-target-id")
    ligands.add_argument("--output-dir", type=Path,
                         help="Output directory for per-target JSONL when using --contexts")

    process = sub.add_parser("standardize", help="Standardize ChEMBL ligand JSONL with RDKit")
    standardize_source = process.add_mutually_exclusive_group(required=True)
    standardize_source.add_argument("--input", type=Path)
    standardize_source.add_argument("--input-dir", type=Path,
                                    help="Process each *.ligands.jsonl independently by target")
    process.add_argument("--output", type=Path, help="Output JSONL for --input")
    process.add_argument("--output-dir", type=Path,
                         help="Output directory for per-target decisions when using --input-dir")

    activity = sub.add_parser("filter-activities", help="Apply explicit ChEMBL activity inclusion policy")
    activity.add_argument("--input", type=Path, required=True)
    activity.add_argument("--policy", type=Path, required=True)
    activity.add_argument("--accepted-output", type=Path, required=True)
    activity.add_argument("--decisions-output", type=Path, required=True)

    context = sub.add_parser("resolve-target-context", help="Resolve protein, ChEMBL, and structure context")
    context.add_argument("--input", type=Path, required=True)
    context.add_argument("--output", type=Path, required=True)

    split = sub.add_parser("create-split", help="Create a leakage-aware split and assignment manifest")
    split.add_argument("--input", type=Path, required=True)
    split.add_argument("--strategy", choices=("random", "scaffold", "temporal", "target_disjoint"),
                       required=True)
    split.add_argument("--output", type=Path, required=True)
    split.add_argument("--seed", type=int, default=17)
    split.add_argument("--fractions", nargs=3, type=float, default=(0.8, 0.1, 0.1),
                       metavar=("TRAIN", "VALIDATION", "TEST"))
    split.add_argument("--source-version", default="unspecified")
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    if args.command == "ingest-targets":
        if args.limit < 1:
            parser.error("--limit must be positive")
        if args.disease_id:
            if args.output is None:
                parser.error("--output is required with --disease-id")
            if args.output_dir is not None:
                parser.error("--output-dir is only used with --config")
            disease = {"key": args.disease_id, "name": args.disease_id,
                       "disease_id": args.disease_id}
            result = [_ingest_target(disease, args.output, args.limit)]
        else:
            if args.output_dir is None:
                parser.error("--output-dir is required with --config")
            if args.output is not None:
                parser.error("--output is only used with --disease-id")
            diseases = _diseases_from_config(args.config)
            results: list[dict[str, Any]] = []
            for disease in diseases:
                path = args.output_dir / f"{disease['key']}.targets.jsonl"
                results.append(_ingest_target(disease, path, args.limit))
            result = results
        print(json.dumps({"datasets": result}, sort_keys=True))
    elif args.command == "fetch-ligands":
        if args.limit < 1:
            parser.error("--limit must be positive")
        if args.chembl_target_id:
            if args.output is None or args.output_dir is not None:
                parser.error("--output is required and --output-dir forbidden with --chembl-target-id")
            targets = [{"chembl_target_id": args.chembl_target_id, "disease_id": "unassigned",
                        "target_id": args.chembl_target_id}]
            output_dir = None
        else:
            if args.output_dir is None or args.output is not None:
                parser.error("--output-dir is required and --output forbidden with --contexts")
            output_dir = args.output_dir
            targets = [row for row in _read_jsonl(args.contexts)]
        results: list[dict[str, Any]] = []
        client = ChEMBLClient()
        for target in targets:
            chembl_target_id = target.get("chembl_target_id")
            disease_id = str(target.get("disease_id") or "unassigned")
            target_id = str(target.get("target_id") or "unassigned")
            if output_dir is None:
                path = args.output
            else:
                path = output_dir / f"{disease_id}__{target_id}.ligands.jsonl"
            if not chembl_target_id:
                results.append({"disease_id": disease_id, "target_id": target_id,
                                "status": "blocked", "reason": "No exact ChEMBL target mapping",
                                "path": None})
                continue
            records = client.target_ligands(str(chembl_target_id), limit=args.limit)
            digest = write_jsonl(path, (asdict(row) for row in records))
            write_dataset_manifest(str(path) + ".manifest.json", source="ChEMBL",
                                   dataset_hash=digest, processing_version="0.2.0",
                                   filters={"chembl_target_id": chembl_target_id,
                                            "limit": args.limit}, record_count=len(records),
                                   metadata={"disease_id": disease_id, "target_id": target_id})
            results.append({"disease_id": disease_id, "target_id": target_id,
                            "chembl_target_id": chembl_target_id, "status": "succeeded",
                            "count": len(records), "sha256": digest, "path": str(path)})
        print(json.dumps({"targets": results}, sort_keys=True))
    elif args.command == "standardize":
        if args.input is not None:
            if args.output is None or args.output_dir is not None:
                parser.error("--output is required and --output-dir forbidden with --input")
            input_paths = [(args.input, args.output)]
        else:
            if args.output_dir is None or args.output is not None:
                parser.error("--output-dir is required and --output forbidden with --input-dir")
            input_paths = [(path, args.output_dir / f"{path.stem}.standardized.jsonl")
                           for path in sorted(args.input_dir.glob("*.ligands.jsonl"))]
            if not input_paths:
                parser.error(f"No *.ligands.jsonl datasets found in {args.input_dir}")
        summaries: list[dict[str, Any]] = []
        for input_path, output_path in input_paths:
            records = [LigandRecord(**row) for row in _read_jsonl(input_path)]
            decisions = standardize_activity_records(records)
            digest = write_jsonl(output_path, (asdict(row) for row in decisions))
            accepted = sum(decision.accepted for decision in decisions)
            rejected = len(decisions) - accepted
            duplicate_structures = sum(decision.duplicate_structure for decision in decisions)
            reason_counts: dict[str, int] = {}
            for decision in decisions:
                if not decision.accepted:
                    reason = decision.rejection_reason or "UNSPECIFIED_REJECTION"
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
            write_dataset_manifest(str(output_path) + ".manifest.json",
                                   source="Standardized ligand dataset", dataset_hash=digest,
                                   processing_version="0.2.0",
                                   filters={"operation": "RDKit parse, hydrogen removal, canonical stereochemical SMILES; assay records retained and repeated structures marked"},
                                   record_count=len(decisions), metadata={
                                       "input_path": str(input_path),
                                       "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                                       "accepted": accepted, "rejected": rejected,
                                       "duplicate_structure_records_retained": duplicate_structures,
                                       "rejection_reasons": reason_counts})
            summaries.append({"input": str(input_path), "path": str(output_path),
                              "count": len(decisions), "accepted": accepted, "rejected": rejected,
                              "duplicate_structure_records_retained": duplicate_structures,
                              "rejection_reasons": reason_counts, "sha256": digest})
        print(json.dumps({"datasets": summaries}, sort_keys=True))
    elif args.command == "filter-activities":
        policy_data = json.loads(args.policy.read_text(encoding="utf-8"))
        allowed_fields = {field.name for field in fields(ActivityPolicy)}
        unknown = set(policy_data) - allowed_fields
        if unknown:
            parser.error(f"Unknown activity policy fields: {sorted(unknown)}")
        for key in ("allowed_types", "allowed_units", "allowed_relations"):
            if key in policy_data:
                policy_data[key] = tuple(policy_data[key])
        policy = ActivityPolicy(**policy_data)
        records = [LigandRecord(**row) for row in _read_jsonl(args.input)]
        accepted_rows, decisions = apply_activity_policy(records, policy)
        dataset_hash = write_jsonl(args.accepted_output, (asdict(row) for row in accepted_rows))
        decision_hash = write_jsonl(args.decisions_output, (asdict(row) for row in decisions))
        rejected = [decision for decision in decisions if not decision.accepted]
        reason_counts: dict[str, int] = {}
        for decision in rejected:
            reason = decision.reason or "UNSPECIFIED_REJECTION"
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        write_dataset_manifest(str(args.accepted_output) + ".manifest.json",
                               source="ChEMBL activity policy output", dataset_hash=dataset_hash,
                               processing_version="0.2.0", filters=policy.as_dict(),
                               record_count=len(accepted_rows),
                               metadata={"input_path": str(args.input),
                                         "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
                                         "decision_sha256": decision_hash,
                                         "rejected_count": len(rejected),
                                         "rejection_reasons": reason_counts})
        print(json.dumps({"input_count": len(records), "accepted": len(accepted_rows),
                          "rejected": len(rejected), "rejection_reasons": reason_counts,
                          "accepted_sha256": dataset_hash, "decision_sha256": decision_hash,
                          "accepted_path": str(args.accepted_output),
                          "decisions_path": str(args.decisions_output)}, sort_keys=True))
    elif args.command == "resolve-target-context":
        targets = [TargetRecord(**row) for row in _read_jsonl(args.input)]
        contexts = [resolve_target_context(target, uniprot_client=UniProtClient(),
                                           chembl_client=ChEMBLClient(), rcsb_client=RCSBClient())
                    for target in targets]
        digest = write_jsonl(args.output, (asdict(context) for context in contexts))
        status_counts: dict[str, int] = {}
        for context in contexts:
            status_counts[context.sequence_status] = status_counts.get(context.sequence_status, 0) + 1
        write_dataset_manifest(str(args.output) + ".manifest.json", source="UniProt/ChEMBL/RCSB",
                               dataset_hash=digest, processing_version="0.2.0",
                               filters={"target_count": len(targets)}, record_count=len(contexts),
                               metadata={"sequence_status_counts": status_counts,
                                         "contexts_with_chembl_target": sum(bool(item.chembl_target_id)
                                                                             for item in contexts),
                                         "contexts_with_structure_ids": sum(bool(item.structure_ids)
                                                                             for item in contexts)})
        print(json.dumps({"count": len(contexts), "sequence_status_counts": status_counts,
                          "contexts_with_chembl_target": sum(bool(item.chembl_target_id)
                                                              for item in contexts),
                          "contexts_with_structure_ids": sum(bool(item.structure_ids)
                                                              for item in contexts),
                          "sha256": digest, "path": str(args.output)}, sort_keys=True))
    elif args.command == "create-split":
        rows = _read_jsonl(args.input)
        if args.seed < 0:
            parser.error("--seed must be non-negative")
        if args.strategy == "target_disjoint":
            split = target_disjoint_split(rows, seed=args.seed, fractions=tuple(args.fractions))
        else:
            split = molecule_split(rows, strategy=args.strategy, seed=args.seed,
                                   fractions=tuple(args.fractions))
        dataset_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
        assignment_hash = write_split_manifest(args.output, split, dataset_hash=dataset_hash,
                                               source_version=args.source_version)
        print(json.dumps({"strategy": split.strategy, "seed": split.seed,
                          "train_count": len(split.train), "validation_count": len(split.validation),
                          "test_count": len(split.test), "dataset_sha256": dataset_hash,
                          "assignment_sha256": assignment_hash, "path": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
