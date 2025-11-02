"""SQLite-backed substitute for DynamoDB-style record storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


class SQLiteStore:
    """Simple key-value store using a normalized table keyed by (pk, sk)."""

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
                CREATE TABLE IF NOT EXISTS kv_records (
                    pk TEXT NOT NULL,
                    sk TEXT NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (pk, sk)
                )
                """
            )

    def put_item(self, item: Dict[str, Any]) -> None:
        pk = item.get("pk")
        sk = item.get("sk")
        if not pk or not sk:
            raise ValueError("Item must include 'pk' and 'sk' keys")

        data_json = json.dumps(item)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kv_records (pk, sk, data)
                VALUES (?, ?, ?)
                ON CONFLICT(pk, sk) DO UPDATE SET data = excluded.data
                """,
                (pk, sk, data_json),
            )

    def get_item(
        self, *, partition_key: str, sort_key: str
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM kv_records WHERE pk = ? AND sk = ?",
                (partition_key, sort_key),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["data"])

    def delete_item(self, *, partition_key: str, sort_key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM kv_records WHERE pk = ? AND sk = ?",
                (partition_key, sort_key),
            )

    def list_items_with_prefix(
        self, *, partition_key: str, sort_key_prefix: str
    ) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data FROM kv_records WHERE pk = ? AND sk LIKE ?",
                (partition_key, f"{sort_key_prefix}%"),
            ).fetchall()
        return [json.loads(row["data"]) for row in rows]


__all__ = ["SQLiteStore"]
