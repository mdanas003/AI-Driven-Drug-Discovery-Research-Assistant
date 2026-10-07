from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satori.capabilities import detect_capabilities
from satori.errors import CheckpointUnavailable
from satori.job_handlers import HANDLERS
from satori.jobs import JobRepository
from satori.model_registry import ModelArtifactRegistry
from satori.runtime_config import RuntimeConfig
from satori.storage import LocalArtifactStore
from satori.vector_store import LocalJsonVectorStore, VectorRecord
from satori.worker import healthcheck, heartbeat, main as worker_main, process_one


class CloudRuntimeConfigTests(unittest.TestCase):
    def test_environment_config_uses_overrides_and_validates_queue(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "SATORI_ARTIFACT_DIR": str(Path(directory) / "out"),
            "SATORI_DATA_DIR": str(Path(directory) / "data"),
            "SATORI_WORKER_QUEUE": "gpu", "SATORI_API_PORT": "8123",
        }, clear=True):
            config = RuntimeConfig.from_env()
        self.assertEqual(config.worker_queue, "gpu")
        self.assertEqual(config.api_port, 8123)
        self.assertTrue(str(config.state_db).endswith("jobs.sqlite3"))

    def test_invalid_queue_is_rejected(self) -> None:
        with patch.dict(os.environ, {"SATORI_WORKER_QUEUE": "quantum"}, clear=True):
            with self.assertRaisesRegex(ValueError, "SATORI_WORKER_QUEUE"):
                RuntimeConfig.from_env()

    def test_capability_report_is_structured_without_assuming_gpu(self) -> None:
        result = detect_capabilities()
        self.assertIn("python", result)
        self.assertIn("cuda_available", result)
        self.assertIn("gpus", result)
        self.assertIsInstance(result["optional_packages"], dict)


class ArtifactStorageTests(unittest.TestCase):
    def test_local_artifact_roundtrip_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(directory)
            result = store.put_json("jobs/a/result.json", {"value": 3})
            self.assertEqual(store.get_json("jobs/a/result.json"), {"value": 3})
            self.assertEqual(result["sha256"], hashlib.sha256(
                json.dumps({"value": 3}, sort_keys=True, indent=2, ensure_ascii=False).encode()).hexdigest())

    def test_local_artifact_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(directory)
            with self.assertRaises(ValueError):
                store.put_bytes("../escape", b"x")

    def test_local_binary_file_transfer_preserves_content_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            source.write_bytes(b"checkpoint-fixture")
            metadata = LocalArtifactStore(root / "store").put_file("models/model.bin", source)
            self.assertEqual(Path(metadata["uri"]).read_bytes(), source.read_bytes())
            self.assertEqual(metadata["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())


class JobAndWorkerTests(unittest.TestCase):
    def test_job_queue_status_and_queue_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = JobRepository(Path(directory) / "jobs.sqlite3")
            job = repo.create("sample", "gpu", {"seed": 17}, {"version": 1}, {"source": "test"})
            self.assertEqual(job["status"], "queued")
            self.assertIsNone(repo.claim("cpu"))
            claimed = repo.claim("gpu")
            self.assertEqual(claimed["job_id"], job["job_id"])
            self.assertEqual(claimed["status"], "running")
            self.assertTrue(claimed["logs"])

    def test_worker_propagates_graphfdm_blocker_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = RuntimeConfig(root / "data", root / "artifacts", root / "artifacts/state/jobs.sqlite3",
                                str(root / "artifacts"), root / "registry.json", root / "cache",
                                "INFO", "127.0.0.1", 8000, "gpu", 0.5, "cpu")
            repo = JobRepository(cfg.state_db)
            job = repo.create("optimize", "gpu", {
                "disease_id": "MONDO_0005233", "target_id": "T1", "molecules": ["CCO"]
            },
                              {}, {"source": "test"})
            self.assertTrue(process_one(repo, cfg, "gpu"))
            done = repo.get(job["job_id"])
            self.assertEqual(done["status"], "blocked")
            self.assertIn("GraphFDM execution blocked", done["error"]["message"])
            self.assertEqual(done["provenance"]["source"], "test")

    def test_worker_persists_result_artifact_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = RuntimeConfig(root / "data", root / "artifacts", root / "artifacts/state/jobs.sqlite3",
                                str(root / "artifacts"), root / "registry.json", root / "cache",
                                "INFO", "127.0.0.1", 8000, "cpu", 0.5, "cpu")
            repo = JobRepository(cfg.state_db)
            job = repo.create("fixture", "cpu", {}, {}, {"data_hash": "abc"})
            with patch.dict(HANDLERS, {"fixture": lambda _payload, _cfg: {"ok": True}}):
                process_one(repo, cfg, "cpu")
            done = repo.get(job["job_id"])
            self.assertEqual(done["status"], "completed")
            self.assertEqual(done["provenance"]["data_hash"], "abc")
            self.assertEqual(done["result"]["artifact"]["sha256"], hashlib.sha256(
                b'{\n  "ok": true\n}').hexdigest())

    def test_worker_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = RuntimeConfig(root, root / "artifacts", root / "artifacts/state/jobs.sqlite3",
                                str(root / "artifacts"), root / "registry.json", root / "cache",
                                "INFO", "127.0.0.1", 8000, "cpu", 0.5, "cpu")
            heartbeat(cfg, "cpu")
            self.assertTrue(healthcheck(cfg, "cpu"))

    def test_worker_startup_once_mode_creates_database_and_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "SATORI_DATA_DIR": str(root / "data"),
                "SATORI_ARTIFACT_DIR": str(root / "artifacts"),
                "SATORI_STATE_DB": str(root / "artifacts" / "state" / "jobs.sqlite3"),
                "SATORI_STORAGE_URI": str(root / "artifacts"),
                "SATORI_WORKER_QUEUE": "cpu",
            }, clear=True), patch("sys.argv", ["satori-worker", "--once"]):
                self.assertEqual(worker_main(), 0)
                self.assertTrue(healthcheck(RuntimeConfig.from_env(), "cpu"))
            self.assertTrue((root / "artifacts" / "state" / "jobs.sqlite3").is_file())


