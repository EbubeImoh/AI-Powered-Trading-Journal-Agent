"""AWS Lambda analysis sub-agent package.

This module orchestrates asynchronous analysis jobs triggered from SQS.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "lambda_handler":
        from .handler import lambda_handler as loaded_lambda_handler

        return loaded_lambda_handler
    raise AttributeError(name)


__all__ = ["lambda_handler"]
