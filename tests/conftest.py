"""Pytest configuration shared across the suite."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Force AnyIO-powered tests to run against asyncio backend only."""
    return "asyncio"
