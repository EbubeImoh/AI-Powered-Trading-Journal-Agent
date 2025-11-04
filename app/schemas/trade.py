"""
Pydantic models for trade ingestion and analysis requests.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

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
    session_id: Optional[str] = Field(
        None,
        description="Optional identifier for an in-progress trade capture session.",
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


class TradeSubmissionResult(BaseModel):
    """Response envelope for conversational trade submission workflow."""

    status: Literal["needs_more_info", "completed"] = Field(
        ...,
        description="Represents whether additional user input is required.",
    )
    session_id: Optional[str] = Field(
        None,
        description="Identifies the conversation session when more input is needed.",
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="Fields still required to log the trade."
    )
    prompt: Optional[str] = Field(
        None, description="Natural language follow-up presented to the user."
    )
    summary: Optional[str] = Field(
        None,
        description="Structured summary of the trade when capture is complete.",
    )
    trade: Optional[TradeIngestionRequest] = Field(
        None,
        description="Structured trade derived from the conversation.",
    )
    ingestion_response: Optional[TradeIngestionResponse] = Field(
        None,
        description="Result of persisting the trade when completed.",
    )


class TelegramUpdate(BaseModel):
    """Minimal Telegram update payload we care about."""

    update_id: int
    message: Optional["TelegramMessage"] = None


class TelegramMessage(BaseModel):
    """Subset of Telegram message fields used in trade capture."""

    message_id: int
    date: int
    text: Optional[str] = None
    caption: Optional[str] = None
    photo: Optional[List[Dict[str, Any]]] = None
    document: Optional[Dict[str, Any]] = None
    audio: Optional[Dict[str, Any]] = None
    voice: Optional[Dict[str, Any]] = None
    video: Optional[Dict[str, Any]] = None
    chat: Dict[str, Any]
    from_: Optional[Dict[str, Any]] = Field(None, alias="from")

    class Config:
        extra = "ignore"


TelegramUpdate.update_forward_refs()


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
    "TradeSubmissionRequest",
    "TradeSubmissionResult",
]
