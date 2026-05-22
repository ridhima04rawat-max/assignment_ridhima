"""
Asynchronous orchestration engine for the Deep Research Agent.

Coordinates persistence (models.py) and web research (research_tools.py) with a
provider-flexible LLM client. No agent frameworks, pure asyncio + OpenAI-compatible APIs.

Importing this module has no side effects.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import uuid
import openai
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal, Optional

import models
import research_tools

logger = logging.getLogger(__name__)

Provider = Literal["gemini", "openai", "groq"]

# Provider-specific defaults; override globally via LLM_MODEL_NAME.
DEFAULT_MODELS: dict[Provider, str] = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
}

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"

MAX_SEARCH_URLS = 6
SEARCH_RESULTS_PER_QUERY = 5


# Grounding & citation system prompt (synthesis step only)


SYNTHESIS_SYSTEM_PROMPT = """You are a meticulous Deep Research synthesis assistant.

Your job is to write a clear, well-structured answer using ONLY the evidence provided
in the user's message (retrieved web snippets). Do not invent facts, statistics, quotes,
or URLs that are not supported by the supplied sources.

NON-NEGOTIABLE CITATION RULES:
- Every factual claim, statistic, date, or attributed statement MUST include an inline
  hyperlink citation in one of these formats exactly:
    [Title — domain](URL)
    or (domain, URL)
- Do NOT use numeric footnotes like [1], [2], or bare [source] tags.
- If a claim cannot be tied to a provided snippet, say so explicitly instead of citing.

CONFLICT HANDLING:
- When sources disagree on numbers, dates, rankings, or conclusions, you MUST name the
  disagreement explicitly and cite BOTH (or all) conflicting sources with their links.
  Example pattern: "Source A reports X ([Title A — domain](URL)), while Source B reports
  Y ([Title B — domain](URL))."

UNCERTAINTY & GAPS:
- If evidence is thin, outdated, ambiguous, or missing for part of the question, state
  the uncertainty clearly. Propose 2–3 concrete next search queries that would reduce
  the gap. Do not pretend confidence you do not have.
- If the retrieved web snippets do not contain enough factual information to conclusively 
  answer the user's question, you MUST explicitly state that there is "insufficient evidence" or 
  "uncertainty due to missing data". Do not attempt to guess or hide the limitation.  

STYLE:
- Use markdown headings and bullets where helpful.
- Lead with a concise direct answer, then supporting detail.
- Do not expose internal chain-of-thought, tool logs, or JSON plans in the final answer.
"""

SESSION_SUMMARY_SYSTEM_PROMPT = """You are a session memory compressor for a research assistant.
Summarize the conversation and prior research turns into a concise rolling summary
(<= 400 words) capturing: user goals, key findings, cited sources mentioned, and open questions.
Do not invent facts. Output plain text only."""

RESEARCH_PLAN_SYSTEM_PROMPT = """You are a deep research planner.
Given the user's question and optional session context, output ONLY valid JSON with:
- "plan": a short numbered research plan (3-5 steps) describing search strategy,
  source fetching, and synthesis approach (plain text string).
- "queries": an array of 2 to 3 distinct search-engine query strings.

Example:
{"plan": "1. Identify ...\\n2. Fetch ...\\n3. Compare ...", "queries": ["query a", "query b"]}
"""

__all__ = [
    "LLMConfig",
    "get_llm_client",
    "execute_agent_turn",
    "SYNTHESIS_SYSTEM_PROMPT",
]



# LLM client routing



@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Resolved async LLM client and model name."""

    client: Any  # AsyncOpenAI instance
    model: str
    provider: Provider


def _detect_provider() -> tuple[Provider, str]:
    """Exclusively track Groq API provider for assignment evaluation."""
    if os.environ.get("GROQ_API_KEY", "").strip():
        return "groq", os.environ["GROQ_API_KEY"].strip()
    raise RuntimeError(
        "No GROQ_API_KEY discovered. Please configure your key to continue evaluation."
    )





