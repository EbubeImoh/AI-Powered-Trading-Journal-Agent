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

    user_id: str = Field(
        ..., description="Application-level identifier for the trader."
    )
    ticker: str = Field(..., min_length=1, max_length=12)
    pnl: float = Field(
        ..., description="Profit or loss for the trade in account currency."
    )
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


class TradeAttachment(BaseModel):
    """Represents a generic attachment supplied by the user."""

    filename: str = Field(..., description="Desired file name including extension.")
    mime_type: str = Field(
        ..., description="MIME type for the attachment (e.g., image/png)."
    )
    file_b64: str = Field(..., description="Base64-encoded file contents.")
    tags: list[str] = Field(
        default_factory=list, description="Optional attachment descriptors."
    )


class TradeSubmissionRequest(BaseModel):
    """Raw user submission that the main agent will structure via Gemini."""

    user_id: str = Field(
        ..., description="Application-level identifier for the trader."
    )
    content: str = Field(
        ..., description="Free-form narrative of the trade, strategy, and outcomes."
    )
    attachments: list[TradeAttachment] = Field(
        default_factory=list,
        description="Optional multi-modal attachments (images, audio, video).",
    )
    ticker: Optional[str] = Field(
        None, description="Optional ticker override supplied by the user."
    )
    pnl: Optional[float] = Field(None, description="Optional profit or loss override.")
    position_type: Optional[str] = Field(
        None, description="Optional position type override."
    )
    entry_timestamp: Optional[datetime] = Field(
        None, description="Optional entry timestamp override."
    )
    exit_timestamp: Optional[datetime] = Field(
        None, description="Optional exit timestamp override."
    )
    notes: Optional[str] = Field(None, description="Optional additional notes.")


class AnalysisRequest(BaseModel):
    """Payload to request an asynchronous analysis job."""

    user_id: str = Field(..., description="The trader requesting analysis.")
    sheet_id: str = Field(
        ..., description="Google Sheet identifier containing journal entries."
    )
    sheet_range: Optional[str] = Field(
        None,
        description="Range (e.g., 'Journal!A1:Z') that will be analyzed.",
    )
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
