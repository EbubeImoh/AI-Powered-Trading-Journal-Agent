"""
FastAPI routes for the trading journal agent.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.clients.google_auth import OAuthTokenExchangeError, OAuthTokenNotFoundError
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
)
from app.schemas import (
    AnalysisRequest,
    OAuthCallbackPayload,
    TelegramUpdate,
    TradeIngestionRequest,
    TradeIngestionResponse,
    TradeSubmissionRequest,
    TradeSubmissionResult,
)

router = APIRouter()


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

    structured_defaults = session.structured if session else {}
    if session:
        history_lines = [*session.conversation, payload.content]
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
    settings: Annotated[Any, Depends(get_app_settings)],
    token: str | None = Query(None, description="Bot token for verification."),
) -> dict:
    """Handle incoming Telegram messages and drive trade capture."""

    message = update.message
    if not message or not message.text:
        return {"status": "ignored"}

    chat_id = message.chat.get("id")
    user_id = str(chat_id)
    text = message.text.strip()

    expected_token = getattr(settings, "telegram_bot_token", None)
    if expected_token and token != expected_token:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Invalid token")

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

    sheet_id = getattr(settings, "telegram_default_sheet_id", None)
    if not sheet_id:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Telegram sheet configuration missing.",
        )

    active_session = capture_store.get_active_for_user(user_id)
    session_id = active_session.session_id if active_session else None

    submission = TradeSubmissionRequest(
        user_id=user_id,
        content=message.text,
        session_id=session_id,
    )

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

    reply_text = result.prompt if result.status == "needs_more_info" else result.summary

    response_text = reply_text or (
        "✅ Trade captured! I'll keep an eye out for your next update."
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
