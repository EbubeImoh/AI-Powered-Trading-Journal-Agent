"""
Data models shared across the analysis Lambda package.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AnalysisJobPayload(TypedDict):
    """Payload structure delivered via SQS."""

    job_id: str
    user_id: str
    sheet_id: str
    prompt: str
    start_date: Optional[str]
    end_date: Optional[str]
    requested_at: str


class AnalysisState(TypedDict, total=False):
    """State tracked inside the LangGraph workflow."""

    job: AnalysisJobPayload
    trades: List[Dict[str, Any]]
    transcriptions: List[Dict[str, Any]]
    image_insights: List[Dict[str, Any]]
    external_research: List[Dict[str, Any]]
    report: str


__all__ = ["AnalysisJobPayload", "AnalysisState"]
