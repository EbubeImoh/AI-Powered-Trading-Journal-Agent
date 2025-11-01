"""
AWS Lambda entrypoint for processing analysis jobs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.clients import DynamoDBClient
from app.core.config import get_settings
from app.core.logging import configure_logging
from agents.analysis_lambda.graph import create_analysis_graph
from agents.analysis_lambda.models import AnalysisJobPayload
from agents.analysis_lambda.tools import AnalysisTools

logger = logging.getLogger(__name__)


def _bootstrap() -> Dict[str, Any]:
    """Initialize shared singletons for the Lambda runtime."""
    settings = get_settings()
    configure_logging(settings.log_level)

    tools = AnalysisTools()
    graph = create_analysis_graph(tools)
    dynamodb = DynamoDBClient(settings.aws)
    return {"graph": graph, "dynamodb": dynamodb}


BOOTSTRAP = _bootstrap()


async def _process_job(payload: AnalysisJobPayload) -> None:
    """Execute the LangGraph workflow for an individual job."""
    graph = BOOTSTRAP["graph"]
    dynamodb: DynamoDBClient = BOOTSTRAP["dynamodb"]

    logger.info("Starting analysis job", extra={"job_id": payload["job_id"]})
    final_state = await graph.ainvoke({"job": payload})
    report = final_state.get("report", "")

    dynamodb.put_item(
        {
            "pk": f"user#{payload['user_id']}",
            "sk": f"analysis#{payload['job_id']}",
            "user_id": payload["user_id"],
            "job_id": payload["job_id"],
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "prompt": payload["prompt"],
            "sheet_id": payload["sheet_id"],
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "requested_at": payload.get("requested_at"),
            "report": report,
        }
    )
    logger.info("Completed analysis job", extra={"job_id": payload["job_id"]})


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler invoked by SQS.

    The handler fan-outs incoming records and processes them sequentially to keep the
    example straightforward. Production implementations could batch or parallelize.
    """
    records: List[Dict[str, Any]] = event.get("Records", [])
    if not records:
        logger.warning("No records found in event payload.")
        return {"statusCode": 200, "processed": 0}

    payloads: List[AnalysisJobPayload] = []
    for record in records:
        body = record.get("body")
        if body is None:
            logger.error("Skipping record without body: %s", record)
            continue
        payload: AnalysisJobPayload = json.loads(body)
        payloads.append(payload)

    if not payloads:
        return {"statusCode": 200, "processed": 0}

    async def _process_all() -> None:
        for payload in payloads:
            await _process_job(payload)

    asyncio.run(_process_all())

    return {"statusCode": 200, "processed": len(payloads)}


__all__ = ["lambda_handler"]
