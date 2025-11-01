from __future__ import annotations
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import GoogleSettings, OAuthSettings
from app.services.google_tokens import GoogleTokenService
from app.services.token_cipher import TokenCipherService


class FakeDynamoDBClient:
    def __init__(self) -> None:
        self._storage: dict[tuple[str, str], dict] = {}

    def put_item(self, item: dict) -> None:
        self._storage[(item["pk"], item["sk"])] = item

    def get_item(self, *, partition_key: str, sort_key: str) -> dict | None:
        return self._storage.get((partition_key, sort_key))


class DummyOAuthClient:
    TOKEN_URL = "https://oauth.example/token"

    def __init__(self, *, refreshed_token: str = "refreshed-access") -> None:
        self.refreshed_token = refreshed_token
        self.calls: list[str] = []

    async def refresh_token(self, refresh_token: str) -> tuple[str, int]:
        self.calls.append(refresh_token)
        return self.refreshed_token, 3600


@pytest.mark.asyncio
async def test_get_credentials_refreshes_and_updates_storage() -> None:
    dynamo = FakeDynamoDBClient()
    cipher = TokenCipherService(secret="secret-key")
    oauth_client = DummyOAuthClient()

    settings = GoogleSettings(
        GOOGLE_CLIENT_ID="client",
        GOOGLE_CLIENT_SECRET="secret",
        GOOGLE_REDIRECT_URI="https://example.com/callback",
    )
    oauth_settings = OAuthSettings()

    expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    dynamo.put_item(
        {
            "pk": "user#123",
            "sk": "oauth#google",
            "access_token_encrypted": cipher.encrypt("initial-token"),
            "refresh_token_encrypted": cipher.encrypt("refresh-token"),
            "expires_at": expires_at,
        }
    )

    service = GoogleTokenService(
        dynamodb_client=dynamo,
        oauth_client=oauth_client,
        google_settings=settings,
        oauth_settings=oauth_settings,
        token_cipher=cipher,
    )

    credentials = await service.get_credentials(user_id="123")

    assert credentials.token == oauth_client.refreshed_token
    assert oauth_client.calls == ["refresh-token"]

    stored = dynamo.get_item(partition_key="user#123", sort_key="oauth#google")
    assert stored is not None
    assert cipher.decrypt(stored["access_token_encrypted"]) == oauth_client.refreshed_token
    assert stored.get("updated_at") is not None


@pytest.mark.asyncio
async def test_get_credentials_migrates_plaintext_tokens() -> None:
    dynamo = FakeDynamoDBClient()
    cipher = TokenCipherService(secret="secret-key")
    oauth_client = DummyOAuthClient()

    settings = GoogleSettings(
        GOOGLE_CLIENT_ID="client",
        GOOGLE_CLIENT_SECRET="secret",
        GOOGLE_REDIRECT_URI="https://example.com/callback",
    )
    oauth_settings = OAuthSettings()

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    dynamo.put_item(
        {
            "pk": "user#abc",
            "sk": "oauth#google",
            "access_token": "legacy-access",
            "refresh_token": "legacy-refresh",
            "expires_at": expires_at,
        }
    )

    service = GoogleTokenService(
        dynamodb_client=dynamo,
        oauth_client=oauth_client,
        google_settings=settings,
        oauth_settings=oauth_settings,
        token_cipher=cipher,
    )

    credentials = await service.get_credentials(user_id="abc")
    assert credentials.token == "legacy-access"

    stored = dynamo.get_item(partition_key="user#abc", sort_key="oauth#google")
    assert "access_token" not in stored
    assert "refresh_token" not in stored
    assert stored["access_token_encrypted"] != "legacy-access"
    assert stored["refresh_token_encrypted"] != "legacy-refresh"
    assert stored.get("updated_at") is not None
