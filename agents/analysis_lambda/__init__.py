"""AWS Lambda analysis sub-agent package.

This module orchestrates asynchronous analysis jobs triggered from SQS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["lambda_handler"]

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .handler import lambda_handler as _lambda_handler_type


def __getattr__(name: str) -> Any:
    if name == "lambda_handler":
        from .handler import lambda_handler as _lambda_handler

        return _lambda_handler
    raise AttributeError(name)
