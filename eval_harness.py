"""
Automated verification and evaluation harness for the Deep Research Agent.

Runs agent_engine.execute_agent_turn against a curated benchmark suite,
computes programmatic quality metrics, prints an ASCII summary, and writes
evaluation_report.md.

Usage:
    python eval_harness.py

Requires API keys (LLM + search) identical to production. No agent frameworks.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import agent_engine
import models

logger = logging.getLogger(__name__)

REPORT_PATH = "evaluation_report.md"


# Citation & calibration patterns (aligned with agent_engine guardrails)


# Markdown link: [Title — domain](https://example.com/path)
RE_MD_CITATION = re.compile(
    r"\[[^\]]+\]\(\s*(https?://[^\s)]+)\s*\)",
    re.IGNORECASE,
)

# Parenthetical: (domain, https://example.com/path)
RE_PAREN_CITATION = re.compile(
    r"\(\s*[^,()]+\s*,\s*(https?://[^\s)]+)\s*\)",
    re.IGNORECASE,
)

RE_UNCERTAINTY = re.compile(
    r"\b("
    r"uncertain|uncertainty|insufficient evidence|insufficient data|"
    r"not enough evidence|could not find|unable to verify|cannot verify|"
    r"missing information|further search|more research needed|"
    r"limited information|no reliable source|cannot confirm|"
    r"no clear documentation|sparse evidence|lack of evidence|"
    r"hallucinat"  # flag if model warns against hallucination
    r")\b",
    re.IGNORECASE,
)

RE_CONFLICT_HANDLING = re.compile(
    r"\b("
    r"conflict|contradict|contradiction|disagree|discrepancy|mixed evidence|"
    r"on the other hand|however|sources differ|competing claims|"
    r"while .+ reports|whereas|in contrast|debate|both sides"
    r")\b",
    re.IGNORECASE,
)

RE_MULTI_TURN_MEMORY = re.compile(
    r"\b(earlier|previous|our discussion|this session|as noted|as mentioned|"
    r"above|prior turn|follow[- ]?up)\b",
    re.IGNORECASE,
)

# Phrases that negate a regex hit inside a local context window (±40 chars).
UNCERTAINTY_NEGATIONS = [
    "no uncertainty",
    "without uncertainty",
    "not uncertain",
    "zero uncertainty",
    "no insufficient evidence",
    "not insufficient",
    "no lack of evidence",
    "without evidence gaps",
]

CONFLICT_NEGATIONS = [
    "no conflict",
    "without conflict",
    "not conflict",
    "zero conflict",
    "no contradiction",
    "without contradiction",
    "no discrepancy",
    "not disagree",
    "no debate",
    "sources do not differ",
    "no mixed evidence",
]

CONTEXT_WINDOW_CHARS = 40



# Benchmark dataset (5 distinct stress tests)



@dataclass
class BenchmarkCase:
    """One evaluation scenario."""

    case_id: str
    category: str
    query: str
    description: str
    expects_uncertainty: bool = False
    expects_conflict_handling: bool = False
    is_multi_turn: bool = False
    follow_up_query: Optional[str] = None
    expected_keywords: list[str] = field(default_factory=list)


BENCHMARK_DATASET: list[BenchmarkCase] = [
    BenchmarkCase(
        case_id="temporal_2025_2026",
        category="Factual / Temporal",
        query=(
            "What were the three largest technology sector corporate acquisitions announced in "
            "Q1 2026, and what were their publicly disclosed deal values in USD?"
        ),
        description=(
            "Requires recent 2025/2026 web evidence; tests recency of search, "
            "fetch, and citation of up-to-date sources."
        ),
        expected_keywords=["Hg Capital", "OneStream", "SpaceX", "xAI"],
    ),
    BenchmarkCase(
        case_id="multi_hop_policy",
        category="Multi-hop",
        query=(
            "How did the EU AI Act enforcement timeline in 2025 affect "
            "open-source LLM deployment by European healthcare startups, and "
            "what compliance tooling emerged in response?"
        ),
        description=(
            "Forces the planner to issue multiple distinct search angles "
            "(policy, healthcare AI, compliance vendors)."
        ),
        expected_keywords=["AI Act", "Healthcare", "Compliance", "Startups"],
    ),
    BenchmarkCase(
        case_id="comparison_ev_vs_h2",
        category="Comparison",
        query=(
            "Compare battery electric trucks versus hydrogen fuel-cell trucks for "
            "long-haul freight in 2025–2026 across cost, infrastructure readiness, "
            "and lifecycle emissions. Cite specific sources for each dimension."
        ),
        description=(
            "Side-by-side comparison requiring multiple evidence strands and "
            "balanced citation across both technologies."
        ),
    ),
    BenchmarkCase(
        case_id="conflicting_sources",
        category="Conflicting Sources",
        query=(
            "Is intermittent fasting more effective than caloric restriction for "
            "long-term weight maintenance according to recent clinical evidence?"
        ),
        description=(
            "Controversial topic where top results often disagree; tests explicit "
            "conflict callouts and dual-source citation."
        ),
        expects_conflict_handling=True,
    ),
    BenchmarkCase(
        case_id="insufficient_evidence",
        category="Insufficient Evidence",
        query=(
            "What was the exact monthly active user count for the closed-beta "
            "social network 'NebulaThread' operating only in Antarctica as of "
            "March 2026?"
        ),
        description=(
            "Obscure fictional/niche target with no authoritative public data; "
            "tests uncertainty calibration vs hallucination."
        ),
        expects_uncertainty=True,
    ),
    BenchmarkCase(
        case_id="multi_turn_memory",
        category="Multi-turn Session",
        query=(
            "Summarize the current state of perovskite solar cell commercial "
            "deployment as of 2025–2026, naming specific companies and pilot projects."
        ),
        follow_up_query=(
            "Based on our earlier discussion in this session, which companies you "
            "mentioned are most likely to reach grid-scale deployment first, and why?"
        ),
        description=(
            "Two sequential turns in one session_id; tests SQLite session memory "
            "and contextual follow-up answers."
        ),
        is_multi_turn=True,
    ),
]



# Turn capture & metric computation



@dataclass
class TurnCapture:
    """Raw artifacts collected from one execute_agent_turn stream."""

    session_id: str
    query: str
    success: bool = False
    error_message: str = ""
    final_answer: str = ""
    search_queries: list[str] = field(default_factory=list)
    urls_opened: list[str] = field(default_factory=list)
    snippets: list[dict[str, Any]] = field(default_factory=list)
    planning_query_count: int = 0
    research_plan: str = ""
    elapsed_seconds: float = 0.0
    chars_ingested: int = 0
    chars_yielded: int = 0
    delta_token_events: int = 0


@dataclass
class TurnMetrics:
    """Programmatic scores for a single completed (or failed) turn."""

    case_id: str
    category: str
    session_id: str
    query: str
    success: bool
    error_message: str
    elapsed_seconds: float
    chars_ingested: int
    chars_yielded: int
    ingest_yield_ratio: float
    citation_count: int
    citation_density_per_1k: float
    cited_urls: list[str]
    grounding_failures: list[str]
    grounding_integrity_score: float
    expressed_uncertainty: bool
    handled_conflict: bool
    showed_session_memory: bool
    search_queries: list[str]
    urls_opened: list[str]
    research_plan: str = ""
    has_plan: bool = False
    answer_excerpt: str = ""
    full_answer: str = ""
    factual_coverage_score: float = 0.0
    expected_keywords: list[str] = field(default_factory=list)


def _normalize_url(url: str) -> str:
    """Canonicalize URLs for set comparisons."""
    url = url.strip().rstrip(".,);]")
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or ""
        return urlunparse((scheme, netloc, path, "", "", ""))
    except Exception:
        return url.lower()


def _extract_cited_urls(answer: str) -> list[str]:
    urls: list[str] = []
    for pattern in (RE_MD_CITATION, RE_PAREN_CITATION):
        for match in pattern.finditer(answer):
            urls.append(match.group(1))
    # Preserve order, dedupe normalized
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in urls:
        norm = _normalize_url(raw)
        if norm not in seen:
            seen.add(norm)
            ordered.append(raw)
    return ordered


def _allowed_source_urls(urls_opened: list[str], snippets: list[dict[str, Any]]) -> set[str]:
    allowed: set[str] = set()
    for u in urls_opened:
        if u:
            allowed.add(_normalize_url(str(u)))
    for sn in snippets:
        u = sn.get("url")
        if u:
            allowed.add(_normalize_url(str(u)))
    return allowed


def _count_citations(answer: str) -> int:
    md_hits = len(RE_MD_CITATION.findall(answer))
    paren_hits = len(RE_PAREN_CITATION.findall(answer))
    return md_hits + paren_hits


def _verify_semantic_context(
    text: str,
    pattern: re.Pattern[str],
    negative_keywords: list[str],
    *,
    window_chars: int = CONTEXT_WINDOW_CHARS,
) -> bool:
    """
    Return True if pattern matches at least once outside negated phrasing.

    Inspects ±window_chars around each match and rejects hits when negation
    phrases (e.g. "no conflict", "without uncertainty") appear in that window.
    """
    if not text.strip():
        return False
    lowered_negations = [n.lower() for n in negative_keywords]
    for match in pattern.finditer(text):
        start = max(0, match.start() - window_chars)
        end = min(len(text), match.end() + window_chars)
        window = text[start:end].lower()
        if any(neg in window for neg in lowered_negations):
            continue
        return True
    return False


def _factual_coverage_score(answer: str, expected_keywords: list[str]) -> float:
    """Fraction of expected factual anchors mentioned in the answer."""
    if not expected_keywords:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in answer_lower)
    return round(hits / len(expected_keywords), 3)


def _compute_chars_ingested(snippets: list[dict[str, Any]], search_snippets: int = 0) -> int:
    total = search_snippets
    for sn in snippets:
        total += len(str(sn.get("text", "")))
    return total


def compute_turn_metrics(
    case: BenchmarkCase,
    capture: TurnCapture,
    *,
    check_memory: bool = False,
) -> TurnMetrics:
    answer = capture.final_answer
    cited = _extract_cited_urls(answer)
    citation_count = _count_citations(answer)
    answer_len = max(len(answer), 1)
    density = (citation_count / answer_len) * 1000.0

    allowed = _allowed_source_urls(capture.urls_opened, capture.snippets)
    grounding_failures: list[str] = []
    for url in cited:
        if _normalize_url(url) not in allowed:
            grounding_failures.append(url)

    if citation_count == 0:
        integrity = 1.0 if not cited else 0.0
    elif not grounding_failures:
        integrity = 1.0
    else:
        integrity = max(
            0.0,
            1.0 - (len(grounding_failures) / max(citation_count, 1)),
        )

    expressed_uncertainty = _verify_semantic_context(
        answer, RE_UNCERTAINTY, UNCERTAINTY_NEGATIONS
    )
    handled_conflict = _verify_semantic_context(
        answer, RE_CONFLICT_HANDLING, CONFLICT_NEGATIONS
    )
    showed_memory = bool(RE_MULTI_TURN_MEMORY.search(answer)) if check_memory else False
    factual_score = _factual_coverage_score(answer, case.expected_keywords)

    ingest = max(capture.chars_ingested, 1)
    ratio = capture.chars_yielded / ingest

    return TurnMetrics(
        case_id=case.case_id,
        category=case.category,
        session_id=capture.session_id,
        query=capture.query,
        success=capture.success,
        error_message=capture.error_message,
        elapsed_seconds=capture.elapsed_seconds,
        chars_ingested=capture.chars_ingested,
        chars_yielded=capture.chars_yielded,
        ingest_yield_ratio=round(ratio, 3),
        citation_count=citation_count,
        citation_density_per_1k=round(density, 2),
        cited_urls=cited,
        grounding_failures=grounding_failures,
        grounding_integrity_score=round(integrity, 3),
        expressed_uncertainty=expressed_uncertainty,
        handled_conflict=handled_conflict,
        showed_session_memory=showed_memory,
        search_queries=list(capture.search_queries),
        urls_opened=list(capture.urls_opened),
        research_plan=capture.research_plan,
        has_plan=bool(capture.research_plan.strip()),
        answer_excerpt=answer[:400] + ("…" if len(answer) > 400 else ""),
        full_answer=answer,
        factual_coverage_score=factual_score,
        expected_keywords=list(case.expected_keywords),
    )


async def consume_agent_turn(
    session_id: str,
    query: str,
    *,
    max_context_chars: int = 12000,
    max_evidence_chars: int = 8000,
) -> TurnCapture:
    """
    Drive execute_agent_turn to completion and accumulate stream artifacts.
    """
    capture = TurnCapture(session_id=session_id, query=query)
    start = time.perf_counter()
    accumulated = ""

    try:
        async for event in agent_engine.execute_agent_turn(
            session_id,
            query,
            max_context_chars=max_context_chars,
            max_evidence_chars=max_evidence_chars,
        ):
            step = str(event.get("step", ""))

            if step == "planning":
                capture.research_plan = str(event.get("plan") or "")
                queries = event.get("queries") or []
                capture.search_queries = [str(q) for q in queries]
                capture.planning_query_count = len(capture.search_queries)

            elif step == "searching":
                capture.urls_opened = [str(u) for u in (event.get("urls") or [])]

            elif step == "context_acquired":
                capture.snippets = list(event.get("chunks") or [])
                opened = event.get("urls_opened") or capture.urls_opened
                capture.urls_opened = [str(u) for u in opened]
                capture.chars_ingested = _compute_chars_ingested(capture.snippets)

            elif step == "generating_answer":
                delta = str(event.get("delta", ""))
                accumulated += delta
                capture.delta_token_events += 1

            elif step == "turn_complete":
                capture.final_answer = str(event.get("final_answer") or accumulated)
                capture.success = True

            elif step == "error":
                capture.error_message = str(event.get("message", "Unknown error"))
                capture.success = False
                break

        if not capture.success and not capture.error_message:
            if accumulated.strip():
                capture.final_answer = accumulated
                capture.success = True
            else:
                capture.error_message = "Turn ended without turn_complete or error."

    except Exception as exc:
        capture.success = False
        capture.error_message = str(exc)
        logger.exception("consume_agent_turn failed")

    capture.elapsed_seconds = round(time.perf_counter() - start, 2)
    if not capture.final_answer:
        capture.final_answer = accumulated
    capture.chars_yielded = len(capture.final_answer)
    if capture.chars_ingested == 0 and capture.snippets:
        capture.chars_ingested = _compute_chars_ingested(capture.snippets)

    return capture



# Benchmark execution loop



def _eval_budgets() -> tuple[int, int]:
    ctx = int(os.environ.get("EVAL_MAX_CONTEXT_CHARS", "12000"))
    ev = int(os.environ.get("EVAL_MAX_EVIDENCE_CHARS", "8000"))
    return ctx, ev


async def run_benchmark_case(case: BenchmarkCase) -> list[TurnMetrics]:
    """
    Execute one benchmark entry (single turn or multi-turn) and return metrics.
    """
    session_id = f"eval-{case.case_id}-{uuid.uuid4().hex[:8]}"
    results: list[TurnMetrics] = []

    logger.info("Running case %s (%s)", case.case_id, case.category)
    max_ctx, max_ev = _eval_budgets()
    capture = await consume_agent_turn(
        session_id,
        case.query,
        max_context_chars=max_ctx,
        max_evidence_chars=max_ev,
    )
    metrics = compute_turn_metrics(case, capture, check_memory=False)
    results.append(metrics)

    if case.is_multi_turn and case.follow_up_query:
        await asyncio.sleep(0.5)  # brief pause between turns
        follow_capture = await consume_agent_turn(
            session_id,
            case.follow_up_query,
            max_context_chars=max_ctx,
            max_evidence_chars=max_ev,
        )
        follow_metrics = compute_turn_metrics(
            case,
            follow_capture,
            check_memory=True,
        )
        # Annotate follow-up row distinctly in report tables.
        follow_metrics.case_id = f"{case.case_id}_followup"
        follow_metrics.query = case.follow_up_query
        results.append(follow_metrics)

    return results


async def run_evaluation_suite() -> list[TurnMetrics]:
    """Iterate all benchmark cases sequentially (non-blocking async I/O)."""
    all_metrics: list[TurnMetrics] = []
    for case in BENCHMARK_DATASET:
        case_metrics = await run_benchmark_case(case)
        all_metrics.extend(case_metrics)
    return all_metrics



# Reporting



def _fmt_bool(value: bool) -> str:
    return "yes" if value else "no"


def _ascii_table(rows: list[list[str]], headers: list[str]) -> str:
    """Render a simple fixed-width ASCII table without third-party deps."""
    cols = list(zip(*([headers] + rows))) if rows else [headers]
    widths = [max(len(str(cell)) for cell in col) for col in cols]
    lines: list[str] = []

    def _row(cells: list[str]) -> str:
        return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells))

    sep = "-+-".join("-" * w for w in widths)
    lines.append(_row(headers))
    lines.append(sep)
    for row in rows:
        lines.append(_row(row))
    return "\n".join(lines)


def print_console_summary(metrics: list[TurnMetrics]) -> None:
    headers = [
        "Case",
        "OK",
        "Time(s)",
        "Facts",
        "Cit/1k",
        "Ground",
        "Uncert",
        "Conflict",
        "In→Out",
    ]
    rows: list[list[str]] = []
    for m in metrics:
        rows.append(
            [
                m.case_id[:22],
                _fmt_bool(m.success),
                f"{m.elapsed_seconds:.1f}",
                f"{m.factual_coverage_score:.2f}",
                f"{m.citation_density_per_1k:.1f}",
                f"{m.grounding_integrity_score:.2f}",
                _fmt_bool(m.expressed_uncertainty),
                _fmt_bool(m.handled_conflict),
                f"{m.ingest_yield_ratio:.2f}",
            ]
        )
    print("\n=== Deep Research Agent — Evaluation Summary ===\n")
    print(_ascii_table(rows, headers))
    print()

    # Calibration callouts
    for m in metrics:
        case = next((c for c in BENCHMARK_DATASET if m.case_id.startswith(c.case_id)), None)
        if case and case.expected_keywords and m.success:
            status = "PASS" if m.factual_coverage_score >= 0.5 else "FAIL"
            print(
                f"[{status}] Factual coverage ({m.factual_coverage_score:.2f}) — {m.case_id}"
            )
        if case and case.expects_uncertainty and m.success:
            status = "PASS" if m.expressed_uncertainty else "FAIL"
            print(f"[{status}] Uncertainty calibration — {m.case_id}")
        if case and case.expects_conflict_handling and m.success:
            status = "PASS" if m.handled_conflict else "FAIL"
            print(f"[{status}] Conflict handling — {m.case_id}")
        if m.case_id.endswith("_followup") and m.success:
            status = "PASS" if m.showed_session_memory else "WARN"
            print(f"[{status}] Session memory heuristic — {m.case_id}")


def write_markdown_report(metrics: list[TurnMetrics]) -> str:
    """Build and persist evaluation_report.md; return file path."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_time = sum(m.elapsed_seconds for m in metrics)
    successes = sum(1 for m in metrics if m.success)
    avg_density = (
        sum(m.citation_density_per_1k for m in metrics if m.success) / max(successes, 1)
    )
    avg_grounding = (
        sum(m.grounding_integrity_score for m in metrics if m.success) / max(successes, 1)
    )
    factual_scored = [m for m in metrics if m.success and m.expected_keywords]
    avg_factual = (
        sum(m.factual_coverage_score for m in factual_scored) / max(len(factual_scored), 1)
    )

    lines: list[str] = [
        "# Deep Research Agent — Evaluation Report",
        "",
        f"**Generated:** {ts}  ",
        f"**Harness:** `eval_harness.py`  ",
        f"**Turns executed:** {len(metrics)}  ",
        f"**Successful turns:** {successes}/{len(metrics)}  ",
        f"**Total wall time:** {total_time:.1f}s  ",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mean citation density (per 1k chars) | {avg_density:.2f} |",
        f"| Mean grounding integrity score | {avg_grounding:.3f} |",
        f"| Mean factual coverage (keyword cases) | {avg_factual:.3f} |",
        f"| Mean ingest→yield ratio | "
        f"{(sum(m.ingest_yield_ratio for m in metrics if m.success) / max(successes, 1)):.3f} |",
        "",
        "## Performance Matrix",
        "",
        "| Case | Category | Success | Time (s) | Factual | Citations | Density/1k | "
        "Grounding | Ingest chars | Yield chars | Ratio |",
        "|------|----------|---------|----------|---------|-----------|------------|"
        "|-----------|--------------|-------------|-------|",
    ]

    for m in metrics:
        lines.append(
            f"| {m.case_id} | {m.category} | {_fmt_bool(m.success)} | "
            f"{m.elapsed_seconds:.1f} | {m.factual_coverage_score:.3f} | "
            f"{m.citation_count} | "
            f"{m.citation_density_per_1k:.2f} | {m.grounding_integrity_score:.3f} | "
            f"{m.chars_ingested} | {m.chars_yielded} | {m.ingest_yield_ratio:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Citation Integrity Breakdown",
            "",
        ]
    )

    for m in metrics:
        lines.append(f"### `{m.case_id}`")
        lines.append("")
        if not m.success:
            lines.append(f"- **Status:** FAILED — {m.error_message}")
            lines.append("")
            continue
        lines.append(f"- **Query:** {m.query}")
        lines.append(f"- **Citations detected:** {m.citation_count}")
        lines.append(f"- **Citation density (per 1k chars):** {m.citation_density_per_1k:.2f}")
        lines.append(f"- **Grounding integrity score:** {m.grounding_integrity_score:.3f}")
        if m.expected_keywords:
            lines.append(
                f"- **Factual coverage score:** {m.factual_coverage_score:.3f} "
                f"(keywords: {', '.join(m.expected_keywords)})"
            )
        if m.cited_urls:
            lines.append("- **Cited URLs:**")
            for u in m.cited_urls:
                lines.append(f"  - {u}")
        else:
            lines.append("- **Cited URLs:** _(none detected)_")
        if m.grounding_failures:
            lines.append("- **Grounding failures (cited but not fetched):**")
            for u in m.grounding_failures:
                lines.append(f"  - ⚠️ {u}")
        else:
            lines.append("- **Grounding failures:** none")
        lines.append(f"- **Planner queries:** {', '.join(m.search_queries) or '—'}")
        lines.append(f"- **URLs opened:** {len(m.urls_opened)}")
        lines.append("")

    lines.extend(["## Factual Correctness", ""])
    for m in metrics:
        if not m.expected_keywords:
            continue
        lines.append(f"### `{m.case_id}`")
        lines.append("")
        if not m.success:
            lines.append(f"- **Status:** FAILED — {m.error_message}")
        else:
            lines.append(f"- **Factual coverage:** {m.factual_coverage_score:.3f}")
            lines.append(f"- **Expected anchors:** {', '.join(m.expected_keywords)}")
            missing = [
                kw
                for kw in m.expected_keywords
                if kw.lower() not in m.full_answer.lower()
            ]
            if missing:
                lines.append(f"- **Missing keywords:** {', '.join(missing)}")
            else:
                lines.append("- **Missing keywords:** none")
        lines.append("")

    lines.extend(["## Calibration & Conflict Callouts", ""])

    for case in BENCHMARK_DATASET:
        case_metrics = [m for m in metrics if m.case_id.startswith(case.case_id)]
        if not case_metrics:
            continue
        lines.append(f"### {case.category} (`{case.case_id}`)")
        lines.append("")
        lines.append(f"_{case.description}_")
        lines.append("")
        primary = case_metrics[0]
        if case.expects_uncertainty:
            verdict = (
                "✅ Expressed uncertainty/language of doubt detected."
                if primary.expressed_uncertainty
                else "❌ No clear uncertainty markers — possible overconfidence/hallucination risk."
            )
            lines.append(f"- **Uncertainty calibration:** {verdict}")
        if case.expects_conflict_handling:
            verdict = (
                "✅ Conflict/discrepancy language present."
                if primary.handled_conflict
                else "❌ No explicit conflict handling detected — review synthesis prompt adherence."
            )
            lines.append(f"- **Conflicting sources handling:** {verdict}")
        if case.is_multi_turn and len(case_metrics) > 1:
            follow = case_metrics[-1]
            verdict = (
                "✅ Follow-up shows session-memory heuristic markers."
                if follow.showed_session_memory
                else "⚠️ Follow-up may not reference prior session context explicitly."
            )
            lines.append(f"- **Multi-turn memory:** {verdict}")
        if case.expected_keywords:
            verdict = (
                "✅ Factual keyword coverage ≥ 50%."
                if primary.factual_coverage_score >= 0.5
                else "❌ Low factual keyword coverage — answer may be incomplete or off-topic."
            )
            lines.append(f"- **Factual correctness:** {verdict}")
        if (
            not case.expected_keywords
            and not case.expects_uncertainty
            and not case.expects_conflict_handling
            and not case.is_multi_turn
        ):
            lines.append("- **General:** No special calibration flags for this case.")
        lines.append("")

    lines.extend(
        [
            "## Carbon / Efficiency Notes",
            "",
            "_Efficiency proxy: characters ingested from ranked context chunks vs "
            "characters in the final answer (higher ratio = more compact synthesis)._",
            "",
        ]
    )
    for m in metrics:
        if m.success:
            lines.append(
                f"- `{m.case_id}`: ingested **{m.chars_ingested}** → yielded "
                f"**{m.chars_yielded}** (ratio **{m.ingest_yield_ratio:.3f}**, "
                f"**{m.elapsed_seconds:.1f}s**)"
            )

    lines.extend(["", "## Answer Excerpts (first 400 chars)", ""])
    for m in metrics:
        q_preview = (m.query[:80] + "…") if len(m.query) > 80 else m.query
        lines.append(f"### `{m.case_id}` — {q_preview}")
        lines.append("")
        if not m.success:
            lines.append(f"_Error: {m.error_message}_")
        elif m.full_answer:
            lines.append(m.full_answer[:2000])
            if len(m.full_answer) > 2000:
                lines.append("\n_(truncated for report)_")
        elif m.answer_excerpt:
            lines.append(f"> {m.answer_excerpt.replace(chr(10), ' ')}")
        lines.append("")
        if m.research_plan:
            lines.append(f"**Plan excerpt:** {m.research_plan[:500]}")
            lines.append("")

    content = "\n".join(lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(content)
    return REPORT_PATH



# Entry point



async def _async_main() -> int:
    """Initialize DB, run suite, emit reports."""
    db_path = os.environ.get("DEEP_RESEARCH_DB_PATH")
    if db_path:
        models.set_db_path(db_path)

    try:
        models.init_db()
    except Exception as exc:
        print(f"Database init failed: {exc}", file=sys.stderr)
        return 1

    print("Starting Deep Research evaluation harness…", file=sys.stderr)
    print(f"Benchmark cases: {len(BENCHMARK_DATASET)}", file=sys.stderr)

    metrics = await run_evaluation_suite()
    print_console_summary(metrics)
    report_path = write_markdown_report(metrics)
    print(f"\nMarkdown report written to: {report_path}", file=sys.stderr)
    failures = [m for m in metrics if not m.success]
    return 1 if failures else 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    exit_code = asyncio.run(_async_main())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
