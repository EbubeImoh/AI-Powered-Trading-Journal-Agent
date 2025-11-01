import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import TradeIngestionResponse, TradeSubmissionRequest


class StubTokenService:
    async def get_credentials(self, *, user_id: str):  # pragma: no cover - simple stub
        return True


class StubExtractionService:
    async def extract(self, submission: TradeSubmissionRequest):
        return submission.dict(
            include={
                "user_id",
                "ticker",
                "pnl",
                "position_type",
                "entry_timestamp",
                "exit_timestamp",
                "notes",
            },
            exclude_none=True,
        )


class StubIngestionService:
    async def ingest_trade(self, *, request, sheet_id, sheet_range=None, attachments=None):
        return TradeIngestionResponse(sheet_row_id="row-1", uploaded_files=[])


@pytest.fixture(autouse=True)
def override_dependencies():
    from app import dependencies

    app.dependency_overrides.clear()
    app.dependency_overrides.update(
        {
            dependencies.get_google_token_service: lambda: StubTokenService(),
            dependencies.get_trade_extraction_service: lambda: StubExtractionService(),
            dependencies.get_trade_ingestion_service: lambda: StubIngestionService(),
        }
    )
    yield
    app.dependency_overrides.clear()


def test_submit_trade_endpoint():
    client = TestClient(app)
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

    response = client.post(
        "/api/trades/submit",
        params={"sheet_id": "sheet-1"},
        json=payload,
    )

    assert response.status_code == 201
    assert response.json()["sheet_row_id"] == "row-1"
