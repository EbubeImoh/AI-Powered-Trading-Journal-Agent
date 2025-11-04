"""Conversational helper for crafting Telegram responses."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Iterable

from app.clients.gemini import GeminiClient, GeminiModelError
from app.services.trade_capture import TradeCaptureSession
from app.schemas import TradeSubmissionResult


class TelegramConversationalAssistant:
    """Generate natural language replies for Telegram trade capture sessions."""

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini = gemini_client

    async def compose_reply(
        self,
        *,
        user_message: str,
        session: TradeCaptureSession | None,
        result: TradeSubmissionResult,
        inferred_fields: dict[str, object] | None = None,
    ) -> str:
        """Ask Gemini to craft a conversational reply.

        When Gemini is unavailable, raises ``GeminiModelError`` so callers can
        decide on the appropriate fallback message.
        """

        prompt = self._build_prompt(
            user_message=user_message,
            session=session,
            result=result,
            inferred_fields=inferred_fields or {},
        )
        response = await self._gemini.generate_text(prompt)
        return response.strip() if response else self._fallback_response(result)

    def _build_prompt(
        self,
        *,
        user_message: str,
        session: TradeCaptureSession | None,
        result: TradeSubmissionResult,
        inferred_fields: dict[str, object],
    ) -> str:
        history = session.conversation if session else []
        known = {k: v for k, v in (result.trade.dict() if result.trade else {}).items() if v is not None}
        if inferred_fields:
            known.update({k: v for k, v in inferred_fields.items() if v})

        missing = result.missing_fields

        system_prompt = dedent(
            """
            You are a friendly Telegram trading journal assistant. Maintain a
            concise, supportive tone while guiding the trader to provide any
            missing information required to log the trade. Incorporate new
            details the trader confirms, acknowledge changes, and avoid repeating
            the same question verbatim when the user declines to answer.

            Requirements:
            - Never mention internal schemas or JSON structures to the user.
            - Ask for one missing field at a time, while reminding them of any
              other outstanding items gently.
            - If the trade is fully captured (no missing fields) respond with a
              short celebratory summary and next steps.
            - If the user says they do not want to provide a field, acknowledge
              that and move on.
            - Keep replies under 3 short paragraphs.
            - Use the conversation history to avoid repeating yourself and to
              maintain context.
            """
        ).strip()

        payload = {
            "known_fields": known,
            "missing_fields": missing,
            "history": history,
            "latest_user_message": user_message,
            "trade_status": result.status,
            "ingestion_summary": result.summary,
        }

        return f"{system_prompt}\nContext:\n{json.dumps(payload, default=str)}"

    @staticmethod
    def _fallback_response(result: TradeSubmissionResult) -> str:
        if result.status == "completed":
            return result.summary or (
                "✅ Trade captured! I'll keep an eye out for your next update."
            )
        return "I'm still listening—let me know the remaining details when you're ready."


__all__ = ["TelegramConversationalAssistant", "GeminiModelError"]
