from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlencode

from satori.data.http import request_cache_metadata, request_json
from satori.data.sources import ChEMBLClient, OpenTargetsClient, UniProtClient
from satori.provenance import write_dataset_manifest, write_json_atomic, write_jsonl


DISEASES = (
    ("nsclc", "MONDO_0005233"),
    ("alzheimers_disease", "MONDO_0004975"),
    ("type_2_diabetes", "MONDO_0005148"),
)


def inspect_targets(output: Path, top_k: int) -> list[dict[str, object]]:
    evidence_dir = output / "target-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    uniprot = UniProtClient()
    chembl = ChEMBLClient()
    for disease_key, disease_id in DISEASES:
        candidates = OpenTargetsClient().disease_targets(disease_id, limit=100)
        rows: list[dict[str, object]] = []
        for rank, candidate in enumerate(candidates, start=1):
            source_row = candidate.metadata["source_row"]
            row: dict[str, object] = {
                "disease_key": disease_key,
                "disease_id": disease_id,
                "rank": rank,
                "target_id": candidate.target_id,
                "gene_symbol": candidate.gene_symbol,
                "association_score": candidate.evidence[0].score,
                "datatype_scores": {
                    score["id"]: score.get("score")
                    for score in source_row.get("datatypeScores", [])
                },
                "opentargets_source_row": source_row,
                "opentargets_provenance": candidate.metadata.get("raw_response"),
            }
            if rank <= top_k:
                try:
                    hits = uniprot.search_ensembl(candidate.target_id)
                    accessions = sorted({hit["primaryAccession"] for hit in hits
                                         if hit.get("primaryAccession")})
                    row["uniprot_accessions"] = accessions
                    row["uniprot_response"] = uniprot.last_response_ref
                    if len(accessions) != 1:
                        row["mapping_status"] = "unmapped" if not accessions else "ambiguous_uniprot"
                    else:
                        chembl_id = chembl.target_id_for_uniprot(accessions[0])
                        row["chembl_mapping"] = chembl.last_target_mapping
                        row["mapping_status"] = "exact_single_accession" if chembl_id else "no_exact_chembl_target"
                        if chembl_id:
                            params = urlencode({"target_chembl_id": chembl_id,
                                                "limit": 1, "offset": 0, "format": "json"})
                            url = f"{chembl.endpoint}/activity.json?{params}"
                            page = request_json(url, cache_dir=chembl.cache_dir)
                            count_ref = request_cache_metadata(url, cache_dir=chembl.cache_dir)
                            row["activity_availability"] = {
                                "total_count": (page.get("page_meta") or {}).get("total_count", 0),
                                "sample_standard_type": (page.get("activities") or [{}])[0].get("standard_type"),
                                "response": count_ref,
                            }
                except Exception as exc:  # preserve target and explicit lookup failure
                    row["mapping_status"] = "lookup_failed"
                    row["mapping_error"] = f"{type(exc).__name__}: {exc}"
            else:
                row["mapping_status"] = "not_attempted_outside_top_k"
            rows.append(row)
        filename = evidence_dir / f"{disease_key}.candidate-targets.jsonl"
        digest = write_jsonl(filename, rows)
        summaries.append({"disease_key": disease_key, "disease_id": disease_id,
                          "candidate_count": len(rows), "mapping_top_k": top_k,
                          "path": str(filename), "sha256": digest,
                          "mapped_top_k": sum(row.get("mapping_status") == "exact_single_accession"
                                              for row in rows[:top_k])})
    write_json_atomic(evidence_dir / "summary.json", {
        "source": "Open Targets Platform GraphQL, UniProtKB REST, ChEMBL REST",
        "ranking": "Open Targets disease associated-target rows, descending source score",
        "candidate_limit": 100,
        "mapping_limit": top_k,
        "diseases": summaries,
    })
    return summaries


