"""
FastAPI routes for the trading journal agent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.google_auth import OAuthTokenExchangeError, OAuthTokenNotFoundError
from app.dependencies import (
    get_analysis_queue_service,
    get_app_settings,
    get_dynamodb_client,
    get_google_oauth_client,
    get_google_token_service,
    get_oauth_state_encoder,
    get_token_cipher_service,
    get_trade_extraction_service,
    get_trade_ingestion_service,
)
from app.schemas import (
    AnalysisRequest,
    OAuthCallbackPayload,
    TradeIngestionRequest,
    TradeIngestionResponse,
    TradeSubmissionRequest,
)

router = APIRouter()


@router.get("/health", status_code=HTTPStatus.OK)
async def healthcheck() -> dict:
    """Simple health endpoint for monitoring."""
    return {"status": "ok"}


@router.get("/auth/google/authorize", status_code=HTTPStatus.OK)
async def start_google_oauth_flow(
    oauth_client: Annotated[Any, Depends(get_google_oauth_client)],
    state_encoder: Annotated[Any, Depends(get_oauth_state_encoder)],
    user_id: str = Query(..., description="User identifier initiating authentication."),
    redirect_to: str | None = Query(
        default=None,
        description="Optional URL to redirect back to on successful authentication.",
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
    return {"authorization_url": authorization_url, "state": state}


@router.post("/auth/google/callback", status_code=HTTPStatus.OK)
async def handle_google_oauth_callback(
    payload: OAuthCallbackPayload,
    oauth_client: Annotated[Any, Depends(get_google_oauth_client)],
    state_encoder: Annotated[Any, Depends(get_oauth_state_encoder)],
    dynamodb_client: Annotated[Any, Depends(get_dynamodb_client)],
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
    dynamodb_client.put_item(token_record)

    return {
        "status": "connected",
        "redirect_to": state_data.get("redirect_to"),
    }


@router.post(
    "/trades", response_model=TradeIngestionResponse, status_code=HTTPStatus.CREATED
)
async def ingest_trade(
    payload: TradeIngestionRequest,
    service: Annotated[Any, Depends(get_trade_ingestion_service)],
    token_service: Annotated[Any, Depends(get_google_token_service)],
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
    response_model=TradeIngestionResponse,
    status_code=HTTPStatus.CREATED,
)
async def submit_trade(
    payload: TradeSubmissionRequest,
    extraction_service: Annotated[Any, Depends(get_trade_extraction_service)],
    ingestion_service: Annotated[Any, Depends(get_trade_ingestion_service)],
    token_service: Annotated[Any, Depends(get_google_token_service)],
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

    structured_request = await extraction_service.extract(payload)
    return await ingestion_service.ingest_trade(
        request=structured_request,
        sheet_id=sheet_id,
        sheet_range=sheet_range,
        attachments=payload.attachments,
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
    dynamodb_client: Annotated[Any, Depends(get_dynamodb_client)],
    user_id: str = Query(
        ..., description="User identifier associated with the job."
    ),
) -> dict:
    """Fetch the status of an analysis job from DynamoDB."""
    item = dynamodb_client.get_item(
        partition_key=f"user#{user_id}", sort_key=f"analysis#{job_id}"
    )
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found.")
    return item


__all__ = ["router"]
