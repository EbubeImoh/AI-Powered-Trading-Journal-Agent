try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover - fallback for direct execution
    import _bootstrap  # type: ignore # noqa: F401

import base64
from datetime import datetime

import httpx
import pytest

from app.main import app
from app.schemas import (
    TradeIngestionRequest,
    TradeIngestionResponse,
    TradeSubmissionRequest,
)
from app.services.trade_capture import TradeCaptureStore
from app.services.trade_extraction import ExtractionResult


class StubTokenService:
    async def get_credentials(self, *, user_id: str):  # pragma: no cover - simple stub
        return True


class ConfigurableExtractionService:
    def __init__(self) -> None:
        self.results: list[ExtractionResult] = []
        self.submissions: list[TradeSubmissionRequest] = []

    async def extract(self, submission: TradeSubmissionRequest) -> ExtractionResult:
        self.submissions.append(submission)
        if not self.results:
            raise AssertionError("No extraction result configured")
        return self.results.pop(0)


class RecordingIngestionService:
    def __init__(self) -> None:
        self.requests = []

    async def ingest_trade(
        self,
        *,
        request: TradeIngestionRequest,
        sheet_id: str,
        sheet_range: str | None = None,
        attachments=None,
    ) -> TradeIngestionResponse:
        self.requests.append(
            {
                "request": request,
                "sheet_id": sheet_id,
                "sheet_range": sheet_range,
                "attachments": attachments or [],
            }
        )
        return TradeIngestionResponse(sheet_row_id="row-1", uploaded_files=[])


pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture()
def overrides(tmp_path):
    from app import dependencies

    extraction = ConfigurableExtractionService()
    ingestion = RecordingIngestionService()
    store = TradeCaptureStore(
        db_path=str(tmp_path / "trade_capture.db"), ttl_seconds=60
    )

    app.dependency_overrides.clear()
    app.dependency_overrides.update(
        {
            dependencies.get_google_token_service: lambda: StubTokenService(),
            dependencies.get_trade_extraction_service: lambda: extraction,
            dependencies.get_trade_ingestion_service: lambda: ingestion,
            dependencies.get_trade_capture_store: lambda: store,
        }
    )

    yield extraction, ingestion, store

    app.dependency_overrides.clear()


@pytest.fixture()
async def client(overrides):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


def _build_complete_trade(user_id: str = "user-1") -> TradeIngestionRequest:
    return TradeIngestionRequest(
        user_id=user_id,
        ticker="NVDA",
        pnl=420.0,
        position_type="long",
        entry_timestamp=datetime.fromisoformat("2025-11-01T09:30:00+00:00"),
        exit_timestamp=datetime.fromisoformat("2025-11-01T15:45:00+00:00"),
        notes="Breakout setup",
    )


async def test_submit_trade_endpoint_completed(overrides, client):
    extraction, ingestion, _ = overrides
    extraction.results.append(
        ExtractionResult(
            trade=_build_complete_trade(),
            structured={},
            missing_fields=[],
        )
    )

    payload = {
        "user_id": "user-1",
        "content": "Bought NVDA call options",
        "attachments": [
            {
                "filename": "chart.png",
                "mime_type": "image/png",
                "file_b64": base64.b64encode(b"img").decode("utf-8"),
            }
        ],
        "ticker": "NVDA",
        "pnl": 420.0,
    }

    response = await client.post(
        "/api/trades/submit",
        params={"sheet_id": "sheet-1"},
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["ingestion_response"]["sheet_row_id"] == "row-1"
    assert "NVDA" in body["summary"]
    assert ingestion.requests[0]["sheet_id"] == "sheet-1"


async def test_submit_trade_endpoint_requests_more_info(overrides, client):
    extraction, _, store = overrides
    extraction.results.append(
        ExtractionResult(
            trade=None,
            structured={"ticker": "NVDA"},
            missing_fields=["pnl", "entry_timestamp"],
        )
    )

    payload = {
        "user_id": "user-83",
        "content": "Short NVDA on rejection",
    }

    response = await client.post(
        "/api/trades/submit",
        params={"sheet_id": "sheet-1"},
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "needs_more_info"
    assert store.get(body["session_id"]) is not None
    assert body["missing_fields"] == ["pnl", "entry_timestamp"]
    assert "profit or loss" in body["prompt"].lower()
