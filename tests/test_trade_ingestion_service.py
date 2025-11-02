try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover - fallback for direct execution
    import _bootstrap  # type: ignore # noqa: F401

import base64

import pytest
from fastapi import HTTPException

from app.schemas import TradeAttachment, TradeIngestionRequest
from app.services.trade_ingestion import TradeIngestionService


class StubDriveClient:
    def __init__(self):
        self.uploads = []

    async def upload_base64_file(
        self, *, user_id: str, file_name: str, file_b64: str, mime_type: str, tags
    ):
        self.uploads.append((user_id, file_name, mime_type, tags))
        return {
            "drive_file_id": file_name,
            "shareable_link": f"https://drive.example.com/{file_name}",
            "mime_type": mime_type,
        }


class StubSheetsClient:
    async def append_trade_row(
        self, *, user_id: str, sheet_id: str, row: list, sheet_range: str | None = None
    ) -> str:
        return "row-42"


def _build_request() -> TradeIngestionRequest:
    return TradeIngestionRequest(
        user_id="user-1",
        ticker="AAPL",
        pnl=100.0,
        position_type="long",
        entry_timestamp="2025-11-01T09:30:00Z",
        exit_timestamp="2025-11-01T15:45:00Z",
        notes="Note",
    )


@pytest.mark.asyncio
async def test_ingestion_service_uploads_attachments():
    service = TradeIngestionService(StubDriveClient(), StubSheetsClient())
    attachment = TradeAttachment(
        filename="chart.png",
        mime_type="image/png",
        file_b64=base64.b64encode(b"img").decode("utf-8"),
        tags=["chart"],
    )

    response = await service.ingest_trade(
        request=_build_request(),
        sheet_id="sheet-1",
        attachments=[attachment],
    )

    assert response.sheet_row_id == "row-42"
    assert response.uploaded_files[0].drive_file_id == "chart.png"


@pytest.mark.asyncio
async def test_ingestion_service_rejects_large_attachment():
    service = TradeIngestionService(StubDriveClient(), StubSheetsClient())
    TradeIngestionService._MAX_ATTACHMENT_BYTES = 10
    big_b64 = base64.b64encode(b"0123456789AB").decode("utf-8")
    attachment = TradeAttachment(
        filename="big.bin",
        mime_type="image/png",
        file_b64=big_b64,
    )

    with pytest.raises(HTTPException):
        await service.ingest_trade(
            request=_build_request(),
            sheet_id="sheet-1",
            attachments=[attachment],
        )

    TradeIngestionService._MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024


@pytest.mark.asyncio
async def test_ingestion_service_rejects_bad_mime():
    service = TradeIngestionService(StubDriveClient(), StubSheetsClient())
    attachment = TradeAttachment(
        filename="doc.pdf",
        mime_type="application/pdf",
        file_b64=base64.b64encode(b"pdf").decode("utf-8"),
    )

    with pytest.raises(HTTPException):
        await service.ingest_trade(
            request=_build_request(),
            sheet_id="sheet-1",
            attachments=[attachment],
        )
