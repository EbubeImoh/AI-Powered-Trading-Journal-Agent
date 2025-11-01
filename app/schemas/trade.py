"""
Pydantic models for trade ingestion and analysis requests.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class TradeFileLink(BaseModel):
    """Represents a file uploaded to Google Drive."""

    drive_file_id: str = Field(..., description="The unique identifier of the file.")
    shareable_link: HttpUrl = Field(
        ..., description="Public or permissioned link to access the file."
    )
    mime_type: str = Field(..., description="MIME type describing the file.")


class TradeIngestionRequest(BaseModel):
    """Incoming payload for logging a trade."""

    user_id: str = Field(..., description="Application-level identifier for the trader.")
    ticker: str = Field(..., min_length=1, max_length=12)
    pnl: float = Field(..., description="Profit or loss for the trade in account currency.")
    position_type: str = Field(
        ...,
        description="Categorization of the position (e.g., long, short, options).",
    )
    entry_timestamp: datetime = Field(...)
    exit_timestamp: datetime = Field(...)
    notes: Optional[str] = Field(
        None,
        description="Free-form text commentary supplied by the trader.",
    )
    image_file_b64: Optional[str] = Field(
        None,
        description="Base64 encoded image of the trade setup chart.",
    )
    audio_file_b64: Optional[str] = Field(
        None,
        description="Base64 encoded voice note describing the trade.",
    )


class TradeIngestionResponse(BaseModel):
    """Response payload returned after logging a trade."""

    sheet_row_id: str = Field(..., description="Identifier of the inserted sheet row.")
    uploaded_files: list[TradeFileLink] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    """Payload to request an asynchronous analysis job."""

    user_id: str = Field(..., description="The trader requesting analysis.")
    sheet_id: str = Field(..., description="Google Sheet identifier containing journal entries.")
    prompt: str = Field(..., description="The question or scope for the analysis job.")
    start_date: Optional[datetime] = Field(
        None, description="Optional window start for historical data consideration."
    )
    end_date: Optional[datetime] = Field(
        None, description="Optional window end for historical data consideration."
    )


class AnalysisJobStatus(BaseModel):
    """Represents the state of an analysis job stored in DynamoDB."""

    job_id: str
    user_id: str
    status: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    result_location: Optional[HttpUrl] = None


__all__ = [
    "AnalysisJobStatus",
    "AnalysisRequest",
    "TradeFileLink",
    "TradeIngestionRequest",
    "TradeIngestionResponse",
]
