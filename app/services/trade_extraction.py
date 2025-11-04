"""Service that leverages Gemini to structure raw trade submissions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.clients import GeminiClient
from app.clients.gemini import GeminiModelError
from app.schemas import TradeIngestionRequest, TradeSubmissionRequest


@dataclass(slots=True)
class ExtractionResult:
    """Outcome of attempting to structure a raw trade submission."""

    trade: Optional[TradeIngestionRequest]
    structured: Dict[str, Any]
    missing_fields: List[str]


class TradeExtractionService:
    """Convert unstructured trade submissions into structured sheet entries."""

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini = gemini_client

    async def extract(self, submission: TradeSubmissionRequest) -> ExtractionResult:
        attachment_metadata = [
            {"filename": attachment.filename, "mime_type": attachment.mime_type}
            for attachment in submission.attachments
        ]

        overrides: Dict[str, Any] = {}
        for field_name in (
            "ticker",
            "pnl",
            "position_type",
            "entry_timestamp",
            "exit_timestamp",
            "notes",
        ):
            value = getattr(submission, field_name)
            if value is not None:
                overrides[field_name] = value

        try:
            gemini_payload = await self._gemini.extract_trade_details(
                content=submission.content,
                attachment_metadata=attachment_metadata,
                overrides=overrides,
            )
        except GeminiModelError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        structured: Dict[str, Any] = {**gemini_payload, **overrides}
        structured["user_id"] = submission.user_id
        if "notes" not in structured or structured["notes"] is None:
            structured["notes"] = submission.notes or ""

        required_fields: List[str] = [
            "ticker",
            "pnl",
            "position_type",
            "entry_timestamp",
            "exit_timestamp",
        ]
        missing = [field for field in required_fields if not structured.get(field)]
        if missing:
            return ExtractionResult(
                trade=None,
                structured=structured,
                missing_fields=missing,
            )

        try:
            request = TradeIngestionRequest(**structured)
        except ValidationError as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unable to extract required trade fields: {exc.errors()}",
            ) from exc

        return ExtractionResult(
            trade=request,
            structured=structured,
            missing_fields=[],
        )


__all__ = ["ExtractionResult", "TradeExtractionService"]
