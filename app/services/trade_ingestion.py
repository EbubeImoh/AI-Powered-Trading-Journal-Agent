"""
Business logic for ingesting trades via the FastAPI agent.
"""

from __future__ import annotations

import base64
import binascii
from datetime import timezone
from typing import List

from fastapi import HTTPException, status

from app.clients import GoogleDriveClient, GoogleSheetsClient
from app.schemas import (
    TradeAttachment,
    TradeFileLink,
    TradeIngestionRequest,
    TradeIngestionResponse,
)


class TradeIngestionService:
    """Coordinate file uploads and sheet updates for trade entries."""

    _ALLOWED_MIME_PREFIXES = ("image/", "audio/", "video/")
    _MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024  # 15 MB

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
        sheet_range: str | None = None,
        attachments: List[TradeAttachment] | None = None,
    ) -> TradeIngestionResponse:
        """Persist trade entry and return summary metadata."""
        uploaded_files: List[TradeFileLink] = []

        combined_attachments: List[TradeAttachment] = list(attachments or [])

        if request.image_file_b64:
            combined_attachments.append(
                TradeAttachment(
                    filename=f"{request.ticker}_setup.png",
                    mime_type="image/png",
                    file_b64=request.image_file_b64,
                    tags=["setup", "image"],
                )
            )

        if request.audio_file_b64:
            combined_attachments.append(
                TradeAttachment(
                    filename=f"{request.ticker}_note.m4a",
                    mime_type="audio/mp4",
                    file_b64=request.audio_file_b64,
                    tags=["note", "audio"],
                )
            )

        for attachment in combined_attachments:
            uploaded_files.append(
                await self._upload_attachment(
                    user_id=request.user_id,
                    attachment=attachment,
                )
            )

        sheet_row = self._build_sheet_row(
            request=request, uploaded_files=uploaded_files
        )
        row_id = await self._sheets.append_trade_row(
            user_id=request.user_id,
            sheet_id=sheet_id,
            row=sheet_row,
            sheet_range=sheet_range,
        )

        return TradeIngestionResponse(
            sheet_row_id=row_id, uploaded_files=uploaded_files
        )

    async def _upload_attachment(
        self,
        *,
        user_id: str,
        attachment: TradeAttachment,
    ) -> TradeFileLink:
        """Upload a trade attachment to Drive and return metadata."""
        try:
            payload = base64.b64decode(attachment.file_b64, validate=True)
        except (ValueError, binascii.Error) as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Attachment {attachment.filename} is not valid base64.",
            ) from exc

        if len(payload) > self._MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Attachment {attachment.filename} exceeds "
                    f"{self._MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB limit."
                ),
            )

        if not attachment.mime_type.startswith(self._ALLOWED_MIME_PREFIXES):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Attachment {attachment.filename} has unsupported MIME type "
                    f"{attachment.mime_type}."
                ),
            )

        metadata = await self._drive.upload_base64_file(
            user_id=user_id,
            file_name=attachment.filename,
            file_b64=attachment.file_b64,
            mime_type=attachment.mime_type,
            tags=attachment.tags,
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
        file_links = "; ".join(
            f"{link.drive_file_id}|{link.mime_type}|{link.shareable_link}"
            for link in uploaded_files
        )

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
