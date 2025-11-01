"""
Domain models for OAuth token persistence.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class StoredOAuthToken(BaseModel):
    """Represents a token record stored in DynamoDB."""

    pk: str = Field(..., description="Partition key derived from user identifier.")
    sk: str = Field(..., description="Sort key describing the record type.")
    access_token: str
    refresh_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


__all__ = ["StoredOAuthToken"]
