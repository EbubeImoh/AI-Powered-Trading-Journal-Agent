"""
Business logic for ingesting trades via the FastAPI agent.
"""

from __future__ import annotations

import base64
from datetime import timezone
from typing import List

from app.clients import GoogleDriveClient, GoogleSheetsClient
from app.schemas import TradeFileLink, TradeIngestionRequest, TradeIngestionResponse


class TradeIngestionService:
    """Coordinate file uploads and sheet updates for trade entries."""

    def __init__(
        self,
        drive_client: GoogleDriveClient,
        sheets_client: GoogleSheetsClient,
    ) -> None:
        self._drive = drive_client
        self._sheets = sheets_client

    async def ingest_trade(
        self,
        *,
        request: TradeIngestionRequest,
        sheet_id: str,
    ) -> TradeIngestionResponse:
        """Persist trade entry and return summary metadata."""
        uploaded_files: List[TradeFileLink] = []

        if request.image_file_b64:
            uploaded_files.append(
                await self._upload_file(
                    user_id=request.user_id,
                    file_name=f"{request.ticker}_setup.png",
                    file_b64=request.image_file_b64,
                    mime_type="image/png",
                    tags=["setup", "image"],
                )
            )

        if request.audio_file_b64:
            uploaded_files.append(
                await self._upload_file(
                    user_id=request.user_id,
                    file_name=f"{request.ticker}_note.m4a",
                    file_b64=request.audio_file_b64,
                    mime_type="audio/mp4",
                    tags=["note", "audio"],
                )
            )

        sheet_row = self._build_sheet_row(request=request, uploaded_files=uploaded_files)
        row_id = await self._sheets.append_trade_row(sheet_id=sheet_id, row=sheet_row)

        return TradeIngestionResponse(sheet_row_id=row_id, uploaded_files=uploaded_files)

    async def _upload_file(
        self,
        *,
        user_id: str,
        file_name: str,
        file_b64: str,
        mime_type: str,
        tags: list[str],
    ) -> TradeFileLink:
        """Upload a base64 file to Drive and return metadata."""
        # Proactively validate payload is proper base64 before network call.
        base64.b64decode(file_b64)
        metadata = await self._drive.upload_base64_file(
            user_id=user_id,
            file_name=file_name,
            file_b64=file_b64,
            mime_type=mime_type,
            tags=tags,
        )
        return TradeFileLink(**metadata)

    @staticmethod
    def _build_sheet_row(
        *,
        request: TradeIngestionRequest,
        uploaded_files: List[TradeFileLink],
    ) -> list:
        """Convert trade request into a row object for Google Sheets."""
        entry_ts = request.entry_timestamp.astimezone(timezone.utc).isoformat()
        exit_ts = request.exit_timestamp.astimezone(timezone.utc).isoformat()
        file_links = ", ".join(link.shareable_link for link in uploaded_files)

        return [
            request.user_id,
            request.ticker.upper(),
            request.position_type,
            request.pnl,
            entry_ts,
            exit_ts,
            request.notes or "",
            file_links,
        ]


__all__ = ["TradeIngestionService"]
