"""Google Drive client wrapper."""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Iterable, Optional, TYPE_CHECKING

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from app.services.google_tokens import GoogleTokenService


class GoogleDriveClient:
    """Upload trade artifacts to Google Drive."""

    def __init__(self, token_service: "GoogleTokenService", drive_root_folder_id: str | None = None) -> None:
        self._token_service = token_service
        self._drive_root_folder_id = drive_root_folder_id

    async def upload_base64_file(
        self,
        *,
        user_id: str,
        file_name: str,
        file_b64: str,
        mime_type: str,
        tags: Optional[Iterable[str]] = None,
    ) -> dict:
        """Upload a base64-encoded file to the user's Drive and return metadata."""
        file_bytes = base64.b64decode(file_b64)
        credentials = await self._token_service.get_credentials(user_id=user_id)

        def _execute_upload() -> dict:
            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            file_metadata = {"name": file_name}
            app_properties = {f"tag_{index}": tag for index, tag in enumerate(tags or [], start=1)}
            if app_properties:
                file_metadata["appProperties"] = app_properties

            if self._drive_root_folder_id:
                file_metadata["parents"] = [self._drive_root_folder_id]

            media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)
            created = (
                service.files()
                .create(body=file_metadata, media_body=media, fields="id, webViewLink, mimeType")
                .execute()
            )

            shareable_link = created.get("webViewLink")
            if not shareable_link:
                shareable_link = f"https://drive.google.com/file/d/{created['id']}/view"

            return {
                "drive_file_id": created["id"],
                "shareable_link": shareable_link,
                "mime_type": created.get("mimeType", mime_type),
            }

        return await asyncio.to_thread(_execute_upload)

    async def download_file_bytes(self, *, user_id: str, file_id: str) -> bytes:
        """Download a file from Drive and return its raw bytes."""
        credentials = await self._token_service.get_credentials(user_id=user_id)

        def _execute_download() -> bytes:
            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            attempt = 0
            while attempt < 3:
                try:
                    request = service.files().get_media(fileId=file_id)
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                    fh.seek(0)
                    return fh.read()
                except HttpError as exc:  # pragma: no cover - network path
                    attempt += 1
                    if attempt >= 3:
                        raise exc
                    time.sleep(0.5 * attempt)
            raise RuntimeError("Failed to download Drive file after retries")

        return await asyncio.to_thread(_execute_download)

    async def get_file_metadata(self, *, user_id: str, file_id: str) -> dict:
        """Fetch metadata for a Drive file."""
        credentials = await self._token_service.get_credentials(user_id=user_id)

        def _execute_metadata() -> dict:
            service = build("drive", "v3", credentials=credentials, cache_discovery=False)
            return (
                service.files()
                .get(fileId=file_id, fields="id,name,mimeType,webViewLink")
                .execute()
            )

        return await asyncio.to_thread(_execute_metadata)


__all__ = ["GoogleDriveClient"]
