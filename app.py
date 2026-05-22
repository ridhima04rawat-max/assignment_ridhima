"""
Deep Research Agent, Streamlit user interface.

Integrates models.py (persistence), research_tools.py (search/scrape),
and agent_engine.py (orchestration). No agent frameworks.

Run: streamlit run app.py
"""

from __future__ import annotations

import asyncio
import os
import queue
from collections import defaultdict
import threading
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Iterator, Optional

import streamlit as st


# Defensive backend imports & database bootstrap


try:
    import models
except ImportError as exc:
    st.error(f"Failed to import models.py: {exc}")
    st.stop()

try:
    import research_tools  # noqa: F401 — availability check
except ImportError as exc:
    st.error(f"Failed to import research_tools.py: {exc}")
    st.stop()

try:
    import agent_engine
except ImportError as exc:
    st.error(f"Failed to import agent_engine.py: {exc}")
    st.stop()

try:
    models.init_db()
except Exception as exc:
    st.error(f"Database initialization failed: {exc}")
    st.stop()


# Page configuration & global styling


st.set_page_config(
    page_title="Deep Research Agent",
    page_icon="🔍",
    layout="wide",
)

CUSTOM_CSS = """
<style>
    /* App shell */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1100px;
    }
    h1, h2, h3 {
        font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
        letter-spacing: -0.02em;
    }
    /* Hero card */
    .dra-hero {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 55%, #0ea5e9 120%);
        color: #f8fafc;
        border-radius: 16px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18);
    }
    .dra-hero p {
        margin: 0.35rem 0 0 0;
        opacity: 0.92;
        font-size: 0.95rem;
    }
    /* Status badges */
    .dra-badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        margin: 0.15rem 0.25rem 0.15rem 0;
        border: 1px solid rgba(0,0,0,0.06);
    }
    .dra-badge-ok {
        background: #dcfce7;
        color: #166534;
    }
    .dra-badge-miss {
        background: #fee2e2;
        color: #991b1b;
    }
    /* Sidebar session buttons breathe */
    section[data-testid="stSidebar"] .stButton > button {
        border-radius: 10px;
        font-weight: 500;
    }
    /* Chat bubbles subtle polish */
    [data-testid="stChatMessage"] {
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
    }
    /* Expander headers */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 0.9rem;
    }
    /* Typing cursor during stream */
    .dra-cursor::after {
        content: "▌";
        animation: dra-blink 1s step-start infinite;
        margin-left: 2px;
        color: #0ea5e9;
    }
    @keyframes dra-blink {
        50% { opacity: 0; }
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# Session state defaults


if "session_id" not in st.session_state:
    st.session_state.session_id = f"session-{uuid.uuid4().hex[:10]}"
if "context_max_chars" not in st.session_state:
    st.session_state.context_max_chars = 12000
if "search_provider" not in st.session_state:
    st.session_state.search_provider = "Force Tavily (if key set)"
if "messages_rendered" not in st.session_state:
    st.session_state.messages_rendered = True
if "_serper_backup" not in st.session_state:
    st.session_state._serper_backup = None
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False



# Async bridge (Streamlit-safe)



def run_async_generator_safely(
    factory: Callable[[], AsyncGenerator[dict[str, Any], None]],
) -> Iterator[dict[str, Any]]:
    """
    Consume an async generator from Streamlit's sync context without colliding
    with Tornado's running event loop.

    Spins up a dedicated thread + fresh asyncio loop, forwards events through a
    thread-safe queue, and yields them synchronously to the UI thread.
    """
    event_queue: queue.Queue[Any] = queue.Queue()
    sentinel = object()

    def _runner() -> None:
        async def _consume() -> None:
            try:
                async for item in factory():
                    event_queue.put(item)
            except Exception as exc:
                event_queue.put({"step": "error", "message": str(exc)})
            finally:
                event_queue.put(sentinel)

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_consume())
        finally:
            loop.close()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()

    while True:
        item = event_queue.get()
        if item is sentinel:
            break
        yield item

    thread.join(timeout=2.0)



# Data access helpers (app-local; models has no list_sessions)



def list_research_sessions() -> list[dict[str, str]]:
    """Return sessions ordered by most recent activity."""
    sessions: list[dict[str, str]] = []
    try:
        for row in models.list_sessions():
            sid = row["session_id"]
            last_ts = row.get("last_ts", "")
            label = sid if len(sid) <= 28 else f"{sid[:12]}…{sid[-6:]}"
            sessions.append({"id": sid, "label": label, "last_ts": last_ts})
    except Exception as exc:
        st.sidebar.warning(f"Could not list sessions: {exc}")
    return sessions


def fetch_all_turns(session_id: str) -> list[models.Turn]:
    """Load full turn history for citation expanders."""
    try:
        return models.get_recent_turns(session_id, limit=500)
    except Exception:
        return []




def _format_ts(iso_ts: str) -> str:
    from datetime import datetime, timedelta
    try:
        # Parse the stored UTC timestamp
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        # Add 5 hours and 30 minutes to convert UTC to IST
        ist_dt = dt + timedelta(hours=5, minutes=30)
        return ist_dt.strftime("%Y-%m-%d %H:%M IST")
    except Exception:
        return iso_ts


def _api_key_status(env_name: str) -> tuple[str, str]:
    """Return (label, css_class) without exposing secrets."""
    present = bool(os.environ.get(env_name, "").strip())
    if present:
        return "Connected", "dra-badge dra-badge-ok"
    return "Missing", "dra-badge dra-badge-miss"


def _apply_search_provider_preference() -> None:
    """
    Temporarily adjust env so research_tools routing matches sidebar choice.
    Serper is preferred when both keys exist (research_tools behavior).
    """
    serper = os.environ.get("SERPER_API_KEY", "").strip()
    tavily = os.environ.get("TAVILY_API_KEY", "").strip()
    choice = st.session_state.search_provider

    if choice.startswith("Force Tavily") and serper and tavily:
        if st.session_state._serper_backup is None:
            st.session_state._serper_backup = serper
        os.environ["SERPER_API_KEY"] = ""
    elif st.session_state._serper_backup:
        os.environ["SERPER_API_KEY"] = st.session_state._serper_backup
        st.session_state._serper_backup = None


def _restore_search_provider_env() -> None:
    if st.session_state._serper_backup:
        os.environ["SERPER_API_KEY"] = st.session_state._serper_backup
        st.session_state._serper_backup = None



# UI components



def render_hero() -> None:
    st.markdown(
        """
        <div class="dra-hero">
            <h1 style="margin:0; font-size:1.65rem;">🔍 Deep Research Agent</h1>
            <p>Plan searches, scrape the web, rank evidence, and synthesize cited answers — live.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )




