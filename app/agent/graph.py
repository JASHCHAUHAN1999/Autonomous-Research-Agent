"""LangGraph wiring for the research agent plus the run_research event stream."""
from __future__ import annotations

from typing import AsyncIterator

from langgraph.graph import StateGraph, START, END

from app.agent.state import ResearchState
from app.agent.nodes import (
    plan_node,
    gather_node,
    process_node,
    reflect_node,
    synthesize_node,
    persist_node,
    route_after_reflect,
)


def build_graph():
    """Assemble and compile the research StateGraph.

    Flow: START -> plan -> gather -> process -> reflect
          reflect --(route_after_reflect)--> {gather, synthesize}
          synthesize -> persist -> END
    """
    builder = StateGraph(ResearchState)

    builder.add_node("plan", plan_node)
    builder.add_node("gather", gather_node)
    builder.add_node("process", process_node)
    builder.add_node("reflect", reflect_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("persist", persist_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "gather")
    builder.add_edge("gather", "process")
    builder.add_edge("process", "reflect")
    builder.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {"gather": "gather", "synthesize": "synthesize"},
    )
    builder.add_edge("synthesize", "persist")
    builder.add_edge("persist", END)

    return builder.compile()


def _node_detail(node: str, update: dict | None) -> str:
    """Build a short, human-readable detail string for a node event."""
    update = update or {}
    if node == "plan":
        plan = update.get("plan") or {}
        srcs = plan.get("sources") if isinstance(plan, dict) else None
        if srcs:
            return "sources: " + ", ".join(srcs)
        return "planning"
    if node == "gather":
        n = len(update.get("raw_results") or [])
        return f"gathered {n} results (iteration {update.get('iteration')})"
    if node == "process":
        n = len(update.get("clean_results") or [])
        return f"kept {n} results"
    if node == "reflect":
        refl = update.get("reflection") or {}
        if isinstance(refl, dict):
            return f"enough={refl.get('enough')}"
        return "reflecting"
    if node == "synthesize":
        md = update.get("report_markdown") or ""
        return f"drafted report ({len(md)} chars)"
    if node == "persist":
        return f"saved run {update.get('run_id')}"
    return node


async def run_research(
    query: str,
    provider: str | None = None,
    model: str | None = None,
    sources: list[str] | None = None,
    api_key: str | None = None,
    source_keys: dict | None = None,
) -> AsyncIterator[dict]:
    """Drive the graph and yield SSE-friendly event dicts.

    Yields one {"type":"node", ...} per executed node, then a single
    {"type":"report", ...}, then {"type":"done"}. Any exception is surfaced
    as a single {"type":"error", "message": str(e)} event.
    """
    try:
        graph = build_graph()

        state: ResearchState = {
            "query": query,
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "source_keys": source_keys or {},
            "iteration": 0,
            "raw_results": [],
            "clean_results": [],
            "errors": [],
        }
        if sources:
            # Thread the user's explicit source choice into state. plan_node
            # constrains itself to these (that are actually available) while the
            # LLM still generates the subqueries. Priming state["plan"] directly
            # would be clobbered by plan_node's fresh return (last-write-wins).
            state["requested_sources"] = list(sources)

        final_state: dict = dict(state)
        async for chunk in graph.astream(state):
            # In the default "updates" stream mode each chunk is
            # {node_name: partial_state_update}.
            for node_name, update in chunk.items():
                if update:
                    final_state.update(update)
                yield {
                    "type": "node",
                    "node": node_name,
                    "detail": _node_detail(node_name, update),
                }

        yield {
            "type": "report",
            "markdown": final_state.get("report_markdown") or "",
            "run_id": final_state.get("run_id"),
        }
        yield {"type": "done"}
    except Exception as e:  # surface any failure as a stream event
        yield {"type": "error", "message": str(e)}
