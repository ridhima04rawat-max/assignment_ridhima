"""
Persistence layer for a Deep Research Agent.

Uses SQLite (stdlib only) for conversation and turn history, with helpers
to save/retrieve data and build a budget-aware context payload for prompts.

Importing this module has no side effects; call init_db() explicitly or run
``python models.py`` to initialize the database.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Literal, Optional, TypedDict, cast

logger = logging.getLogger(__name__)

Role = Literal["user", "assistant", "system"]
TRUNCATION_NOTE = "[Older history truncated for context window management]"

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "deep_research.db"
_db_path: Path = DEFAULT_DB_PATH

__all__ = [
    "Message",
    "Turn",
    "ContextPayload",
    "TRUNCATION_NOTE",
    "DEFAULT_DB_PATH",
    "set_db_path",
    "get_db_path",
    "get_connection",
    "init_db",
    "save_message",
    "save_turn",
    "get_session_history",
    "get_recent_turns",
    "list_sessions",
    "get_session_summary",
    "save_session_summary",
    "should_trigger_summary",
    "build_context_payload",
]

SUMMARY_TRIGGER_MESSAGE_COUNT = 8
SUMMARY_TRIGGER_CHAR_COUNT = 10_000
SUMMARY_DELTA_MESSAGES = 8  # ~4 turns since last LLM summary
SUMMARY_DELTA_CHARS = 3000



# Data containers



@dataclass(frozen=True, slots=True)
class Message:
    id: int
    session_id: str
    role: str
    message: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class Turn:
    id: int
    session_id: str
    query: str
    search_queries_issued: list[str]
    urls_opened: list[str]
    context_snippets_selected: list[dict[str, Any]]
    final_answer: str
    timestamp: str
    research_plan: str = ""


class ContextPayload(TypedDict, total=False):
    session_id: str
    messages: list[dict[str, str]]
    research_turns: list[dict[str, Any]]
    rolling_summary: str
    truncation_notes: list[str]
    metadata: dict[str, Any]



# Database configuration



def set_db_path(path: str | Path) -> None:
    """Set the SQLite database file path (call before init_db)."""
    global _db_path
    _db_path = Path(path)


def get_db_path() -> Path:
    return _db_path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection(
    *,
    db_path: Optional[Path] = None,
    readonly: bool = False,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Yield a SQLite connection with safe lifecycle management.

    Commits on success, rolls back on error, always closes the connection.
    """
    path = db_path if db_path is not None else _db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    uri = f"file:{path.resolve().as_posix()}?mode={'ro' if readonly else 'rwc'}"
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        logger.error("Database error: %s", exc)
        raise
    finally:
        if conn is not None:
            conn.close()


