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
from app.schemas import TradeAttachment, TradeIngestionRequest, TradeIngestionResponse, TradeSubmissionRequest
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


class StubAssistant:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object, dict]] = []

    async def compose_reply(self, **kwargs):
        self.calls.append(
            (
                kwargs.get("user_message"),
                kwargs.get("session"),
                kwargs.get("result"),
                kwargs.get("inferred_fields") or {},
            )
        )
        result = kwargs.get("result")
        if result and result.status == "completed":
            return "assistant: trade captured"
        missing = result.missing_fields if result else []
        return f"assistant: missing {missing}"


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
    assistant = StubAssistant()
    queue_service = RecordingQueueService()
    record_store = DummyRecordStore()

    base_settings = copy.deepcopy(get_settings())
    base_settings.telegram_bot_token = "bot-token"
    base_settings.telegram_default_sheet_id = "sheet-telegram"

    app.dependency_overrides.clear()
    # ensure cached dependencies don't leak between tests
    if hasattr(dependencies.get_telegram_conversation_assistant, "cache_clear"):
        dependencies.get_telegram_conversation_assistant.cache_clear()
    app.dependency_overrides.update(
        {
            dependencies.get_google_token_service: lambda: StubTokenService(),
            dependencies.get_trade_extraction_service: lambda: extraction,
            dependencies.get_trade_ingestion_service: lambda: ingestion,
            dependencies.get_trade_capture_store: lambda: store,
            dependencies.get_app_settings: lambda: base_settings,
            dependencies.get_telegram_conversation_assistant: lambda: assistant,
            dependencies.get_analysis_queue_service: lambda: queue_service,
            dependencies.get_sqlite_store: lambda: record_store,
        }
    )

    yield extraction, ingestion, store, base_settings, assistant, queue_service, record_store

    app.dependency_overrides.clear()


@pytest.fixture()
async def client(overrides):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client


async def test_telegram_webhook_needs_more_info(overrides, client):
    extraction, _, store, _, assistant, _, _ = overrides

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
    assert data["text"].startswith("assistant: missing")
    active_session = store.get_active_for_user("42")
    assert active_session is not None


async def test_telegram_webhook_completed(overrides, client):
    extraction, ingestion, store, _, assistant, _, _ = overrides

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
    assert data["text"].startswith("assistant: trade captured")
    assert ingestion.requests


async def test_telegram_webhook_connect(overrides, client):
    extraction, ingestion, store, _, assistant, _, _ = overrides

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
    _, _, _, base_settings, assistant, _, _ = overrides
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
    extraction, _, store, _, assistant, _, _ = overrides

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
    extraction, _, store, _, assistant, _, _ = overrides

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
    assert data["text"].startswith("assistant: missing")
    assert extraction.submissions[-1].ticker == "GOLD"


async def test_telegram_handles_ticker_negation(overrides, client):
    extraction, _, store, _, assistant, _, _ = overrides

    extraction.results.extend(
        [
            ExtractionResult(
                trade=None,
                structured={},
                missing_fields=["ticker", "pnl"],
            ),
            ExtractionResult(
                trade=None,
                structured={},
                missing_fields=["ticker", "pnl"],
            ),
        ]
    )

    start_payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "text": "Hi",
            "chat": {"id": 201},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=start_payload,
    )
    assert response.status_code == 200
    session = store.get_active_for_user("201")
    assert session is not None

    follow_payload = {
        "update_id": 2,
        "message": {
            "message_id": 2,
            "date": 0,
            "text": "No, that's not my ticker",
            "chat": {"id": 201},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=follow_payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["text"].startswith("assistant: missing")
    assert extraction.submissions[-1].ticker is None


async def test_telegram_handles_photo_attachment(monkeypatch, overrides, client):
    from app.api import routes as telegram_routes

    extraction, _, store, _, assistant, _, _ = overrides

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

    async def fake_collect(message_dict, bot_token):
        return (
            [
                TradeAttachment(
                    filename="chart.png",
                    mime_type="image/png",
                    file_b64="ZGF0YQ==",
                    tags=["photo"],
                )
            ],
            ["Photo attached: chart.png"],
        )

    monkeypatch.setattr(
        telegram_routes, "_collect_telegram_attachments", fake_collect
    )

    payload = {
        "update_id": 10,
        "message": {
            "message_id": 5,
            "date": 0,
            "text": "",
            "caption": "Here is the setup",
            "chat": {"id": 301},
            "photo": [
                {
                    "file_id": "photo-id",
                    "file_unique_id": "unique-photo",
                    "file_size": 12345,
                    "width": 800,
                    "height": 600,
                }
            ],
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 200
    assert assistant.calls, "assistant should be invoked for media messages"
    assert extraction.submissions, "extraction service should receive submission"
    assert extraction.submissions[-1].attachments
    assert assistant.calls[-1][0].startswith("Here is the setup")


async def test_telegram_parses_natural_entry_time(overrides, client):
    extraction, _, store, _, assistant, _, _ = overrides

    extraction.results.extend(
        [
            ExtractionResult(
                trade=None,
                structured={},
                missing_fields=["ticker", "entry_timestamp"],
            ),
            ExtractionResult(
                trade=None,
                structured={"ticker": "GOLD"},
                missing_fields=["exit_timestamp"],
            ),
        ]
    )

    start_payload = {
        "update_id": 20,
        "message": {
            "message_id": 10,
            "date": 0,
            "text": "Start",
            "chat": {"id": 400},
        },
    }

    await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=start_payload,
    )

    follow_payload = {
        "update_id": 21,
        "message": {
            "message_id": 11,
            "date": 0,
            "text": "My entry was 3pm",
            "chat": {"id": 400},
        },
    }

    await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=follow_payload,
    )

    submission = extraction.submissions[-1]
    assert submission.entry_timestamp is not None
    assert submission.entry_timestamp.tzinfo is not None
    assert submission.entry_timestamp.hour == 15


async def test_telegram_analysis_enqueue(overrides, client):
    extraction, _, store, base_settings, assistant, queue_service, record_store = overrides

    payload = {
        "update_id": 30,
        "message": {
            "message_id": 15,
            "date": 0,
            "text": "/analysis Summarize last week's trades",
            "chat": {"id": 500},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 200
    assert "job-1" in response.json()["text"]
    assert queue_service.requests
    request = queue_service.requests[-1]
    assert request.prompt == "Summarize last week's trades"


async def test_telegram_analysis_status(overrides, client):
    extraction, _, store, base_settings, assistant, queue_service, record_store = overrides

    record_store.items[("user#500", "analysis#job-1")] = {
        "status": "completed",
        "summary": "All good",
    }

    payload = {
        "update_id": 31,
        "message": {
            "message_id": 16,
            "date": 0,
            "text": "/analysis_status job-1",
            "chat": {"id": 500},
        },
    }

    response = await client.post(
        "/api/integrations/telegram/webhook",
        params={"token": "bot-token"},
        json=payload,
    )

    assert response.status_code == 200
    text = response.json()["text"].lower()
    assert "job-1" in text and "completed" in text
class RecordingQueueService:
    def __init__(self) -> None:
        self.requests = []

    def enqueue_analysis(self, request):
        self.requests.append(request)
        return f"job-{len(self.requests)}"


class DummyRecordStore:
    def __init__(self) -> None:
        self.items = {}

    def get_item(self, *, partition_key: str, sort_key: str):
        return self.items.get((partition_key, sort_key))

    def put_item(self, item):  # pragma: no cover - not used in tests
        key = (item["pk"], item["sk"])
        self.items[key] = item
