"""Tests for Firecrawl wrapper.

DEVIATION FROM PLAN: The installed firecrawl-py==4.28.2 exposes V1FirecrawlApp
(not Firecrawl) with .search() returning a response whose .data is a list of
dicts (not .web list of objects). .scrape_url() is the scrape method (not
.scrape()). The wrapper uses V1FirecrawlApp and normalises accordingly.
"""
import os
from types import SimpleNamespace

import pytest

from src.tools import ToolError
from src.tools import firecrawl as fc


class _FakeSearchResponse:
    """Mimics V1SearchResponse: .data is a list of dicts."""

    def __init__(self, data):
        self.data = data
        self.success = True


class _FakeClient:
    def __init__(self, *, search_data=None, search_exc=None):
        self._search_data = search_data
        self._search_exc = search_exc

    def search(self, query, **kwargs):
        if self._search_exc:
            raise self._search_exc
        return _FakeSearchResponse(self._search_data)


def test_search_news_returns_typed_hits(monkeypatch):
    data = [
        {"title": "T1", "url": "https://a.com", "description": "d1", "markdown": "m1"},
        {"title": "T2", "url": "https://b.com", "description": "d2", "markdown": None},
    ]
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_data=data))
    hits = fc.search_news("AAPL stock news", limit=2)
    assert len(hits) == 2
    assert hits[0].title == "T1"
    assert hits[0].url == "https://a.com"
    assert hits[0].snippet == "d1"


def test_search_news_handles_object_items(monkeypatch):
    """Defensive: SDK may yield objects with attribute access in some builds."""
    item = SimpleNamespace(title="T", url="https://a.com", description="d", markdown="m")
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_data=[item]))
    hits = fc.search_news("q", limit=1)
    assert hits[0].url == "https://a.com"


def test_search_news_empty_data_returns_empty(monkeypatch):
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_data=[]))
    assert fc.search_news("q") == []


def test_search_news_surfaces_errors(monkeypatch):
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_exc=ValueError("429 rate limit")))
    with pytest.raises(ToolError) as ei:
        fc.search_news("q")
    assert ei.value.tool == "firecrawl"
    assert "429" in str(ei.value)


def test_dead_scrape_article_stays_removed():
    """scrape_article (and its Article dataclass) had no callers and was removed
    in the WP-14 sweep; a re-add must be a deliberate decision."""
    assert not hasattr(fc, "scrape_article")
    assert not hasattr(fc, "Article")


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live API")
def test_search_news_live():
    hits = fc.search_news("Apple stock news", limit=2)
    assert all(h.url for h in hits)
