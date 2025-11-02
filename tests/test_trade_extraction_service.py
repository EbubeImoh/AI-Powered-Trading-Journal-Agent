try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover - fallback for direct execution
    import _bootstrap  # type: ignore # noqa: F401

import pytest

from app.schemas import TradeAttachment, TradeSubmissionRequest
from app.services.trade_extraction import ExtractionResult, TradeExtractionService


class StubGemini:
    async def extract_trade_details(self, **_: dict) -> dict:
        return {
            "ticker": "AAPL",
            "pnl": 250.5,
            "position_type": "long",
            "entry_timestamp": "2025-11-01T09:30:00Z",
            "exit_timestamp": "2025-11-01T15:45:00Z",
            "notes": "Auto-notes",
        }


class StubGeminiMissing:
    async def extract_trade_details(self, **_: dict) -> dict:
        return {"ticker": "AAPL"}


@pytest.mark.asyncio
async def test_trade_extraction_service_success():
    service = TradeExtractionService(StubGemini())
    submission = TradeSubmissionRequest(
        user_id="user-1",
        content="Bought AAPL breakout",
        attachments=[
            TradeAttachment(
                filename="chart.png",
                mime_type="image/png",
                file_b64="aGVsbG8=",
                tags=["chart"],
            )
        ],
        pnl=300.0,
    )

    result = await service.extract(submission)

    assert isinstance(result, ExtractionResult)
    assert result.trade is not None
    assert result.trade.ticker == "AAPL"
    assert result.trade.pnl == 300.0  # override applied
    assert result.trade.notes == "Auto-notes"
    assert result.missing_fields == []


@pytest.mark.asyncio
async def test_trade_extraction_service_missing_fields_raises():
    service = TradeExtractionService(StubGeminiMissing())
    submission = TradeSubmissionRequest(
        user_id="user-1",
        content="Missing timestamps",
    )

    result = await service.extract(submission)

    assert result.trade is None
    assert result.missing_fields == [
        "pnl",
        "position_type",
        "entry_timestamp",
        "exit_timestamp",
    ]
