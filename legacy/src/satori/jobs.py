"""SQLite-backed, single-host job queue. Keep the repository replaceable for cloud DBs."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRepository:
    def __init__(self, database: str | Path):
        self.database = Path(database).expanduser().resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, queue_name TEXT NOT NULL,
                status TEXT NOT NULL, progress REAL NOT NULL, payload_json TEXT NOT NULL,
                config_json TEXT NOT NULL, provenance_json TEXT NOT NULL, logs_json TEXT NOT NULL,
                result_json TEXT, error_json TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, started_at TEXT, finished_at TEXT)""")
            db.execute("CREATE INDEX IF NOT EXISTS jobs_queue_status ON jobs(queue_name,status,created_at)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        for field in ("payload", "config", "provenance", "logs", "result", "error"):
            raw = result.pop(field + "_json", None)
            result[field] = json.loads(raw) if raw is not None else None
        return result

    def create(self, kind: str, queue: str, payload: dict[str, Any], config: dict[str, Any],
               provenance: dict[str, Any]) -> dict[str, Any]:
        if not kind or not queue:
            raise ValueError("kind and queue are required")
        job_id, timestamp = str(uuid.uuid4()), now()
        with closing(self._connect()) as db:
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                job_id, kind, queue, "queued", 0.0, json.dumps(payload, sort_keys=True),
                json.dumps(config, sort_keys=True), json.dumps(provenance, sort_keys=True),
                "[]", None, None, timestamp, timestamp, None, None))
        self.add_log(job_id, "info", "job accepted", {"kind": kind, "queue": queue})
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as db:
            return self._decode(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())

    def claim(self, queue: str) -> dict[str, Any] | None:
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT job_id FROM jobs WHERE queue_name=? AND status='queued' "
                             "ORDER BY created_at,job_id LIMIT 1", (queue,)).fetchone()
            if row is None:
                db.execute("COMMIT")
                return None
            timestamp = now()
            db.execute("UPDATE jobs SET status='running',progress=0.01,started_at=?,updated_at=? "
                       "WHERE job_id=? AND status='queued'", (timestamp, timestamp, row["job_id"]))
            db.execute("COMMIT")
        self.add_log(row["job_id"], "info", "worker claimed job", {"queue": queue})
        return self.get(row["job_id"])

    def update(self, job_id: str, *, status: str | None = None, progress: float | None = None,
               result: dict[str, Any] | None = None, error: dict[str, Any] | None = None,
               provenance: dict[str, Any] | None = None) -> None:
        if progress is not None and not 0 <= progress <= 1:
            raise ValueError("progress must be in [0,1]")
        allowed = {"queued", "running", "completed", "blocked", "failed", "cancelled"}
        if status is not None and status not in allowed:
            raise ValueError(f"unsupported job status: {status}")
        fields: list[str] = ["updated_at=?"]
        values: list[Any] = [now()]
        if status is not None:
            fields.append("status=?"); values.append(status)
            if status in {"completed", "blocked", "failed", "cancelled"}:
                fields.append("finished_at=?"); values.append(now())
        if progress is not None:
            fields.append("progress=?"); values.append(progress)
        for column, value in (("result_json", result), ("error_json", error),
                              ("provenance_json", provenance)):
            if value is not None:
                fields.append(column + "=?"); values.append(json.dumps(value, sort_keys=True))
        values.append(job_id)
        with closing(self._connect()) as db:
            cursor = db.execute(f"UPDATE jobs SET {','.join(fields)} WHERE job_id=?", values)
            if cursor.rowcount != 1:
                raise KeyError(f"unknown job: {job_id}")

    def add_log(self, job_id: str, level: str, message: str,
                context: dict[str, Any] | None = None) -> None:
        event = {"at": now(), "level": level.upper(), "message": message, "context": context or {}}
        with closing(self._connect()) as db:
            row = db.execute("SELECT logs_json FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown job: {job_id}")
            logs = json.loads(row[0]); logs.append(event)
            db.execute("UPDATE jobs SET logs_json=?,updated_at=? WHERE job_id=?",
                       (json.dumps(logs, sort_keys=True), now(), job_id))