def init_db(*, db_path: Optional[Path] = None) -> None:
    """Create the database file and initialize schemas with indexes."""
    path = db_path if db_path is not None else _db_path
    path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = """
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_conversation_session_id
            ON conversation_history (session_id);
        CREATE INDEX IF NOT EXISTS idx_conversation_timestamp
            ON conversation_history (timestamp);

        CREATE TABLE IF NOT EXISTS turn_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            query TEXT NOT NULL,
            search_queries_issued TEXT NOT NULL DEFAULT '[]',
            urls_opened TEXT NOT NULL DEFAULT '[]',
            context_snippets_selected TEXT NOT NULL DEFAULT '[]',
            final_answer TEXT NOT NULL DEFAULT '',
            timestamp TEXT NOT NULL,
            research_plan TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_turn_session_id
            ON turn_history (session_id);
        CREATE INDEX IF NOT EXISTS idx_turn_timestamp
            ON turn_history (timestamp);

        CREATE TABLE IF NOT EXISTS session_summaries (
            session_id TEXT PRIMARY KEY,
            rolling_summary TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            last_message_count INTEGER NOT NULL DEFAULT 0,
            last_char_count INTEGER NOT NULL DEFAULT 0
        );
    """

    try:
        with get_connection(db_path=path) as conn:
            conn.executescript(schema_sql)
            _migrate_schema(conn)
        logger.info("Database initialized at %s", path.resolve())
    except sqlite3.Error as exc:
        logger.error("Failed to initialize database at %s: %s", path, exc)
        raise


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply additive schema upgrades for existing databases."""
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(turn_history)").fetchall()
    }
    if "research_plan" not in columns:
        conn.execute(
            "ALTER TABLE turn_history ADD COLUMN research_plan TEXT NOT NULL DEFAULT ''"
        )
    summary_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(session_summaries)").fetchall()
    }
    if summary_cols and "last_message_count" not in summary_cols:
        conn.execute(
            "ALTER TABLE session_summaries ADD COLUMN last_message_count INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE session_summaries ADD COLUMN last_char_count INTEGER NOT NULL DEFAULT 0"
        )



# Serialization helpers



def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads_list(raw: Optional[str]) -> list[Any]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        logger.warning("Invalid JSON list in database; returning empty list")
        return []


def _row_to_message(row: sqlite3.Row) -> Message:
    return Message(
        id=int(row["id"]),
        session_id=str(row["session_id"]),
        role=str(row["role"]),
        message=str(row["message"]),
        timestamp=str(row["timestamp"]),
    )


def _row_to_turn(row: sqlite3.Row) -> Turn:
    return Turn(
        id=int(row["id"]),
        session_id=str(row["session_id"]),
        query=str(row["query"]),
        search_queries_issued=cast(list[str], _json_loads_list(row["search_queries_issued"])),
        urls_opened=cast(list[str], _json_loads_list(row["urls_opened"])),
        context_snippets_selected=cast(
            list[dict[str, Any]],
            _json_loads_list(row["context_snippets_selected"]),
        ),
        final_answer=str(row["final_answer"]),
        timestamp=str(row["timestamp"]),
        research_plan=str(row["research_plan"]) if "research_plan" in row.keys() else "",
    )


def _validate_role(role: str) -> None:
    if role not in ("user", "assistant", "system"):
        raise ValueError(f"Invalid role {role!r}; expected user, assistant, or system")



# Persistence API



def save_message(session_id: str, role: str, message: str) -> None:
    """Persist a single conversation message for a session."""
    _validate_role(role)
    ts = _utc_now_iso()
    sql = """
        INSERT INTO conversation_history (session_id, role, message, timestamp)
        VALUES (?, ?, ?, ?)
    """
    try:
        with get_connection() as conn:
            conn.execute(sql, (session_id, role, message, ts))
    except sqlite3.Error as exc:
        logger.error(
            "save_message failed for session_id=%s role=%s: %s",
            session_id,
            role,
            exc,
        )
        raise


def save_turn(
    session_id: str,
    query: str,
    search_queries: list[str],
    urls: list[str],
    snippets: list[dict[str, Any]],
    final_answer: str,
    *,
    research_plan: str = "",
) -> None:
    """Persist one research turn (query, plan, searches, URLs, snippets, answer)."""
    ts = _utc_now_iso()
    sql = """
        INSERT INTO turn_history (
            session_id,
            query,
            search_queries_issued,
            urls_opened,
            context_snippets_selected,
            final_answer,
            timestamp,
            research_plan
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        session_id,
        query,
        _json_dumps(search_queries),
        _json_dumps(urls),
        _json_dumps(snippets),
        final_answer,
        ts,
        research_plan,
    )
    try:
        with get_connection() as conn:
            conn.execute(sql, params)
    except sqlite3.Error as exc:
        logger.error("save_turn failed for session_id=%s: %s", session_id, exc)
        raise


def get_session_history(session_id: str) -> list[Message]:
    """Return all messages for a session, ordered chronologically (oldest first)."""
    sql = """
        SELECT id, session_id, role, message, timestamp
        FROM conversation_history
        WHERE session_id = ?
        ORDER BY timestamp ASC, id ASC
    """
    try:
        with get_connection(readonly=True) as conn:
            rows = conn.execute(sql, (session_id,)).fetchall()
        return [_row_to_message(row) for row in rows]
    except sqlite3.Error as exc:
        logger.error("get_session_history failed for session_id=%s: %s", session_id, exc)
        raise


