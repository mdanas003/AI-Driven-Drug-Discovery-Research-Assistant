from __future__ import annotations

import json
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from satori.activity import ActivityPolicy, apply_activity_policy
from satori.chemistry import standardize_many
from satori.data.http import request_json
from satori.data.sources import ChEMBLClient, OpenTargetsClient, RCSBClient
from satori.errors import ExternalSourceError
from satori.provenance import write_dataset_manifest, write_jsonl
from satori.schemas import EvidenceRecord, LigandRecord, to_jsonable
from satori.splits import molecule_split, write_split_manifest
from satori.cli import _diseases_from_config, main


class FakeResponse:
    status = 200

    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_: object):
        return None

    def read(self) -> bytes:
        return self.body


class Phase1DataTests(unittest.TestCase):
    def test_raw_json_response_is_cached_and_replayed_offline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def opener(request, timeout):
                calls.append((request.full_url, timeout))
                return FakeResponse(b'{"data":{"ok":true}}')

            first = request_json("https://example.test/api", cache_dir=directory,
                                 opener=opener, sleeper=lambda _: None)
            replay = request_json("https://example.test/api", cache_dir=directory, offline=True)
            self.assertEqual(first, replay)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 2)

    def test_corrupt_cached_response_fails_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request_json("https://example.test/api", cache_dir=directory,
                         opener=lambda *_args, **_kwargs: FakeResponse(b'{"ok":1}'))
            response_file = next(path for path in Path(directory).glob("*.json")
                                 if not path.name.endswith(".meta.json"))
            response_file.write_text('{"tampered":true}', encoding="utf-8")
            with self.assertRaisesRegex(ExternalSourceError, "checksum mismatch"):
                request_json("https://example.test/api", cache_dir=directory, offline=True)

    def test_offline_cache_miss_is_not_a_live_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ExternalSourceError, "No cached response"):
                request_json("https://example.test/missing", cache_dir=directory, offline=True)

    def test_transient_http_failure_retries_and_bad_request_fails_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            attempts = []

            def flaky(_request, timeout):
                attempts.append(timeout)
                if len(attempts) == 1:
                    raise HTTPError("https://example.test", 503, "busy", {}, None)
                return FakeResponse(b'{"ok":true}')

            result = request_json("https://example.test/retry", cache_dir=directory,
                                 opener=flaky, sleeper=lambda _: None)
            self.assertEqual(result, {"ok": True})
            self.assertEqual(len(attempts), 2)

            bad_attempts = []

            def bad_request(_request, timeout):
                bad_attempts.append(timeout)
                raise HTTPError("https://example.test", 400, "bad request", {}, None)

            with self.assertRaises(ExternalSourceError):
                request_json("https://example.test/bad", cache_dir=directory,
                             opener=bad_request, sleeper=lambda _: None)
            self.assertEqual(len(bad_attempts), 1)

    def test_rcsb_coordinate_download_has_atomic_hash_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "1abc.cif"
            with patch("satori.data.sources.urlopen", return_value=FakeResponse(b"data_fixture\n")):
                result = RCSBClient().download_cif("1abc", str(destination))
            self.assertEqual(Path(result).read_bytes(), b"data_fixture\n")
            manifest = json.loads(Path(str(destination) + ".manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["pdb_id"], "1ABC")
            self.assertEqual(manifest["byte_count"], len(b"data_fixture\n"))
            self.assertEqual(len(manifest["coordinate_sha256"]), 64)

    def test_opentargets_maps_evidence_and_rejects_malformed_target(self) -> None:
        response = {"data": {"disease": {"id": "MONDO_0004975", "name": "Alzheimer disease",
            "associatedTargets": {"rows": [{"target": {"id": "ENSG1", "approvedSymbol": "GENE"},
                "score": 0.8, "datatypeScores": [{"id": "genetic", "score": 0.7}]}]}}}}
        with patch("satori.data.sources.request_json", return_value=response), \
             patch("satori.data.sources.request_cache_metadata", return_value={"retrieved_at": "2024-01-01T00:00:00+00:00", "response_sha256": "fixture"}):
            target = OpenTargetsClient().disease_targets("MONDO_0004975")[0]
        self.assertEqual(target.target_id, "ENSG1")
        self.assertEqual(target.metadata["disease_name"], "Alzheimer disease")
        self.assertEqual(target.evidence[0].score, 0.8)
        malformed = {"data": {"disease": {"associatedTargets": {"rows": [{"target": {}}]}}}}
        with patch("satori.data.sources.request_json", return_value=malformed), \
             patch("satori.data.sources.request_cache_metadata", return_value={"retrieved_at": "2024-01-01T00:00:00+00:00", "response_sha256": "fixture"}):
            with self.assertRaisesRegex(ExternalSourceError, "without a target identifier"):
                OpenTargetsClient().disease_targets("MONDO_0004975")

    def test_chembl_preserves_missing_smiles_and_raw_activity(self) -> None:
        pages = [
            {"activities": [{"molecule_chembl_id": "CHEMBL1", "standard_value": "10",
              "pchembl_value": "8.0", "assay_chembl_id": "CHEMBL_ASSAY1",
              "standard_type": "Ki", "standard_units": "nM", "activity_id": 7,
              "document_chembl_id": "CHEMBL_DOC1", "standard_relation": "="}],
             "page_meta": {"total_count": 1}},
            {"molecules": []},
        ]
        with patch("satori.data.sources.request_json", side_effect=pages), \
             patch("satori.data.sources.request_cache_metadata", return_value={"retrieved_at": "2024-01-01T00:00:00+00:00", "response_sha256": "fixture"}):
            rows = ChEMBLClient().target_ligands("CHEMBL_TARGET1", limit=1)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0].smiles)
        self.assertEqual(rows[0].activity_value, 10.0)
        self.assertEqual(rows[0].provenance["source_record"]["activity_id"], 7)
        decision = standardize_many(rows)[0]
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "MISSING_SMILES")

    def test_standardization_records_invalid_and_duplicate_reasons(self) -> None:
        decisions = standardize_many([
            LigandRecord("a", "CCO"), LigandRecord("b", "OCC"),
            LigandRecord("c", "not-smiles"), LigandRecord("d", None),
        ])
        self.assertEqual([row.accepted for row in decisions], [True, False, False, False])
        self.assertEqual([row.reason for row in decisions], [None, "DUPLICATE", "INVALID_SMILES", "MISSING_SMILES"])
        self.assertEqual(decisions[0].canonical_smiles, "CCO")

    def test_jsonl_hash_and_manifest_are_stable_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            first = write_jsonl(path, [{"b": 2, "a": 1}, {"id": "x"}])
            second = write_jsonl(path, [{"a": 1, "b": 2}, {"id": "x"}])
            self.assertEqual(first, second)
            write_dataset_manifest(str(path) + ".manifest.json", source="fixture",
                                   dataset_hash=first, processing_version="test",
                                   filters={"cutoff": 0.2}, record_count=2, split_seed=17)
            manifest = json.loads(Path(str(path) + ".manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_hash_sha256"], first)
            self.assertEqual(manifest["record_count"], 2)
            self.assertEqual(manifest["split_seed"], 17)
            self.assertEqual(to_jsonable(EvidenceRecord("d", "t", 0.3, "fixture"))["target_id"], "t")

    def test_activity_filter_is_explicit_and_returns_every_decision(self) -> None:
        rows = [
            LigandRecord("a", "CCO", assay_id="assay1", activity_type="Ki",
                         activity_value=5, activity_units="nM", pchembl_value=8.0,
                         provenance={"relation": "="}),
            LigandRecord("b", "CCN", assay_id="assay2", activity_type="IC50",
                         activity_value=50, activity_units="nM", pchembl_value=7.0,
                         provenance={"relation": "="}),
            LigandRecord("c", "CCC", assay_id="assay3", activity_type="Ki",
                         activity_value=5, activity_units="uM", pchembl_value=None,
                         provenance={"relation": ">"}),
        ]
        kept, decisions = apply_activity_policy(rows, ActivityPolicy(
            "test-policy-v1", allowed_types=("Ki",), allowed_units=("nM",),
            allowed_relations=("=",), min_pchembl=7.5))
        self.assertEqual([row.molecule_id for row in kept], ["a"])
        self.assertEqual(len(decisions), len(rows))
        self.assertEqual([item.reason for item in decisions],
                         [None, "ACTIVITY_TYPE_NOT_ALLOWED", "ACTIVITY_UNITS_NOT_ALLOWED"])

    def test_split_manifest_records_exact_assignments_and_hash(self) -> None:
        rows = [{"record_id": str(i), "molecule_id": str(i), "smiles": "CC"} for i in range(10)]
        split = molecule_split(rows, strategy="random", seed=17)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "split.json"
            assignment_hash = write_split_manifest(path, split, dataset_hash="dataset-hash",
                                                   source_version="fixture-v1")
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["assignment_hash_sha256"], assignment_hash)
            self.assertEqual(manifest["record_counts"], {"train": 8, "validation": 1, "test": 1})
            self.assertEqual(set(manifest["assignments"]["train"] +
                                 manifest["assignments"]["validation"] +
                                 manifest["assignments"]["test"]), {str(i) for i in range(10)})

    def test_three_disease_configuration_and_scaffold_split_are_valid(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        diseases = _diseases_from_config(repo / "config.example.json")
        self.assertEqual([disease["key"] for disease in diseases],
                         ["nsclc", "alzheimers_disease", "type_2_diabetes"])
        rows = [{"record_id": f"r{i}", "molecule_id": f"m{i}", "smiles": smiles}
                for i, smiles in enumerate(("c1ccccc1", "Cc1ccccc1", "CCO", "CCN", "C1CCCCC1"))]
        split = molecule_split(rows, strategy="scaffold", seed=17,
                               fractions=(0.6, 0.2, 0.2))
        split.validate_disjoint()
        groups = {row["record_id"]: row["smiles"] for row in rows}
        from rdkit import Chem
        from rdkit.Chem.Scaffolds import MurckoScaffold
        partitions = [set(split.train), set(split.validation), set(split.test)]
        by_scaffold = {}
        for row in rows:
            scaffold = MurckoScaffold.MurckoScaffoldSmiles(
                mol=Chem.MolFromSmiles(row["smiles"]), includeChirality=True) or "acyclic:all"
            by_scaffold.setdefault(scaffold, set()).add(row["record_id"])
        for scaffold_rows in by_scaffold.values():
            self.assertLessEqual(sum(bool(scaffold_rows & part) for part in partitions), 1)

    def test_config_ingestion_writes_separate_dataset_and_manifest_per_disease(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "targets"
            with patch.object(sys, "argv", ["satori", "ingest-targets", "--config",
                                              str(repo / "config.example.json"), "--output-dir",
                                              str(output_dir), "--limit", "2"]), \
                 patch("satori.cli.OpenTargetsClient") as client_class:
                client_class.return_value.disease_targets.return_value = []
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    main()
            summary = json.loads(output.getvalue())
            self.assertEqual(len(summary["datasets"]), 3)
            for disease in ("nsclc", "alzheimers_disease", "type_2_diabetes"):
                dataset = output_dir / f"{disease}.targets.jsonl"
                manifest = Path(str(dataset) + ".manifest.json")
                self.assertTrue(dataset.exists())
                self.assertTrue(manifest.exists())
            self.assertEqual(client_class.return_value.disease_targets.call_count, 3)


if __name__ == "__main__":
    unittest.main()
