"""
Service helpers for enqueuing analysis jobs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from app.clients import DynamoDBClient, SQSClient
from app.schemas import AnalysisRequest


class AnalysisQueueService:
    """Queue asynchronous analysis jobs and track their lifecycle."""

    def __init__(self, sqs_client: SQSClient, dynamodb_client: DynamoDBClient) -> None:
        self._sqs = sqs_client
        self._ddb = dynamodb_client

    def enqueue_analysis(self, *, request: AnalysisRequest) -> str:
        """Create a job record and enqueue the task."""
        job_id = self._build_job_id(request.user_id)
        payload = self._build_message_payload(job_id=job_id, request=request)

        # Persist pending status in DynamoDB.
        self._ddb.put_item(
            {
                "pk": f"user#{request.user_id}",
                "sk": f"analysis#{job_id}",
                "status": "pending",
                "requested_at": datetime.utcnow().isoformat(),
                "prompt": request.prompt,
                "sheet_id": request.sheet_id,
                "start_date": request.start_date.isoformat() if request.start_date else None,
                "end_date": request.end_date.isoformat() if request.end_date else None,
            }
        )

        self._sqs.enqueue_analysis_request(payload)
        return job_id

    @staticmethod
    def _build_job_id(user_id: str) -> str:
        """Generate a deterministic job identifier."""
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{user_id}-{timestamp}"

    @staticmethod
    def _build_message_payload(*, job_id: str, request: AnalysisRequest) -> Dict[str, Any]:
        """Construct the message payload for the analysis worker."""
        return {
            "job_id": job_id,
            "user_id": request.user_id,
            "prompt": request.prompt,
            "sheet_id": request.sheet_id,
            "start_date": request.start_date.isoformat() if request.start_date else None,
            "end_date": request.end_date.isoformat() if request.end_date else None,
            "requested_at": datetime.utcnow().isoformat(),
        }


__all__ = ["AnalysisQueueService"]
