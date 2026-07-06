"""System prompts and prompt builders for the research agent."""

from __future__ import annotations

from app.sources.base import SourceResult

PLAN_SYSTEM = (
    "You are the planning module of an autonomous research agent. Given a "
    "user's research query and the list of data sources that are currently "
    "available, decide which sources to use and craft focused search "
    "subqueries for each chosen source.\n"
    "Respond with STRICT JSON only - no prose, no explanations, and no "
    "Markdown code fences. The JSON object must have exactly these keys:\n"
    '  "sources": a list of source names. Every name MUST come from the '
    "available sources you are given - pick a subset, and never invent a "
    "name that is not in that list.\n"
    '  "subqueries": an object mapping each chosen source name to a list of '
    "1-3 query strings. For the \"web\" source, each entry MUST be a full "
    "http(s) URL to fetch, not a search phrase.\n"
    '  "reasoning": a short string explaining why you chose those sources.'
)


def _format_results(results: list[SourceResult]) -> str:
    """Render results as a stable numbered list for filter/reflect/synth."""
    lines: list[str] = []
    for i, r in enumerate(results):
        snippet = (r.content or "")[:500]
        lines.append(
            f"[{i}] source={r.source} | title={r.title} | url={r.url}\n"
            f"{snippet}"
        )
    return "\n\n".join(lines)


def build_plan_prompt(query: str, available: list[str]) -> str:
    return (
        f"Research query:\n{query}\n\n"
        f"Available sources: {', '.join(available)}\n\n"
        "Choose a subset of the available sources listed above and write "
        "subqueries for each. Remember: every name in 'sources' must appear "
        "in the available list, and for the 'web' source the subqueries must "
        "be full URLs. Return strict JSON with the keys sources, subqueries, "
        "and reasoning."
    )


FILTER_SYSTEM = (
    "You are the relevance-filtering module of a research agent. You are "
    "given a research query and a numbered list of candidate results. Decide "
    "which results are relevant and useful enough to keep for writing the "
    "report.\n"
    "Respond with STRICT JSON only - no prose and no Markdown code fences - "
    'as an object with a single key "keep" whose value is a list of the '
    "integer indices (0-based, matching the numbers in brackets) of the "
    "results to keep."
)


def build_filter_prompt(query: str, results: list[SourceResult]) -> str:
    return (
        f"Research query:\n{query}\n\n"
        f"Candidate results:\n{_format_results(results)}\n\n"
        'Return strict JSON of the form {"keep": [list of indices to keep]}.'
    )


REFLECT_SYSTEM = (
    "You are the reflection module of a research agent. Given the research "
    "query and the results gathered so far, judge whether the material is "
    "sufficient to write a thorough, well-supported report.\n"
    "Respond with STRICT JSON only - no prose and no Markdown code fences - "
    "as an object with exactly these keys:\n"
    '  "enough": a boolean, true if the results are sufficient.\n'
    '  "gaps": a list of short strings naming information that is still '
    "missing (use an empty list when enough is true)."
)


def build_reflect_prompt(query: str, results: list[SourceResult]) -> str:
    return (
        f"Research query:\n{query}\n\n"
        f"Results gathered so far:\n{_format_results(results)}\n\n"
        'Return strict JSON of the form {"enough": bool, "gaps": [strings]}.'
    )


SYNTH_SYSTEM = (
    "You are the synthesis module of a research agent. Using ONLY the "
    "provided results, write a clear, well-structured research report in "
    "GitHub-flavored Markdown. The report MUST contain these four sections, "
    "each introduced by a Markdown '##' heading, in this exact order:\n"
    "## Key Points\n"
    "## Important Findings\n"
    "## References / Sources\n"
    "## Actionable Insights\n"
    "List the sources you used, with their URLs, under 'References / "
    "Sources'. Do not fabricate facts that are not supported by the provided "
    "results."
)


def build_synth_prompt(query: str, results: list[SourceResult]) -> str:
    return (
        f"Research query:\n{query}\n\n"
        f"Results to synthesize:\n{_format_results(results)}\n\n"
        "Write the Markdown report now. It must include the sections "
        "Key Points, Important Findings, References / Sources, and "
        "Actionable Insights, in that order."
    )
