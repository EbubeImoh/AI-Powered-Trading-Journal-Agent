"""Schemas related to OAuth flows."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OAuthCallbackPayload(BaseModel):
    """Payload sent to complete the OAuth callback exchange."""

    code: str = Field(..., description="Authorization code returned by Google OAuth.")
    state: str = Field(..., description="Opaque state token issued when starting OAuth.")


__all__ = ["OAuthCallbackPayload"]
