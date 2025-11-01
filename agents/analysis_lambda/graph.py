"""
LangGraph workflow definition for the analysis sub-agent.
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from agents.analysis_lambda.models import AnalysisJobPayload, AnalysisState
from agents.analysis_lambda.tools import AnalysisTools


async def _load_trades(state: AnalysisState, tools: AnalysisTools) -> AnalysisState:
    """Fetch trading data from Google Sheets."""
    job: AnalysisJobPayload = state["job"]
    sheet_range = job.get("sheet_range") or "Sheet1!A1:Z"
    trades = await tools.read_trading_journal(
        user_id=job["user_id"],
        sheet_id=job["sheet_id"],
        range_=sheet_range,
    )
    state["trades"] = trades
    return state


async def _collect_assets(state: AnalysisState, tools: AnalysisTools) -> AnalysisState:
    """Resolve Drive file metadata for assets referenced in trades."""
    job: AnalysisJobPayload = state["job"]
    trades = state.get("trades", [])
    if not trades:
        state["assets"] = []
        return state

    assets = await tools.collect_assets(user_id=job["user_id"], trades=trades)
    state["assets"] = assets
    return state


async def _transcribe_audio(state: AnalysisState, tools: AnalysisTools) -> AnalysisState:
    """Generate transcripts for audio assets."""
    job: AnalysisJobPayload = state["job"]
    assets = state.get("assets", [])
    audio_assets = [asset for asset in assets if asset.get("mime_type", "").startswith("audio/")]
    if not audio_assets:
        state["transcriptions"] = []
        return state

    transcripts = await tools.transcribe_audio_assets(user_id=job["user_id"], assets=audio_assets)
    state["transcriptions"] = transcripts
    return state


async def _analyze_images(state: AnalysisState, tools: AnalysisTools) -> AnalysisState:
    """Run Gemini vision on chart screenshots."""
    job: AnalysisJobPayload = state["job"]
    assets = state.get("assets", [])
    image_assets = [asset for asset in assets if asset.get("mime_type", "").startswith("image/")]
    if not image_assets:
        state["image_insights"] = []
        return state

    insights = await tools.analyze_trade_images(user_id=job["user_id"], assets=image_assets)
    state["image_insights"] = insights
    return state


async def _perform_research(state: AnalysisState, tools: AnalysisTools) -> AnalysisState:
    """Gather supplemental research related to the job prompt."""
    job: AnalysisJobPayload = state["job"]
    prompt = job["prompt"]
    if not prompt:
        state["external_research"] = []
        return state

    research = await tools.perform_web_research(query=prompt)
    state["external_research"] = research
    return state


async def _synthesize_report(state: AnalysisState, tools: AnalysisTools) -> AnalysisState:
    """Run Gemini to synthesize a comprehensive analysis report."""
    job: AnalysisJobPayload = state["job"]
    trades = state.get("trades", [])
    audio_insights = state.get("transcriptions", [])
    image_insights = state.get("image_insights", [])
    web_research = state.get("external_research", [])

    if not trades:
        state["report"] = (
            "No journal entries were available for the requested window. Please ensure your sheet contains data."
        )
        return state

    report = await tools.synthesize_report(
        job_prompt=job["prompt"],
        trades=trades,
        audio_insights=audio_insights,
        image_insights=image_insights,
        web_research=web_research,
    )

    if not report:
        report = {"error": "Gemini did not return a response."}

    state["report"] = report
    return state


def create_analysis_graph(tools: AnalysisTools) -> Any:
    """Compile and return the analysis LangGraph workflow."""
    graph = StateGraph(AnalysisState)

    async def load_trades_node(state: AnalysisState) -> AnalysisState:
        return await _load_trades(state, tools)

    async def collect_assets_node(state: AnalysisState) -> AnalysisState:
        return await _collect_assets(state, tools)

    async def transcribe_audio_node(state: AnalysisState) -> AnalysisState:
        return await _transcribe_audio(state, tools)

    async def analyze_images_node(state: AnalysisState) -> AnalysisState:
        return await _analyze_images(state, tools)

    async def perform_research_node(state: AnalysisState) -> AnalysisState:
        return await _perform_research(state, tools)

    async def synthesize_report_node(state: AnalysisState) -> AnalysisState:
        return await _synthesize_report(state, tools)

    graph.add_node("load_trades", load_trades_node)
    graph.add_node("collect_assets", collect_assets_node)
    graph.add_node("transcribe_audio", transcribe_audio_node)
    graph.add_node("analyze_images", analyze_images_node)
    graph.add_node("perform_research", perform_research_node)
    graph.add_node("synthesize_report", synthesize_report_node)

    graph.add_edge(START, "load_trades")
    graph.add_edge("load_trades", "collect_assets")
    graph.add_edge("collect_assets", "transcribe_audio")
    graph.add_edge("transcribe_audio", "analyze_images")
    graph.add_edge("analyze_images", "perform_research")
    graph.add_edge("perform_research", "synthesize_report")
    graph.add_edge("synthesize_report", END)
    return graph.compile()


__all__ = ["create_analysis_graph"]
