"""
Tool abstractions used by the analysis agent.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.clients import GoogleDriveClient, GoogleSheetsClient
from app.core.config import get_settings


class AnalysisTools:
    """Facade over external integrations needed during analysis."""

    def __init__(
        self,
        sheets_client: GoogleSheetsClient | None = None,
        drive_client: GoogleDriveClient | None = None,
    ) -> None:
        settings = get_settings()
        self._sheets = sheets_client or GoogleSheetsClient(settings.google)
        self._drive = drive_client or GoogleDriveClient(settings.google)

    async def read_trading_journal(self, *, sheet_id: str, range_: str | None = None) -> List[Dict[str, Any]]:
        """Fetch entries from the user's trading journal."""
        return await self._sheets.fetch_trades(sheet_id=sheet_id, range_=range_)

    async def transcribe_audio_assets(self, *, file_links: List[str]) -> List[Dict[str, Any]]:
        """Transcribe audio files referenced in the journal."""
        # Placeholder: integrate with Gemini audio transcription.
        raise NotImplementedError("Audio transcription tool not yet implemented.")

    async def analyze_trade_images(self, *, file_links: List[str]) -> List[Dict[str, Any]]:
        """Analyze screenshots using Gemini Vision."""
        raise NotImplementedError("Image analysis tool not yet implemented.")

    async def perform_web_research(self, *, query: str) -> List[Dict[str, Any]]:
        """Call Google web search for supplemental research."""
        raise NotImplementedError("Web research tool not yet implemented.")


__all__ = ["AnalysisTools"]
