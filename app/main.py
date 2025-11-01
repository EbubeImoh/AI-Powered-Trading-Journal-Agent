"""
FastAPI application entrypoint for the trading journal agent.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Factory for the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="AI-Powered Trading Journal Agent",
        version="0.1.0",
        description="REST API for trade ingestion and analysis orchestration.",
    )
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()

__all__ = ["app", "create_app"]