def get_llm_client() -> LLMConfig:
    """
    Build an async OpenAI-compatible client from environment configuration.

    Priority: GEMINI_API_KEY > OPENAI_API_KEY > GROQ_API_KEY
    Model override: LLM_MODEL_NAME (else provider default).
    """
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "openai package is required. Install with: pip install openai"
        ) from exc

    provider, api_key = _detect_provider()
    model_override = os.environ.get("LLM_MODEL_NAME", "").strip()
    model = model_override or DEFAULT_MODELS[provider]

    if provider == "gemini":
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=GEMINI_OPENAI_BASE_URL,
        )
    elif provider == "groq":
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=GROQ_OPENAI_BASE_URL,
        )
    else:
        client = AsyncOpenAI(api_key=api_key)

    logger.info("LLM client ready: provider=%s model=%s", provider, model)
    return LLMConfig(client=client, model=model, provider=provider)



# Prompt & parsing helpers



def _parse_research_plan_response(raw: str) -> tuple[str, list[str]]:
    """
    Parse planner JSON into (research_plan, search_queries).
    Falls back to query-only list parsing when needed.
    """
    text = raw.strip()
    if not text:
        return "", []

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            plan = str(parsed.get("plan") or "").strip()
            queries_raw = parsed.get("queries") or parsed.get("search_queries") or []
            if isinstance(queries_raw, list):
                queries = [str(q).strip() for q in queries_raw if str(q).strip()]
                return plan, queries
    except json.JSONDecodeError:
        pass

    return "", _parse_json_string_list(raw)


def _parse_json_string_list(raw: str) -> list[str]:
    """
    Parse LLM output into a list of query strings.
    Handles markdown fences and embedded JSON arrays.
    """
    text = raw.strip()
    if not text:
        return []

    # Strip ```json ... ``` or ``` ... ``` wrappers.
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass

    # Fallback: first JSON array substring in the response.
    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        try:
            parsed = json.loads(array_match.group(0))
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass

    # Last resort: quoted strings on separate lines.
    quoted = re.findall(r'"([^"]{3,200})"', text)
    if quoted:
        return [q.strip() for q in quoted[:3]]

    return []


def _clamp_search_queries(queries: list[str], user_query: str) -> list[str]:
    """Ensure 2–3 queries; pad or trim as needed."""
    cleaned = [q for q in queries if q]
    if not cleaned:
        cleaned = [user_query]
    if len(cleaned) == 1:
        cleaned.append(f"{user_query} latest research overview")
    if len(cleaned) > 3:
        cleaned = cleaned[:3]
    return cleaned


