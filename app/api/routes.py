"""
FastAPI routes for the trading journal agent.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import (
    get_analysis_queue_service,
    get_dynamodb_client,
    get_google_oauth_client,
    get_oauth_state_encoder,
    get_trade_ingestion_service,
)
from app.schemas import AnalysisRequest, TradeIngestionRequest, TradeIngestionResponse

router = APIRouter()


@router.get("/health", status_code=HTTPStatus.OK)
async def healthcheck() -> dict:
    """Simple health endpoint for monitoring."""
    return {"status": "ok"}


@router.get("/auth/google/authorize", status_code=HTTPStatus.OK)
async def start_google_oauth_flow(
    oauth_client=Depends(get_google_oauth_client),
    state_encoder=Depends(get_oauth_state_encoder),
    redirect_to: str | None = Query(
        default=None,
        description="Optional URL to redirect back to on successful authentication.",
    ),
) -> dict:
    """
    Kick off the OAuth flow by generating a state token and authorization URL.
    """
    nonce = uuid.uuid4().hex
    state_payload = {"nonce": nonce, "redirect_to": redirect_to}
    state = state_encoder.encode(state_payload)
    authorization_url = oauth_client.build_authorization_url(state=state)
    return {"authorization_url": authorization_url, "state": state}


@router.post("/auth/google/callback", status_code=HTTPStatus.ACCEPTED)
async def handle_google_oauth_callback() -> dict:
    """
    Endpoint placeholder for handling Google OAuth callback.

    The actual implementation will exchange the authorization code for tokens and
    store them in DynamoDB for asynchronous operations.
    """
    raise HTTPException(
        status_code=HTTPStatus.NOT_IMPLEMENTED,
        detail="OAuth callback handling not yet implemented.",
    )


@router.post("/trades", response_model=TradeIngestionResponse, status_code=HTTPStatus.CREATED)
async def ingest_trade(
    payload: TradeIngestionRequest,
    sheet_id: str = Query(..., description="Google Sheet identifier for the trading journal."),
    service=Depends(get_trade_ingestion_service),
) -> TradeIngestionResponse:
    """Accept a trade payload and persist it to Google Drive and Sheets."""
    return await service.ingest_trade(request=payload, sheet_id=sheet_id)


@router.post("/analysis/jobs", status_code=HTTPStatus.ACCEPTED)
async def request_analysis_job(
    payload: AnalysisRequest,
    queue_service=Depends(get_analysis_queue_service),
) -> dict:
    """Enqueue an asynchronous analysis job."""
    job_id = queue_service.enqueue_analysis(request=payload)
    return {"job_id": job_id, "status": "pending"}


@router.get("/analysis/jobs/{job_id}", status_code=HTTPStatus.OK)
async def get_analysis_job_status(
    job_id: str,
    user_id: str = Query(..., description="User identifier associated with the job."),
    dynamodb_client=Depends(get_dynamodb_client),
) -> dict:
    """Fetch the status of an analysis job from DynamoDB."""
    item = dynamodb_client.get_item(partition_key=f"user#{user_id}", sort_key=f"analysis#{job_id}")
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found.")
    return item


__all__ = ["router"]
