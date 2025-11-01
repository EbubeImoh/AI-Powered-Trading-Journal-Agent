"""
Amazon SQS client wrapper for queueing analysis jobs.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import boto3

from app.core.config import AWSSettings


class SQSClient:
    """Send analysis jobs to the asynchronous worker queue."""

    def __init__(self, settings: AWSSettings) -> None:
        self._settings = settings
        self._client = boto3.client("sqs", region_name=settings.region_name)

    def enqueue_analysis_request(self, payload: Dict[str, Any]) -> str:
        """Push a message onto the SQS queue."""
        response = self._client.send_message(
            QueueUrl=self._settings.sqs_queue_url,
            MessageBody=json.dumps(payload),
        )
        return response["MessageId"]


__all__ = ["SQSClient"]
