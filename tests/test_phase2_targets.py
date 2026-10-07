from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from satori.errors import ComponentBlocked
from satori.evaluation import evaluate_target_rankings, ranking_metrics
from satori.schemas import EvidenceRecord

try:
    import torch
except ImportError:  # pragma: no cover - preserves core-only test environments
    torch = None


@unittest.skipIf(torch is None, "PyTorch ML dependency is not installed")
class Phase2TargetTests(unittest.TestCase):
    def setUp(self) -> None:
        from satori.targets.graph import encode_evidence_graph

        self.records = [
            EvidenceRecord("d1", "t1", 0.9, "source-a", retrieved_at="2024-01-01T00:00:00+00:00",
                           event_time="2023-01-01T00:00:00+00:00", source_record_id="e1"),
            EvidenceRecord("d1", "t1", 0.7, "source-b", retrieved_at="2024-01-01T00:00:00+00:00",
                           event_time="2023-06-01T00:00:00+00:00", source_record_id="e2"),
            EvidenceRecord("d1", "t2", 0.4, "source-a", retrieved_at="2024-01-01T00:00:00+00:00",
                           event_time="2023-12-01T00:00:00+00:00", source_record_id="e3"),
        ]
        self.encode = encode_evidence_graph

    def test_graph_encoding_is_deterministic_and_keeps_edge_provenance_time(self) -> None:
        graph_a, ids_a = self.encode(self.records, reference_time=datetime(2024, 1, 1, tzinfo=timezone.utc))
        graph_b, ids_b = self.encode(list(reversed(self.records)),
                                     reference_time=datetime(2024, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(ids_a, ["t1", "t2"])
        self.assertEqual(ids_a, ids_b)
        self.assertTrue(torch.equal(graph_a.node_features, graph_b.node_features))
        self.assertTrue(torch.equal(graph_a.edge_index, graph_b.edge_index))
        self.assertTrue(torch.equal(graph_a.edge_time_features, graph_b.edge_time_features))
        self.assertEqual(len(graph_a.edge_provenance), graph_a.edge_index.shape[1])
        self.assertEqual(graph_a.edge_time_features.shape[1], 4)
        self.assertGreater(graph_a.edge_time_features[:, 1].max().item(), 0.0)

    def test_chronological_snapshots_exclude_future_evidence(self) -> None:
        from satori.targets.graph import encode_temporal_snapshots

        snapshots = encode_temporal_snapshots(
            self.records,
            [datetime(2023, 7, 1, tzinfo=timezone.utc), datetime(2024, 1, 1, tzinfo=timezone.utc)],
        )
        self.assertEqual(snapshots[0].target_ids, ["t1"])
        self.assertEqual(snapshots[1].target_ids, ["t1", "t2"])
        self.assertLess(snapshots[0].as_of, snapshots[1].as_of)

    def test_relational_attention_forward_loss_backward_and_checkpoint_roundtrip(self) -> None:
        from satori.targets.graph import (RelationalGraphAttention, pairwise_target_loss,
                                          load_target_ranker, save_target_ranker)

        graph, _ = self.encode(self.records)
        torch.manual_seed(7)
        model = RelationalGraphAttention(hidden_width=16, depth=2, heads=4, dropout=0.0)
        scores = model(graph)
        self.assertEqual(tuple(scores.shape), (2,))
        self.assertTrue(torch.isfinite(scores).all().item())
        loss = pairwise_target_loss(scores, torch.tensor([0]), torch.tensor([1]))
        loss.backward()
        self.assertTrue(any(parameter.grad is not None for parameter in model.parameters()))

        metadata = {"input_width": 6, "hidden_width": 16, "relation_count": 6,
                    "depth": 2, "heads": 4, "dropout": 0.0,
                    "dataset_version": "fixture-v1", "dataset_hash_sha256": "abc",
                    "split_strategy": "target_disjoint", "seed": 7,
                    "benchmark_id": "fixture-only", "negative_sampling_policy": "fixture"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ranker.pt"
            save_target_ranker(model, path, metadata)
            loaded = load_target_ranker(path)
            self.assertTrue(torch.equal(scores.detach(), loaded(graph).detach()))

    def test_temporal_ranker_consumes_graph_history(self) -> None:
        from satori.targets.graph import DynamicTemporalGraphRanker, encode_temporal_snapshots

        snapshots = encode_temporal_snapshots(
            self.records,
            [datetime(2023, 7, 1, tzinfo=timezone.utc), datetime(2024, 1, 1, tzinfo=timezone.utc)],
        )
        model = DynamicTemporalGraphRanker(hidden_width=16, depth=1, heads=4, dropout=0.0)
        scores, target_ids = model(snapshots)
        self.assertEqual(target_ids, ["t1", "t2"])
        self.assertEqual(tuple(scores.shape), (2,))
        self.assertTrue(torch.isfinite(scores).all().item())
        scores.sum().backward()
        self.assertTrue(any(parameter.grad is not None for parameter in model.parameters()))

    def test_gfm_does_not_silently_substitute_local_gnn(self) -> None:
        from satori.targets.graph import load_graph_foundation_ranker

        with self.assertRaisesRegex(ComponentBlocked, "not a pretrained foundation model"):
            load_graph_foundation_ranker("", "")
        with self.assertRaisesRegex(ComponentBlocked, "No simpler model was substituted"):
            load_graph_foundation_ranker("unconfigured-gfm", "missing-checkpoint")

    def test_seed_utility_repeats_python_numpy_and_torch_streams(self) -> None:
        import random
        import numpy as np
        from satori.reproducibility import seed_everything

        seed_everything(23)
        first = (random.random(), float(np.random.random()), torch.rand(1).item())
        seed_everything(23)
        second = (random.random(), float(np.random.random()), torch.rand(1).item())
        self.assertEqual(first, second)

    @unittest.skipUnless(torch is not None and torch.cuda.is_available(), "CUDA GPU unavailable")
    def test_rtx_cuda_forward_backward_is_finite_and_memory_bounded(self) -> None:
        from satori.reproducibility import seed_everything
        from satori.targets.graph import RelationalGraphAttention

        seed_everything(17)
        graph, _ = self.encode(self.records, device="cuda")
        model = RelationalGraphAttention(hidden_width=32, depth=2, heads=4, dropout=0.0).cuda()
        scores = model(graph)
        scores.sum().backward()
        self.assertEqual(scores.device.type, "cuda")
        self.assertTrue(torch.isfinite(scores).all().item())
        self.assertLess(torch.cuda.max_memory_allocated(), 1024**3)

    def test_evidence_and_random_rankings_are_explicit_baselines(self) -> None:
        from satori.targets.graph import evidence_score_ranking, random_target_ranking

        ranked = evidence_score_ranking(self.records, disease_id="d1")
        self.assertEqual(ranked, [("t1", 0.9), ("t2", 0.4)])
        random_a = random_target_ranking(["a", "b", "c", "d"], seed=17)
        random_b = random_target_ranking(["a", "b", "c", "d"], seed=17)
        self.assertEqual(random_a, random_b)
        self.assertEqual(ranking_metrics(["t1", "t2"], {"t2"}, k=2)["mrr"], 0.5)
        report = evaluate_target_rankings(
            {"evidence-score-baseline": ["t1", "t2"], "random-baseline": ["t2", "t1"]},
            {"t2"}, benchmark_id="fixture", dataset_hash_sha256="data-hash",
            split_manifest_hash_sha256="split-hash", ks=(1, 2))
        self.assertEqual(report["rankers"]["random-baseline"]["mrr"], 1.0)
        self.assertEqual(report["benchmark_id"], "fixture")


if __name__ == "__main__":
    unittest.main()