def _format_context_for_plan(payload: dict[str, Any]) -> str:
    """Compact session context for the search-planning prompt."""
    lines: list[str] = []
    for msg in payload.get("messages", [])[-8:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
    for turn in payload.get("research_turns", [])[-2:]:
        lines.append(f"PRIOR RESEARCH QUERY: {turn.get('query', '')}")
        plan = str(turn.get("research_plan", ""))[:250]
        if plan:
            lines.append(f"PRIOR PLAN: {plan}")
        answer = str(turn.get("final_answer", ""))[:400]
        if answer:
            lines.append(f"PRIOR ANSWER EXCERPT: {answer}")
    if payload.get("rolling_summary"):
        lines.append(f"ROLLING SUMMARY: {payload['rolling_summary']}")
    if payload.get("truncation_notes"):
        lines.append(f"NOTE: {payload['truncation_notes'][0]}")
    return "\n".join(lines) if lines else "(no prior history)"


def _format_synthesis_conversation_history(
    payload: dict[str, Any],
    current_query: str,
) -> str:
    """
    Build conversation history for synthesis (excludes the current user message).
    """
    lines: list[str] = []
    current_norm = current_query.strip()
    for msg in payload.get("messages", []):
        role = str(msg.get("role", "user"))
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if role == "user" and content == current_norm:
            continue
        lines.append(f"**{role.upper()}:** {content}")
    return "\n\n".join(lines)


def _format_snippets_markdown(chunks: list[dict[str, Any]]) -> str:
    """Structured evidence blocks for the synthesis prompt."""
    if not chunks:
        return "_No web evidence was retrieved for this turn._"

    blocks: list[str] = []
    for i, ch in enumerate(chunks, 1):
        title = ch.get("title") or "Untitled"
        url = ch.get("url") or ""
        domain = ch.get("domain") or ""
        score = ch.get("score", 0.0)
        text = str(ch.get("text", "")).strip()
        blocks.append(
            f"### Source {i}: {title}\n"
            f"- **URL:** {url}\n"
            f"- **Domain:** {domain}\n"
            f"- **Relevance score:** {score}\n\n"
            f"{text}\n"
        )
    return "\n---\n".join(blocks)



async def _llm_complete(
    llm: LLMConfig,
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
) -> str:
    """Non-streaming chat completion."""
    response = await llm.client.chat.completions.create(
        model=llm.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    choice = response.choices[0].message
    return str(choice.content or "").strip()






async def _llm_stream_deltas(
    llm: LLMConfig,
    *,
    system: str,
    user: str,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """Streaming chat completion; yields text deltas only."""
    stream = await llm.client.chat.completions.create(
        model=llm.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            yield delta.content



# Research pipeline helpers



async def _run_searches_parallel(queries: list[str]) -> list[dict[str, Any]]:
    """Offload synchronous execute_web_search to a thread per query."""

    async def _one(q: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            research_tools.execute_web_search,
            q,
            SEARCH_RESULTS_PER_QUERY,
        )

    batches = await asyncio.gather(*[_one(q) for q in queries], return_exceptions=True)
    combined: list[dict[str, Any]] = []
    for batch in batches:
        if isinstance(batch, BaseException):
            logger.warning("Search batch failed: %s", batch)
            continue
        combined.extend(batch)
    return combined


def _dedupe_urls(
    search_hits: list[dict[str, Any]],
    *,
    max_urls: int = MAX_SEARCH_URLS,
) -> tuple[list[str], dict[str, str]]:
    """
    Return unique URLs (preserving best rank) and a url -> title map.
    """
    seen: set[str] = set()
    urls: list[str] = []
    title_by_url: dict[str, str] = {}

    for hit in search_hits:
        url = str(hit.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        title = str(hit.get("title") or "").strip()
        if title:
            title_by_url[url] = title
        if len(urls) >= max_urls:
            break

    return urls, title_by_url


def _inject_title_hints(
    pages: list[dict[str, Any]],
    title_by_url: dict[str, str],
) -> list[dict[str, Any]]:
    for page in pages:
        url = str(page.get("url") or "")
        if url and not str(page.get("title") or "").strip():
            hint = title_by_url.get(url, "")
            if hint:
                page["title"] = hint
    return pages



# State machine: execute_agent_turn



async def execute_agent_turn(
    session_id: str,
    user_query: str,
    *,
    max_context_chars: int = 12000,
    max_evidence_chars: int = 8000,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Run one full deep-research turn and yield JSON-serializable progress events.

    Event steps (in order):
      initializing -> planning -> searching -> context_acquired ->
      generating_answer (many deltas) -> turn_complete
    On failure: {"step": "error", "message": "..."}
    """
    user_query = user_query.strip()
    if not user_query:
        yield {"step": "error", "message": "user_query must not be empty"}
        return

    # Turn-scoped accumulators (safe if an exception fires mid-pipeline).
    generated_queries: list[str] = []
    research_plan: str = ""
    urls_opened: list[str] = []
    selected_chunks: list[dict[str, Any]] = []
    accumulated_answer = ""
    max_context_chars = max(4000, min(max_context_chars, 20000))
    max_evidence_chars = max(2000, min(max_evidence_chars, 16000))

    try:
        llm = get_llm_client()
    except Exception as exc:
        logger.error("LLM initialization failed: %s", exc)
        yield {"step": "error", "message": f"LLM initialization failed: {exc}"}
        return

    # Step 1: Save user prompt & load context 
    try:
        await asyncio.to_thread(models.save_message, session_id, "user", user_query)
        def _load_context() -> dict[str, Any]:
            return models.build_context_payload(
                session_id,
                max_context_chars,
                focus_query=user_query,
            )

        context_payload = await asyncio.to_thread(_load_context)
        yield {
            "step": "initializing",
            "message": "Initialized session context database.",
        }
    except Exception as exc:
        logger.exception("Step 1 failed for session %s", session_id)
        yield {"step": "error", "message": f"Context initialization failed: {exc}"}
        return

    # Step 2: Generate search plan 
    try:
        history_text = _format_context_for_plan(context_payload)
        plan_user = (
            f"USER QUESTION:\n{user_query}\n\n"
            f"CONVERSATION / PRIOR RESEARCH CONTEXT:\n{history_text}\n\n"
            'Return JSON with keys "plan" and "queries" (2-3 search strings).'
        )
        raw_plan = await _llm_complete(
            llm,
            system=RESEARCH_PLAN_SYSTEM_PROMPT,
            user=plan_user,
            temperature=0.1,
        )
        research_plan, parsed_queries = _parse_research_plan_response(raw_plan)
        if not research_plan:
            research_plan = (
                "1. Issue targeted web searches for the user question.\n"
                "2. Fetch and rank page content for relevance and recency.\n"
                "3. Synthesize a cited answer and note conflicts or gaps."
            )
        generated_queries = _clamp_search_queries(parsed_queries, user_query)
        yield {
            "step": "planning",
            "plan": research_plan,
            "queries": generated_queries,
        }
    except Exception as exc:
        logger.exception("Step 2 failed for session %s", session_id)
        yield {"step": "error", "message": f"Search planning failed: {exc}"}
        return

    #  Step 3: Concurrent web searches (thread-offloaded) 
    try:
        search_hits = await _run_searches_parallel(generated_queries)
        urls_opened, title_by_url = _dedupe_urls(search_hits, max_urls=MAX_SEARCH_URLS)
        yield {"step": "searching", "urls": urls_opened}
    except Exception as exc:
        logger.exception("Step 3 failed for session %s", session_id)
        yield {"step": "error", "message": f"Web search failed: {exc}"}
        return

    if not urls_opened:
        yield {
            "step": "error",
            "message": (
                "No search URLs returned. Configure SERPER_API_KEY or TAVILY_API_KEY."
            ),
        }
        return

    # Step 4: Fetch pages & select optimal context 
    try:
        fetched_pages = await research_tools.fetch_page_content_async(urls_opened)
        fetched_pages = _inject_title_hints(fetched_pages, title_by_url)
        pages_with_text = [p for p in fetched_pages if str(p.get("text") or "").strip()]

        selected_chunks = research_tools.select_optimal_context(
            pages_with_text,
            user_query,
            max_total_chars=max_evidence_chars,
            search_hits=search_hits,
        )
        scraped_urls = [
            str(p.get("url"))
            for p in fetched_pages
            if p.get("url")
        ]
        yield {
            "step": "context_acquired",
            "chunks": selected_chunks,
            "urls_opened": scraped_urls,
        }
    except Exception as exc:
        logger.exception("Step 4 failed for session %s", session_id)
        yield {"step": "error", "message": f"Content fetch/ranking failed: {exc}"}
        return

    # Step 5: Streaming synthesis with grounding guardrails 
    try:
        evidence_md = _format_snippets_markdown(selected_chunks)
        conv_history = _format_synthesis_conversation_history(context_payload, user_query)
        synthesis_parts: list[str] = []
        rolling = str(context_payload.get("rolling_summary") or "").strip()
        if rolling:
            synthesis_parts.append(f"## Session Summary\n{rolling}")
        if conv_history:
            synthesis_parts.append(f"## Conversation History\n{conv_history}")
        synthesis_parts.append(f"## User question\n{user_query}")
        synthesis_parts.append(
            f"## Retrieved evidence (use only these sources)\n{evidence_md}"
        )
        synthesis_parts.append(
            "Write the final researched answer now. Respect conversation history for "
            "follow-ups; cite only from retrieved evidence above."
        )
        synthesis_user = "\n\n".join(synthesis_parts)

        async for token in _llm_stream_deltas(
            llm,
            system=SYNTHESIS_SYSTEM_PROMPT,
            user=synthesis_user,
            temperature=0.3,
        ):
            accumulated_answer += token
            yield {"step": "generating_answer", "delta": token}

    except Exception as exc:
        logger.exception("Step 5 failed for session %s", session_id)
        yield {"step": "error", "message": f"Answer generation failed: {exc}"}
        return

    # Post-turn persistence 
    try:
        if accumulated_answer.strip():
            await asyncio.to_thread(
                models.save_message,
                session_id,
                "assistant",
                accumulated_answer,
            )
        await asyncio.to_thread(
            models.save_turn,
            session_id,
            user_query,
            generated_queries,
            urls_opened,
            selected_chunks,
            accumulated_answer,
            research_plan=research_plan,
        )

        # Refresh persisted rolling summary when session grows long.
        try:
            if await asyncio.to_thread(models.should_trigger_summary, session_id):
                history_rows = await asyncio.to_thread(
                    models.get_session_history, session_id
                )
                summary_input = "\n".join(
                    f"{m.role.upper()}: {m.message[:500]}" for m in history_rows[-16:]
                )
                new_summary = await _llm_complete(
                    llm,
                    system=SESSION_SUMMARY_SYSTEM_PROMPT,
                    user=f"Session transcript:\n{summary_input}",
                    temperature=0.2,
                )
                if new_summary.strip():
                    msg_count = len(history_rows)
                    char_count = sum(len(m.message) for m in history_rows)

                    def _persist_summary() -> None:
                        models.save_session_summary(
                            session_id,
                            new_summary,
                            message_count=msg_count,
                            char_count=char_count,
                        )

                    await asyncio.to_thread(_persist_summary)
        except Exception as exc:
            logger.warning("Session summary update skipped: %s", exc)

        yield {
            "step": "turn_complete",
            "final_answer": accumulated_answer,
            "research_plan": research_plan,
        }
    except Exception as exc:
        logger.exception("Persistence failed for session %s", session_id)
        yield {"step": "error", "message": f"Failed to persist turn: {exc}"}



# Standalone CLI verification



async def _run_cli_turn(session_id: str, query: str) -> int:
    """Execute one turn and print events to stdout; return exit code."""
    exit_code = 0
    async for event in execute_agent_turn(session_id, query):
        step = event.get("step", "")
        if step == "generating_answer":
            # Stream tokens inline without JSON wrapping for readability.
            sys.stdout.write(str(event.get("delta", "")))
            sys.stdout.flush()
        else:
            print(json.dumps(event, ensure_ascii=False), file=sys.stderr)
            if step == "error":
                exit_code = 1
        if step == "turn_complete":
            print(file=sys.stderr)  # newline after streamed answer
    return exit_code


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Optional DB path from environment (matches models.py CLI convention).
    db_path = os.environ.get("DEEP_RESEARCH_DB_PATH")
    if db_path:
        models.set_db_path(db_path)

    try:
        models.init_db()
    except Exception as exc:
        print(json.dumps({"step": "error", "message": f"Database init failed: {exc}"}))
        sys.exit(1)

    query = os.environ.get(
        "AGENT_DEMO_QUERY",
        "What are the latest developments in solid-state battery technology?",
    ).strip()
    session_id = os.environ.get("AGENT_DEMO_SESSION_ID", f"cli-{uuid.uuid4().hex[:8]}")

    print(
        json.dumps(
            {
                "step": "cli_start",
                "session_id": session_id,
                "query": query,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )

    try:
        exit_code = asyncio.run(_run_cli_turn(session_id, query))
    except KeyboardInterrupt:
        print(json.dumps({"step": "error", "message": "Interrupted by user"}))
        sys.exit(130)

    sys.exit(exit_code)


if __name__ == "__main__":
    _main()
