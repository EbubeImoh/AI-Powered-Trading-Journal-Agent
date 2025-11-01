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
    trades = await tools.read_trading_journal(sheet_id=job["sheet_id"])
    state["trades"] = trades
    return state


async def _synthesize_report(state: AnalysisState, tools: AnalysisTools) -> AnalysisState:
    """
    Placeholder synthesis step that inspects journal entries and produces a draft report.

    This will ultimately call Gemini for deep reasoning, but for now we construct a stub
    based on the number of trades retrieved.
    """
    trades = state.get("trades", [])
    job: AnalysisJobPayload = state["job"]

    summary_lines = [
        f"Analysis request: {job['prompt']}",
        f"Trades reviewed: {len(trades)}",
    ]

    if not trades:
        summary_lines.append("No trades were available in the requested window.")
    else:
        tickers = {trade.get("ticker") for trade in trades if trade.get("ticker")}
        summary_lines.append(f"Unique tickers: {len(tickers)}")
        summary_lines.append("Detailed analysis is pending Gemini integration.")

    state["report"] = "\n".join(summary_lines)
    return state


def create_analysis_graph(tools: AnalysisTools) -> Any:
    """Compile and return the analysis LangGraph workflow."""
    graph = StateGraph(AnalysisState)

    async def load_trades_node(state: AnalysisState) -> AnalysisState:
        return await _load_trades(state, tools)

    async def synthesize_report_node(state: AnalysisState) -> AnalysisState:
        return await _synthesize_report(state, tools)

    graph.add_node("load_trades", load_trades_node)
    graph.add_node("synthesize_report", synthesize_report_node)

    graph.add_edge(START, "load_trades")
    graph.add_edge("load_trades", "synthesize_report")
    graph.add_edge("synthesize_report", END)
    return graph.compile()


__all__ = ["create_analysis_graph"]
