from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satori.schemas import TargetRecord
from satori.data.sources import ChEMBLClient
from satori.chemistry import standardize_activity_records
from satori.targets.context import resolve_target_context
from satori.cli import main
from satori.schemas import LigandRecord


class FakeUniProt:
    def __init__(self, matches, sequence="MKWVTFISLL"):
        self.matches = matches
        self.sequence = sequence

    def search_ensembl(self, _gene_id):
        return self.matches

    def enrich(self, record, accession):
        record.uniprot_id = accession
        record.sequence = self.sequence
        record.metadata["uniprot"] = {"entry_name": "FIXTURE_HUMAN"}
        return record


class FakeChEMBL:
    def __init__(self, target_id="CHEMBL_TARGET1"):
        self.target_id = target_id

    def target_id_for_uniprot(self, _accession):
        return self.target_id


class FakeRCSB:
    def __init__(self, ids=None):
        self.ids = ids or []

    def search_uniprot(self, _accession):
        return self.ids


class Phase3ContextTests(unittest.TestCase):
    def test_chembl_mapping_prefers_only_exact_human_single_protein_target(self):
        rows = {"targets": [
            {"target_chembl_id": "CHEMBL_COMPLEX", "target_type": "PROTEIN-PROTEIN INTERACTION",
             "organism": "Homo sapiens", "target_components": [{"accession": "P12345"}]},
            {"target_chembl_id": "CHEMBL_MOUSE", "target_type": "SINGLE PROTEIN",
             "organism": "Mus musculus", "target_components": [{"accession": "P12345"}]},
            {"target_chembl_id": "CHEMBL_HUMAN", "target_type": "SINGLE PROTEIN",
             "organism": "Homo sapiens", "target_components": [{"accession": "P12345"}]},
        ]}
        with patch("satori.data.sources.request_json", return_value=rows), \
             patch("satori.data.sources.request_cache_metadata", return_value={
                 "retrieved_at": "2024-01-01T00:00:00+00:00", "response_sha256": "fixture"}):
            client = ChEMBLClient()
            result = client.target_id_for_uniprot("P12345")
        self.assertEqual(result, "CHEMBL_HUMAN")
        self.assertEqual(client.last_target_mapping["organism"], "Homo sapiens")

    def test_context_resolves_sequence_and_persists_structure_gap(self):
        target = TargetRecord("ENSG000001", gene_symbol="GENE", disease_id="MONDO_X")
        result = resolve_target_context(
            target,
            uniprot_client=FakeUniProt([{"primaryAccession": "P12345"}]),
            chembl_client=FakeChEMBL(),
            rcsb_client=FakeRCSB(),
        )
        self.assertEqual(result.uniprot_id, "P12345")
        self.assertEqual(result.sequence, "MKWVTFISLL")
        self.assertEqual(len(result.sequence_sha256), 64)
        self.assertEqual(result.ligand_data_status, "target_linked")
        self.assertEqual(result.structure_status, "no_structures_found")
        self.assertFalse(result.affinity_ready)
        self.assertTrue(any("No RCSB structures" in reason for reason in result.blockers))

    def test_ambiguous_uniprot_mapping_blocks_without_guessing(self):
        context = resolve_target_context(
            TargetRecord("ENSG000002", disease_id="MONDO_Y"),
            uniprot_client=FakeUniProt([{"primaryAccession": "P11111"},
                                        {"primaryAccession": "P22222"}]),
            chembl_client=FakeChEMBL(), rcsb_client=FakeRCSB(),
        )
        self.assertEqual(context.sequence_status, "blocked_ambiguous")
        self.assertIsNone(context.uniprot_id)
        self.assertEqual(context.ligand_data_status, "unresolved")
        self.assertFalse(context.docking_ready)

    def test_invalid_protein_sequence_is_not_marked_ready(self):
        context = resolve_target_context(
            TargetRecord("ENSG000003", disease_id="MONDO_Z"),
            uniprot_client=FakeUniProt([{"primaryAccession": "P33333"}], sequence="MKW-?"),
            chembl_client=FakeChEMBL(), rcsb_client=FakeRCSB(["1ABC"]),
        )
        self.assertEqual(context.sequence_status, "invalid_sequence")
        self.assertIsNone(context.sequence)
        self.assertEqual(context.structure_ids, ["1ABC"])
        self.assertTrue(any("unexpected sequence symbols" in reason for reason in context.blockers))

    def test_ligand_ingestion_preserves_linked_and_blocked_target_states(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contexts = root / "contexts.jsonl"
            contexts.write_text("\n".join([
                json.dumps({"disease_id": "d1", "target_id": "t1", "chembl_target_id": "CHEMBL1"}),
                json.dumps({"disease_id": "d2", "target_id": "t2", "chembl_target_id": None}),
            ]) + "\n", encoding="utf-8")
            output_dir = root / "ligands"
            argv = ["satori", "fetch-ligands", "--contexts", str(contexts),
                    "--output-dir", str(output_dir), "--limit", "5"]
            with patch.object(sys, "argv", argv), \
                 patch("satori.cli.ChEMBLClient") as client_class:
                client_class.return_value.target_ligands.return_value = [LigandRecord("m1", "CCO")]
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    main()
            result = json.loads(stdout.getvalue())["targets"]
            self.assertEqual([row["status"] for row in result], ["succeeded", "blocked"])
            self.assertEqual(client_class.return_value.target_ligands.call_count, 1)
            self.assertEqual(len(list(output_dir.glob("*.ligands.jsonl"))), 1)

    def test_multi_target_standardization_deduplicates_within_target_not_across_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir, output_dir = root / "raw", root / "standardized"
            input_dir.mkdir()
            for target in ("target-a", "target-b"):
                (input_dir / f"{target}.ligands.jsonl").write_text(
                    json.dumps({"molecule_id": "CHEMBL1", "smiles": "CCO",
                                "target_id": target}) + "\n", encoding="utf-8")
            argv = ["satori", "standardize", "--input-dir", str(input_dir),
                    "--output-dir", str(output_dir)]
            with patch.object(sys, "argv", argv):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    main()
            result = json.loads(stdout.getvalue())["datasets"]
            self.assertEqual(len(result), 2)
            self.assertTrue(all(row["accepted"] == 1 and row["rejected"] == 0 for row in result))
            self.assertEqual(len(list(output_dir.glob("*.standardized.jsonl"))), 2)

    def test_standardization_retains_repeated_assay_records_and_marks_structure_duplicates(self):
        rows = standardize_activity_records([
            LigandRecord("CHEMBL1", "CCO", target_id="t1", assay_id="assay1",
                         activity_type="Ki", activity_value=10, activity_units="nM"),
            LigandRecord("CHEMBL1", "OCC", target_id="t1", assay_id="assay2",
                         activity_type="IC50", activity_value=20, activity_units="nM"),
        ])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.accepted for row in rows))
        self.assertEqual([row.duplicate_structure for row in rows], [False, True])
        self.assertEqual([row.source_record.assay_id for row in rows], ["assay1", "assay2"])


if __name__ == "__main__":
    unittest.main()
