"""
AWS Lambda analysis sub-agent package.

This module orchestrates asynchronous analysis jobs triggered from SQS.
"""

from .handler import lambda_handler

__all__ = ["lambda_handler"]
