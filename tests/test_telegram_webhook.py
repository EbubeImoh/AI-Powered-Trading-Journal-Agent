try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover - fallback for direct execution
    import _bootstrap  # type: ignore # noqa: F401

import copy
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException
from http import HTTPStatus

from app.main import app
from app.schemas import TradeIngestionRequest, TradeIngestionResponse, TradeSubmissionRequest
from app.services.trade_capture import TradeCaptureStore
from app.services.trade_extraction import ExtractionResult


class StubTokenService:
    async def get_credentials(self, *, user_id: str):  # pragma: no cover - simple stub
        return True


class ConfigurableExtractionService:
    def __init__(self) -> None:
        self.results: list[ExtractionResult] = []
        self.submissions: list[TradeSubmissionRequest] = []

    async def extract(self, submission):
        self.submissions.append(submission)
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


pytestmark = pytest.mark.anyio("asyncio")


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

    yield extraction, ingestion, store, base_settings

    app.dependency_overrides.clear()


@pytest.fixture()
async def client(overrides):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


async def test_telegram_webhook_needs_more_info(overrides, client):
    extraction, _, store, _ = overrides

    extraction.results.append(
        ExtractionResult(
            trade=None,
            structured={"ticker": "NVDA"},
            missing_fields=["pnl"],
        )
    )

    payload = {
        "update_id": 123,
        "message": {
            "message_id": 1,
            "date": 0,
            "text": "NVDA breakout",
            "chat": {"id": 42},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["method"] == "sendMessage"
    assert data["chat_id"] == 42
    assert "profit or loss" in data["text"].lower()
    active_session = store.get_active_for_user("42")
    assert active_session is not None


async def test_telegram_webhook_completed(overrides, client):
    extraction, ingestion, store, _ = overrides

    extraction.results.append(
        ExtractionResult(
            trade=_complete_trade(),
            structured={},
            missing_fields=[],
        )
    )

    payload = {
        "update_id": 123,
        "message": {
            "message_id": 1,
            "date": 0,
            "text": "All done",
            "chat": {"id": 77},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["method"] == "sendMessage"
    assert data["chat_id"] == 77
    assert "nvda" in data["text"].lower()
    assert ingestion.requests


async def test_telegram_webhook_connect(overrides, client):
    extraction, ingestion, store, _ = overrides

    payload = {
        "update_id": 456,
        "message": {
            "message_id": 2,
            "date": 0,
            "text": "/connect",
            "chat": {"id": 99},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["method"] == "sendMessage"
    assert data["chat_id"] == 99
    assert "connect your google account" in data["text"].lower()
    assert "user_id=99" in data["text"]
    assert "redirect=1" in data["text"]


async def test_telegram_connect_authorize_roundtrip(overrides, client):
    _, _, _, base_settings = overrides
    base_settings.telegram_connect_base_url = "https://api.pecuniatrust.com"

    class DummyOAuthClient:
        def __init__(self) -> None:
            self.states: list[str] = []

        def build_authorization_url(self, state: str) -> str:
            self.states.append(state)
            return f"https://oauth.example.com/auth?state={state}"

    from app.dependencies import get_google_oauth_client

    dummy_client = DummyOAuthClient()
    app.dependency_overrides[get_google_oauth_client] = lambda: dummy_client

    payload = {
        "update_id": 789,
        "message": {
            "message_id": 3,
            "date": 0,
            "text": "/connect",
            "chat": {"id": 12345},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 200
    connect_reply = response.json()
    assert connect_reply["method"] == "sendMessage"
    link_line = connect_reply["text"].splitlines()[-1].strip()

    parsed = urlparse(link_line)
    assert parsed.scheme == "https"
    assert parsed.netloc == "api.pecuniatrust.com"
    assert parsed.path == "/api/auth/google/authorize"
    query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    assert query == {"user_id": "12345", "redirect": "1"}

    auth_response = await client.get(parsed.path, params={"user_id": "12345"})
    assert auth_response.status_code == 200
    data = auth_response.json()
    assert data["authorization_url"].startswith("https://oauth.example.com/auth")
    assert dummy_client.states and dummy_client.states[-1] == data["state"]


async def test_telegram_prompts_connect_when_not_authorized(overrides, client):
    extraction, _, store, _ = overrides

    class UnauthorizedTokenService:
        async def get_credentials(self, *, user_id: str):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Google account not connected.",
            )

    from app import dependencies

    override_key = dependencies.get_google_token_service
    previous = app.dependency_overrides.get(override_key)
    app.dependency_overrides[override_key] = lambda: UnauthorizedTokenService()
    try:
        payload = {
            "update_id": 999,
            "message": {
                "message_id": 4,
                "date": 0,
                "text": "Log my trade",
                "chat": {"id": 555},
            },
        }

        response = await client.post(
            "/api/integrations/telegram/webhook",
            params={"token": "bot-token"},
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["method"] == "sendMessage"
        assert data["chat_id"] == 555
        assert "send /connect" in data["text"].lower()
        assert store.get_active_for_user("555") is None
    finally:
        if previous is not None:
            app.dependency_overrides[override_key] = previous
        else:
            app.dependency_overrides.pop(override_key, None)


async def test_telegram_absorbs_single_field_reply(overrides, client):
    extraction, _, store, _ = overrides

    extraction.results.extend(
        [
            ExtractionResult(
                trade=None,
                structured={},
                missing_fields=["ticker", "pnl"],
            ),
            ExtractionResult(
                trade=None,
                structured={"ticker": "GOLD"},
                missing_fields=["pnl"],
            ),
        ]
    )

    start_payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "text": "Hi",
            "chat": {"id": 200},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=start_payload,
    )
    assert response.status_code == 200
    session = store.get_active_for_user("200")
    assert session is not None

    follow_payload = {
        "update_id": 2,
        "message": {
            "message_id": 2,
            "date": 0,
            "text": "Gold",
            "chat": {"id": 200},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=follow_payload,
    )
    assert response.status_code == 200
    data = response.json()
    lower = data["text"].lower()
    assert "profit or loss" in lower
    assert "which ticker" not in lower
    assert extraction.submissions[-1].ticker == "GOLD"
