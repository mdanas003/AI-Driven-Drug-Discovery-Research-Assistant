from __future__ import annotations

import unittest

from satori.optimization.pareto import pareto_front
from satori.schemas import LigandRecord
from satori.triage import triage_with_audit


class Phase5OptimizationTests(unittest.TestCase):
    def test_pareto_front_keeps_tradeoffs_and_reports_dominators(self):
        rows = [
            {"activity": 0.9, "toxicity": 0.4},
            {"activity": 0.7, "toxicity": 0.2},
            {"activity": 0.5, "toxicity": 0.1},
            {"activity": 0.4, "toxicity": 0.9},
        ]
        result = pareto_front(rows, maximize=("activity",), minimize=("toxicity",))
        self.assertEqual([row.nondominated for row in result], [True, True, True, False])
        self.assertEqual(result[3].dominators, (0, 1, 2))
        self.assertEqual(result[0].objective_values, rows[0])

    def test_pareto_identical_points_both_survive(self):
        result = pareto_front([{"qed": 0.5}, {"qed": 0.5}], maximize=("qed",))
        self.assertTrue(all(row.nondominated for row in result))

    def test_pareto_rejects_missing_or_nonfinite_values(self):
        for rows in ([{"a": 1}, {}], [{"a": float("nan")}], [{"a": float("inf")} ]):
            with self.assertRaises(ValueError):
                pareto_front(rows, maximize=("a",))

    def test_triage_records_acceptance_and_filter_configuration(self):
        rows = [
            LigandRecord("ethanol", "CCO", target_id="T1", source="fixture"),
            LigandRecord("invalid", "not-smiles", target_id="T1", source="fixture"),
            LigandRecord("heavy", "C" * 100, target_id="T1", source="fixture"),
        ]
        result = triage_with_audit(rows, qed_min=0, max_molecular_weight=500,
                                   apply_pains=False)
        self.assertEqual(len(result), 3)
        self.assertTrue(result[0].accepted)
        self.assertEqual(result[0].candidate.provenance["filters"]["max_molecular_weight"], 500)
        self.assertEqual(result[1].reason, "INVALID_SMILES")
        self.assertEqual(result[2].reason, "MOLECULAR_WEIGHT_ABOVE_THRESHOLD")


if __name__ == "__main__":
    unittest.main()
