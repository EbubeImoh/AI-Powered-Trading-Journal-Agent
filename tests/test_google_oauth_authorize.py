try:
    from . import _bootstrap  # noqa: F401
except Exception:  # pragma: no cover
    import _bootstrap  # type: ignore # noqa: F401

import httpx
import pytest

from app.main import app


@pytest.mark.anyio
async def test_authorize_returns_json_by_default():
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


@pytest.mark.anyio
async def test_authorize_redirects_for_html_accept():
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
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
