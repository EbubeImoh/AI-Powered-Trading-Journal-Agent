"""
AWS Lambda entrypoint for processing analysis jobs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.clients import (
    DynamoDBClient,
    GeminiClient,
    GoogleDriveClient,
    GoogleOAuthClient,
    GoogleSheetsClient,
    WebSearchClient,
)
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services import GoogleTokenService, TokenCipherService
from app.clients.google_auth import OAuthTokenNotFoundError
from agents.analysis_lambda.graph import create_analysis_graph
from agents.analysis_lambda.models import AnalysisJobPayload
from agents.analysis_lambda.tools import AnalysisTools

logger = logging.getLogger(__name__)


def _bootstrap() -> Dict[str, Any]:
    """Initialize shared singletons for the Lambda runtime."""
    settings = get_settings()
    configure_logging(settings.log_level)

    dynamodb = DynamoDBClient(settings.aws)
    oauth_client = GoogleOAuthClient(settings.google, settings.oauth)
    token_cipher = TokenCipherService(
        secret=settings.security.token_encryption_secret or settings.google.client_secret
    )
    token_service = GoogleTokenService(
        dynamodb_client=dynamodb,
        oauth_client=oauth_client,
        google_settings=settings.google,
        oauth_settings=settings.oauth,
        token_cipher=token_cipher,
    )

    drive_client = GoogleDriveClient(
        token_service=token_service,
        drive_root_folder_id=settings.google.drive_root_folder_id,
    )
    sheets_client = GoogleSheetsClient(token_service=token_service)
    gemini_client = GeminiClient(settings.gemini)
    web_search_client = None
    if settings.serpapi_api_key:
        web_search_client = WebSearchClient(api_key=settings.serpapi_api_key)
    tools = AnalysisTools(
        sheets_client=sheets_client,
        drive_client=drive_client,
        gemini_client=gemini_client,
        web_search_client=web_search_client,
    )
    graph = create_analysis_graph(tools)
    return {"graph": graph, "dynamodb": dynamodb}


BOOTSTRAP = _bootstrap()


async def _process_job(payload: AnalysisJobPayload) -> None:
    """Execute the LangGraph workflow for an individual job."""
    graph = BOOTSTRAP["graph"]
    dynamodb: DynamoDBClient = BOOTSTRAP["dynamodb"]

    logger.info("Starting analysis job", extra={"job_id": payload["job_id"]})
    try:
        final_state = await graph.ainvoke({"job": payload})
    except OAuthTokenNotFoundError as exc:
        logger.error("Missing OAuth tokens for analysis job", extra={"job_id": payload["job_id"]})
        _persist_job_record(
            dynamodb=dynamodb,
            payload=payload,
            status="failed",
            error=str(exc),
        )
        return
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unexpected failure while running analysis job", extra={"job_id": payload["job_id"]})
        _persist_job_record(
            dynamodb=dynamodb,
            payload=payload,
            status="failed",
            error=str(exc),
        )
        raise

    report_payload = final_state.get("report") or {}
    report_json = json.dumps(report_payload)
    report_markdown = _render_markdown(report_payload)
    transcriptions = final_state.get("transcriptions")
    image_insights = final_state.get("image_insights")
    external_research = final_state.get("external_research")
    _persist_job_record(
        dynamodb=dynamodb,
        payload=payload,
        status="completed",
        report=report_json,
        report_markdown=report_markdown,
        audio_insights=transcriptions,
        image_insights=image_insights,
        external_research=external_research,
    )
    logger.info("Completed analysis job", extra={"job_id": payload["job_id"]})


def _persist_job_record(
    *,
    dynamodb: DynamoDBClient,
    payload: AnalysisJobPayload,
    status: str,
    report: str | None = None,
    report_markdown: str | None = None,
    error: str | None = None,
    audio_insights: list[dict[str, Any]] | None = None,
    image_insights: list[dict[str, Any]] | None = None,
    external_research: list[dict[str, Any]] | None = None,
) -> None:
    """Write the job record status back to DynamoDB."""
    record: Dict[str, Any] = {
        "pk": f"user#{payload['user_id']}",
        "sk": f"analysis#{payload['job_id']}",
        "user_id": payload["user_id"],
        "job_id": payload["job_id"],
        "status": status,
        "prompt": payload["prompt"],
        "sheet_id": payload["sheet_id"],
    }

    if report is not None:
        record["report"] = report
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
    if report_markdown is not None:
        record["report_markdown"] = report_markdown
    if error is not None:
        record["error"] = error
        record["completed_at"] = datetime.now(timezone.utc).isoformat()
    if audio_insights:
        record["audio_insights"] = audio_insights
    if image_insights:
        record["image_insights"] = image_insights
    if external_research:
        record["external_research"] = external_research
    if payload.get("sheet_range"):
        record["sheet_range"] = payload["sheet_range"]
    if payload.get("start_date"):
        record["start_date"] = payload["start_date"]
    if payload.get("end_date"):
        record["end_date"] = payload["end_date"]
    if payload.get("requested_at"):
        record["requested_at"] = payload["requested_at"]

    dynamodb.put_item(record)


def _render_markdown(report: dict[str, Any]) -> str:
    if not report:
        return "Report unavailable."
    lines = ["# Performance Overview"]
    perf = report.get("performance_overview", {})
    summary = perf.get("summary")
    if summary:
        lines.append(summary)
    metrics = perf.get("key_metrics", [])
    if metrics:
        lines.append("\n## Key Metrics")
        lines.extend(f"- {metric}" for metric in metrics)

    patterns = report.get("behavioural_patterns", [])
    if patterns:
        lines.append("\n## Behavioural Patterns")
        lines.extend(f"- {pattern}" for pattern in patterns)

    opportunities = report.get("opportunities", [])
    if opportunities:
        lines.append("\n## Opportunities")
        lines.extend(f"- {item}" for item in opportunities)

    action_plan = report.get("action_plan", [])
    if action_plan:
        lines.append("\n## Action Plan")
        for step in action_plan:
            title = step.get("title", "Action")
            detail = step.get("detail", "")
            lines.append(f"- **{title}** — {detail}")

    return "\n".join(lines)


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
