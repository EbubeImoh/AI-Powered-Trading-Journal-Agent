"""
Google OAuth utilities.

These helpers manage the user authentication flow and token refresh lifecycle.
"""

from __future__ import annotations

import base64
import hmac
import json
from hashlib import sha256
from typing import Any, Dict, Tuple

import httpx

from fastapi import HTTPException, status

from app.core.config import GoogleSettings, OAuthSettings


class OAuthStateEncoder:
    """Encode and decode OAuth state values to guard against tampering."""

    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key.encode("utf-8")

    def encode(self, payload: Dict[str, Any]) -> str:
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        signature = hmac.new(self._secret_key, serialized.encode("utf-8"), sha256).digest()
        return base64.urlsafe_b64encode(signature + serialized.encode("utf-8")).decode("utf-8")

    def decode(self, token: str) -> Dict[str, Any]:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8"))
        signature, serialized = decoded[:32], decoded[32:]
        expected_signature = hmac.new(self._secret_key, serialized, sha256).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OAuth state signature.",
            )
        return json.loads(serialized)


class OAuthTokenExchangeError(Exception):
    """Raised when the token endpoint returns an error."""


class OAuthTokenNotFoundError(Exception):
    """Raised when no persisted OAuth token is available for a user."""


class GoogleOAuthClient:
    """Build Google authorization URLs and exchange authorization codes."""

    AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, google_settings: GoogleSettings, oauth_settings: OAuthSettings) -> None:
        self._google = google_settings
        self._oauth = oauth_settings

    def build_authorization_url(self, state: str, access_type: str = "offline") -> str:
        """Construct the Google OAuth consent URL."""
        from urllib.parse import urlencode

        params = {
            "client_id": self._google.client_id,
            "redirect_uri": str(self._google.redirect_uri),
            "response_type": "code",
            "scope": " ".join(self._oauth.scopes),
            "access_type": access_type,
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        query = urlencode(params)
        return f"{self.AUTH_BASE_URL}?{query}"

    async def exchange_authorization_code(self, code: str) -> Tuple[str, str, int]:
        """
        Exchange an authorization code for tokens.

        Returns a tuple of (access_token, refresh_token, expires_in_seconds).
        """
        payload = {
            "code": code,
            "client_id": self._google.client_id,
            "client_secret": self._google.client_secret,
            "redirect_uri": str(self._google.redirect_uri),
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.TOKEN_URL, data=payload)

        if response.status_code != status.HTTP_200_OK:
            raise OAuthTokenExchangeError(response.text)

        token_payload = response.json()
        access_token = token_payload.get("access_token")
        refresh_token = token_payload.get("refresh_token")
        expires_in = token_payload.get("expires_in")

        if not access_token or not refresh_token or not expires_in:
            raise OAuthTokenExchangeError("Incomplete token payload returned from Google.")

        return access_token, refresh_token, int(expires_in)

    async def refresh_token(self, refresh_token: str) -> Tuple[str, int]:
        """Refresh the access token using a stored refresh token."""
        payload = {
            "client_id": self._google.client_id,
            "client_secret": self._google.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.TOKEN_URL, data=payload)

        if response.status_code != status.HTTP_200_OK:
            raise OAuthTokenExchangeError(response.text)

        token_payload = response.json()
        access_token = token_payload.get("access_token")
        expires_in = token_payload.get("expires_in")

        if not access_token or not expires_in:
            raise OAuthTokenExchangeError("Incomplete refresh payload returned from Google.")

        return access_token, int(expires_in)


__all__ = [
    "GoogleOAuthClient",
    "OAuthStateEncoder",
    "OAuthTokenExchangeError",
    "OAuthTokenNotFoundError",
]
