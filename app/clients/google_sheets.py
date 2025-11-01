"""Google Sheets client wrapper for journaling rows."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, TYPE_CHECKING

from googleapiclient.discovery import build

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from app.services.google_tokens import GoogleTokenService


class GoogleSheetsClient:
    """Append and read rows in the user's trading journal sheet."""

    def __init__(self, token_service: "GoogleTokenService") -> None:
        self._token_service = token_service

    async def append_trade_row(
        self,
        *,
        user_id: str,
        sheet_id: str,
        row: List[Any],
        sheet_range: str | None = None,
    ) -> str:
        """Append a new row to the Google Sheet and return the updated range."""
        credentials = await self._token_service.get_credentials(user_id=user_id)

        def _execute_append() -> str:
            service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
            result = (
                service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=sheet_id,
                    range=sheet_range or "Sheet1!A1",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [row]},
                )
                .execute()
            )
            updates = result.get("updates", {})
            return updates.get("updatedRange") or updates.get("tableRange") or ""

        return await asyncio.to_thread(_execute_append)

    async def fetch_trades(
        self,
        *,
        user_id: str,
        sheet_id: str,
        range_: str,
    ) -> List[Dict[str, Any]]:
        """Fetch rows of trading data for analysis."""
        credentials = await self._token_service.get_credentials(user_id=user_id)

        def _execute_fetch() -> List[Dict[str, Any]]:
            service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
            response = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=sheet_id,
                    range=range_,
                    valueRenderOption="UNFORMATTED_VALUE",
                    majorDimension="ROWS",
                )
                .execute()
            )
            values = response.get("values", [])
            if not values:
                return []

            headers = values[0]
            rows = []
            for row_values in values[1:]:
                row_dict: Dict[str, Any] = {}
                for index, header in enumerate(headers):
                    if not header:
                        continue
                    if index < len(row_values):
                        row_dict[header] = row_values[index]
                    else:
                        row_dict[header] = None
                rows.append(row_dict)
            return rows

        return await asyncio.to_thread(_execute_fetch)


__all__ = ["GoogleSheetsClient"]
