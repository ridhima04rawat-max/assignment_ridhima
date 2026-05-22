"""
Web research, scraping, and content filtering for a Deep Research Agent.

Dependencies: httpx, beautifulsoup4 (stdlib for the rest).
Importing this module has no side effects.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Realistic desktop browser User Agent to reduce naive bot blocks.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

STRIP_TAGS = frozenset({"script", "style", "nav", "footer", "header", "aside", "form"})

SERPER_SEARCH_URL = "https://google.serper.dev/search"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

CHUNK_MIN_CHARS = 800
CHUNK_MAX_CHARS = 1000
CHUNK_TARGET_CHARS = 900

SearchResult = dict[str, Any]
FetchedPage = dict[str, Any]
ContextChunk = dict[str, Any]

__all__ = [
    "execute_web_search",
    "fetch_page_content_async",
    "select_optimal_context",
    "DEFAULT_USER_AGENT",
]



# Utilities



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc or ""
    except Exception:
        return ""


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens (length >= 2)."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 2]


def _normalize_search_result(
    *,
    title: str,
    url: str,
    snippet: str,
    relevance_score: Optional[float] = None,
) -> SearchResult:
    return {
        "title": title.strip(),
        "url": url.strip(),
        "snippet": snippet.strip(),
        "relevance_score": relevance_score,
    }



# Search module



def _search_via_serper(
    query: str,
    max_results: int,
    api_key: str,
    *,
    timeout: float = 15.0,
) -> list[SearchResult]:
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": max_results}
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.post(SERPER_SEARCH_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    results: list[SearchResult] = []
    for item in data.get("organic", [])[:max_results]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or item.get("url") or "")
        if not url:
            continue
        results.append(
            _normalize_search_result(
                title=str(item.get("title") or ""),
                url=url,
                snippet=str(item.get("snippet") or item.get("description") or ""),
                relevance_score=None,
            )
        )
    return results


def _search_via_tavily(
    query: str,
    max_results: int,
    api_key: str,
    *,
    timeout: float = 15.0,
) -> list[SearchResult]:
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.post(TAVILY_SEARCH_URL, json=payload)
        response.raise_for_status()
        data = response.json()

    results: list[SearchResult] = []
    for item in data.get("results", [])[:max_results]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if not url:
            continue
        score = item.get("score")
        relevance: Optional[float] = float(score) if score is not None else None
        results.append(
            _normalize_search_result(
                title=str(item.get("title") or ""),
                url=url,
                snippet=str(item.get("content") or item.get("snippet") or ""),
                relevance_score=relevance,
            )
        )
    return results


def execute_web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Run a web search via Serper or Tavily (env-driven) and return normalized hits.

    Environment variables (first match wins):
      - SERPER_API_KEY  -> https://google.serper.dev/search
      - TAVILY_API_KEY  -> https://api.tavily.com/search

    On timeout, HTTP errors, or missing API keys, logs the failure and returns [].
    """
    query = query.strip()
    if not query:
        logger.warning("execute_web_search called with empty query")
        return []
    max_results = max(1, min(max_results, 20))

    serper_key = os.environ.get("SERPER_API_KEY", "").strip()
    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()

    if not serper_key and not tavily_key:
        logger.error(
            "No search API key configured. Set SERPER_API_KEY or TAVILY_API_KEY."
        )
        return []

    try:
        if serper_key:
            return _search_via_serper(query, max_results, serper_key)
        return _search_via_tavily(query, max_results, tavily_key)
    except httpx.TimeoutException as exc:
        logger.error("Search API timeout for query=%r: %s", query, exc)
        return []
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Search API HTTP %s for query=%r: %s",
            exc.response.status_code,
            query,
            exc,
        )
        return []
    except httpx.HTTPError as exc:
        logger.error("Search API request failed for query=%r: %s", query, exc)
        return []
    except (ValueError, KeyError, TypeError) as exc:
        logger.error("Search API response parse error for query=%r: %s", query, exc)
        return []



# HTML extraction



def _decode_html(content: bytes, declared_encoding: Optional[str]) -> str:
    if declared_encoding:
        try:
            return content.decode(declared_encoding, errors="replace")
        except LookupError:
            pass
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return str(og["content"]).strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(separator=" ", strip=True)
    return ""


def _html_to_clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()



# Async page fetch



