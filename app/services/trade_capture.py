"""SQLite-backed storage for conversational trade capture sessions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.schemas import TradeAttachment, TradeIngestionRequest


def _default_json_serializer(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Type {type(value)!r} not serializable")


def _ensure_directory(db_path: Path) -> None:
    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class TradeCaptureSession:
    """Represents the evolving state of a user's trade submission."""

    session_id: str
    user_id: str
    structured: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    conversation: List[str] = field(default_factory=list)
    attachments: List[TradeAttachment] = field(default_factory=list)
    trade: Optional[TradeIngestionRequest] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def merge_structured(self, payload: Dict[str, Any]) -> None:
        for key, value in payload.items():
            if value in (None, "", []):
                continue
            self.structured[key] = value
        self.touch()

    def set_missing_fields(self, fields: List[str]) -> None:
        self.missing_fields = fields
        self.touch()

    def append_message(self, message: str) -> None:
        if message:
            self.conversation.append(message.strip())
        self.touch()

    def extend_attachments(self, new_attachments: List[TradeAttachment]) -> None:
        if new_attachments:
            self.attachments.extend(new_attachments)
        self.touch()

    def set_trade(self, trade: TradeIngestionRequest | None) -> None:
        self.trade = trade
        self.touch()

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class TradeCaptureStore:
    """SQLite-backed trade capture store with TTL pruning."""

    def __init__(self, db_path: str, ttl_seconds: int = 900) -> None:
        self._db_path = Path(db_path)
        self._ttl = ttl_seconds
        _ensure_directory(self._db_path)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_capture_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    structured TEXT,
                    missing_fields TEXT,
                    conversation TEXT,
                    attachments TEXT,
                    trade TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _prune(self) -> None:
        threshold = (
            datetime.now(timezone.utc) - timedelta(seconds=self._ttl)
        ).isoformat()
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM trade_capture_sessions WHERE updated_at < ?",
                (threshold,),
            )

    def create(
        self,
        *,
        user_id: str,
        initial_message: str,
        structured: Dict[str, Any],
        missing_fields: List[str],
        attachments: List[TradeAttachment],
        trade: TradeIngestionRequest | None = None,
    ) -> TradeCaptureSession:
        self._prune()
        session = TradeCaptureSession(
            session_id=uuid4().hex,
            user_id=user_id,
        )
        session.append_message(initial_message)
        session.merge_structured(structured)
        session.set_missing_fields(missing_fields)
        session.extend_attachments(attachments)
        session.set_trade(trade)
        self._save_session(session)
        return session

    def get(self, session_id: str) -> Optional[TradeCaptureSession]:
        self._prune()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trade_capture_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def get_active_for_user(self, user_id: str) -> Optional[TradeCaptureSession]:
        """Return the most recent session still awaiting user input for a user."""
        self._prune()
        with self._connect() as conn:
            row = conn.execute(
                (
                    "SELECT * FROM trade_capture_sessions "
                    "WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1"
                ),
                (user_id,),
            ).fetchone()
        if not row:
            return None
        session = self._row_to_session(row)
        if not session.missing_fields:
            return None
        return session

    def update(
        self,
        session_id: str,
        *,
        message: str,
        structured: Dict[str, Any],
        missing_fields: List[str],
        attachments: List[TradeAttachment],
        trade: TradeIngestionRequest | None = None,
    ) -> Optional[TradeCaptureSession]:
        session = self.get(session_id)
        if not session:
            return None
        session.append_message(message)
        session.merge_structured(structured)
        session.set_missing_fields(missing_fields)
        session.extend_attachments(attachments)
        session.set_trade(trade)
        self._save_session(session)
        return session

    def delete(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM trade_capture_sessions WHERE session_id = ?",
                (session_id,),
            )

    def _save_session(self, session: TradeCaptureSession) -> None:
        structured_json = json.dumps(
            session.structured, default=_default_json_serializer
        )
        missing_json = json.dumps(session.missing_fields)
        conversation_json = json.dumps(session.conversation)
        attachments_json = json.dumps(
            [attachment.dict() for attachment in session.attachments]
        )
        trade_json = json.dumps(session.trade.dict()) if session.trade else None

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trade_capture_sessions (
                    session_id,
                    user_id,
                    structured,
                    missing_fields,
                    conversation,
                    attachments,
                    trade,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    structured = excluded.structured,
                    missing_fields = excluded.missing_fields,
                    conversation = excluded.conversation,
                    attachments = excluded.attachments,
                    trade = excluded.trade,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    session.session_id,
                    session.user_id,
                    structured_json,
                    missing_json,
                    conversation_json,
                    attachments_json,
                    trade_json,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )

    def _row_to_session(self, row: sqlite3.Row) -> TradeCaptureSession:
        structured = json.loads(row["structured"]) if row["structured"] else {}
        missing = json.loads(row["missing_fields"]) if row["missing_fields"] else []
        conversation = (
            json.loads(row["conversation"]) if row["conversation"] else []
        )
        attachments_raw = (
            json.loads(row["attachments"]) if row["attachments"] else []
        )
        attachments = [TradeAttachment(**item) for item in attachments_raw]
        trade = None
        if row["trade"]:
            trade_data = json.loads(row["trade"])
            trade = TradeIngestionRequest.parse_obj(trade_data)
        created_at = datetime.fromisoformat(row["created_at"])
        updated_at = datetime.fromisoformat(row["updated_at"])

        session = TradeCaptureSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            structured=structured,
            missing_fields=missing,
            conversation=conversation,
            attachments=attachments,
            trade=trade,
            created_at=created_at,
            updated_at=updated_at,
        )
        return session


__all__ = ["TradeCaptureSession", "TradeCaptureStore"]
