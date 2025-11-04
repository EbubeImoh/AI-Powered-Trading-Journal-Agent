"""Client wrapper for interacting with Google Gemini models."""

from __future__ import annotations

import asyncio
import json
from textwrap import dedent
from typing import Any, Iterable

import google.generativeai as genai
from google.api_core.exceptions import GoogleAPICallError, NotFound

from app.core.config import GeminiSettings


class GeminiModelError(RuntimeError):
    """Raised when Gemini cannot fulfill a request due to configuration issues."""


class GeminiClient:
    """Provide helper methods for reasoning, vision, and research tasks."""

    def __init__(self, settings: GeminiSettings) -> None:
        self._settings = settings
        # Configure the global client once per process.
        genai.configure(api_key=settings.api_key)

    async def generate_trade_analysis(
        self,
        *,
        system_prompt: str,
        job_prompt: str,
        trades: list[dict[str, Any]],
        audio_insights: list[dict[str, Any]] | None = None,
        image_insights: list[dict[str, Any]] | None = None,
        web_research: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Call Gemini text model to synthesize a holistic trade analysis."""

        def _invoke() -> str:
            model = genai.GenerativeModel(self._settings.model_name)
            content = _build_analysis_prompt(
                system_prompt=system_prompt,
                job_prompt=job_prompt,
                trades=trades,
                audio_insights=audio_insights or [],
                image_insights=image_insights or [],
                web_research=web_research or [],
            )
            try:
                response = model.generate_content(content, safety_settings=[])
            except NotFound as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    "Gemini model '"
                    f"{self._settings.model_name}"
                    "' is not available. Update GEMINI_MODEL_NAME to a supported value."
                ) from exc
            except GoogleAPICallError as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    f"Gemini generate_content failed: {exc.message}"
                ) from exc
            return response.text or ""

        raw = await asyncio.to_thread(_invoke)
        return _parse_json_response(raw)

    async def vision_insights(
        self,
        *,
        prompt: str,
        image_base64: str,
        mime_type: str = "image/png",
    ) -> dict[str, Any]:
        """Generate insights about an image by invoking the Gemini vision model."""

        def _invoke() -> str:
            model = genai.GenerativeModel(self._settings.vision_model_name)
            try:
                response = model.generate_content(
                    [
                        prompt,
                        {
                            "mime_type": mime_type,
                            "data": image_base64,
                        },
                    ],
                    safety_settings=[],
                )
            except NotFound as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    "Gemini vision model '"
                    f"{self._settings.vision_model_name}"
                    "' is not available. Update GEMINI_VISION_MODEL_NAME to a supported value."
                ) from exc
            except GoogleAPICallError as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    f"Gemini vision generate_content failed: {exc.message}"
                ) from exc
            return response.text or ""

        raw = await asyncio.to_thread(_invoke)
        return _parse_json_response(raw)

    async def transcribe_audio(
        self,
        *,
        prompt: str,
        audio_base64: str,
        mime_type: str,
    ) -> dict[str, Any]:
        """Invoke Gemini to transcribe an audio clip."""

        def _invoke() -> str:
            model = genai.GenerativeModel(self._settings.model_name)
            try:
                response = model.generate_content(
                    [
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {"mime_type": mime_type, "data": audio_base64},
                            ],
                        }
                    ],
                    safety_settings=[],
                )
            except NotFound as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    "Gemini model '"
                    f"{self._settings.model_name}"
                    "' is not available. Update GEMINI_MODEL_NAME to a supported value."
                ) from exc
            except GoogleAPICallError as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    f"Gemini audio generate_content failed: {exc.message}"
                ) from exc
            return response.text or ""

        raw = await asyncio.to_thread(_invoke)
        return _parse_json_response(raw)

    async def extract_trade_details(
        self,
        *,
        content: str,
        attachment_metadata: list[dict[str, str]] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Request structured trade details from a free-form description."""

        attachments_section = json.dumps(attachment_metadata or [])
        overrides_section = json.dumps(overrides or {})

        def _invoke() -> str:
            model = genai.GenerativeModel(self._settings.model_name)
            prompt = dedent(
                (
                    "You are a trading journal assistant. Analyse the user's "
                    "description and return JSON with keys: ticker (string), "
                    "pnl (number), "
                    "position_type (string), entry_timestamp (ISO8601 string), "
                    "exit_timestamp (ISO8601 string), notes (string).\n"
                    "Use attachment metadata when relevant: "
                    f"{attachments_section}\n"
                    "Prefer using explicit overrides when provided: "
                    f"{overrides_section}\n"
                    "User submission:\n"
                    f"{content}"
                )
            )
            try:
                response = model.generate_content(
                    [
                        {
                            "role": "user",
                            "parts": [prompt],
                        }
                    ],
                    safety_settings=[],
                )
            except NotFound as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    "Gemini model '"
                    f"{self._settings.model_name}"
                    "' is not available. Update GEMINI_MODEL_NAME to a supported value."
                ) from exc
            except GoogleAPICallError as exc:  # pragma: no cover - network call
                raise GeminiModelError(
                    f"Gemini text generate_content failed: {exc.message}"
                ) from exc
            return response.text or ""

        raw = await asyncio.to_thread(_invoke)
        return _parse_json_response(raw)