def retrieve_activity_rows(output: Path, candidates_per_disease: int, limit: int,
                           activity_page_size: int) -> list[dict[str, object]]:
    source_dir = output / "target-evidence"
    activity_dir = output / "chembl-target-activities"
    activity_dir.mkdir(parents=True, exist_ok=True)
    client = ChEMBLClient()
    summaries = []
    for disease_key, _ in DISEASES:
        path = source_dir / f"{disease_key}.candidate-targets.jsonl"
        candidates = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                      if line.strip()]
        mapped = [row for row in candidates
                  if row.get("mapping_status") == "exact_single_accession"
                  and row.get("chembl_mapping", {}).get("target_chembl_id")]
        mapped.sort(key=lambda row: (-(row.get("association_score") or 0), row.get("target_id", "")))
        for candidate in mapped[:candidates_per_disease]:
            chembl_id = candidate["chembl_mapping"]["target_chembl_id"]
            filename = activity_dir / f"{disease_key}__{candidate['target_id']}__{chembl_id}.jsonl"
            manifest_path = Path(str(filename) + ".manifest.json")
            existing = None
            if filename.exists() and manifest_path.exists():
                try:
                    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    existing = None
            if (existing and existing.get("metadata", {}).get("target_id") == candidate["target_id"]
                    and (existing.get("record_count") or 0) >= min(
                        limit, candidate.get("activity_availability", {}).get("total_count") or limit)):
                summaries.append({
                    "disease_key": disease_key, "disease_id": candidate["disease_id"],
                    "rank": candidate["rank"], "gene_symbol": candidate["gene_symbol"],
                    "target_id": candidate["target_id"],
                    "uniprot_accession": candidate["uniprot_accessions"][0],
                    "chembl_target_id": chembl_id,
                    "opentargets_score": candidate["association_score"],
                    "reported_total_count": candidate.get("activity_availability", {}).get("total_count"),
                    "retrieved_count": existing.get("record_count"),
                    "truncated_at_limit": existing.get("metadata", {}).get("truncated_at_limit"),
                    "path": str(filename), "sha256": existing.get("dataset_hash_sha256"),
                    "reused_existing_dataset": True,
                })
                print(disease_key, candidate["rank"], candidate["gene_symbol"],
                      "reused", existing.get("record_count"), flush=True)
                continue
            try:
                records = client.target_ligands(chembl_id, limit=limit,
                                                page_size=activity_page_size)
            except Exception as exc:
                summaries.append({
                    "disease_key": disease_key, "disease_id": candidate["disease_id"],
                    "rank": candidate["rank"], "gene_symbol": candidate["gene_symbol"],
                    "target_id": candidate["target_id"],
                    "chembl_target_id": chembl_id, "status": "retrieval_failed",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "reported_total_count": candidate.get("activity_availability", {}).get("total_count"),
                })
                print(disease_key, candidate["rank"], candidate["gene_symbol"],
                      "retrieval_failed", type(exc).__name__, flush=True)
                continue
            digest = write_jsonl(filename, (asdict(record) for record in records))
            total = candidate.get("activity_availability", {}).get("total_count")
            write_dataset_manifest(
                str(filename) + ".manifest.json",
                source="ChEMBL REST API",
                source_version="ChEMBL API (live service; response metadata retained per page)",
                dataset_hash=digest,
                processing_version="0.3.0",
                filters={"target_chembl_id": chembl_id,
                         "activity_limit": limit,
                         "activity_page_size": activity_page_size,
                         "standard_activity_types": "all; no endpoint pooling or thresholding at retrieval",
                         "pagination": "offset, page size <= 1000"},
                record_count=len(records),
                metadata={"disease_key": disease_key,
                          "disease_id": candidate["disease_id"],
                          "target_id": candidate["target_id"],
                          "gene_symbol": candidate["gene_symbol"],
                          "uniprot_accession": candidate["uniprot_accessions"][0],
                          "target_evidence_rank": candidate["rank"],
                          "opentargets_score": candidate["association_score"],
                          "opentargets_provenance": candidate.get("opentargets_provenance"),
                          "reported_total_activity_count": total,
                          "truncated_at_limit": total is not None and total > len(records),
                          "activity_and_molecule_response_refs": client.last_response_refs})
            summaries.append({
                "disease_key": disease_key,
                "disease_id": candidate["disease_id"],
                "rank": candidate["rank"],
                "gene_symbol": candidate["gene_symbol"],
                "target_id": candidate["target_id"],
                "uniprot_accession": candidate["uniprot_accessions"][0],
                "chembl_target_id": chembl_id,
                "opentargets_score": candidate["association_score"],
                "reported_total_count": total,
                "retrieved_count": len(records),
                "truncated_at_limit": total is not None and total > len(records),
                "path": str(filename),
                "sha256": digest,
                "status": "retrieved",
            })
            print(disease_key, candidate["rank"], candidate["gene_symbol"], chembl_id,
                  "count", total, "retrieved", len(records), "sha256", digest, flush=True)
    write_json_atomic(activity_dir / "retrieval-summary.json", {
        "source": "ChEMBL REST activity and molecule endpoints",
        "retrieval_limit_per_target": limit,
        "disease_candidate_limit": candidates_per_disease,
        "targets": summaries,
    })
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument("--activities-per-disease", type=int, default=5)
    parser.add_argument("--activity-limit", type=int, default=1000)
    parser.add_argument("--activity-page-size", type=int, default=100)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    inspect_targets(args.output, args.top_k)
    if not args.inspect_only:
        retrieve_activity_rows(args.output, args.activities_per_disease, args.activity_limit,
                               args.activity_page_size)


if __name__ == "__main__":
    main()
