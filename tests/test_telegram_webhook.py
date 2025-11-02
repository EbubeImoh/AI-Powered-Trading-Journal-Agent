try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover - fallback for direct execution
    import _bootstrap  # type: ignore # noqa: F401

import copy
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import TradeIngestionRequest, TradeIngestionResponse
from app.services.trade_capture import TradeCaptureStore
from app.services.trade_extraction import ExtractionResult


class StubTokenService:
    async def get_credentials(self, *, user_id: str):  # pragma: no cover - simple stub
        return True


class ConfigurableExtractionService:
    def __init__(self) -> None:
        self.results: list[ExtractionResult] = []

    async def extract(self, submission):
        if not self.results:
            raise AssertionError("Extraction result not configured")
        return self.results.pop(0)


class RecordingIngestionService:
    def __init__(self) -> None:
        self.requests = []

    async def ingest_trade(
        self,
        *,
        request,
        sheet_id,
        sheet_range=None,
        attachments=None,
    ):
        self.requests.append((request, sheet_id, sheet_range, attachments))
        return TradeIngestionResponse(sheet_row_id="row-telegram", uploaded_files=[])


def _complete_trade(user_id: str = "chat-1") -> TradeIngestionRequest:
    return TradeIngestionRequest(
        user_id=user_id,
        ticker="NVDA",
        pnl=150.0,
        position_type="long",
        entry_timestamp=datetime.fromisoformat("2025-11-01T09:30:00+00:00"),
        exit_timestamp=datetime.fromisoformat("2025-11-01T15:45:00+00:00"),
        notes="Telegram session",
    )


@pytest.fixture()
def overrides(tmp_path):
    from app import dependencies
    from app.core.config import get_settings

    extraction = ConfigurableExtractionService()
    ingestion = RecordingIngestionService()
    store = TradeCaptureStore(db_path=str(tmp_path / "telegram_capture.db"))

    base_settings = copy.deepcopy(get_settings())
    base_settings.telegram_bot_token = "bot-token"
    base_settings.telegram_default_sheet_id = "sheet-telegram"

    app.dependency_overrides.clear()
    app.dependency_overrides.update(
        {
            dependencies.get_google_token_service: lambda: StubTokenService(),
            dependencies.get_trade_extraction_service: lambda: extraction,
            dependencies.get_trade_ingestion_service: lambda: ingestion,
            dependencies.get_trade_capture_store: lambda: store,
            dependencies.get_app_settings: lambda: base_settings,
        }
    )

    yield extraction, ingestion, store

    app.dependency_overrides.clear()


def test_telegram_webhook_needs_more_info(overrides):
    extraction, _, store = overrides

    extraction.results.append(
        ExtractionResult(
            trade=None,
            structured={"ticker": "NVDA"},
            missing_fields=["pnl"],
        )
    )

    client = TestClient(app)
    payload = {
        "update_id": 123,
        "message": {
            "message_id": 1,
            "date": 0,
            "text": "NVDA breakout",
            "chat": {"id": 42},
        },
    }

    response = client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "needs_more_info"
    assert data["reply"]
    session_id = data["session_id"]
    assert session_id
    assert store.get(session_id)


def test_telegram_webhook_completed(overrides):
    extraction, ingestion, store = overrides

    extraction.results.append(
        ExtractionResult(
            trade=_complete_trade(),
            structured={},
            missing_fields=[],
        )
    )

    client = TestClient(app)
    payload = {
        "update_id": 123,
        "message": {
            "message_id": 1,
            "date": 0,
            "text": "All done",
            "chat": {"id": 77},
        },
    }

    response = client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "completed"
    assert "trade" not in data
    assert ingestion.requests


def test_telegram_webhook_connect(overrides):
    extraction, ingestion, store = overrides

    client = TestClient(app)
    payload = {
        "update_id": 456,
        "message": {
            "message_id": 2,
            "date": 0,
            "text": "/connect",
            "chat": {"id": 99},
        },
    }

    response = client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "connect"
    assert "connect your google account" in data["reply"].lower()
    assert "user_id=99" in data["reply"]
    assert data["chat_id"] == 99