def _truncate(value: Any, max_len: int = 4000) -> Any:
    """Best-effort truncate long strings to keep prompt sizes manageable."""
    if isinstance(value, str) and len(value) > max_len:
        return value[: max_len - 3] + "..."
    return value


def _flatten_dicts(dicts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened = []
    for item in dicts:
        flattened.append({key: _truncate(val) for key, val in item.items()})
    return flattened


def _build_analysis_prompt(
    *,
    system_prompt: str,
    job_prompt: str,
    trades: list[dict[str, Any]],
    audio_insights: list[dict[str, Any]],
    image_insights: list[dict[str, Any]],
    web_research: list[dict[str, Any]],
) -> list[str | dict[str, Any]]:
    """Construct a structured prompt for the Gemini model."""
    header = dedent(
        (
            "System Instructions:\n"
            f"{system_prompt}\n\n"
            "User Request:\n"
            f"{job_prompt}\n\n"
            "Incorporate the following data sources to produce a structured coaching "
            "report. Use bullet points, call out recurring behaviours, and end with "
            "2-3 prioritized action items.\n"
        )
    )

    sections: list[str | dict[str, Any]] = [header]
    sections.append(
        {
            "role": "user",
            "parts": ["Journal Entries", json.dumps(_flatten_dicts(trades))],
        }
    )

    if audio_insights:
        sections.append(
            {
                "role": "user",
                "parts": [
                    "Audio Sentiment",
                    json.dumps(_flatten_dicts(audio_insights)),
                ],
            }
        )
    if image_insights:
        sections.append(
            {
                "role": "user",
                "parts": [
                    "Chart Reviews",
                    json.dumps(_flatten_dicts(image_insights)),
                ],
            }
        )
    if web_research:
        sections.append(
            {
                "role": "user",
                "parts": [
                    "Research",
                    json.dumps(_flatten_dicts(web_research)),
                ],
            }
        )

    sections.append(
        {
            "role": "user",
            "parts": [
                (
                    "Respond strictly in JSON with the schema: {"
                    '"performance_overview": {"summary": string, '
                    '"key_metrics": [string]}, '
                    '"behavioural_patterns": [string], '
                    '"opportunities": [string], '
                    '"action_plan": [{"title": string, "detail": string}]}. '
                    "Do not include prose outside the JSON object."
                ),
            ],
        }
    )
    return sections


def _parse_json_response(payload: str) -> Any:
    payload = payload.strip()
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}


__all__ = ["GeminiClient"]
