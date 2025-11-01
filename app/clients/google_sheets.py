"""
Google Sheets client wrapper for journaling rows.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.config import GoogleSettings


class GoogleSheetsClient:
    """Append and read rows in the user's trading journal sheet."""

    def __init__(self, settings: GoogleSettings) -> None:
        self._settings = settings

    async def append_trade_row(self, sheet_id: str, row: List[Any]) -> str:
        """
        Append a new row to the Google Sheet and return the row identifier.
        """
        raise NotImplementedError("Google Sheets integration not yet implemented.")

    async def fetch_trades(self, sheet_id: str, range_: str | None = None) -> List[Dict[str, Any]]:
        """Fetch rows of trading data for analysis."""
        raise NotImplementedError("Google Sheets integration not yet implemented.")


__all__ = ["GoogleSheetsClient"]
