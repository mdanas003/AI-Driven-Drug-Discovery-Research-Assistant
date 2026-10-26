from __future__ import annotations

import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from satori.errors import ComponentBlocked
from satori.evaluation import generation_metrics
from satori.generation.models import GPMolFormerGenerator, GenerationRequest


class FakeTokenizer:
    def __call__(self, prompt: str, return_tensors: str):
        return {"input_ids": FakeTensor()}

    def batch_decode(self, output, skip_special_tokens: bool):
        return output


class FakeTensor:
    def to(self, device):
        return self


class FakeModel:
    def parameters(self):
        return iter([SimpleNamespace(device="cpu")])

    def generate(self, **kwargs):
        return ["c1ccccc1", "not-a-smiles"][:kwargs["num_return_sequences"]]


class GenerationContractTests(unittest.TestCase):
    def test_generation_metrics_mark_unavailable_endpoints_instead_of_inventing_scores(self):
        metrics = generation_metrics(["CCO", "not-a-smiles"])
        self.assertEqual(metrics["validity"], 0.5)
        self.assertIsNone(metrics["novelty"])
        self.assertEqual(metrics["novelty_status"], "BLOCKED_NO_TRAINING_REFERENCE")
        self.assertIsNone(metrics["synthetic_accessibility"])
        self.assertIsNone(metrics["three_d_validity"])

    def test_preserves_raw_invalid_and_scaffold_validation(self):
        generator = GPMolFormerGenerator()
        generator._model = FakeModel()
        generator._tokenizer = FakeTokenizer()
        with patch("torch.inference_mode", return_value=nullcontext()), patch(
            "satori.reproducibility.seed_everything", return_value={"seed": 4}
        ):
            result = generator.generate(GenerationRequest(
                target_id="EGFR", count=2, seed=4, scaffold_smiles="c1ccccc1"
            ))
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].valid_smiles)
        self.assertTrue(result[0].scaffold_preserved)
        self.assertFalse(result[1].valid_smiles)
        self.assertEqual(result[1].validation_reason, "INVALID_SMILES")
        self.assertFalse(result[0].target_conditioned)
        self.assertEqual(result[0].provenance["model_revision"], generator.model_revision)

    def test_target_or_fragment_conditioning_is_blocked_before_checkpoint_load(self):
        generator = GPMolFormerGenerator()
        with patch.object(generator, "_load") as load:
            with self.assertRaises(ComponentBlocked):
                generator.generate(GenerationRequest(
                    target_id="EGFR", count=1, seed=1, pocket_path="pocket.pdb"
                ))
            with self.assertRaises(ComponentBlocked):
                generator.generate(GenerationRequest(
                    target_id="EGFR", count=1, seed=1, fragment_smiles=("CCO",)
                ))
            load.assert_not_called()

    def test_invalid_scaffold_is_rejected_before_checkpoint_load(self):
        generator = GPMolFormerGenerator()
        with patch.object(generator, "_load") as load:
            with self.assertRaises(ValueError):
                generator.generate(GenerationRequest(
                    target_id="EGFR", count=1, seed=1, scaffold_smiles="not-a-smiles"
                ))
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