def get_recent_turns(session_id: str, limit: int = 3) -> list[Turn]:
    """Return the most recent research turns in chronological order."""
    if limit < 1:
        return []
    sql = """
        SELECT
            id,
            session_id,
            query,
            search_queries_issued,
            urls_opened,
            context_snippets_selected,
            final_answer,
            timestamp,
            research_plan
        FROM turn_history
        WHERE session_id = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
    """
    try:
        with get_connection(readonly=True) as conn:
            rows = conn.execute(sql, (session_id, limit)).fetchall()
        turns = [_row_to_turn(row) for row in rows]
        turns.reverse()
        return turns
    except sqlite3.Error as exc:
        logger.error("get_recent_turns failed for session_id=%s: %s", session_id, exc)
        raise


def list_sessions() -> list[dict[str, str]]:
    """Return session ids ordered by most recent activity."""
    sql = """
        SELECT session_id, MAX(last_ts) AS last_ts FROM (
            SELECT session_id, timestamp AS last_ts FROM conversation_history
            UNION ALL
            SELECT session_id, timestamp AS last_ts FROM turn_history
        )
        GROUP BY session_id
        ORDER BY last_ts DESC
    """
    try:
        with get_connection(readonly=True) as conn:
            rows = conn.execute(sql).fetchall()
        return [
            {"session_id": str(r["session_id"]), "last_ts": str(r["last_ts"] or "")}
            for r in rows
        ]
    except sqlite3.Error as exc:
        logger.error("list_sessions failed: %s", exc)
        raise


def get_session_summary(session_id: str) -> str:
    """Return the persisted rolling summary for a session (empty if none)."""
    sql = "SELECT rolling_summary FROM session_summaries WHERE session_id = ?"
    try:
        with get_connection(readonly=True) as conn:
            row = conn.execute(sql, (session_id,)).fetchone()
        if row is None:
            return ""
        return str(row["rolling_summary"] or "").strip()
    except sqlite3.Error as exc:
        logger.error("get_session_summary failed for session_id=%s: %s", session_id, exc)
        raise


def save_session_summary(
    session_id: str,
    summary: str,
    *,
    message_count: int,
    char_count: int,
) -> None:
    """Upsert the LLM-maintained rolling summary and snapshot sizes at update time."""
    ts = _utc_now_iso()
    sql = """
        INSERT INTO session_summaries (
            session_id, rolling_summary, updated_at, last_message_count, last_char_count
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            rolling_summary = excluded.rolling_summary,
            updated_at = excluded.updated_at,
            last_message_count = excluded.last_message_count,
            last_char_count = excluded.last_char_count
    """
    try:
        with get_connection() as conn:
            conn.execute(
                sql,
                (session_id, summary.strip(), ts, message_count, char_count),
            )
    except sqlite3.Error as exc:
        logger.error("save_session_summary failed for session_id=%s: %s", session_id, exc)
        raise


def should_trigger_summary(session_id: str) -> bool:
    """
    Return True only when enough *new* content accumulated since the last summary.

    Avoids re-summarizing on every turn after the first threshold is crossed.
    """
    try:
        messages = get_session_history(session_id)
        current_count = len(messages)
        current_chars = sum(len(m.message) for m in messages)

        if current_count < SUMMARY_TRIGGER_MESSAGE_COUNT and current_chars < SUMMARY_TRIGGER_CHAR_COUNT:
            return False

        sql = """
            SELECT last_message_count, last_char_count
            FROM session_summaries WHERE session_id = ?
        """
        with get_connection(readonly=True) as conn:
            row = conn.execute(sql, (session_id,)).fetchone()

        if row is None:
            return True

        last_count = int(row["last_message_count"] or 0)
        last_chars = int(row["last_char_count"] or 0)
        delta_messages = current_count - last_count
        delta_chars = current_chars - last_chars

        return (
            delta_messages >= SUMMARY_DELTA_MESSAGES
            or delta_chars >= SUMMARY_DELTA_CHARS
        )
    except sqlite3.Error:
        return False



