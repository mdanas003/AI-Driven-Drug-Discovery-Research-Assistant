from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch

from satori.affinity.model import ProteinLigandBatch, ProteinLigandCrossAttention
from satori.docking import VinaDockingEngine
from satori.errors import ComponentBlocked


class Phase6ContractsTests(unittest.TestCase):
    def test_cross_attention_contract_and_uncertainty_loss(self):
        torch.manual_seed(9)
        model = ProteinLigandCrossAttention(protein_width=12, ligand_width=10,
                                            hidden=32, heads=4, rbf_bins=8, dropout=0)
        batch = ProteinLigandBatch(
            protein_features=torch.randn(2, 5, 12), protein_coords=torch.randn(2, 5, 3),
            protein_mask=torch.tensor([[1, 1, 1, 1, 1], [1, 1, 1, 0, 0]], dtype=torch.bool),
            ligand_features=torch.randn(2, 4, 10), ligand_coords=torch.randn(2, 4, 3),
            ligand_mask=torch.tensor([[1, 1, 1, 1], [1, 1, 0, 0]], dtype=torch.bool),
        )
        mean, logvar = model(batch)
        self.assertEqual(mean.shape, (2,))
        self.assertEqual(logvar.shape, (2,))
        loss = model.gaussian_nll(mean, logvar, torch.tensor([7.1, 6.4]))
        loss.backward()
        self.assertTrue(torch.isfinite(loss))

    def test_untrained_affinity_checkpoint_is_not_loaded_as_prediction(self):
        from satori.affinity.model import load_affinity_model
        with self.assertRaises(ValueError):
            load_affinity_model("")

    def test_vina_missing_executable_is_explicitly_blocked(self):
        with patch("satori.docking.shutil.which", return_value=None):
            with self.assertRaises(ComponentBlocked):
                VinaDockingEngine()

    def test_vina_result_captures_score_pose_and_version(self):
        fake_run = [
            SimpleNamespace(returncode=0, stdout="mode | affinity\n1 -8.2 0 0\n", stderr=""),
            SimpleNamespace(returncode=0, stdout="AutoDock Vina 1.2.7", stderr=""),
        ]
        with tempfile.TemporaryDirectory() as directory, \
             patch("satori.docking.shutil.which", return_value="vina.exe"), \
             patch("satori.docking.subprocess.run", side_effect=fake_run) as run:
            output = Path(directory) / "poses" / "ligand.pdbqt"
            result = VinaDockingEngine().dock("receptor.pdbqt", "ligand.pdbqt", output,
                                              (1, 2, 3), (20, 20, 20))
            self.assertEqual(result.score_kcal_mol, -8.2)
            self.assertEqual(result.tool_version, "AutoDock Vina 1.2.7")
            self.assertEqual(result.pose_path, str(output))
            self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
