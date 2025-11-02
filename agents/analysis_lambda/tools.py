"""Tool abstractions used by the analysis agent."""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict, List, Optional

from app.clients import (
    GeminiClient,
    GoogleDriveClient,
    GoogleSheetsClient,
    WebSearchClient,
)


class AnalysisTools:
    """Facade over external integrations needed during analysis."""

    def __init__(
        self,
        sheets_client: GoogleSheetsClient,
        drive_client: GoogleDriveClient,
        gemini_client: GeminiClient,
        web_search_client: WebSearchClient | None = None,
    ) -> None:
        self._sheets = sheets_client
        self._drive = drive_client
        self._gemini = gemini_client
        self._web_search = web_search_client

    async def read_trading_journal(
        self,
        *,
        user_id: str,
        sheet_id: str,
        range_: str,
    ) -> List[Dict[str, Any]]:
        """Fetch entries from the user's trading journal."""
        return await self._sheets.fetch_trades(
            user_id=user_id, sheet_id=sheet_id, range_=range_
        )

    async def collect_assets(
        self,
        *,
        user_id: str,
        trades: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Gather Drive asset metadata referenced by journal entries."""
        assets: List[Dict[str, Any]] = []
        for trade in trades:
            links = _extract_links_from_trade(trade)
            if not links:
                continue
            trade_context = {
                "ticker": trade.get("ticker") or trade.get("Ticker"),
                "pnl": trade.get("pnl") or trade.get("PnL"),
                "entry_timestamp": trade.get("entry_timestamp")
                or trade.get("Entry Timestamp"),
                "exit_timestamp": trade.get("exit_timestamp")
                or trade.get("Exit Timestamp"),
                "notes": trade.get("notes") or trade.get("Notes"),
            }
            for link in links:
                file_id = link["file_id"]
                if not file_id:
                    continue
                try:
                    metadata = await self._drive.get_file_metadata(
                        user_id=user_id, file_id=file_id
                    )
                except Exception:  # pragma: no cover - network defensive path
                    continue
                assets.append(
                    {
                        "file_id": metadata.get("id", file_id),
                        "mime_type": metadata.get("mimeType") or link.get("mime_type"),
                        "link": metadata.get("webViewLink") or link.get("url"),
                        "name": metadata.get("name"),
                        "trade": trade_context,
                    }
                )
        return assets

    async def transcribe_audio_assets(
        self,
        *,
        user_id: str,
        assets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Transcribe audio files referenced in the journal."""
        transcripts: List[Dict[str, Any]] = []
        for asset in assets:
            raw = await self._drive.download_file_bytes(
                user_id=user_id, file_id=asset["file_id"]
            )
            audio_b64 = base64.b64encode(raw).decode("utf-8")
            transcript = await self._gemini.transcribe_audio(
                prompt=(
                    "Transcribe the trader's voice note and summarize sentiment "
                    "(positive/negative/neutral). Return JSON with keys transcript, "
                    "sentiment, highlights."
                ),
                audio_base64=audio_b64,
                mime_type=asset.get("mime_type", "audio/mp4"),
            )
            transcripts.append(
                {
                    "file_id": asset["file_id"],
                    "link": asset.get("link"),
                    "name": asset.get("name"),
                    "trade": asset.get("trade"),
                    "transcript": _ensure_dict(transcript),
                }
            )
        return transcripts

    async def analyze_trade_images(
        self,
        *,
        user_id: str,
        assets: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Analyze screenshots using Gemini Vision."""
        insights: List[Dict[str, Any]] = []
        for asset in assets:
            raw = await self._drive.download_file_bytes(
                user_id=user_id, file_id=asset["file_id"]
            )
            image_b64 = base64.b64encode(raw).decode("utf-8")
            analysis = await self._gemini.vision_insights(
                prompt=(
                    "Review the trading chart. Comment on setup quality, entry timing, "
                    "and risk management. Provide JSON with keys summary, risks, "
                    "opportunities."
                ),
                image_base64=image_b64,
                mime_type=asset.get("mime_type", "image/png"),
            )
            insights.append(
                {
                    "file_id": asset["file_id"],
                    "link": asset.get("link"),
                    "name": asset.get("name"),
                    "trade": asset.get("trade"),
                    "analysis": _ensure_dict(analysis),
                }
            )
        return insights

    async def perform_web_research(self, *, query: str) -> List[Dict[str, Any]]:
        """Call external search provider for supplemental research."""
        if not self._web_search:
            return []
        normalized_query = query.strip()
        if not normalized_query:
            return []
        return await self._web_search.search(normalized_query)

    async def synthesize_report(
        self,
        *,
        job_prompt: str,
        trades: List[Dict[str, Any]],
        audio_insights: List[Dict[str, Any]],
        image_insights: List[Dict[str, Any]],
        web_research: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a coaching report using Gemini."""
        system_prompt = (
            "You are an elite trading performance coach. Blend quantitative trade "
            "metrics with behavioural observations."
        )

        report = await self._gemini.generate_trade_analysis(
            system_prompt=system_prompt,
            job_prompt=job_prompt,
            trades=trades,
            audio_insights=audio_insights,
            image_insights=image_insights,
            web_research=web_research,
        )
        return _ensure_dict(report)


def _extract_links_from_trade(trade: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    candidate_keys = [
        "file_links",
        "attachments",
        "files",
        "File Links",
        "Attachments",
    ]
    raw_value = None
    for key in candidate_keys:
        value = trade.get(key)
        if value:
            raw_value = value
            break

    if not raw_value:
        return []

    parts = [
        segment.strip()
        for segment in re.split(r"[,;]", str(raw_value))
        if segment.strip()
    ]
    parsed: List[Dict[str, Optional[str]]] = []
    for entry in parts:
        file_id: Optional[str]
        mime_type: Optional[str]
        url: str
        components = entry.split("|")
        if len(components) == 3:
            file_id, mime_type, url = components
        elif len(components) == 2:
            file_id, url = components
            mime_type = None
        else:
            file_id = _derive_file_id_from_url(entry)
            mime_type = None
            url = entry
        parsed.append({"file_id": file_id, "mime_type": mime_type, "url": url})
    return parsed


def _derive_file_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/file/d/([^/]+)/", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([^&]+)", url)
    if match:
        return match.group(1)
    return None


def _ensure_dict(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            value = json.loads(payload)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        return {"raw": payload}
    return {"raw": payload}


__all__ = ["AnalysisTools"]
