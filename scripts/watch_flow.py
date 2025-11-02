"""Watch the local job queue and status store to visualize the agent flow."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from app.clients.local_queue import SQLiteQueueClient
from app.clients.sqlite_store import SQLiteStore
from app.core.config import get_settings
from app.services.trade_capture import TradeCaptureStore


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _print_header(title: str) -> None:
    line = "=" * len(title)
    print(f"\n{title}\n{line}")


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _poll_queue(
    conn: sqlite3.Connection, last_id: int
) -> Tuple[int, Iterator[Dict[str, Any]]]:
    rows = conn.execute(
        (
            "SELECT id, payload, created_at FROM analysis_job_queue "
            "WHERE id > ? ORDER BY id"
        ),
        (last_id,),
    ).fetchall()
    new_last_id = last_id
    events: list[Dict[str, Any]] = []
    for row in rows:
        new_last_id = max(new_last_id, row["id"])
        payload = json.loads(row["payload"])
        payload["queue_id"] = row["id"]
        payload["queued_at"] = row["created_at"]
        events.append(payload)
    return new_last_id, iter(events)


def _poll_job_statuses(
    conn: sqlite3.Connection,
    previous: Dict[str, str],
) -> Dict[str, str]:
    rows = conn.execute(
        "SELECT data FROM kv_records WHERE sk LIKE 'analysis#%'",
    ).fetchall()
    current: Dict[str, str] = {}
    for row in rows:
        record = json.loads(row["data"])
        job_id = record.get("job_id")
        status = record.get("status", "unknown")
        if job_id:
            current[job_id] = status
            if previous.get(job_id) != status:
                summary = record.get("prompt", "(no prompt)")
                completed = record.get("completed_at")
                print(
                    f"[{_timestamp()}] JOB {job_id} status → {status.upper()}"
                    f" | prompt='{summary}'"
                    + (f" | completed_at={completed}" if completed else "")
                )
    return current


def _poll_sessions(
    conn: sqlite3.Connection,
    previous: Dict[str, str],
) -> Dict[str, str]:
    rows = conn.execute(
        "SELECT session_id, missing_fields, updated_at FROM trade_capture_sessions",
    ).fetchall()
    current: Dict[str, str] = {}
    for row in rows:
        session_id = row["session_id"]
        missing_fields = (
            json.loads(row["missing_fields"])
            if row["missing_fields"]
            else []
        )
        status = ",".join(missing_fields) if missing_fields else "complete"
        current[session_id] = status
        if previous.get(session_id) != status:
            print(
                f"[{_timestamp()}] SESSION {session_id} missing → {status or 'none'}"
            )
    return current


def watch(poll_interval: float = 1.0) -> None:
    settings = get_settings()
    db_path = Path(settings.trade_capture_db_path).expanduser()
    # Ensure required tables exist by instantiating the relevant helpers.
    TradeCaptureStore(db_path=str(db_path))
    SQLiteStore(str(db_path))
    SQLiteQueueClient(str(db_path))

    _print_header("Watching trade agent flow (Ctrl+C to exit)")
    last_queue_id = 0
    seen_statuses: Dict[str, str] = {}
    seen_sessions: Dict[str, str] = {}

    while True:
        try:
            with _connect(db_path) as conn:
                last_queue_id, events = _poll_queue(conn, last_queue_id)
                for event in events:
                    job_id = event.get("job_id")
                    user_id = event.get("user_id")
                    prompt = event.get("prompt", "")
                    print(
                        f"[{_timestamp()}] QUEUED job={job_id} user={user_id}"
                        f" | prompt='{prompt}'"
                    )

                seen_statuses = _poll_job_statuses(conn, seen_statuses)
                seen_sessions = _poll_sessions(conn, seen_sessions)
        except sqlite3.Error as exc:
            print(f"[{_timestamp()}] SQLite error: {exc}")

        time.sleep(poll_interval)


if __name__ == "__main__":  # pragma: no cover - manual execution path
    try:
        watch()
    except KeyboardInterrupt:
        print("\nStopped watching.")
