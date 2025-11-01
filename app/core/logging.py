"""
Logging utilities for the FastAPI application and background workers.

Provides a consistent logging format and configuration.
"""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging with a sensible default format."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


__all__ = ["configure_logging"]