# Context builder engine



@dataclass
class _ContextBlock:
    """One chronological slice of context with a stable sort key."""

    sort_key: tuple[str, int]
    block_type: Literal["message", "turn", "summary"]
    payload: dict[str, Any]
    char_weight: int = 0
    relevance: float = 0.0

    def __post_init__(self) -> None:
        if self.char_weight <= 0:
            self.char_weight = len(_json_dumps(self.payload))


def _message_block(msg: Message) -> _ContextBlock:
    payload = {
        "role": msg.role,
        "content": msg.message,
        "timestamp": msg.timestamp,
    }
    return _ContextBlock(
        sort_key=(msg.timestamp, msg.id),
        block_type="message",
        payload=payload,
    )


def _turn_block(turn: Turn, *, relevance: float = 0.0) -> _ContextBlock:
    payload = {
        "query": turn.query,
        "research_plan": turn.research_plan,
        "search_queries": turn.search_queries_issued,
        "urls_opened": turn.urls_opened,
        "snippets": turn.context_snippets_selected,
        "final_answer": turn.final_answer,
        "timestamp": turn.timestamp,
    }
    return _ContextBlock(
        sort_key=(turn.timestamp, turn.id),
        block_type="turn",
        payload=payload,
        relevance=relevance,
    )


def _summary_block(summary_text: str, *, sort_key: tuple[str, int]) -> _ContextBlock:
    payload = {"role": "system", "content": summary_text, "timestamp": sort_key[0]}
    return _ContextBlock(
        sort_key=sort_key,
        block_type="summary",
        payload=payload,
        relevance=1.0,
    )


def _token_overlap_score(query: str, text: str) -> float:
    q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    t_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    if not q_tokens or not t_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / len(q_tokens)


def _turn_relevance(turn: Turn, focus_query: Optional[str]) -> float:
    if not focus_query:
        return 0.0
    blob = " ".join(
        [
            turn.query,
            turn.research_plan,
            " ".join(turn.search_queries_issued),
            turn.final_answer[:600],
        ]
    )
    return _token_overlap_score(focus_query, blob)


def _extractive_rolling_summary(dropped: list[_ContextBlock], max_chars: int = 1800) -> str:
    """
    Build a compact rolling summary from pruned blocks (extractive fallback, no LLM).
    """
    if not dropped:
        return ""
    parts: list[str] = []
    for block in dropped[-12:]:
        if block.block_type == "message":
            role = str(block.payload.get("role", "user"))
            content = str(block.payload.get("content", "")).strip()
            if content:
                excerpt = content[:220].replace("\n", " ")
                parts.append(f"{role}: {excerpt}")
        elif block.block_type == "turn":
            q = str(block.payload.get("query", ""))[:120]
            ans = str(block.payload.get("final_answer", ""))[:180].replace("\n", " ")
            parts.append(f"prior research Q: {q}")
            if ans:
                parts.append(f"prior answer: {ans}")
    combined = " ".join(parts)
    if len(combined) <= max_chars:
        return combined
    return combined[: max_chars - 3] + "..."


def _payload_char_count(payload: dict[str, Any]) -> int:
    return len(_json_dumps(payload))


def _truncate_text(text: str, max_len: int) -> tuple[str, bool]:
    if max_len <= 0:
        return "", True
    if len(text) <= max_len:
        return text, False
    if max_len <= len(TRUNCATION_NOTE) + 4:
        return text[:max_len], True
    suffix = "..."
    keep = max_len - len(suffix)
    return text[:keep] + suffix, True


