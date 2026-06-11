"""Firecrawl v2 wrapper (firecrawl-py==4.28.2).

DEVIATION FROM PLAN: The installed SDK exposes V1FirecrawlApp (not Firecrawl).
- search(query, limit=...) returns a response whose .data is a list of dicts
  with keys {url, title, description, markdown} — NOT .web list of objects.

search_news(query, limit) -> list[NewsHit]   (v1 search, data field)

Failures surface as ToolError (no silent except). Blocking I/O — callers wrap
with `await asyncio.to_thread(...)`. The unused scrape_article/Article pair was
removed in the WP-14 sweep (no callers).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.config.settings import get_settings
from src.tools import ToolError


@dataclass
class NewsHit:
    title: str
    url: str
    snippet: str
    markdown: str | None  # populated only when search scraped full content


def _get(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from an SDK item that may be an object or a dict."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


@lru_cache(maxsize=1)
def _client():
    # Cached per process; if firecrawl_api_key changes, call `_client.cache_clear()`
    # (mirrors get_llm/get_settings).
    from firecrawl import V1FirecrawlApp  # v2 package; class is V1FirecrawlApp

    return V1FirecrawlApp(api_key=get_settings().firecrawl_api_key)


def search_news(query: str, limit: int = 5) -> list[NewsHit]:
    # APP_FAKE_LLM seam (WP-5): flag read at CALL time; canned deterministic
    # headlines, no network. Lazy import avoids a module cycle.
    if get_settings().fake_llm:
        from src.tools.fake_data import fake_news_hits

        return fake_news_hits(query, limit)
    try:
        result = _client().search(query, limit=limit)
    except Exception as exc:  # surface, never swallow
        raise ToolError("firecrawl", f"search failed: {exc}") from exc

    # V1SearchResponse.data is a list of dicts {url, title, description, markdown}
    data = _get(result, "data", None)
    if data is None:
        data = []

    hits: list[NewsHit] = []
    for item in data:
        url = _get(item, "url")
        if not url:
            continue
        hits.append(
            NewsHit(
                title=_get(item, "title", "") or "",
                url=url,
                snippet=_get(item, "description", "") or "",
                markdown=_get(item, "markdown"),
            )
        )
    return hits
