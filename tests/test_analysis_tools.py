try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover - fallback for direct execution
    import _bootstrap  # type: ignore # noqa: F401

import asyncio

import pytest

from agents.analysis_lambda.tools import AnalysisTools, _extract_links_from_trade


class StubDriveClient:
    def __init__(self, metadata: dict[str, dict], binaries: dict[str, bytes]) -> None:
        self._metadata = metadata
        self._binaries = binaries

    async def get_file_metadata(self, *, user_id: str, file_id: str) -> dict:
        return self._metadata[file_id]

    async def download_file_bytes(self, *, user_id: str, file_id: str) -> bytes:
        return self._binaries[file_id]


class StubSheetsClient:
    async def fetch_trades(self, **_: str) -> list[dict]:
        return []


class StubGeminiClient:
    def __init__(self) -> None:
        self.audio_prompts: list[str] = []
        self.vision_prompts: list[str] = []

    async def transcribe_audio(self, *, prompt: str, audio_base64: str, mime_type: str) -> str:
        self.audio_prompts.append(prompt)
        assert audio_base64  # base64 payload provided
        return "{\"transcript\": \"Sample\", \"sentiment\": \"positive\"}"

    async def vision_insights(self, *, prompt: str, image_base64: str, mime_type: str) -> str:
        self.vision_prompts.append(prompt)
        assert image_base64
        return "{\"summary\": \"Looks good\"}"

    async def generate_trade_analysis(self, **_: str) -> str:
        return "analysis"


class StubWebSearchClient:
    async def search(self, query: str):
        return [{"title": "Result", "link": "https://example.com", "snippet": query}]


def test_extract_links_parses_modern_format() -> None:
    trade = {
        "file_links": "abc123|image/png|https://drive.google.com/file/d/abc123/view; def456|audio/mp4|https://drive.google.com/file/d/def456/view",
    }

    links = _extract_links_from_trade(trade)
    assert len(links) == 2
    assert links[0]["file_id"] == "abc123"
    assert links[0]["mime_type"] == "image/png"
    assert links[1]["mime_type"] == "audio/mp4"


def test_extract_links_parses_legacy_links() -> None:
    trade = {
        "Attachments": "https://drive.google.com/file/d/xyz890/view",
    }

    links = _extract_links_from_trade(trade)
    assert len(links) == 1
    assert links[0]["file_id"] == "xyz890"


@pytest.mark.asyncio
async def test_collect_assets_and_transcribe_and_analyze() -> None:
    trades = [
        {
            "file_links": "audio123|audio/mp4|https://drive/audio; image456|image/png|https://drive/image",
            "ticker": "AAPL",
            "pnl": 150.0,
        }
    ]

    drive = StubDriveClient(
        metadata={
            "audio123": {
                "id": "audio123",
                "mimeType": "audio/mp4",
                "webViewLink": "https://drive/audio",
                "name": "voice-note.m4a",
            },
            "image456": {
                "id": "image456",
                "mimeType": "image/png",
                "webViewLink": "https://drive/image",
                "name": "chart.png",
            },
        },
        binaries={
            "audio123": b"audio-bytes",
            "image456": b"image-bytes",
        },
    )
    gemini = StubGeminiClient()
    tools = AnalysisTools(
        sheets_client=StubSheetsClient(),
        drive_client=drive,
        gemini_client=gemini,
        web_search_client=StubWebSearchClient(),
    )

    assets = await tools.collect_assets(user_id="user", trades=trades)
    assert len(assets) == 2

    audio_assets = [asset for asset in assets if asset["mime_type"].startswith("audio/")]
    image_assets = [asset for asset in assets if asset["mime_type"].startswith("image/")]

    transcripts = await tools.transcribe_audio_assets(user_id="user", assets=audio_assets)
    assert transcripts and transcripts[0]["transcript"]["transcript"] == "Sample"

    insights = await tools.analyze_trade_images(user_id="user", assets=image_assets)
    assert insights and insights[0]["analysis"]["summary"] == "Looks good"

    research = await tools.perform_web_research(query="breakout strategy best practices")
    assert research and research[0]["title"] == "Result"