class ModelRegistryTests(unittest.TestCase):
    def test_resolver_checks_file_hash_and_unavailable_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "checkpoint.bin"
            artifact.write_bytes(b"model")
            (root / "registry.json").write_text(json.dumps({"models": {
                "ready": {"availability": "available", "artifact_path": str(artifact),
                          "sha256": hashlib.sha256(b"model").hexdigest()},
                "blocked": {"availability": "blocked", "blocker": "checkpoint missing"}}}))
            registry = ModelArtifactRegistry(root / "registry.json")
            self.assertEqual(registry.resolve("ready"), artifact.resolve())
            with self.assertRaisesRegex(CheckpointUnavailable, "checkpoint missing"):
                registry.resolve("blocked")


class VectorStoreTests(unittest.TestCase):
    def test_local_index_persists_cosine_order_and_validates_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.json"
            store = LocalJsonVectorStore(path)
            store.upsert([VectorRecord("a", [1.0, 0.0], {"source": "fixture"}),
                          VectorRecord("b", [0.0, 1.0], {})])
            hits = LocalJsonVectorStore(path).query([0.8, 0.2])
            self.assertEqual(hits[0].record_id, "a")
            self.assertEqual(hits[0].metadata["source"], "fixture")
            with self.assertRaisesRegex(ValueError, "dimensions"):
                store.query([1.0])


class CloudApiTests(unittest.TestCase):
    def test_health_and_job_submission(self) -> None:
        try:
            from fastapi.testclient import TestClient
            from satori.api import app
        except ImportError:
            self.skipTest("Install the cloud-api extra to exercise HTTP routes")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "SATORI_DATA_DIR": str(Path(directory) / "data"),
            "SATORI_ARTIFACT_DIR": str(Path(directory) / "artifacts"),
            "SATORI_STATE_DB": str(Path(directory) / "artifacts" / "jobs.sqlite3"),
            "SATORI_STORAGE_URI": str(Path(directory) / "artifacts"),
            "SATORI_API_TOKEN": "test-only-token",
        }, clear=True):
            app.state._state.clear()
            client = TestClient(app)
            self.assertEqual(client.get("/health").status_code, 200)
            submitted = client.post("/optimize", headers={"Authorization": "Bearer test-only-token"},
                                    json={"disease_id": "MONDO_0005233", "target_id": "T1",
                                          "molecules": ["CCO"]})
            self.assertEqual(submitted.status_code, 202)
            self.assertEqual(submitted.json()["queue"], "gpu")
            status_response = client.get(submitted.json()["status_url"],
                                         headers={"Authorization": "Bearer test-only-token"})
            self.assertEqual(status_response.json()["status"], "queued")
            self.assertEqual(client.post("/generate", headers={"Authorization": "Bearer test-only-token"}, json={"api_key": "do-not-store"}).status_code, 422)
            self.assertEqual(client.get(submitted.json()["status_url"]).status_code, 401)
            app.state._state.clear()


if __name__ == "__main__":
    unittest.main()
