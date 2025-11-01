"""HTTP utilities providing retry/backoff semantics."""

from __future__ import annotations

import asyncio
from typing import Callable, TypeVar

import httpx

T = TypeVar("T")


class RetryConfig:
    def __init__(self, *, attempts: int = 3, backoff_seconds: float = 1.0) -> None:
        self.attempts = attempts
        self.backoff_seconds = backoff_seconds


async def request_with_retry(
    func: Callable[..., httpx.Response],
    *args,
    retry_config: RetryConfig | None = None,
    **kwargs,
) -> httpx.Response:
    config = retry_config or RetryConfig()
    attempt = 0
    last_exception: Exception | None = None

    while attempt < config.attempts:
        try:
            response = await func(*args, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as exc:  # pragma: no cover - network path
            last_exception = exc
            attempt += 1
            if attempt >= config.attempts:
                break
            await asyncio.sleep(config.backoff_seconds * attempt)

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("Request failed without raising an exception")


__all__ = ["RetryConfig", "request_with_retry"]
