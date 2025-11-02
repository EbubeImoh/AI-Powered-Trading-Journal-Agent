"""Search client integrating with SerpAPI to gather reference material."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from app.utils.http import RetryConfig, request_with_retry


class WebSearchClient:
    """Perform web searches using SerpAPI."""

    _BASE_URL = "https://serpapi.com/search.json"

    def __init__(self, *, api_key: str, engine: str = "google") -> None:
        self._api_key = api_key
        self._engine = engine

    async def search(self, query: str, *, num_results: int = 5) -> List[Dict[str, Any]]:
        """Execute a search query and return simplified results."""

        params = {
            "engine": self._engine,
            "q": query,
            "num": num_results,
            "api_key": self._api_key,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await request_with_retry(
                client.get,
                self._BASE_URL,
                params=params,
                retry_config=RetryConfig(),
            )

        payload = response.json()
        results: List[Dict[str, Any]] = []
        for item in payload.get("organic_results", [])[:num_results]:
            results.append(
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet"),
                    "position": item.get("position"),
                }
            )
        return results


__all__ = ["WebSearchClient"]