def _mark_boundary(block: _ContextBlock) -> None:
    """Append the truncation placeholder at the structural boundary."""
    if block.block_type in ("message", "summary"):
        content = str(block.payload.get("content", ""))
        if not content.startswith(TRUNCATION_NOTE):
            block.payload["content"] = f"{TRUNCATION_NOTE}\n\n{content}"
    else:
        query = str(block.payload.get("query", ""))
        if not query.startswith(TRUNCATION_NOTE):
            block.payload["query"] = f"{TRUNCATION_NOTE}\n\n{query}"
    block.char_weight = len(_json_dumps(block.payload))


def _shrink_block(block: _ContextBlock, target_len: int) -> bool:
    """Truncate text fields inside a block. Returns True if anything changed."""
    changed = False
    if block.block_type in ("message", "summary"):
        content = str(block.payload.get("content", ""))
        new_content, did = _truncate_text(content, target_len)
        if did:
            block.payload["content"] = new_content
            changed = True
    else:
        for key in ("final_answer", "query"):
            text = str(block.payload.get(key, ""))
            new_text, did = _truncate_text(text, max(32, target_len // 2))
            if did:
                block.payload[key] = new_text
                changed = True
        snippets = block.payload.get("snippets")
        if isinstance(snippets, list) and len(snippets) > 1:
            block.payload["snippets"] = snippets[-1:]
            changed = True
        for key in ("search_queries", "urls_opened"):
            items = block.payload.get(key)
            if isinstance(items, list) and len(items) > 3:
                block.payload[key] = items[-3:]
                changed = True
    if changed:
        block.char_weight = len(_json_dumps(block.payload))
    return changed


def _apply_char_budget(
    blocks: list[_ContextBlock],
    max_chars: int,
) -> tuple[list[_ContextBlock], list[str]]:
    """
    Enforce max_chars with chronological pruning: drop oldest blocks first,
    then truncate text inside the oldest remaining block until within budget.
    Newest interaction details are always preferred.
    """
    notes: list[str] = []
    if max_chars < 1:
        return [], [TRUNCATION_NOTE]

    working = list(blocks)

    def total_chars(items: list[_ContextBlock]) -> int:
        return sum(b.char_weight for b in items)

    def _pop_oldest_prunable(items: list[_ContextBlock]) -> bool:
        """Remove the oldest block that is safe to drop (never drop summary blocks first)."""
        for i, block in enumerate(items):
            if block.block_type != "summary":
                items.pop(i)
                return True
        if items:
            items.pop(0)
            return True
        return False

    dropped_oldest = False
    while working and total_chars(working) > max_chars:
        if not _pop_oldest_prunable(working):
            break
        dropped_oldest = True

    if dropped_oldest:
        notes.append(TRUNCATION_NOTE)
        if working:
            _mark_boundary(working[0])

    while working and total_chars(working) > max_chars:
        overflow = total_chars(working) - max_chars
        oldest = working[0]
        if _shrink_block(oldest, max(32, oldest.char_weight - overflow)):
            if TRUNCATION_NOTE not in notes:
                notes.append(TRUNCATION_NOTE)
            if not str(oldest.payload.get("content", oldest.payload.get("query", ""))).startswith(
                TRUNCATION_NOTE
            ):
                _mark_boundary(oldest)
        else:
            if not _pop_oldest_prunable(working):
                break
            if TRUNCATION_NOTE not in notes:
                notes.append(TRUNCATION_NOTE)
            if working:
                _mark_boundary(working[0])

    return working, notes


def build_context_payload(
    session_id: str,
    max_chars: int = 12000,
    *,
    focus_query: Optional[str] = None,
) -> dict:
    """
    Assemble prompt context: messages, relevance-ranked prior turns, and web snippets.

    When history exceeds max_chars:
      1. Rank prior turns by token overlap with focus_query (if provided).
      2. Drop oldest blocks and replace them with an extractive rolling_summary.
      3. Truncate remaining oldest block text as a last resort.
    """
    messages = get_session_history(session_id)
    turns = get_recent_turns(session_id, limit=50)
    stored_summary = get_session_summary(session_id)

    message_blocks = [_message_block(m) for m in messages]
    turn_blocks = [
        _turn_block(t, relevance=_turn_relevance(t, focus_query)) for t in turns
    ]

    # Prioritize high-relevance turns, then newest messages.
    turn_blocks.sort(key=lambda b: (b.relevance, b.sort_key[0], b.sort_key[1]), reverse=True)
    message_blocks.sort(key=lambda b: b.sort_key)

    blocks: list[_ContextBlock] = message_blocks + turn_blocks

    def _total(items: list[_ContextBlock]) -> int:
        return sum(b.char_weight for b in items)

    truncation_notes: list[str] = []
    rolling_summary = stored_summary

    if _total(blocks) > max_chars:
        dropped: list[_ContextBlock] = []
        working = list(blocks)
        while working and _total(working) > max_chars:
            dropped.append(working.pop(0))
        if dropped:
            extractive = _extractive_rolling_summary(dropped)
            if stored_summary and extractive:
                rolling_summary = f"{stored_summary}\n\n{extractive}"
            elif extractive:
                rolling_summary = extractive
            elif not rolling_summary:
                rolling_summary = extractive
            truncation_notes.append(TRUNCATION_NOTE)

        # Budget messages/turns first; inject summary afterward so it is not pop(0)'d.
        blocks, extra_notes = _apply_char_budget(working, max_chars)
        truncation_notes.extend(extra_notes)

        if rolling_summary:
            summary_prefix = (
                "Rolling summary of earlier conversation and research turns: "
            )
            summary_block = _summary_block(
                summary_prefix + rolling_summary,
                sort_key=("0000-01-01T00:00:00+00:00", 0),
            )
            blocks.insert(0, summary_block)
            while sum(b.char_weight for b in blocks) > max_chars:
                pruned = False
                for i in range(len(blocks) - 1, 0, -1):
                    if blocks[i].block_type != "summary":
                        blocks.pop(i)
                        pruned = True
                        break
                if pruned:
                    continue
                if _shrink_block(blocks[0], max(200, max_chars - sum(b.char_weight for b in blocks[1:]))):
                    blocks[0].char_weight = len(_json_dumps(blocks[0].payload))
                else:
                    break
    else:
        blocks, truncation_notes = _apply_char_budget(blocks, max_chars)

    out_messages: list[dict[str, str]] = []
    out_turns: list[dict[str, Any]] = []
    for block in blocks:
        if block.block_type == "message":
            out_messages.append(
                {
                    "role": str(block.payload["role"]),
                    "content": str(block.payload["content"]),
                    "timestamp": str(block.payload["timestamp"]),
                }
            )
        elif block.block_type == "summary":
            out_messages.append(
                {
                    "role": "system",
                    "content": str(block.payload["content"]),
                    "timestamp": str(block.payload["timestamp"]),
                }
            )
        else:
            out_turns.append(dict(block.payload))

    payload: dict[str, Any] = {
        "session_id": session_id,
        "messages": out_messages,
        "research_turns": out_turns,
        "truncation_notes": truncation_notes,
        "metadata": {
            "max_chars": max_chars,
            "char_count": 0,
            "truncated": bool(truncation_notes),
            "message_count": len(out_messages),
            "turn_count": len(out_turns),
            "has_rolling_summary": bool(rolling_summary),
            "focus_query": focus_query or "",
        },
    }
    if rolling_summary:
        payload["rolling_summary"] = rolling_summary
    payload["metadata"]["char_count"] = _payload_char_count(payload)
    return payload



# Optional CLI entry (no side effects on import)



def _main() -> None:
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    env_path = os.environ.get("DEEP_RESEARCH_DB_PATH")
    if env_path:
        set_db_path(env_path)
    try:
        init_db()
        print(f"Database ready at {get_db_path().resolve()}", file=sys.stderr)
    except sqlite3.Error as exc:
        print(f"Initialization failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
