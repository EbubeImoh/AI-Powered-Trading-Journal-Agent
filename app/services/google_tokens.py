"""
Helpers for retrieving and refreshing Google OAuth tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials

from app.clients import DynamoDBClient, GoogleOAuthClient
from app.clients.google_auth import OAuthTokenNotFoundError
from app.core.config import GoogleSettings, OAuthSettings
from app.services.token_cipher import TokenCipherService


class GoogleTokenService:
    """Manages access to persisted Google OAuth tokens."""

    _REFRESH_WINDOW = timedelta(minutes=5)

    def __init__(
        self,
        dynamodb_client: DynamoDBClient,
        oauth_client: GoogleOAuthClient,
        google_settings: GoogleSettings,
        oauth_settings: OAuthSettings,
        token_cipher: TokenCipherService,
    ) -> None:
        self._ddb = dynamodb_client
        self._oauth = oauth_client
        self._google = google_settings
        self._oauth_settings = oauth_settings
        self._cipher = token_cipher

    async def get_credentials(self, *, user_id: str) -> Credentials:
        """Retrieve credentials for a user, refreshing tokens when necessary."""
        record = self._ddb.get_item(
            partition_key=f"user#{user_id}",
            sort_key="oauth#google",
        )
        if not record:
            raise OAuthTokenNotFoundError(f"No OAuth token stored for user {user_id}.")

        encrypted_access_token = record.get("access_token_encrypted")
        encrypted_refresh_token = record.get("refresh_token_encrypted")
        expires_at = record.get("expires_at")

        # Backward compatibility: migrate legacy plaintext tokens if encountered.
        legacy_access_token = record.get("access_token")
        legacy_refresh_token = record.get("refresh_token")
        update_required = False
        if legacy_access_token and not encrypted_access_token:
            encrypted_access_token = self._cipher.encrypt(legacy_access_token)
            record["access_token_encrypted"] = encrypted_access_token
            record.pop("access_token", None)
            update_required = True
        if legacy_refresh_token and not encrypted_refresh_token:
            encrypted_refresh_token = self._cipher.encrypt(legacy_refresh_token)
            record["refresh_token_encrypted"] = encrypted_refresh_token
            record.pop("refresh_token", None)
            update_required = True
        if (legacy_access_token or legacy_refresh_token) and not expires_at:
            raise OAuthTokenNotFoundError(
                "Legacy token record missing expiration; re-authentication required."
            )
        if update_required:
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._ddb.put_item(record)

        if not encrypted_access_token or not encrypted_refresh_token or not expires_at:
            raise OAuthTokenNotFoundError(
                "Stored OAuth token is missing required fields."
            )

        access_token = self._cipher.decrypt(encrypted_access_token)
        refresh_token = self._cipher.decrypt(encrypted_refresh_token)

        expires_at_dt = datetime.fromisoformat(expires_at)
        now = datetime.now(timezone.utc)
        if expires_at_dt.tzinfo is None:
            expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)

        if expires_at_dt <= now + self._REFRESH_WINDOW:
            refreshed_at = datetime.now(timezone.utc)
            access_token, expires_in = await self._oauth.refresh_token(refresh_token)
            expires_at_dt = refreshed_at + timedelta(seconds=expires_in)
            record["access_token_encrypted"] = self._cipher.encrypt(access_token)
            record["expires_at"] = expires_at_dt.isoformat()
            record["updated_at"] = refreshed_at.isoformat()
            self._ddb.put_item(record)

        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=GoogleOAuthClient.TOKEN_URL,
            client_id=self._google.client_id,
            client_secret=self._google.client_secret,
            scopes=list(self._oauth_settings.scopes),
        )

        return credentials


__all__ = ["GoogleTokenService"]
