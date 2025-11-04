"""
FastAPI routes for the trading journal agent.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.clients.google_auth import OAuthTokenExchangeError, OAuthTokenNotFoundError
from app.services.trade_capture import TradeCaptureSession
from app.services.telegram_conversation import (
    GeminiModelError,
    TelegramConversationalAssistant,
)
from app.dependencies import (
    get_analysis_queue_service,
    get_app_settings,
    get_google_oauth_client,
    get_google_token_service,
    get_oauth_state_encoder,
    get_sqlite_store,
    get_token_cipher_service,
    get_trade_capture_store,
    get_trade_extraction_service,
    get_trade_ingestion_service,
    get_telegram_conversation_assistant,
)
from app.schemas import (
    AnalysisRequest,
    OAuthCallbackPayload,
    TelegramUpdate,
    TradeAttachment,
    TradeIngestionRequest,
    TradeIngestionResponse,
    TradeSubmissionRequest,
    TradeSubmissionResult,
)

router = APIRouter()
logger = logging.getLogger(__name__)


_FIELD_PROMPTS = {
    "ticker": "Which ticker were you trading?",
    "pnl": "What was the profit or loss on the trade?",
    "position_type": "Was it a long, short, or another position type?",
    "entry_timestamp": "When did you enter the position?",
    "exit_timestamp": "When did you exit the position?",
}


@router.get("/health", status_code=HTTPStatus.OK)
async def healthcheck() -> dict:
    """Simple health endpoint for monitoring."""
    return {"status": "ok"}


@router.get("/auth/google/authorize", status_code=HTTPStatus.OK)
async def start_google_oauth_flow(
    request: Request,
    oauth_client: Annotated[Any, Depends(get_google_oauth_client)],
    state_encoder: Annotated[Any, Depends(get_oauth_state_encoder)],
    user_id: str = Query(..., description="User identifier initiating authentication."),
    redirect_to: str | None = Query(
        default=None,
        description="Optional URL to redirect back to on successful authentication.",
    ),
    redirect: bool = Query(
        default=False,
        description="When true, respond with a redirect to the Google consent screen.",
    ),
) -> dict:
    """
    Kick off the OAuth flow by generating a state token and authorization URL.
    """
    nonce = uuid.uuid4().hex
    state_payload = {
        "nonce": nonce,
        "redirect_to": redirect_to,
        "user_id": user_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    state = state_encoder.encode(state_payload)
    authorization_url = oauth_client.build_authorization_url(state=state)

    accept_header = request.headers.get("accept", "")
    wants_html = "text/html" in accept_header.lower()
    if redirect or wants_html:
        return RedirectResponse(url=authorization_url, status_code=HTTPStatus.TEMPORARY_REDIRECT)

    return {"authorization_url": authorization_url, "state": state}


@router.post("/auth/google/callback", status_code=HTTPStatus.OK)
async def handle_google_oauth_callback(
    payload: OAuthCallbackPayload,
    oauth_client: Annotated[Any, Depends(get_google_oauth_client)],
    state_encoder: Annotated[Any, Depends(get_oauth_state_encoder)],
    record_store: Annotated[Any, Depends(get_sqlite_store)],
    settings: Annotated[Any, Depends(get_app_settings)],
    token_cipher: Annotated[Any, Depends(get_token_cipher_service)],
) -> dict:
    """Complete the OAuth exchange, store tokens, and return redirect metadata."""
    state_data = state_encoder.decode(payload.state)

    issued_at_raw = state_data.get("issued_at")
    if not issued_at_raw:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Missing issued_at in state token.",
        )

    try:
        issued_at = datetime.fromisoformat(issued_at_raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Invalid issued_at in state token.",
        ) from exc

    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if now - issued_at > timedelta(seconds=settings.oauth.state_ttl_seconds):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="OAuth state token has expired."
        )

    user_id = state_data.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Missing user identifier in state token.",
        )

    try:
        (
            access_token,
            refresh_token,
            expires_in,
        ) = await oauth_client.exchange_authorization_code(payload.code)
    except OAuthTokenExchangeError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Failed to exchange authorization code.",
        ) from exc

    expires_at = now + timedelta(seconds=expires_in)
    token_record = {
        "pk": f"user#{user_id}",
        "sk": "oauth#google",
        "user_id": user_id,
        "provider": "google",
        "access_token_encrypted": token_cipher.encrypt(access_token),
        "refresh_token_encrypted": token_cipher.encrypt(refresh_token),
        "expires_at": expires_at.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    record_store.put_item(token_record)

    return {
        "status": "connected",
        "redirect_to": state_data.get("redirect_to"),
    }


@router.get("/auth/google/callback", status_code=HTTPStatus.OK)
async def handle_google_oauth_callback_get(
    request: Request,
    oauth_client: Annotated[Any, Depends(get_google_oauth_client)],
    state_encoder: Annotated[Any, Depends(get_oauth_state_encoder)],
    record_store: Annotated[Any, Depends(get_sqlite_store)],
    settings: Annotated[Any, Depends(get_app_settings)],
    token_cipher: Annotated[Any, Depends(get_token_cipher_service)],
    state: str = Query(..., description="OAuth state token."),
    code: str = Query(..., description="Authorization code returned by Google."),
    redirect: bool = Query(
        default=False,
        description="When true, redirect browser clients instead of returning JSON.",
    ),
) -> Response:
    payload = OAuthCallbackPayload(state=state, code=code)
    result = await handle_google_oauth_callback(
        payload=payload,
        oauth_client=oauth_client,
        state_encoder=state_encoder,
        record_store=record_store,
        settings=settings,
        token_cipher=token_cipher,
    )

    accept_header = request.headers.get("accept", "")
    wants_html = "text/html" in accept_header.lower()
    redirect_target = result.get("redirect_to") or settings.frontend_base_url

    if redirect_target and (redirect or wants_html):
        return RedirectResponse(url=str(redirect_target), status_code=HTTPStatus.TEMPORARY_REDIRECT)

    return JSONResponse(content=result)


@router.post(
    "/trades", response_model=TradeIngestionResponse, status_code=HTTPStatus.CREATED
)
async def ingest_trade(
    payload: TradeIngestionRequest,
    service: Annotated[Any, Depends(get_trade_ingestion_service)],
    token_service: Annotated[Any, Depends(get_google_token_service)],
    capture_store: Annotated[Any, Depends(get_trade_capture_store)],
    sheet_id: str = Query(
        ..., description="Google Sheet identifier for the trading journal."
    ),
    sheet_range: str | None = Query(
        default=None,
        description=(
            "Target range (e.g., 'Journal!A1') where new trades should be appended."
        ),
    ),
) -> TradeIngestionResponse:
    """Accept a trade payload and persist it to Google Drive and Sheets."""
    try:
        await token_service.get_credentials(user_id=payload.user_id)
    except OAuthTokenNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Google account not connected.",
        ) from exc

    return await service.ingest_trade(
        request=payload, sheet_id=sheet_id, sheet_range=sheet_range
    )


@router.post(
    "/trades/submit",
    response_model=TradeSubmissionResult,
)
async def submit_trade(
    payload: TradeSubmissionRequest,
    response: Response,
    extraction_service: Annotated[Any, Depends(get_trade_extraction_service)],
    ingestion_service: Annotated[Any, Depends(get_trade_ingestion_service)],
    token_service: Annotated[Any, Depends(get_google_token_service)],
    capture_store: Annotated[Any, Depends(get_trade_capture_store)],
    sheet_id: str = Query(
        ..., description="Google Sheet identifier for the trading journal."
    ),
    sheet_range: str | None = Query(
        default=None,
        description=(
            "Target range (e.g., 'Journal!A1') where new trades should be appended."
        ),
    ),
) -> TradeIngestionResponse:
    """Accept a raw user submission, structure it with Gemini, and persist it."""
    try:
        await token_service.get_credentials(user_id=payload.user_id)
    except OAuthTokenNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Google account not connected.",
        ) from exc

    session = None
    if payload.session_id:
        session = capture_store.get(payload.session_id)

    history_content = payload.content
    aggregated_attachments = list(payload.attachments)

    structured_defaults = dict(session.structured) if session else {}
    quick_updates: dict[str, Any] = {}
    if session:
        quick_updates = _absorb_user_reply(session, payload.content)
        if quick_updates:
            structured_defaults.update(quick_updates)
            payload = payload.copy(update=quick_updates)

    if session:
        history_lines = list(session.conversation)
        if quick_updates:
            acknowledgement = _format_acknowledgement(quick_updates)
            if acknowledgement:
                history_lines.append(acknowledgement)
        history_lines.append(payload.content)
        history_content = "\n".join(filter(None, history_lines))
        aggregated_attachments = [*session.attachments, *payload.attachments]

    # Build a composite submission that includes prior structured overrides.
    ticker = payload.ticker or structured_defaults.get("ticker")
    pnl = payload.pnl or structured_defaults.get("pnl")
    position_type = payload.position_type or structured_defaults.get("position_type")
    entry_ts = payload.entry_timestamp or structured_defaults.get("entry_timestamp")
    exit_ts = payload.exit_timestamp or structured_defaults.get("exit_timestamp")
    notes = payload.notes or structured_defaults.get("notes")

    combined_submission = TradeSubmissionRequest(
        user_id=payload.user_id,
        session_id=payload.session_id,
        content=history_content,
        attachments=aggregated_attachments,
        ticker=ticker,
        pnl=pnl,
        position_type=position_type,
        entry_timestamp=entry_ts,
        exit_timestamp=exit_ts,
        notes=notes,
    )

    extraction = await extraction_service.extract(combined_submission)

    if extraction.missing_fields:
        if session:
            updated_session = capture_store.update(
                session.session_id,
                message=payload.content,
                structured=extraction.structured,
                missing_fields=extraction.missing_fields,
                attachments=payload.attachments,
                trade=extraction.trade,
            )
            session_id = (
                updated_session.session_id
                if updated_session
                else session.session_id
            )
        else:
            session_obj = capture_store.create(
                user_id=payload.user_id,
                initial_message=payload.content,
                structured=extraction.structured,
                missing_fields=extraction.missing_fields,
                attachments=payload.attachments,
                trade=extraction.trade,
            )
            session_id = session_obj.session_id

        follow_up = _build_follow_up_prompt(
            extraction.missing_fields,
            extraction.structured,
        )

        response.status_code = HTTPStatus.ACCEPTED
        return TradeSubmissionResult(
            status="needs_more_info",
            session_id=session_id,
            missing_fields=extraction.missing_fields,
            prompt=follow_up,
            trade=extraction.trade,
        )

    # We have a fully structured trade; record it and close the session.
    ingestion_response = await ingestion_service.ingest_trade(
        request=extraction.trade,
        sheet_id=sheet_id,
        sheet_range=sheet_range,
        attachments=aggregated_attachments,
    )

    if session:
        capture_store.delete(session.session_id)

    response.status_code = HTTPStatus.CREATED
    return TradeSubmissionResult(
        status="completed",
        session_id=session.session_id if session else None,
        trade=extraction.trade,
        ingestion_response=ingestion_response,
        summary=_render_trade_summary(extraction.trade),
    )


@router.post("/analysis/jobs", status_code=HTTPStatus.ACCEPTED)
async def request_analysis_job(
    payload: AnalysisRequest,
    queue_service: Annotated[Any, Depends(get_analysis_queue_service)],
    token_service: Annotated[Any, Depends(get_google_token_service)],
) -> dict:
    """Enqueue an asynchronous analysis job."""
    try:
        await token_service.get_credentials(user_id=payload.user_id)
    except OAuthTokenNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Google account not connected.",
        ) from exc

    job_id = queue_service.enqueue_analysis(request=payload)
    return {"job_id": job_id, "status": "pending"}


@router.get("/analysis/jobs/{job_id}", status_code=HTTPStatus.OK)
async def get_analysis_job_status(
    job_id: str,
    record_store: Annotated[Any, Depends(get_sqlite_store)],
    user_id: str = Query(
        ..., description="User identifier associated with the job."
    ),
) -> dict:
    """Fetch the status of an analysis job from DynamoDB."""
    item = record_store.get_item(
        partition_key=f"user#{user_id}", sort_key=f"analysis#{job_id}"
    )
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found.")
    return item


@router.post("/integrations/telegram/webhook", status_code=HTTPStatus.OK)
async def telegram_webhook(
    request: Request,
    update: TelegramUpdate,
    extraction_service: Annotated[Any, Depends(get_trade_extraction_service)],
    ingestion_service: Annotated[Any, Depends(get_trade_ingestion_service)],
    token_service: Annotated[Any, Depends(get_google_token_service)],
    capture_store: Annotated[Any, Depends(get_trade_capture_store)],
    assistant: Annotated[
        TelegramConversationalAssistant, Depends(get_telegram_conversation_assistant)
    ],
    queue_service: Annotated[Any, Depends(get_analysis_queue_service)],
    record_store: Annotated[Any, Depends(get_sqlite_store)],
    settings: Annotated[Any, Depends(get_app_settings)],
    token: str | None = Query(None, description="Bot token for verification."),
) -> dict:
    """Handle incoming Telegram messages and drive trade capture."""

    message = update.message
    if not message:
        return {"status": "ignored"}

    message_dict = message.dict(exclude_none=True)
    chat_id = message.chat.get("id")
    user_id = str(chat_id)
    text = (message.text or getattr(message, "caption", "") or "").strip()
    has_media = any(
        key in message_dict for key in ("photo", "document", "voice", "audio", "video")
    )
    if not text and not has_media:
        return {"status": "ignored"}
    if not text:
        text = "(attachment)"

    expected_token = getattr(settings, "telegram_bot_token", None)
    if expected_token and token != expected_token:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Invalid token")

    sheet_id = getattr(settings, "telegram_default_sheet_id", None)
    if not sheet_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Telegram sheet configuration missing.",
        )

    if text.lower().startswith("/connect"):
        base_url = settings.telegram_connect_base_url
        if base_url:
            authorize_base = f"{str(base_url).rstrip('/')}/api/auth/google/authorize"
        else:
            authorize_base = str(request.url_for("start_google_oauth_flow"))
        connect_url = f"{authorize_base}?user_id={user_id}&redirect=1"
        reply_text = (
            "Tap to connect your Google account:\n"
            f"{connect_url}"
        )
        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": reply_text,
        }

    if text.lower().startswith("/analysis_status"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return {
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": "Usage: /analysis_status <job_id>",
            }
        job_id = parts[1].strip()
        item = record_store.get_item(
            partition_key=f"user#{user_id}", sort_key=f"analysis#{job_id}"
        )
        if not item:
            return {
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": f"I couldn't find an analysis job with ID {job_id}.",
            }
        status = item.get("status", "unknown")
        summary = item.get("summary") or item.get("report_markdown")
        message = f"Analysis job {job_id} status: {status.upper()}"
        if summary:
            message += f"\n\nSummary:\n{summary[:1000]}"
        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": message,
        }

    if text.lower().startswith("/analysis"):
        try:
            await token_service.get_credentials(user_id=user_id)
        except OAuthTokenNotFoundError as exc:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Google account not connected.",
            ) from exc

        prompt = text.partition(" ")[2].strip()
        if not prompt:
            prompt = "Provide a performance summary of my recent trades."

        analysis_request = AnalysisRequest(
            user_id=user_id,
            sheet_id=sheet_id,
            sheet_range=None,
            prompt=prompt,
        )
        job_id = queue_service.enqueue_analysis(request=analysis_request)
        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": (
                f"Analysis job queued with ID {job_id}. "
                "I'll keep an eye out for the results."
            ),
        }

    active_session = capture_store.get_active_for_user(user_id)
    session_id = active_session.session_id if active_session else None

    attachments, attachment_notes = await _collect_telegram_attachments(
        message_dict, expected_token
    )
    assistant_message = text
    if attachment_notes:
        notes_block = "\n".join(attachment_notes)
        assistant_message = f"{text}\n\nAttachments:\n{notes_block}"

    submission = TradeSubmissionRequest(
        user_id=user_id,
        content=assistant_message,
        session_id=session_id,
        attachments=attachments,
    )

    inferred_fields: dict[str, Any] = {}
    if active_session:
        inferred_fields = _absorb_user_reply(active_session, assistant_message)
        if inferred_fields:
            submission = submission.copy(update=inferred_fields)

    # TODO: lookup sheet configuration per Telegram chat / user mapping.
    try:
        result = await submit_trade(
            payload=submission,
            response=Response(),
            extraction_service=extraction_service,
            ingestion_service=ingestion_service,
            token_service=token_service,
            capture_store=capture_store,
            sheet_id=sheet_id,
        )
    except HTTPException as exc:
        if exc.status_code == HTTPStatus.UNAUTHORIZED:
            return {
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": (
                    "I can't access your Google account yet. "
                    "Send /connect to authorize me, then try again."
                ),
            }
        if exc.status_code == HTTPStatus.SERVICE_UNAVAILABLE:
            return {
                "method": "sendMessage",
                "chat_id": chat_id,
                "text": (
                    "Gemini is unavailable right now (model configuration issue). "
                    "Please check the GEMINI_MODEL_NAME setting or try again later."
                ),
            }
        raise

    session_for_reply = (
        capture_store.get(result.session_id) if result.session_id else None
    )

    try:
        response_text = await assistant.compose_reply(
            user_message=submission.content,
            session=session_for_reply,
            result=result,
            inferred_fields=inferred_fields,
        )
    except GeminiModelError:
        reply_text = (
            result.summary
            if result.status == "completed"
            else result.prompt
        )
        acknowledgement = _format_acknowledgement(inferred_fields)
        fallback_core = reply_text or (
            "Gemini is unavailable right now. We'll keep your details safe; try again soon."
        )
        response_text = (
            f"{acknowledgement}\n\n{fallback_core}".strip()
            if acknowledgement
            else fallback_core
        )

    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": response_text,
    }


def _build_follow_up_prompt(
    missing_fields: list[str], structured: dict[str, Any]
) -> str:
    context_parts: list[str] = []
    ticker = structured.get("ticker")
    if ticker:
        context_parts.append(f"ticker {ticker}")
    position = structured.get("position_type")
    if position:
        context_parts.append(position.lower())
    pnl = structured.get("pnl")
    if pnl is not None:
        context_parts.append(f"PnL {pnl}")

    if context_parts:
        context = "I have this so far: " + ", ".join(context_parts) + "."
    else:
        context = "Thanks for the details so far."

    if not missing_fields:
        return context

    next_field = missing_fields[0]
    primary_question = _FIELD_PROMPTS.get(
        next_field, f"Please share {next_field.replace('_', ' ')}."
    )

    if len(missing_fields) == 1:
        return f"{context} {primary_question}"

    remaining = [
        field.replace("_", " ") for field in missing_fields[1:]
    ]
    reminder = ", ".join(remaining)
    return (
        f"{context} {primary_question} When you can, also let me know: {reminder}."
    )


TELEGRAM_API_BASE = "https://api.telegram.org"


async def _collect_telegram_attachments(
    message: dict[str, Any], bot_token: str | None
) -> tuple[list[TradeAttachment], list[str]]:
    if not bot_token:
        return [], []

    has_media = any(
        key in message for key in ("photo", "document", "audio", "voice", "video")
    )
    if not has_media:
        return [], []

    attachments: list[TradeAttachment] = []
    notes: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if "photo" in message:
                photo = message["photo"][-1]
                await _append_file_attachment(
                    client,
                    bot_token,
                    file_id=photo["file_id"],
                    filename=f"photo_{photo.get('file_unique_id', photo['file_id'])}.jpg",
                    mime_type="image/jpeg",
                    note_prefix="Photo attached",
                    tags=["photo"],
                    attachments=attachments,
                    notes=notes,
                )

            document = message.get("document")
            if document:
                await _append_file_attachment(
                    client,
                    bot_token,
                    file_id=document["file_id"],
                    filename=document.get("file_name")
                    or f"document_{document.get('file_unique_id', document['file_id'])}",
                    mime_type=document.get("mime_type", "application/octet-stream"),
                    note_prefix="Document attached",
                    tags=["document"],
                    attachments=attachments,
                    notes=notes,
                )

            audio = message.get("audio")
            if audio:
                await _append_file_attachment(
                    client,
                    bot_token,
                    file_id=audio["file_id"],
                    filename=audio.get("file_name")
                    or f"audio_{audio.get('file_unique_id', audio['file_id'])}.mp3",
                    mime_type=audio.get("mime_type", "audio/mpeg"),
                    note_prefix="Audio attached",
                    tags=["audio"],
                    attachments=attachments,
                    notes=notes,
                )

            voice = message.get("voice")
            if voice:
                await _append_file_attachment(
                    client,
                    bot_token,
                    file_id=voice["file_id"],
                    filename=f"voice_{voice.get('file_unique_id', voice['file_id'])}.ogg",
                    mime_type=voice.get("mime_type", "audio/ogg"),
                    note_prefix="Voice note attached",
                    tags=["voice"],
                    attachments=attachments,
                    notes=notes,
                )

            video = message.get("video")
            if video:
                await _append_file_attachment(
                    client,
                    bot_token,
                    file_id=video["file_id"],
                    filename=video.get("file_name")
                    or f"video_{video.get('file_unique_id', video['file_id'])}.mp4",
                    mime_type=video.get("mime_type", "video/mp4"),
                    note_prefix="Video attached",
                    tags=["video"],
                    attachments=attachments,
                    notes=notes,
                )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to process Telegram attachments: %s", exc)

    return attachments, notes


async def _append_file_attachment(
    client: httpx.AsyncClient,
    bot_token: str,
    file_id: str,
    filename: str,
    mime_type: str,
    note_prefix: str,
    tags: list[str],
    attachments: list[TradeAttachment],
    notes: list[str],
) -> None:
    try:
        file_path = await _telegram_get_file_path(client, bot_token, file_id)
        content = await _telegram_download_file(client, bot_token, file_path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to download Telegram file %s: %s", file_id, exc)
        return

    file_b64 = base64.b64encode(content).decode("utf-8")
    attachments.append(
        TradeAttachment(
            filename=filename,
            mime_type=mime_type,
            file_b64=file_b64,
            tags=tags,
        )
    )
    notes.append(f"{note_prefix}: {filename}")


async def _telegram_get_file_path(
    client: httpx.AsyncClient, bot_token: str, file_id: str
) -> str:
    resp = await client.get(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/getFile",
        params={"file_id": file_id},
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("ok") or "result" not in payload:
        raise RuntimeError("Telegram getFile response was not OK")
    return payload["result"]["file_path"]


async def _telegram_download_file(
    client: httpx.AsyncClient, bot_token: str, file_path: str
) -> bytes:
    resp = await client.get(
        f"{TELEGRAM_API_BASE}/file/bot{bot_token}/{file_path}"
    )
    resp.raise_for_status()
    return resp.content


def _format_acknowledgement(fields: dict[str, Any]) -> str:
    if not fields:
        return ""

    phrases: list[str] = []
    for key, value in fields.items():
        if value is None:
            if key == "ticker":
                phrases.append("No worries, we'll grab the ticker next")
            elif key == "pnl":
                phrases.append("I'll wait for the PnL when you're ready")
            elif key in {"entry_timestamp", "exit_timestamp"}:
                phrases.append(f"Still awaiting the {key.replace('_', ' ')}")
            continue

        if key == "ticker":
            phrases.append(f"Ticker noted as {value}")
        elif key == "pnl":
            phrases.append(f"PnL logged as {value}")
        elif key == "position_type":
            phrases.append(f"Position type set to {value}")
        elif key in {"entry_timestamp", "exit_timestamp"}:
            when = value.isoformat() if isinstance(value, datetime) else str(value)
            phrases.append(f"{key.replace('_', ' ').title()} recorded as {when}")
        elif key == "notes":
            phrases.append("Added that to your notes")

    if not phrases:
        return ""

    if any(value is not None for value in fields.values()):
        return "Got it — " + "; ".join(phrases)
    return "; ".join(phrases)


def _absorb_user_reply(
    session: TradeCaptureSession, message_text: str
) -> dict[str, Any]:
    pending = session.missing_fields
    text = message_text.strip()
    if not pending or not text:
        return {}

    if text.startswith("/") or text.startswith("!"):
        return {}

    updates: dict[str, Any] = {}
    lower = text.lower()

    negation_present = bool(
        re.search(r"\b(no|not|isn't|ain't|never|nah|nope)\b", lower)
    )

    entry_keywords = {"entry", "entered", "open"}
    exit_keywords = {"exit", "exited", "close", "closed"}

    mentions_entry = any(word in lower for word in entry_keywords)
    mentions_exit = any(word in lower for word in exit_keywords)

    if "position_type" in pending:
        for keyword in ("long", "short", "call", "put"):
            if keyword in lower:
                updates.setdefault("position_type", keyword)
                break

    if "pnl" in pending:
        pnl_match = re.search(r"([-+]?[\d,]+(?:\.\d+)?)", text)
        if pnl_match:
            try:
                updates["pnl"] = float(pnl_match.group(1).replace(",", ""))
            except ValueError:
                pass

    if "entry_timestamp" in pending or "exit_timestamp" in pending:
        parsed_dt = _parse_datetime_expression(text)
        if parsed_dt:
            if mentions_exit and "exit_timestamp" in pending:
                updates.setdefault("exit_timestamp", parsed_dt)
            elif mentions_entry and "entry_timestamp" in pending:
                updates.setdefault("entry_timestamp", parsed_dt)
            else:
                for field in ("entry_timestamp", "exit_timestamp"):
                    if field in pending and field not in updates:
                        updates[field] = parsed_dt
                        break

    if "ticker" in pending:
        if ("ticker" in lower or "symbol" in lower) and negation_present:
            updates.setdefault("ticker", None)
        else:
            ticker = _extract_ticker_candidate(text)
            if ticker:
                updates.setdefault("ticker", ticker)

    if "notes" in pending and text:
        updates.setdefault("notes", text)

    return updates


def _extract_ticker_candidate(message_text: str) -> str | None:
    tokens = re.findall(r"[A-Za-z]{2,10}", message_text)
    stop_words = {
        "THE",
        "WITH",
        "LONG",
        "SHORT",
        "ENTRY",
        "EXIT",
        "LOSS",
        "GAIN",
        "PROFIT",
        "AM",
        "TRADING",
        "TRADED",
        "TRADE",
        "PAIR",
        "MADE",
        "LOST",
        "BOUGHT",
        "SOLD",
        "IT",
        "WAS",
        "POSITION",
        "START",
        "TICKER",
        "HELLO",
        "THANKS",
        "THANK",
        "PLEASE",
        "NO",
        "NOT",
    }
    for token in reversed(tokens):
        candidate = token.upper()
        if candidate not in stop_words:
            return candidate
    return None


def _parse_datetime_expression(message_text: str) -> datetime | None:
    # ISO-like pattern first
    iso_match = re.search(
        r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?(?:Z|[+-]\d{2}:\d{2})?\b",
        message_text,
    )
    if iso_match:
        candidate = iso_match.group(0).replace(" ", "T")
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None

    time_match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        message_text,
        flags=re.IGNORECASE,
    )
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        meridiem = time_match.group(3).lower()
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12
        now = datetime.now(timezone.utc)
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return None


def _render_trade_summary(trade: TradeIngestionRequest) -> str:
    entry = trade.entry_timestamp.strftime("%Y-%m-%d %H:%M")
    exit_time = trade.exit_timestamp.strftime("%Y-%m-%d %H:%M")
    notes = trade.notes or "No additional notes."
    core = (
        f"Recorded {trade.position_type} {trade.ticker} trade from {entry} to "
        f"{exit_time} with PnL {trade.pnl}."
    )
    return f"{core} Notes: {notes}"


__all__ = ["router"]
