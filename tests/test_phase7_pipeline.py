from __future__ import annotations

import json
import hashlib
import tempfile
import unittest

from satori.errors import ComponentBlocked
from satori.pipeline import Pipeline


class Phase7PipelineTests(unittest.TestCase):
    def test_run_is_restart_inspectable_and_records_complete_stage_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Pipeline(directory)
            run = pipeline.create_run("MONDO_0005233", {"disease": "NSCLC"}, seed=42)
            calls = []
            stages = {name: (lambda context, stage=name: calls.append(stage) or stage)
                      for name in pipeline.stage_order}
            completed = pipeline.execute(run, stages)
            self.assertEqual(completed.status, "completed")
            self.assertEqual(calls, list(pipeline.stage_order))
            stored = json.loads((pipeline.artifact_dir / "runs" / run.run_id / "run.json").read_text())
            self.assertEqual(stored["run"]["config_hash"], run.config_hash)
            self.assertEqual([s["status"] for s in stored["run"]["stages"]],
                             ["succeeded"] * len(pipeline.stage_order))
            self.assertTrue(stored["runtime"]["python"])
            first_stage = stored["run"]["stages"][0]
            artifact_path = pipeline.artifact_dir / first_stage["output_artifact"]
            self.assertTrue(artifact_path.exists())
            self.assertEqual(hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                             first_stage["output_sha256"])

    def test_blocked_stage_preserves_completed_artifacts_and_stage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Pipeline(directory)
            run = pipeline.create_run("MONDO_0004975", {}, seed=7)
            stages = {name: (lambda context: name) for name in pipeline.stage_order}
            stages["optimization"] = lambda context: (_ for _ in ()).throw(
                ComponentBlocked("GraphFDM checkpoint absent")
            )
            result = pipeline.execute(run, stages)
            self.assertEqual(result.status, "blocked")
            self.assertEqual([s["name"] for s in result.stages], list(pipeline.stage_order[:4]))
            self.assertEqual(result.stages[-1]["status"], "blocked")
            self.assertIn("GraphFDM checkpoint absent", result.blockers[0])

    def test_missing_stage_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Pipeline(directory)
            run = pipeline.create_run("MONDO_0005148", {}, seed=3)
            result = pipeline.execute(run, {})
            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.stages[0]["status"], "blocked")

    def test_nonserializable_stage_result_is_a_failure_not_a_silent_drop(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline = Pipeline(directory)
            run = pipeline.create_run("MONDO_0005233", {}, seed=11)
            result = pipeline.execute(run, {"target_discovery": lambda context: object()})
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.stages[0]["status"], "failed")
            self.assertEqual(result.stages[0]["error_type"], "TypeError")


if __name__ == "__main__":
    unittest.main()