async def _fetch_single_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout_secs: int,
    title_hint: str = "",
) -> FetchedPage:
    """
    Fetch one URL; on SSL failure retry once with verify=False.
    """
    retrieved_at = _utc_now_iso()
    base: FetchedPage = {
        "url": url,
        "title": title_hint,
        "text": "",
        "retrieved_at": retrieved_at,
        "domain": _safe_domain(url),
        "status_code": None,
        "error": None,
    }

    async def _request(verify_ssl: bool) -> httpx.Response:
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if not verify_ssl:
            async with httpx.AsyncClient(verify=False) as insecure:
                return await insecure.get(
                    url,
                    timeout=timeout_secs,
                    follow_redirects=True,
                    headers=headers,
                )
        return await client.get(
            url,
            timeout=timeout_secs,
            follow_redirects=True,
            headers=headers,
        )

    response: Optional[httpx.Response] = None
    try:
        response = await _request(verify_ssl=True)
    except httpx.HTTPStatusError as exc:
        base["status_code"] = exc.response.status_code
        base["error"] = f"HTTP {exc.response.status_code}"
        logger.warning("HTTP error fetching %s: %s", url, base["error"])
        return base
    except httpx.SSLError as exc:
        logger.warning("SSL error for %s, retrying with verify=False: %s", url, exc)
        try:
            response = await _request(verify_ssl=False)
        except httpx.HTTPError as retry_exc:
            base["error"] = f"SSL retry failed: {retry_exc}"
            logger.warning("SSL retry failed for %s: %s", url, retry_exc)
            return base
    except httpx.TimeoutException:
        base["error"] = "timeout"
        logger.warning("Timeout fetching %s", url)
        return base
    except httpx.HTTPError as exc:
        base["error"] = str(exc)
        logger.warning("Request failed for %s: %s", url, exc)
        return base

    if response is None:
        base["error"] = "no response"
        return base

    base["status_code"] = response.status_code
    if response.status_code >= 400:
        base["error"] = f"HTTP {response.status_code}"
        logger.warning("Non-success status for %s: %s", url, base["error"])
        return base

    try:
        encoding = response.encoding
        html = _decode_html(response.content, encoding)
        soup = BeautifulSoup(html, "html.parser")
        parsed_title = _extract_title(soup)
        base["title"] = parsed_title or title_hint or base["title"]
        base["text"] = _html_to_clean_text(html)
    except Exception as exc:
        base["error"] = f"parse error: {exc}"
        logger.warning("Failed to parse %s: %s", url, exc)
        return base

    if not base["text"]:
        base["error"] = base["error"] or "empty page content"
    return base


