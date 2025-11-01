"""
Google Drive client wrapper.
"""

from __future__ import annotations

import base64
from typing import Iterable, Optional

from app.core.config import GoogleSettings


class GoogleDriveClient:
    """Upload trade artifacts to Google Drive."""

    def __init__(self, settings: GoogleSettings) -> None:
        self._settings = settings

    async def upload_base64_file(
        self,
        *,
        user_id: str,
        file_name: str,
        file_b64: str,
        mime_type: str,
        tags: Optional[Iterable[str]] = None,
    ) -> dict:
        """
        Upload a base64-encoded file to the user's Drive.

        Returns metadata dictionary containing file id and shareable link.
        """
        # Placeholder: decode to ensure payload is valid. Actual upload uses Google Drive API.
        base64.b64decode(file_b64)
        raise NotImplementedError("Google Drive upload integration not yet implemented.")


__all__ = ["GoogleDriveClient"]