def render_api_status_panel() -> None:
    st.sidebar.subheader("API Status")
    keys = [
        ("GROQ_API_KEY", "Groq LLM"),
        ("TAVILY_API_KEY", "Tavily Search"),
    ]
    for env_name, label in keys:
        status, css = _api_key_status(env_name)
        st.sidebar.markdown(
            f"**{label}**<br><span class='{css}'>{status}</span>",
            unsafe_allow_html=True,
        )







def render_sidebar() -> None:
    st.sidebar.title("Research Console")

    render_api_status_panel()
    st.sidebar.divider()

    st.sidebar.subheader("Model & Context")
    st.session_state.context_max_chars = st.sidebar.slider(
        "Context budget (chars)",
        min_value=4000,
        max_value=20000,
        value=int(st.session_state.context_max_chars),
        step=1000,
        help="Passed to models.build_context_payload for this session's turns.",
    )
    

    st.sidebar.divider()
    st.sidebar.subheader("Sessions")

    if st.sidebar.button(
        "➕ New Research Session",
        use_container_width=True,
        disabled=st.session_state.is_processing,
    ):
        st.session_state.session_id = f"session-{uuid.uuid4().hex[:10]}"
        st.session_state.messages_rendered = False
        st.rerun()

    sessions = list_research_sessions()
    current = st.session_state.session_id

    if not sessions:
        st.sidebar.caption("No saved sessions yet. Start a query below.")
    else:
        total_sessions = len(sessions)
        for idx, sess in enumerate(sessions):
            sid = sess["id"]
            # Formats using the updated logic containing our inline +5:30 timedelta shift
            time_label = _format_ts(sess["last_ts"]) if sess["last_ts"] else "New Session"
            
            # Since rows return newest-first, derive true chronological index values
            session_num = total_sessions - idx
            
            # Formats presentation string combining chronological sequence and clean local time
            btn_label = f"🔬 Session #{session_num} | {time_label}"
            if sid == current:
                btn_label = f"▶ {btn_label}"
                
            if st.sidebar.button(
                btn_label,
                key=f"load_session_{sid}",
                use_container_width=True,
                help=f"Session ID: {sid}",
                disabled=st.session_state.is_processing,
            ):
                st.session_state.session_id = sid
                st.session_state.messages_rendered = False
                st.rerun()

    st.sidebar.caption(f"Active session:\n`{current}`")