async def fetch_page_content_async(
    urls: list[str],
    timeout_secs: int = 8,
) -> list[dict]:
    """
    Concurrently fetch URLs and return cleaned text plus citation metadata.

    Each result dict contains:
      url, title, text, retrieved_at (ISO 8601 UTC), domain,
      status_code (int|None), error (str|None)
    """
    seen: set[str] = set()
    unique_urls: list[str] = []
    for raw in urls:
        u = raw.strip()
        if u and u not in seen:
            seen.add(u)
            unique_urls.append(u)

    if not unique_urls:
        return []

    timeout_secs = max(3, min(timeout_secs, 60))
    results: list[FetchedPage] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
    ) as client:
        tasks = [
            _fetch_single_url(client, url, timeout_secs=timeout_secs)
            for url in unique_urls
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

    for url, item in zip(unique_urls, gathered):
        if isinstance(item, BaseException):
            logger.warning("Unexpected exception fetching %s: %s", url, item)
            results.append(
                {
                    "url": url,
                    "title": "",
                    "text": "",
                    "retrieved_at": _utc_now_iso(),
                    "domain": _safe_domain(url),
                    "status_code": None,
                    "error": str(item),
                }
            )
        else:
            results.append(item)
    return results



# Context scoring & selection (BM25 style over chunks)



def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _chunk_text(text: str) -> list[str]:
    """
    Break text into semantic windows of roughly 800-1000 characters,
    preferring paragraph boundaries.
    """
    if not text:
        return []
    if len(text) <= CHUNK_MAX_CHARS:
        return [text]

    chunks: list[str] = []
    paragraphs = _split_paragraphs(text)
    buffer = ""

    def flush_buffer() -> None:
        nonlocal buffer
        if buffer.strip():
            chunks.append(buffer.strip())
        buffer = ""

    for para in paragraphs:
        if len(para) > CHUNK_MAX_CHARS:
            flush_buffer()
            start = 0
            while start < len(para):
                end = min(start + CHUNK_TARGET_CHARS, len(para))
                if end < len(para):
                    space = para.rfind(" ", start, end)
                    if space > start + CHUNK_MIN_CHARS // 2:
                        end = space
                chunks.append(para[start:end].strip())
                start = end
            continue

        candidate = f"{buffer}\n\n{para}".strip() if buffer else para
        if len(candidate) <= CHUNK_MAX_CHARS:
            buffer = candidate
        else:
            flush_buffer()
            buffer = para
        if len(buffer) >= CHUNK_MIN_CHARS:
            flush_buffer()

    flush_buffer()

    # Merge tiny trailing fragments into previous chunk when possible.
    merged: list[str] = []
    for ch in chunks:
        if merged and len(ch) < CHUNK_MIN_CHARS // 2 and len(merged[-1]) + len(ch) + 2 <= CHUNK_MAX_CHARS:
            merged[-1] = f"{merged[-1]}\n\n{ch}"
        else:
            merged.append(ch)
    return merged


def _build_idf(corpus_tokens: list[list[str]]) -> dict[str, float]:
    n = len(corpus_tokens)
    if n == 0:
        return {}
    df: Counter[str] = Counter()
    for doc in corpus_tokens:
        for term in set(doc):
            df[term] += 1
    idf: dict[str, float] = {}
    for term, freq in df.items():
        idf[term] = math.log((n - freq + 0.5) / (freq + 0.5) + 1.0)
    return idf


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    idf: dict[str, float],
    avg_dl: float,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    dl = len(doc_tokens)
    tf = Counter(doc_tokens)
    score = 0.0
    for term in set(query_tokens):
        if term not in tf:
            continue
        term_idf = idf.get(term, 0.0)
        freq = tf[term]
        denom = freq + k1 * (1.0 - b + b * (dl / avg_dl if avg_dl > 0 else 1.0))
        score += term_idf * (freq * (k1 + 1.0)) / denom
    return score


def _recency_boost(text: str, user_query: str) -> float:
    """
    Boost chunks mentioning target years (e.g. 2025/2026). +0.15 per year hit.
    """
    years_in_query = set(re.findall(r"\b(20[2-3][0-9])\b", user_query))
    if not years_in_query:
        years_in_query = {"2025", "2026"}
    hits = sum(1 for y in years_in_query if y in text)
    bonus = 0.15 * hits
    recent_terms = ("latest", "recent", "current", "today", "this year")
    term_hits = sum(1 for t in recent_terms if t in text.lower())
    return min(0.45, bonus + 0.02 * term_hits)


def _search_hit_boost(url: str, search_hits: list[dict[str, Any]]) -> float:
    for hit in search_hits:
        if str(hit.get("url") or "").strip() == url.strip():
            score = hit.get("relevance_score")
            if score is not None:
                try:
                    return min(0.2, float(score) * 0.1)
                except (TypeError, ValueError):
                    pass
            return 0.03
    return 0.0


def _jaccard_boost(query_tokens: list[str], doc_tokens: list[str]) -> float:
    q_set = set(query_tokens)
    d_set = set(doc_tokens)
    if not q_set or not d_set:
        return 0.0
    inter = len(q_set & d_set)
    union = len(q_set | d_set)
    return inter / union if union else 0.0


def _diversity_penalty(chunk: str, selected_texts: list[str]) -> float:
    """Reduce score when chunk heavily overlaps already-selected content."""
    if not selected_texts:
        return 0.0
    chunk_tokens = set(_tokenize(chunk))
    if not chunk_tokens:
        return 0.0
    max_overlap = 0.0
    for prev in selected_texts:
        prev_tokens = set(_tokenize(prev))
        if not prev_tokens:
            continue
        overlap = len(chunk_tokens & prev_tokens) / len(chunk_tokens)
        max_overlap = max(max_overlap, overlap)
    return max_overlap * 0.35


def select_optimal_context(
    fetched_pages: list[dict],
    user_query: str,
    max_total_chars: int = 8000,
    *,
    search_hits: Optional[list[dict[str, Any]]] = None,
) -> list[dict]:
    """
    Rank text chunks against the user query and return a diverse, budget-limited
    subset with citation metadata (url, title, domain) on every chunk.

    Each returned dict contains:
      text, url, title, domain, score, chunk_index
    """
    max_total_chars = max(500, max_total_chars)
    query_tokens = _tokenize(user_query)
    if not query_tokens:
        query_tokens = _tokenize(user_query.replace("_", " "))

    candidates: list[dict[str, Any]] = []

    for page in fetched_pages:
        text = str(page.get("text") or "").strip()
        if not text:
            continue
        url = str(page.get("url") or "")
        title = str(page.get("title") or "")
        domain = str(page.get("domain") or _safe_domain(url))
        retrieved_at = str(page.get("retrieved_at") or "")
        for idx, chunk in enumerate(_chunk_text(text)):
            candidates.append(
                {
                    "text": chunk,
                    "url": url,
                    "title": title,
                    "domain": domain,
                    "chunk_index": idx,
                    "retrieved_at": retrieved_at,
                }
            )

    if not candidates:
        return []

    corpus_tokens = [_tokenize(c["text"]) for c in candidates]
    idf = _build_idf(corpus_tokens)
    lengths = [len(t) for t in corpus_tokens]
    avg_dl = sum(lengths) / len(lengths) if lengths else 1.0

    hits = search_hits or []
    pool: list[dict[str, Any]] = []
    for cand, doc_tokens in zip(candidates, corpus_tokens):
        bm25 = _bm25_score(query_tokens, doc_tokens, idf, avg_dl)
        jaccard = _jaccard_boost(query_tokens, doc_tokens)
        recency = _recency_boost(str(cand.get("text", "")), user_query)
        hit_boost = _search_hit_boost(str(cand.get("url", "")), hits)
        pool.append(
            {
                **cand,
                "_base_score": bm25 + (0.5 * jaccard) + recency + hit_boost,
            }
        )

    # Iterative maximally diverse selection: re-rank remaining pool each pick.
    selected: list[ContextChunk] = []
    selected_texts: list[str] = []
    used_urls: set[str] = set()
    char_budget = 0
    remaining = list(pool)

    while remaining and char_budget < max_total_chars:
        best_idx = -1
        best_score = -1.0
        best_text = ""
        best_cand: Optional[dict[str, Any]] = None

        for idx, cand in enumerate(remaining):
            raw_text = str(cand["text"])
            room = max_total_chars - char_budget
            if room < 200:
                break
            use_text = raw_text
            if len(use_text) > room:
                use_text = use_text[: room - 3].rstrip() + "..."

            diversity = _diversity_penalty(use_text, selected_texts)
            score = float(cand["_base_score"]) * (1.0 - diversity)
            url = str(cand.get("url") or "")
            if url and url not in used_urls:
                score += 0.05

            if score > best_score:
                best_score = score
                best_idx = idx
                best_text = use_text
                best_cand = cand

        if best_idx < 0 or best_cand is None:
            break

        entry: ContextChunk = {
            "text": best_text,
            "url": best_cand["url"],
            "title": best_cand["title"],
            "domain": best_cand["domain"],
            "score": round(best_score, 4),
            "chunk_index": int(best_cand["chunk_index"]),
            "retrieved_at": best_cand.get("retrieved_at", ""),
        }
        selected.append(entry)
        selected_texts.append(best_text)
        char_budget += len(best_text)
        url_key = str(best_cand.get("url") or "")
        if url_key:
            used_urls.add(url_key)
        remaining.pop(best_idx)

    selected.sort(key=lambda c: float(c.get("score", 0.0)), reverse=True)
    return selected



# Standalone smoke test



async def _demo_async(query: str) -> None:
    print(f"Query: {query}", file=sys.stderr)
    results = execute_web_search(query, max_results=3)
    if not results:
        print(
            "No search results (configure SERPER_API_KEY or TAVILY_API_KEY).",
            file=sys.stderr,
        )
        return

    print(f"Search hits: {len(results)}", file=sys.stderr)
    for i, hit in enumerate(results, 1):
        print(f"  [{i}] {hit['title'][:80]} -> {hit['url']}", file=sys.stderr)

    urls = [h["url"] for h in results if h.get("url")]
    title_by_url = {h["url"]: h.get("title", "") for h in results}
    pages = await fetch_page_content_async(urls[:2], timeout_secs=8)
    for page in pages:
        if not page.get("title") and page.get("url") in title_by_url:
            page["title"] = title_by_url[page["url"]]

    ok_pages = [p for p in pages if p.get("text")]
    print(f"Fetched pages with text: {len(ok_pages)}/{len(pages)}", file=sys.stderr)

    chunks = select_optimal_context(ok_pages, query, max_total_chars=4000)
    print(f"Selected context chunks: {len(chunks)}", file=sys.stderr)
    for i, ch in enumerate(chunks[:3], 1):
        preview = ch["text"][:120].replace("\n", " ")
        print(
            f"  chunk {i} score={ch['score']} domain={ch['domain']} "
            f"preview={preview!r}...",
            file=sys.stderr,
        )


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sample_query = os.environ.get("RESEARCH_DEMO_QUERY", "latest advances in solid-state batteries")
    asyncio.run(_demo_async(sample_query))


if __name__ == "__main__":
    _main()
