try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover
    import _bootstrap  # type: ignore # noqa: F401

import copy

import httpx
import pytest

from app.main import app


class DummyOAuthClient:
    def __init__(self) -> None:
        self.states: list[str] = []
        self.codes: list[str] = []

    def build_authorization_url(self, state: str) -> str:
        self.states.append(state)
        return f"https://oauth.example.com/auth?state={state}"

    async def exchange_authorization_code(self, code: str) -> tuple[str, str, int]:
        self.codes.append(code)
        return ("access-token", "refresh-token", 3600)


class DummyStore:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def put_item(self, item: dict) -> None:
        self.items.append(item)


class DummyCipher:
    def encrypt(self, value: str) -> str:
        return f"enc:{value}"


@pytest.fixture()
def oauth_overrides():
    from app import dependencies
    from app.core.config import get_settings

    dummy_client = DummyOAuthClient()
    dummy_store = DummyStore()
    dummy_cipher = DummyCipher()
    base_settings = copy.deepcopy(get_settings())
    base_settings.frontend_base_url = None

    overrides = {
        dependencies.get_google_oauth_client: lambda: dummy_client,
        dependencies.get_sqlite_store: lambda: dummy_store,
        dependencies.get_token_cipher_service: lambda: dummy_cipher,
        dependencies.get_app_settings: lambda: base_settings,
    }

    app.dependency_overrides.update(overrides)

    yield dummy_client, dummy_store, base_settings

    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_authorize_returns_json_by_default(oauth_overrides):
    dummy_client, _, _ = oauth_overrides
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/auth/google/authorize",
            params={"user_id": "abc123"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert data["authorization_url"].startswith("https://")
    assert dummy_client.states


@pytest.mark.anyio
async def test_authorize_redirects_for_html_accept(oauth_overrides):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/auth/google/authorize",
            params={"user_id": "abc123"},
            headers={"accept": "text/html"},
        )

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "https://oauth.example.com/auth"
    )


@pytest.mark.anyio
async def test_callback_get_returns_json_when_no_frontend(oauth_overrides):
    dummy_client, dummy_store, _ = oauth_overrides

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        auth_resp = await client.get(
            "/api/auth/google/authorize",
            params={"user_id": "user-1"},
        )

        state = dummy_client.states[-1]
        callback_resp = await client.get(
            "/api/auth/google/callback",
            params={"state": state, "code": "oauth-code"},
        )

    assert callback_resp.status_code == 200
    data = callback_resp.json()
    assert data["status"] == "connected"
    assert dummy_client.codes[-1] == "oauth-code"
    assert dummy_store.items


@pytest.mark.anyio
async def test_callback_get_redirects_when_frontend_available(oauth_overrides):
    dummy_client, _, settings = oauth_overrides
    settings.frontend_base_url = "https://app.example.com/oauth/success"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.get(
            "/api/auth/google/authorize",
            params={"user_id": "user-2"},
        )

        state = dummy_client.states[-1]
        callback_resp = await client.get(
            "/api/auth/google/callback",
            params={"state": state, "code": "oauth-code"},
            headers={"accept": "text/html"},
        )

    assert callback_resp.status_code == 307
    assert (
        callback_resp.headers["location"]
        == "https://app.example.com/oauth/success"
    )