def _build_turn_lookup(turns: list[models.Turn]) -> dict[str, list[models.Turn]]:
    """Map user query text -> turn records (FIFO per duplicate query)."""
    lookup: dict[str, list[models.Turn]] = defaultdict(list)
    for turn in turns:
        lookup[turn.query.strip()].append(turn)
    return lookup


def _pop_turn_for_user_query(
    lookup: dict[str, list[models.Turn]],
    user_query: str,
) -> Optional[models.Turn]:
    key = user_query.strip()
    if key in lookup and lookup[key]:
        return lookup[key].pop(0)
    return None


def render_turn_expander(turn: models.Turn) -> None:
    display_time = _format_ts(turn.timestamp)
    with st.expander(f"📊 Research Turn Details | {display_time}", expanded=False):
        st.markdown(f"**Turn Timestamp:** `{display_time}`")
    
        if turn.research_plan:
            st.markdown("**Research plan**")
            st.markdown(turn.research_plan)
        st.markdown("**Planner search queries**")
        if turn.search_queries_issued:
            for q in turn.search_queries_issued:
                st.code(q, language=None)
        else:
            st.caption("No queries recorded.")

        st.markdown("**URLs fetched**")
        if turn.urls_opened:
            for url in turn.urls_opened:
                st.markdown(f"- [{url}]({url})")
        else:
            st.caption("No URLs recorded.")

        st.markdown("**Top context snippets**")
        snippets = turn.context_snippets_selected or []
        if snippets:
            rows = []
            for sn in snippets:
                rows.append(
                    {
                        "Score": sn.get("score", 0),
                        "Domain": sn.get("domain", ""),
                        "Title": (sn.get("title") or "")[:80],
                        "URL": sn.get("url", ""),
                        "Preview": (str(sn.get("text", ""))[:120] + "…")
                        if len(str(sn.get("text", ""))) > 120
                        else str(sn.get("text", "")),
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No snippets stored for this turn.")


def render_chat_history(session_id: str) -> None:
    messages = models.get_session_history(session_id)
    turns = fetch_all_turns(session_id)
    turn_lookup = _build_turn_lookup(turns)
    pending_user_query: Optional[str] = None

    for msg in messages:
        with st.chat_message(msg.role):
            icon = "👤" if msg.role == "user" else "🤖"
            st.caption(f"{icon} {msg.role.title()} | {_format_ts(msg.timestamp)}")
            st.markdown(msg.message)
            if msg.role == "user":
                pending_user_query = msg.message.strip()
            elif msg.role == "assistant" and pending_user_query:
                turn = _pop_turn_for_user_query(turn_lookup, pending_user_query)
                if turn is not None:
                    render_turn_expander(turn)
                pending_user_query = None


def _status_update(status: Any, label: str) -> None:
    status.update(label=label)


def _render_planning_badges(status: Any, queries: list[str]) -> None:
    _status_update(status, "Planning search strategy…")
    st.write("**Generated search queries**")
    cols = st.columns(min(len(queries), 3) or 1)
    for i, q in enumerate(queries):
        with cols[i % len(cols)]:
            st.markdown(
                f"<span class='dra-badge dra-badge-ok'>{q}</span>",
                unsafe_allow_html=True,
            )


def _render_url_list(urls: list[str]) -> None:
    for url in urls:
        st.markdown(f"- `{url}`")

def _render_scraped_pages(chunks: list[dict[str, Any]], urls_opened: list[str]) -> None:
    sources: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for ch in chunks:
        url = str(ch.get("url") or "").strip()
        dom = str(ch.get("domain") or "")
        title = str(ch.get("title") or "Untitled")
        
        # Deduplicate using the URL directly to ensure clean, unique links
        if url and url not in seen:
            seen.add(url)
            sources.append((dom, title, url))
            
    if sources:
        st.write("**Scraped sources**")
        for dom, title, url in sources:
            # Renders a pristine, fully clickable markdown link immediately live
            st.markdown(f"- [**{title}**]({url}) — `{dom}`")
    elif urls_opened:
        st.write("**Pages requested**")
        _render_url_list(urls_opened[:8])




def _handle_progress_event(
    event: dict[str, Any],
    status: Any,
    progress_area: Any,
) -> tuple[str, bool]:
    """
    Update the st.status container for a single backend event.
    Returns (accumulated_delta_text, is_error).
    """
    step = str(event.get("step", ""))

    if step == "initializing":
        _status_update(status, "Context initializing…")
        with progress_area.container():
            st.write(event.get("message", "Initialized session context database."))
        return "", False

    if step == "planning":
        plan_text = str(event.get("plan") or "")
        queries = event.get("queries") or []
        with progress_area.container():
            if plan_text:
                st.markdown("**Research plan**")
                st.markdown(plan_text)
            _render_planning_badges(status, queries)
        return "", False

    if step == "searching":
        _status_update(status, "Searching the web…")
        urls = event.get("urls") or []
        with progress_area.container():
            st.write("**Target URLs discovered**")
            _render_url_list(urls)
        return "", False

    if step == "context_acquired":
        _status_update(status, "Fetching & filtering content…")
        chunks = event.get("chunks") or []
        urls_opened = event.get("urls_opened") or []
        scores = [float(c.get("score", 0)) for c in chunks]
        top_score = max(scores) if scores else 0.0
        with progress_area.container():
            st.write("**Context filtering complete**")
            st.markdown(
                f"- Parsed chunks: **{len(chunks)}**  \n"
                f"- Highest relevance score: **{top_score:.3f}**"
            )
            _render_scraped_pages(chunks, urls_opened)
        return "", False

    if step == "generating_answer":
        _status_update(status, "Synthesizing answer (streaming)…")
        return str(event.get("delta", "")), False

    if step == "error":
        _status_update(status, "Research failed")
        with progress_area.container():
            st.error(event.get("message", "Unknown error"))
        return "", True

    if step == "turn_complete":
        return "", False

    return "", False


def run_research_turn(session_id: str, user_query: str) -> None:
    """Execute one agent turn with live status + streaming assistant message."""
    st.session_state.is_processing = True
    accumulated = ""
    streaming_started = False
    error_seen = False

    # 1. Local accumulators to store the live research state
    live_plan = ""
    live_queries = []
    live_urls = []
    live_chunks = []

    max_context = int(st.session_state.context_max_chars)
    max_evidence = max(2000, int(max_context * 0.65))

    def _factory() -> AsyncGenerator[dict[str, Any], None]:
        return agent_engine.execute_agent_turn(
            session_id,
            user_query,
            max_context_chars=max_context,
            max_evidence_chars=max_evidence,
        )

    _apply_search_provider_preference()

    # Live answer stream in the chat column (updated token by token).
    with st.chat_message("assistant"):
        response_placeholder = st.empty()

    try:
        with st.status(
            "Initializing deep research engines…",
            expanded=True,
        ) as status:
            progress_area = st.empty()

            for event in run_async_generator_safely(_factory):
                step = event.get("step", "")

                # 2. Collect details as the state machine moves through its steps
                if step == "planning":
                    live_plan = str(event.get("plan") or "")
                    live_queries = event.get("queries") or []
                elif step == "searching":
                    live_urls = event.get("urls") or []
                elif step == "context_acquired":
                    live_chunks = event.get("chunks") or []
                    if "urls_opened" in event:
                        live_urls = event.get("urls_opened") or live_urls

                if step == "generating_answer":
                    if not streaming_started:
                        streaming_started = True
                        _status_update(status, "Synthesizing cited answer…")
                    delta, err = _handle_progress_event(event, status, progress_area)
                    if err:
                        error_seen = True
                        break
                    accumulated += delta
                    response_placeholder.markdown(
                        f'<div class="dra-cursor">{accumulated}</div>',
                        unsafe_allow_html=True,
                    )
                    continue

                _, err = _handle_progress_event(event, status, progress_area)
                if err:
                    error_seen = True
                    break

                if step == "turn_complete":
                    accumulated = str(event.get("final_answer") or accumulated)
                    
                    # 3. BUILD THE RICH PREMIUM VIEW IMMEDIATELY LIVE
                    with progress_area.container():
                        if live_plan:
                            st.markdown("**Research plan**")
                            st.markdown(live_plan)
                        
                        st.markdown("**Planner search queries**")
                        if live_queries:
                            for q in live_queries:
                                st.code(q, language=None)
                        else:
                            st.caption("No queries recorded.")

                        st.markdown("**URLs fetched**")
                        if live_urls:
                            for url in live_urls:
                                st.markdown(f"- [{url}]({url})")
                        else:
                            st.caption("No URLs recorded.")

                        st.markdown("**Top context snippets**")
                        if live_chunks:
                            rows = []
                            for sn in live_chunks:
                                rows.append({
                                    "Score": sn.get("score", 0),
                                    "Domain": sn.get("domain", ""),
                                    "Title": (sn.get("title") or "")[:80],
                                    "URL": sn.get("url", ""),
                                    "Preview": (str(sn.get("text", ""))[:120] + "…")
                                    if len(str(sn.get("text", ""))) > 120
                                    else str(sn.get("text", "")),
                                })
                            st.dataframe(rows, use_container_width=True, hide_index=True)
                        else:
                            st.caption("No snippets stored for this turn.")
                    break

            if error_seen:
                status.update(state="error", label="Research encountered an error")
            else:
                status.update(
                    state="complete",
                    label="Synthesis completed successfully!",
                )

        if accumulated and not error_seen:
            response_placeholder.markdown(accumulated)

    finally:
        _restore_search_provider_env()
        st.session_state.is_processing = False








# Main layout



def main() -> None:
    render_sidebar()
    render_hero()

    session_id = st.session_state.session_id

    # Historical chat for the active session.
    render_chat_history(session_id)

    if st.session_state.is_processing:
        st.info("Research in progress… session controls and input are temporarily locked.")

    # Chat input drives a new research turn.
    if prompt := st.chat_input(
        "Ask a research question…",
        disabled=st.session_state.is_processing,
    ):
        with st.chat_message("user"):
            st.markdown(prompt)

        run_research_turn(session_id, prompt)


# Streamlit executes this file as a script (not __main__); invoke once at load.
main()
