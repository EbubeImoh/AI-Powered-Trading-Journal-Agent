"""SQLite-backed queue implementation used in place of AWS SQS."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class SQLiteQueueClient:
    """Persist job payloads in a SQLite table for later processing."""

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        if self._db_path.parent and not self._db_path.parent.exists():
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_job_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def enqueue_analysis_request(self, payload: Dict[str, Any]) -> None:
        message_json = json.dumps(payload)
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO analysis_job_queue (payload, created_at) VALUES (?, ?)",
                (message_json, created_at),
            )

    def dequeue_analysis_request(self) -> Dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, payload FROM analysis_job_queue ORDER BY id LIMIT 1"
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "DELETE FROM analysis_job_queue WHERE id = ?",
                (row["id"],),
            )
        return json.loads(row["payload"])


__all__ = ["SQLiteQueueClient"]
