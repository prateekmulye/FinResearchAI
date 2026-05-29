# WP-B: Tools + Analysts + Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `router`, `news_analyst`, `fundamentals_analyst`, and `technicals_analyst` graph nodes with real async implementations, backed by typed, error-surfacing tool wrappers for Firecrawl (web news), yfinance (fundamentals), and tradingview-ta (technicals).

**Architecture:** Three blocking SDK wrappers in `src/tools/` return typed dataclasses and raise a single `ToolError` on failure (no silent `except`). Three async analyst nodes call their wrapper via `await asyncio.to_thread(...)`, then summarize the raw data into a frozen `AnalystReport` via `get_llm("quick").with_structured_output(AnalystReport, method="function_calling")`. The async `router` node resolves the ticker/screener/exchange via an LLM structured call against a locally-defined `TickerResolution` schema, emits a `model_plan`, and optionally short-circuits on a cached verdict (guarded against WP-C not being merged). Every node creates one `CostTracker(node)` and returns `run_metrics`. No unit test hits the network.

**Tech Stack:** Python 3.13, `firecrawl-py==4.28.2` (v2 `Firecrawl` SDK), `yfinance==0.2.66`, `tradingview-ta==3.3.0`, `langchain-openai==1.1.6`, `pydantic==2.12.5`, `pytest==8.4.2`, `pytest-asyncio>=0.24`, `respx>=0.21`.

---

## Context for the implementer

This WP codes **against the frozen contract** from `2026-05-29-foundation-and-state-contract.md` and `COORDINATION.md`. Import, do not redefine: `get_settings`, `get_llm`, `CostTracker`, `AnalystReport`, `AgentState`. The legacy modules `src/agents/{analyst,manager,reporter}.py` and `src/agents/researchers/*` are being superseded — do **not** import from them; WP-I deletes them later.

**Frozen conventions you must follow exactly:**
- Every node is `async def node(state: AgentState) -> dict`.
- Blocking SDK calls are wrapped: `await asyncio.to_thread(sync_fn, ...)`.
- Structured output: `get_llm(tier).with_structured_output(Schema, method="function_calling")`, then `await llm.ainvoke(messages, config={"callbacks": [tracker]})`, store `result.model_dump()`.
- Each node returns `"run_metrics": tracker.totals()["per_node"]`.
- No network in unit tests: mock `get_llm` (a fake whose `.with_structured_output(...).ainvoke(...)` returns a prepared Pydantic model) and monkeypatch the tool SDK objects / use `respx`. One `@pytest.mark.live` test per external, skipped unless `RUN_LIVE=1`.
- Absolute imports: `from src.llm.factory import get_llm`.

**Verified external APIs (Context7, 2026-05-29 — do NOT guess, use exactly these):**

1. **Firecrawl `firecrawl-py==4.28.2` (v2 SDK).** Import is `from firecrawl import Firecrawl`. Construct `Firecrawl(api_key=...)`. The v1 class `FirecrawlApp` is legacy — use `Firecrawl`.
   - **Search:** `client.search(query: str, limit: int = ...)` returns an object with results grouped by source. The **web** results are at `result.web` — a list of items each exposing `.title`, `.url`, `.description`, and (if scraped) `.markdown`. (Verified from the v2 quickstarts: `for result in results.web: print(result.title, result.url)`; the REST `/v2/search` response is `data.web[]` with `{url, title, description, markdown}`.) **Documented coding assumption:** items support both attribute access (`item.url`) and, defensively, dict access (`item["url"]`); the wrapper normalizes via a `_get(item, "url")` helper that tries attribute then key. This guards against minor SDK shape drift across 4.x patch releases.
   - **Scrape:** `client.scrape(url: str, formats: list[str] = ["markdown"])` returns a document object exposing `.markdown` and `.metadata` (snake_case fields). **Documented coding assumption:** same `_get` normalization for `markdown`.

2. **yfinance `0.2.66`.** `yf.Ticker(symbol).info` -> `dict`. Keys used (verified present in `.info`): `trailingPE`, `forwardPE`, `earningsQuarterlyGrowth`, `revenueGrowth` (fallback `revenueQuarterlyGrowth`), `dividendYield`, `payoutRatio`, `profitMargins` (fallback computed), `grossMargins`, `marketCap`, `beta`, `longName`, `sector`. All reads use `.get(key)` (yfinance omits keys for some tickers). `.info` can raise on a bad symbol — surface as `ToolError`.

3. **tradingview-ta `3.3.0`.** `from tradingview_ta import TA_Handler, Interval`. Construct `TA_Handler(symbol=..., screener=..., exchange=..., interval=Interval.INTERVAL_1_DAY, timeout=10)`, then `.get_analysis()` -> `Analysis` with `.summary` (`{"RECOMMENDATION","BUY","NEUTRAL","SELL"}`), `.oscillators`, `.moving_averages`, and `.indicators` (raw dict: `RSI`, `MACD.macd`, `MACD.signal`, `close`). Bad exchange/symbol raises (commonly the lib's own exception or a network error) — wrap with an exchange-fallback retry + exponential backoff, then `ToolError`.

**Structured-output method risk (must verify at impl start):** `method="function_calling"` requires the chosen Ollama Cloud model (`gpt-oss:20b`) to support OpenAI tool calling. If a live `with_structured_output(...).ainvoke(...)` probe (Task 11) raises a "tool calling not supported" / 400 error, fall back to `method="json_schema"` for the `quick` tier and record the decision here. The analyst/router code reads the method from a module constant `STRUCT_METHOD` so the fallback is a one-line change in each node module.

API keys (`OLLAMA_API_KEY`, `FIRECRAWL_API_KEY`) live in `.env` (gitignored). No unit test reads them.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Add `data`/`web` optional-deps (firecrawl-py, yfinance, tradingview-ta) |
| `src/tools/__init__.py` | Package marker + shared `ToolError` |
| `src/tools/firecrawl.py` | `search_news(query, limit)` + `scrape_article(url)`; typed `NewsHit`/`Article`; surfaces errors |
| `src/tools/yfinance.py` | `fetch_fundamentals(ticker)` -> typed `Fundamentals` dataclass / dict |
| `src/tools/tradingview.py` | `fetch_technicals(ticker, screener, exchange)` -> `Technicals` with exchange-fallback retry + backoff |
| `src/agents/__init__.py` | Package marker (create if absent for new tree) |
| `src/agents/router.py` | async `router` node + local `TickerResolution` schema + `model_plan` + guarded cache short-circuit |
| `src/agents/analysts/__init__.py` | Package marker |
| `src/agents/analysts/news.py` | async `news_analyst` node (Firecrawl -> AnalystReport) |
| `src/agents/analysts/fundamentals.py` | async `fundamentals_analyst` node (yfinance -> AnalystReport) |
| `src/agents/analysts/technicals.py` | async `technicals_analyst` node (tradingview -> AnalystReport) |
| `src/graph.py` | Wire real nodes (coordinated edit with WP-D; see Task 13) |
| `tests/tools/test_firecrawl.py` | Firecrawl wrapper unit tests (monkeypatch SDK) + 1 live |
| `tests/tools/test_yfinance.py` | yfinance wrapper unit tests (monkeypatch Ticker) + 1 live |
| `tests/tools/test_tradingview.py` | tradingview wrapper unit tests (monkeypatch handler) + 1 live |
| `tests/agents/test_router.py` | router node unit tests (mock get_llm) + 1 live |
| `tests/agents/test_news_analyst.py` | news analyst node unit tests (mock get_llm + tool) |
| `tests/agents/test_fundamentals_analyst.py` | fundamentals analyst node unit tests |
| `tests/agents/test_technicals_analyst.py` | technicals analyst node unit tests |

---

### Task 1: Pin tool dependencies in `pyproject.toml`

**Files:**
- Edit: `pyproject.toml`

- [ ] **Step 1: Add the `web` and `data` optional-dependency groups**

Replace the commented placeholder lines in `[project.optional-dependencies]` (added by the Foundation plan) so the `web` and `data` groups are real and pinned:

```toml
[project.optional-dependencies]
# memory  = ["chromadb>=0.5", "fastembed>=0.4"]
web     = ["firecrawl-py==4.28.2"]
data    = ["yfinance==0.2.66", "tradingview-ta==3.3.0"]
# api     = ["fastapi>=0.125", "uvicorn>=0.30", "sse-starlette>=2.1", "httpx>=0.27"]
dev = [
    "pytest==8.4.2",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "ruff>=0.6",
    "mypy>=1.11",
]
```

(Leave the `memory` and `api` lines commented — WP-C / WP-G own them. Keep the existing `dev` block; the snippet above is the full final state of the section.)

- [ ] **Step 2: Install the new groups**

Run: `pip install -e ".[web,data,dev]"`
Expected: resolves and installs `firecrawl-py==4.28.2`, `yfinance==0.2.66`, `tradingview-ta==3.3.0`. Confirm:
Run: `python -c "import firecrawl, yfinance, tradingview_ta; print(firecrawl.__name__, yfinance.__version__)"`
Expected: prints `firecrawl 0.2.66`.

- [ ] **Step 3: Verify the v2 class name is importable**

Run: `python -c "from firecrawl import Firecrawl; print('ok')"`
Expected: prints `ok`. If this raises `ImportError`, the installed firecrawl-py is a v1 line — reinstall `firecrawl-py==4.28.2` and retry. (v1 exposes `FirecrawlApp`; v2 exposes `Firecrawl`.)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(deps): pin firecrawl-py/yfinance/tradingview-ta in web+data groups"
```

---

### Task 2: Shared tool error type

**Files:**
- Create: `src/tools/__init__.py`

- [ ] **Step 1: Write the failing test** (inline in the firecrawl test module is fine, but a tiny dedicated check keeps it isolated)

```python
# tests/tools/test_tool_error.py
import pytest
from src.tools import ToolError


def test_tool_error_carries_tool_and_message():
    err = ToolError("firecrawl", "boom")
    assert err.tool == "firecrawl"
    assert "firecrawl" in str(err)
    assert "boom" in str(err)
    assert isinstance(err, RuntimeError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_tool_error.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/__init__.py
"""External-data tool wrappers (Firecrawl, yfinance, tradingview-ta).

Every wrapper surfaces failures as ToolError — never a silent except. Analyst
nodes catch ToolError and degrade gracefully into a low-confidence report.
"""
from __future__ import annotations


class ToolError(RuntimeError):
    """Raised when an external tool call fails. Carries the tool name."""

    def __init__(self, tool: str, message: str) -> None:
        self.tool = tool
        super().__init__(f"[{tool}] {message}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_tool_error.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add src/tools/__init__.py tests/tools/test_tool_error.py
git commit -m "feat(tools): add shared ToolError type"
```

---

### Task 3: Firecrawl wrapper

**Files:**
- Create: `src/tools/firecrawl.py`
- Test: `tests/tools/test_firecrawl.py`

- [ ] **Step 1: Write the failing test** (monkeypatch the SDK — no network)

```python
# tests/tools/test_firecrawl.py
import os
from types import SimpleNamespace

import pytest

from src.tools import ToolError
from src.tools import firecrawl as fc


class _FakeSearchResult:
    # mimics v2 result: web is a list of items with attribute access
    def __init__(self, web):
        self.web = web


class _FakeClient:
    def __init__(self, *, search_web=None, search_exc=None, scrape_md=None, scrape_exc=None):
        self._search_web = search_web
        self._search_exc = search_exc
        self._scrape_md = scrape_md
        self._scrape_exc = scrape_exc

    def search(self, query, limit=5, **kwargs):
        if self._search_exc:
            raise self._search_exc
        return _FakeSearchResult(self._search_web)

    def scrape(self, url, formats=None, **kwargs):
        if self._scrape_exc:
            raise self._scrape_exc
        return SimpleNamespace(markdown=self._scrape_md, metadata={"source_url": url})


def test_search_news_returns_typed_hits(monkeypatch):
    web = [
        SimpleNamespace(title="T1", url="https://a.com", description="d1", markdown="m1"),
        SimpleNamespace(title="T2", url="https://b.com", description="d2", markdown=None),
    ]
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_web=web))
    hits = fc.search_news("AAPL stock news", limit=2)
    assert len(hits) == 2
    assert hits[0].title == "T1"
    assert hits[0].url == "https://a.com"
    assert hits[0].snippet == "d1"


def test_search_news_handles_dict_items(monkeypatch):
    # defensive: SDK may yield dicts in some patch versions
    web = [{"title": "T", "url": "https://a.com", "description": "d", "markdown": "m"}]
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_web=web))
    hits = fc.search_news("q", limit=1)
    assert hits[0].url == "https://a.com"


def test_search_news_empty_web_returns_empty(monkeypatch):
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_web=[]))
    assert fc.search_news("q") == []


def test_search_news_surfaces_errors(monkeypatch):
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(search_exc=ValueError("429 rate limit")))
    with pytest.raises(ToolError) as ei:
        fc.search_news("q")
    assert ei.value.tool == "firecrawl"
    assert "429" in str(ei.value)


def test_scrape_article_returns_markdown(monkeypatch):
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(scrape_md="# Title\n\nbody"))
    art = fc.scrape_article("https://a.com")
    assert art.url == "https://a.com"
    assert art.markdown.startswith("# Title")


def test_scrape_article_surfaces_errors(monkeypatch):
    monkeypatch.setattr(fc, "_client", lambda: _FakeClient(scrape_exc=RuntimeError("boom")))
    with pytest.raises(ToolError):
        fc.scrape_article("https://a.com")


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live API")
def test_search_news_live():
    hits = fc.search_news("Apple stock news", limit=2)
    assert all(h.url for h in hits)
```

- [ ] **Step 2: Register the `live` marker** so the skipif/marker is clean.

Add to `pyproject.toml` under `[tool.pytest.ini_options]` (append the `markers` key):

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
asyncio_mode = "auto"
markers = [
    "live: hits a real external API; skipped unless RUN_LIVE=1",
]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_firecrawl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.firecrawl'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/tools/firecrawl.py
"""Firecrawl v2 wrapper. SDK class is `Firecrawl` (firecrawl-py==4.28.2).

search_news(query, limit) -> list[NewsHit]   (v2 search, web source)
scrape_article(url)        -> Article         (v2 scrape, markdown format)

Both surface failures as ToolError (no silent except). Blocking I/O — callers
wrap with `await asyncio.to_thread(...)`.
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


@dataclass
class Article:
    url: str
    markdown: str


def _get(item: Any, key: str, default: Any = None) -> Any:
    """Read a field from an SDK item that may be an object or a dict."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


@lru_cache(maxsize=1)
def _client():
    from firecrawl import Firecrawl  # v2 class name (v1 was FirecrawlApp)

    return Firecrawl(api_key=get_settings().firecrawl_api_key)


def search_news(query: str, limit: int = 5) -> list[NewsHit]:
    try:
        result = _client().search(query, limit=limit)
    except Exception as exc:  # surface, never swallow
        raise ToolError("firecrawl", f"search failed: {exc}") from exc

    web = _get(result, "web", None)
    if web is None and isinstance(result, dict):
        web = result.get("data", {}).get("web", [])
    web = web or []

    hits: list[NewsHit] = []
    for item in web:
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


def scrape_article(url: str) -> Article:
    try:
        doc = _client().scrape(url, formats=["markdown"])
    except Exception as exc:
        raise ToolError("firecrawl", f"scrape failed for {url}: {exc}") from exc

    markdown = _get(doc, "markdown") or ""
    if not markdown:
        raise ToolError("firecrawl", f"scrape returned empty markdown for {url}")
    return Article(url=url, markdown=markdown)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_firecrawl.py -v -m "not live"`
Expected: PASS (6 tests; the live test is deselected).

- [ ] **Step 6: Commit**

```bash
git add src/tools/firecrawl.py tests/tools/test_firecrawl.py pyproject.toml
git commit -m "feat(tools): add Firecrawl v2 search_news/scrape_article wrapper"
```

---

### Task 4: yfinance wrapper

**Files:**
- Create: `src/tools/yfinance.py`
- Test: `tests/tools/test_yfinance.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_yfinance.py
import os
from types import SimpleNamespace

import pytest

from src.tools import ToolError
from src.tools import yfinance as yfw


def test_fetch_fundamentals_maps_keys(monkeypatch):
    info = {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "trailingPE": 28.0,
        "forwardPE": 25.0,
        "earningsQuarterlyGrowth": 0.1,
        "revenueGrowth": 0.05,
        "dividendYield": 0.0056,
        "payoutRatio": 0.15,
        "profitMargins": 0.25,
        "grossMargins": 0.44,
        "marketCap": 2_700_000_000_000,
        "beta": 1.2,
    }
    monkeypatch.setattr(yfw, "_ticker_info", lambda t: info)
    f = yfw.fetch_fundamentals("AAPL")
    assert f.name == "Apple Inc."
    assert f.trailing_pe == 28.0
    assert f.dividend_yield == 0.0056
    assert f.profit_margins == 0.25
    d = f.to_dict()
    assert d["forward_pe"] == 25.0
    assert d["sector"] == "Technology"


def test_fetch_fundamentals_tolerates_missing_keys(monkeypatch):
    monkeypatch.setattr(yfw, "_ticker_info", lambda t: {"longName": "X Corp"})
    f = yfw.fetch_fundamentals("X")
    assert f.name == "X Corp"
    assert f.trailing_pe is None
    assert f.market_cap is None


def test_fetch_fundamentals_empty_info_raises(monkeypatch):
    monkeypatch.setattr(yfw, "_ticker_info", lambda t: {})
    with pytest.raises(ToolError) as ei:
        yfw.fetch_fundamentals("BADTICKER")
    assert ei.value.tool == "yfinance"


def test_fetch_fundamentals_surfaces_sdk_error(monkeypatch):
    def _boom(t):
        raise ConnectionError("yahoo down")

    monkeypatch.setattr(yfw, "_ticker_info", _boom)
    with pytest.raises(ToolError):
        yfw.fetch_fundamentals("AAPL")


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live API")
def test_fetch_fundamentals_live():
    f = yfw.fetch_fundamentals("AAPL")
    assert f.name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_yfinance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.yfinance'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/yfinance.py
"""yfinance wrapper (yfinance==0.2.66).

fetch_fundamentals(ticker) -> Fundamentals. Reads `yf.Ticker(t).info` (a dict)
and maps the verified keys. Missing keys are tolerated (yfinance omits them per
ticker); an empty/unusable info dict or any SDK error surfaces as ToolError.
Blocking I/O — callers wrap with `await asyncio.to_thread(...)`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from src.tools import ToolError


@dataclass
class Fundamentals:
    ticker: str
    name: str | None
    sector: str | None
    trailing_pe: float | None
    forward_pe: float | None
    earnings_growth: float | None
    revenue_growth: float | None
    dividend_yield: float | None
    payout_ratio: float | None
    profit_margins: float | None
    gross_margins: float | None
    market_cap: float | None
    beta: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _ticker_info(ticker: str) -> dict:
    import yfinance as yf

    return yf.Ticker(ticker).info or {}


def fetch_fundamentals(ticker: str) -> Fundamentals:
    try:
        info = _ticker_info(ticker)
    except Exception as exc:
        raise ToolError("yfinance", f"info fetch failed for {ticker}: {exc}") from exc

    # A valid ticker returns a rich dict; an unknown symbol returns {} or a
    # near-empty stub with no name/marketCap.
    if not info or (info.get("longName") is None and info.get("marketCap") is None):
        raise ToolError("yfinance", f"no fundamentals for {ticker!r}")

    return Fundamentals(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        trailing_pe=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        earnings_growth=info.get("earningsQuarterlyGrowth"),
        revenue_growth=info.get("revenueGrowth", info.get("revenueQuarterlyGrowth")),
        dividend_yield=info.get("dividendYield"),
        payout_ratio=info.get("payoutRatio"),
        profit_margins=info.get("profitMargins"),
        gross_margins=info.get("grossMargins"),
        market_cap=info.get("marketCap"),
        beta=info.get("beta"),
    )
```

Note: `test_fetch_fundamentals_tolerates_missing_keys` passes `{"longName": "X Corp"}` — that has a name, so it survives the empty-guard, and all other fields default to `None`. Good.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_yfinance.py -v -m "not live"`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/tools/yfinance.py tests/tools/test_yfinance.py
git commit -m "feat(tools): add yfinance fetch_fundamentals wrapper"
```

---

### Task 5: tradingview-ta wrapper

**Files:**
- Create: `src/tools/tradingview.py`
- Test: `tests/tools/test_tradingview.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_tradingview.py
import os
from types import SimpleNamespace

import pytest

from src.tools import ToolError
from src.tools import tradingview as tv


def _fake_analysis():
    return SimpleNamespace(
        summary={"RECOMMENDATION": "BUY", "BUY": 12, "NEUTRAL": 9, "SELL": 7},
        oscillators={"RECOMMENDATION": "NEUTRAL"},
        moving_averages={"RECOMMENDATION": "BUY"},
        indicators={"RSI": 55.2, "MACD.macd": 2.4, "MACD.signal": 1.9, "close": 170.0},
    )


def test_fetch_technicals_maps_fields(monkeypatch):
    monkeypatch.setattr(tv, "_analyze", lambda **kw: _fake_analysis())
    t = tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert t.recommendation == "BUY"
    assert t.rsi == 55.2
    assert t.macd == 2.4
    assert t.macd_signal == 1.9
    d = t.to_dict()
    assert d["buy_signals"] == 12
    assert d["sell_signals"] == 7


def test_fetch_technicals_exchange_fallback(monkeypatch):
    calls = []

    def _analyze(*, symbol, screener, exchange, **kw):
        calls.append(exchange)
        if exchange == "NASDAQ":
            raise ValueError("symbol not found on NASDAQ")
        return _fake_analysis()

    monkeypatch.setattr(tv, "_analyze", _analyze)
    monkeypatch.setattr(tv, "_BACKOFF_BASE", 0.0)  # no real sleeping in tests
    t = tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert t.recommendation == "BUY"
    assert "NASDAQ" in calls and "NYSE" in calls  # fell back to NYSE


def test_fetch_technicals_all_exchanges_fail_raises(monkeypatch):
    monkeypatch.setattr(tv, "_analyze", lambda **kw: (_ for _ in ()).throw(ValueError("nope")))
    monkeypatch.setattr(tv, "_BACKOFF_BASE", 0.0)
    with pytest.raises(ToolError) as ei:
        tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert ei.value.tool == "tradingview"


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live API")
def test_fetch_technicals_live():
    t = tv.fetch_technicals("AAPL", screener="america", exchange="NASDAQ")
    assert t.recommendation in {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tools/test_tradingview.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.tradingview'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tools/tradingview.py
"""tradingview-ta wrapper (tradingview-ta==3.3.0).

fetch_technicals(ticker, screener, exchange) -> Technicals.
Uses TA_Handler(...).get_analysis(); reads .summary + .indicators.
Keeps an exchange-fallback retry with exponential backoff (mitigates the
rate-limit / wrong-exchange risk noted in the design spec §8.4), then ToolError.
Blocking I/O — callers wrap with `await asyncio.to_thread(...)`.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass

from src.tools import ToolError

# Fallback chain by screener: if the primary exchange fails, try siblings.
_FALLBACKS: dict[str, list[str]] = {
    "america": ["NASDAQ", "NYSE", "AMEX"],
    "india": ["NSE", "BSE"],
}
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5  # seconds; monkeypatched to 0.0 in unit tests


@dataclass
class Technicals:
    ticker: str
    exchange: str
    recommendation: str
    buy_signals: int
    neutral_signals: int
    sell_signals: int
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    close: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _analyze(*, symbol: str, screener: str, exchange: str):
    from tradingview_ta import TA_Handler, Interval

    handler = TA_Handler(
        symbol=symbol,
        screener=screener,
        exchange=exchange,
        interval=Interval.INTERVAL_1_DAY,
        timeout=10,
    )
    return handler.get_analysis()


def _candidate_exchanges(screener: str, exchange: str) -> list[str]:
    chain = list(_FALLBACKS.get(screener, []))
    ordered = [exchange] + [e for e in chain if e != exchange]
    return ordered or [exchange]


def fetch_technicals(ticker: str, screener: str, exchange: str) -> Technicals:
    last_exc: Exception | None = None
    for attempt, ex in enumerate(_candidate_exchanges(screener, exchange)):
        try:
            analysis = _analyze(symbol=ticker, screener=screener, exchange=ex)
        except Exception as exc:  # rate limit / wrong exchange / network
            last_exc = exc
            time.sleep(_BACKOFF_BASE * (2 ** attempt))
            continue
        summary = analysis.summary or {}
        ind = analysis.indicators or {}
        return Technicals(
            ticker=ticker,
            exchange=ex,
            recommendation=summary.get("RECOMMENDATION", "NEUTRAL"),
            buy_signals=int(summary.get("BUY", 0)),
            neutral_signals=int(summary.get("NEUTRAL", 0)),
            sell_signals=int(summary.get("SELL", 0)),
            rsi=ind.get("RSI"),
            macd=ind.get("MACD.macd"),
            macd_signal=ind.get("MACD.signal"),
            close=ind.get("close"),
        )
    raise ToolError(
        "tradingview",
        f"all exchanges failed for {ticker} ({screener}): {last_exc}",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tools/test_tradingview.py -v -m "not live"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/tools/tradingview.py tests/tools/test_tradingview.py
git commit -m "feat(tools): add tradingview-ta fetch_technicals with exchange fallback"
```

---

### Task 6: Router node — local `TickerResolution` schema + node skeleton

**Files:**
- Create: `src/agents/__init__.py` (if absent)
- Create: `src/agents/router.py`
- Test: `tests/agents/test_router.py` (resolution + model_plan part)

> `TickerResolution` is defined **locally in `src/agents/router.py`** (not in the frozen `src/llm/schemas.py`) per the WP-B brief, to avoid touching the frozen contract.

- [ ] **Step 1: Write the failing test** (mock `get_llm`; no network)

```python
# tests/agents/test_router.py
import pytest

from src.agents import router as router_mod
from src.agents.router import TickerResolution, router


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        assert method in {"function_calling", "json_schema"}
        return _FakeStructured(self._result)


@pytest.fixture
def patch_llm(monkeypatch):
    def _install(resolution: TickerResolution):
        monkeypatch.setattr(router_mod, "get_llm", lambda tier: _FakeLLM(resolution))

    return _install


async def test_router_resolves_and_plans(patch_llm, monkeypatch):
    # ensure no cache module short-circuits
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda *a, **k: None)
    patch_llm(TickerResolution(resolved_ticker="RELIANCE.NS", screener="india", exchange="NSE"))
    out = await router({"ticker": "RELIANCE", "investor_mode": "Neutral"})
    assert out["resolved_ticker"] == "RELIANCE.NS"
    assert out["screener"] == "india"
    assert out["exchange"] == "NSE"
    assert out["model_plan"]["analysts"] == "quick"
    assert out["model_plan"]["debate"] == "deep"
    assert isinstance(out["run_metrics"], list)
    assert out["run_metrics"][0]["node"] == "router"


async def test_router_us_ticker(patch_llm, monkeypatch):
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda *a, **k: None)
    patch_llm(TickerResolution(resolved_ticker="AAPL", screener="america", exchange="NASDAQ"))
    out = await router({"ticker": "AAPL", "investor_mode": "Bullish"})
    assert out["resolved_ticker"] == "AAPL"
    assert out["exchange"] == "NASDAQ"


def test_ticker_resolution_schema_defaults():
    r = TickerResolution(resolved_ticker="MSFT")
    assert r.screener == "america"
    assert r.exchange == "NASDAQ"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.router'` (or `src.agents` if the package marker is missing).

- [ ] **Step 3: Create `src/agents/__init__.py`** (empty package marker — only if it does not already exist)

```python
```

- [ ] **Step 4: Write minimal implementation**

```python
# src/agents/router.py
"""Router node: resolve ticker -> (resolved_ticker, screener, exchange), pick a
model plan, and optionally short-circuit on a cached verdict.

`TickerResolution` is defined locally (not in the frozen src/llm/schemas.py) to
keep the data contract untouched, per WP-B scope.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.llm.cost import CostTracker
from src.llm.factory import get_llm

# Flip to "json_schema" only if the quick model lacks tool calling (see Task 11).
STRUCT_METHOD = "function_calling"

_SYSTEM = """You resolve a user-provided stock symbol or company name to an exact
exchange-qualified ticker for data APIs.

Rules:
- US (NASDAQ/NYSE/AMEX): no suffix. screener="america".
- India NSE: suffix ".NS", screener="india", exchange="NSE". BSE: ".BO", "BSE".
- Japan TSE: ".T", screener="japan", exchange="TSE".
- China SSE: ".SS" / SZSE: ".SZ", screener="china".
- Hong Kong HKEX: ".HK", screener="hongkong", exchange="HKEX".
Return resolved_ticker exactly as a data API expects it."""


class TickerResolution(BaseModel):
    """LLM-resolved symbol routing. Local to WP-B (not the frozen schema set)."""

    resolved_ticker: str = Field(description="Exchange-qualified ticker, e.g. AAPL or RELIANCE.NS")
    screener: str = Field(default="america", description="TradingView screener, e.g. america, india")
    exchange: str = Field(default="NASDAQ", description="Exchange code, e.g. NASDAQ, NSE")


def _model_plan() -> dict:
    """Tier-per-phase routing (M7). Quick for retrieval/analysts; deep for reasoning."""
    return {"analysts": "quick", "debate": "deep", "verdict": "deep", "risk": "deep"}


def _get_cached_verdict(ticker: str, max_age_min: int):
    """Guarded import of the WP-C cache. Returns None if memory is not merged yet."""
    try:
        from src.memory.cache import get_cached_verdict
    except ImportError:
        return None
    try:
        return get_cached_verdict(ticker, max_age_min)
    except Exception:
        return None


async def router(state: dict) -> dict:
    tracker = CostTracker("router")
    raw_ticker = (state.get("ticker") or "").strip()

    llm = get_llm("quick").with_structured_output(TickerResolution, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Resolve this symbol or company: {raw_ticker!r}"),
    ]
    resolution: TickerResolution = await llm.ainvoke(messages, config={"callbacks": [tracker]})

    out: dict = {
        "resolved_ticker": resolution.resolved_ticker,
        "screener": resolution.screener,
        "exchange": resolution.exchange,
        "model_plan": _model_plan(),
        "run_metrics": tracker.totals()["per_node"],
    }

    # Optional cache short-circuit (WP-C). If a fresh verdict exists, attach it so
    # the graph (WP-D's conditional edge) can skip straight to the reporter.
    cached = _get_cached_verdict(resolution.resolved_ticker, max_age_min=60)
    if cached is not None:
        out["final_decision"] = cached.model_dump()
        out["model_plan"] = {**out["model_plan"], "cache_hit": True}

    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/agents/test_router.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/agents/__init__.py src/agents/router.py tests/agents/test_router.py
git commit -m "feat(router): async ticker resolution + model plan + guarded cache"
```

---

### Task 7: Router — cache short-circuit test

**Files:**
- Edit: `tests/agents/test_router.py`

- [ ] **Step 1: Add a failing test** for the cache hit path (mock the guarded cache fn)

```python
# append to tests/agents/test_router.py
from src.llm.schemas import FinalDecision


async def test_router_cache_short_circuits(patch_llm, monkeypatch):
    patch_llm(TickerResolution(resolved_ticker="AAPL", screener="america", exchange="NASDAQ"))
    cached = FinalDecision(action="BUY", conviction=0.7, score=72, rationale="cached")
    monkeypatch.setattr(router_mod, "_get_cached_verdict", lambda ticker, max_age_min: cached)
    out = await router({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert out["final_decision"]["action"] == "BUY"
    assert out["final_decision"]["score"] == 72
    assert out["model_plan"]["cache_hit"] is True
```

- [ ] **Step 2: Run** `python -m pytest tests/agents/test_router.py -v`
Expected: PASS (4 tests). (The implementation from Task 6 already supports this; this test pins the behavior.)

- [ ] **Step 3: Commit**

```bash
git add tests/agents/test_router.py
git commit -m "test(router): pin cache short-circuit behavior"
```

---

### Task 8: News analyst node

**Files:**
- Create: `src/agents/analysts/__init__.py`
- Create: `src/agents/analysts/news.py`
- Test: `tests/agents/test_news_analyst.py`

- [ ] **Step 1: Write the failing test** (mock `get_llm` + the firecrawl wrapper)

```python
# tests/agents/test_news_analyst.py
import pytest

from src.agents.analysts import news as news_mod
from src.agents.analysts.news import news_analyst
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.firecrawl import NewsHit


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        return _FakeStructured(self._result)


def _install_llm(monkeypatch, report):
    monkeypatch.setattr(news_mod, "get_llm", lambda tier: _FakeLLM(report))


async def test_news_analyst_happy_path(monkeypatch):
    hits = [NewsHit(title="Apple beats earnings", url="https://x.com", snippet="strong q", markdown=None)]
    monkeypatch.setattr(news_mod, "search_news", lambda q, limit=5: hits)
    report = AnalystReport(summary="Positive coverage", key_points=["earnings beat"], confidence=0.7,
                           citations=["https://x.com"])
    _install_llm(monkeypatch, report)
    out = await news_analyst({"resolved_ticker": "AAPL"})
    assert "news" in out["analyst_reports"]
    assert out["analyst_reports"]["news"]["summary"] == "Positive coverage"
    assert out["run_metrics"][0]["node"] == "news_analyst"


async def test_news_analyst_tool_failure_degrades(monkeypatch):
    def _boom(q, limit=5):
        raise ToolError("firecrawl", "429")

    monkeypatch.setattr(news_mod, "search_news", _boom)
    # get_llm must NOT be called on the failure path
    monkeypatch.setattr(news_mod, "get_llm", lambda tier: (_ for _ in ()).throw(AssertionError("llm called")))
    out = await news_analyst({"resolved_ticker": "AAPL"})
    rep = out["analyst_reports"]["news"]
    assert rep["confidence"] == 0.0
    assert "firecrawl" in rep["summary"].lower() or "unavailable" in rep["summary"].lower()
    assert out["run_metrics"][0]["node"] == "news_analyst"


async def test_news_analyst_empty_hits_degrades(monkeypatch):
    monkeypatch.setattr(news_mod, "search_news", lambda q, limit=5: [])
    monkeypatch.setattr(news_mod, "get_llm", lambda tier: (_ for _ in ()).throw(AssertionError("llm called")))
    out = await news_analyst({"resolved_ticker": "AAPL"})
    assert out["analyst_reports"]["news"]["confidence"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agents/test_news_analyst.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.agents.analysts.news'`

- [ ] **Step 3: Create `src/agents/analysts/__init__.py`** (empty) and write the node

```python
```

```python
# src/agents/analysts/news.py
"""News analyst: Firecrawl search -> structured AnalystReport (quick tier)."""
from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.firecrawl import search_news

STRUCT_METHOD = "function_calling"

_SYSTEM = """You are a financial news analyst. Given recent web headlines and
snippets about a stock, produce a concise sentiment summary, 3-5 key points, a
confidence in [0,1], and the source URLs as citations. Be factual; do not invent
news that is not in the provided material."""


def _degraded(reason: str) -> AnalystReport:
    return AnalystReport(summary=f"News unavailable: {reason}", confidence=0.0)


async def news_analyst(state: dict) -> dict:
    tracker = CostTracker("news_analyst")
    ticker = state.get("resolved_ticker") or state.get("ticker") or ""

    try:
        hits = await asyncio.to_thread(search_news, f"{ticker} stock news latest", 5)
    except ToolError as exc:
        return {
            "analyst_reports": {"news": _degraded(str(exc)).model_dump()},
            "run_metrics": tracker.totals()["per_node"],
        }

    if not hits:
        return {
            "analyst_reports": {"news": _degraded("no results").model_dump()},
            "run_metrics": tracker.totals()["per_node"],
        }

    material = "\n".join(f"- {h.title} ({h.url}): {h.snippet}" for h in hits)
    llm = get_llm("quick").with_structured_output(AnalystReport, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Ticker: {ticker}\nHeadlines:\n{material}"),
    ]
    report: AnalystReport = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    return {
        "analyst_reports": {"news": report.model_dump()},
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/agents/test_news_analyst.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/agents/analysts/__init__.py src/agents/analysts/news.py tests/agents/test_news_analyst.py
git commit -m "feat(analyst): async news_analyst (Firecrawl -> AnalystReport)"
```

---

### Task 9: Fundamentals analyst node

**Files:**
- Create: `src/agents/analysts/fundamentals.py`
- Test: `tests/agents/test_fundamentals_analyst.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_fundamentals_analyst.py
import pytest

from src.agents.analysts import fundamentals as fund_mod
from src.agents.analysts.fundamentals import fundamentals_analyst
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.yfinance import Fundamentals


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        return _FakeStructured(self._result)


def _fund():
    return Fundamentals(
        ticker="AAPL", name="Apple Inc.", sector="Technology", trailing_pe=28.0,
        forward_pe=25.0, earnings_growth=0.1, revenue_growth=0.05, dividend_yield=0.0056,
        payout_ratio=0.15, profit_margins=0.25, gross_margins=0.44,
        market_cap=2.7e12, beta=1.2,
    )


async def test_fundamentals_analyst_happy_path(monkeypatch):
    monkeypatch.setattr(fund_mod, "fetch_fundamentals", lambda t: _fund())
    report = AnalystReport(summary="Healthy margins", key_points=["P/E 28"], confidence=0.65)
    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: _FakeLLM(report))
    out = await fundamentals_analyst({"resolved_ticker": "AAPL"})
    rep = out["analyst_reports"]["fundamentals"]
    assert rep["summary"] == "Healthy margins"
    assert rep["data"]["trailing_pe"] == 28.0  # raw numbers attached for the reporter
    assert out["run_metrics"][0]["node"] == "fundamentals_analyst"


async def test_fundamentals_analyst_tool_failure_degrades(monkeypatch):
    def _boom(t):
        raise ToolError("yfinance", "no fundamentals")

    monkeypatch.setattr(fund_mod, "fetch_fundamentals", _boom)
    monkeypatch.setattr(fund_mod, "get_llm", lambda tier: (_ for _ in ()).throw(AssertionError("llm called")))
    out = await fundamentals_analyst({"resolved_ticker": "BAD"})
    assert out["analyst_reports"]["fundamentals"]["confidence"] == 0.0
```

- [ ] **Step 2: Run** `python -m pytest tests/agents/test_fundamentals_analyst.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the node**

```python
# src/agents/analysts/fundamentals.py
"""Fundamentals analyst: yfinance -> structured AnalystReport (quick tier).

The raw numeric fundamentals are attached to report.data so the reporter (WP-F)
can render charts without re-fetching.
"""
from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.yfinance import fetch_fundamentals

STRUCT_METHOD = "function_calling"

_SYSTEM = """You are a fundamentals analyst. Given a company's financial metrics
(P/E, growth, margins, dividend, beta), summarize financial health, list 3-5 key
points, and give a confidence in [0,1]. Reason only from the numbers provided."""


def _degraded(reason: str) -> AnalystReport:
    return AnalystReport(summary=f"Fundamentals unavailable: {reason}", confidence=0.0)


async def fundamentals_analyst(state: dict) -> dict:
    tracker = CostTracker("fundamentals_analyst")
    ticker = state.get("resolved_ticker") or state.get("ticker") or ""

    try:
        f = await asyncio.to_thread(fetch_fundamentals, ticker)
    except ToolError as exc:
        return {
            "analyst_reports": {"fundamentals": _degraded(str(exc)).model_dump()},
            "run_metrics": tracker.totals()["per_node"],
        }

    data = f.to_dict()
    llm = get_llm("quick").with_structured_output(AnalystReport, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Ticker: {ticker}\nMetrics: {data}"),
    ]
    report: AnalystReport = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    # Attach raw numbers for the reporter; preserve any LLM-provided data too.
    merged = {**data, **(report.data or {})}
    report = report.model_copy(update={"data": merged})
    return {
        "analyst_reports": {"fundamentals": report.model_dump()},
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 4: Run** `python -m pytest tests/agents/test_fundamentals_analyst.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/agents/analysts/fundamentals.py tests/agents/test_fundamentals_analyst.py
git commit -m "feat(analyst): async fundamentals_analyst (yfinance -> AnalystReport)"
```

---

### Task 10: Technicals analyst node

**Files:**
- Create: `src/agents/analysts/technicals.py`
- Test: `tests/agents/test_technicals_analyst.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_technicals_analyst.py
import pytest

from src.agents.analysts import technicals as tech_mod
from src.agents.analysts.technicals import technicals_analyst
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.tradingview import Technicals


class _FakeStructured:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        return _FakeStructured(self._result)


def _tech():
    return Technicals(
        ticker="AAPL", exchange="NASDAQ", recommendation="BUY", buy_signals=12,
        neutral_signals=9, sell_signals=7, rsi=55.2, macd=2.4, macd_signal=1.9, close=170.0,
    )


async def test_technicals_analyst_happy_path(monkeypatch):
    monkeypatch.setattr(tech_mod, "fetch_technicals", lambda t, screener, exchange: _tech())
    report = AnalystReport(summary="Bullish momentum", key_points=["RSI 55"], confidence=0.6)
    monkeypatch.setattr(tech_mod, "get_llm", lambda tier: _FakeLLM(report))
    out = await technicals_analyst({"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"})
    rep = out["analyst_reports"]["technicals"]
    assert rep["summary"] == "Bullish momentum"
    assert rep["data"]["recommendation"] == "BUY"
    assert out["run_metrics"][0]["node"] == "technicals_analyst"


async def test_technicals_analyst_tool_failure_degrades(monkeypatch):
    def _boom(t, screener, exchange):
        raise ToolError("tradingview", "all exchanges failed")

    monkeypatch.setattr(tech_mod, "fetch_technicals", _boom)
    monkeypatch.setattr(tech_mod, "get_llm", lambda tier: (_ for _ in ()).throw(AssertionError("llm called")))
    out = await technicals_analyst({"resolved_ticker": "AAPL", "screener": "america", "exchange": "NASDAQ"})
    assert out["analyst_reports"]["technicals"]["confidence"] == 0.0
```

- [ ] **Step 2: Run** `python -m pytest tests/agents/test_technicals_analyst.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the node**

```python
# src/agents/analysts/technicals.py
"""Technicals analyst: tradingview-ta -> structured AnalystReport (quick tier)."""
from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm.cost import CostTracker
from src.llm.factory import get_llm
from src.llm.schemas import AnalystReport
from src.tools import ToolError
from src.tools.tradingview import fetch_technicals

STRUCT_METHOD = "function_calling"

_SYSTEM = """You are a technical analyst. Given TradingView signals (overall
recommendation, buy/neutral/sell counts, RSI, MACD), summarize the technical
posture, list 3-5 key points, and give a confidence in [0,1]. Reason only from
the indicators provided."""


def _degraded(reason: str) -> AnalystReport:
    return AnalystReport(summary=f"Technicals unavailable: {reason}", confidence=0.0)


async def technicals_analyst(state: dict) -> dict:
    tracker = CostTracker("technicals_analyst")
    ticker = state.get("resolved_ticker") or state.get("ticker") or ""
    screener = state.get("screener", "america")
    exchange = state.get("exchange", "NASDAQ")

    try:
        t = await asyncio.to_thread(fetch_technicals, ticker, screener, exchange)
    except ToolError as exc:
        return {
            "analyst_reports": {"technicals": _degraded(str(exc)).model_dump()},
            "run_metrics": tracker.totals()["per_node"],
        }

    data = t.to_dict()
    llm = get_llm("quick").with_structured_output(AnalystReport, method=STRUCT_METHOD)
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=f"Ticker: {ticker}\nSignals: {data}"),
    ]
    report: AnalystReport = await llm.ainvoke(messages, config={"callbacks": [tracker]})
    merged = {**data, **(report.data or {})}
    report = report.model_copy(update={"data": merged})
    return {
        "analyst_reports": {"technicals": report.model_dump()},
        "run_metrics": tracker.totals()["per_node"],
    }
```

- [ ] **Step 4: Run** `python -m pytest tests/agents/test_technicals_analyst.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/agents/analysts/technicals.py tests/agents/test_technicals_analyst.py
git commit -m "feat(analyst): async technicals_analyst (tradingview -> AnalystReport)"
```

---

### Task 11: Live structured-output probe + method decision

**Files:**
- Create: `tests/agents/test_struct_method_live.py`

> This is the one explicit verification of the structured-output risk flagged in COORDINATION §2. It is skipped in CI; run it once locally to lock in `function_calling` vs `json_schema`.

- [ ] **Step 1: Write the live probe test**

```python
# tests/agents/test_struct_method_live.py
import os

import pytest
from langchain_core.messages import HumanMessage

from src.agents.router import TickerResolution
from src.llm.factory import get_llm


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="set RUN_LIVE=1 for live LLM")
async def test_quick_model_supports_function_calling():
    """Verify the quick tier handles with_structured_output(method='function_calling').
    If this raises a 'tool calling not supported' / 400 error, change STRUCT_METHOD
    to 'json_schema' in router.py + the three analyst modules and re-run."""
    llm = get_llm("quick").with_structured_output(TickerResolution, method="function_calling")
    result = await llm.ainvoke([HumanMessage(content="Resolve the ticker for Apple Inc.")])
    assert isinstance(result, TickerResolution)
    assert result.resolved_ticker
```

- [ ] **Step 2: Run it once locally** (requires `OLLAMA_API_KEY` in `.env`)

Run: `RUN_LIVE=1 python -m pytest tests/agents/test_struct_method_live.py -v -m live`
Expected (PASS): `function_calling` works on `gpt-oss:20b` — leave all `STRUCT_METHOD = "function_calling"`. Done.
Expected (FAIL with a tool-calling/400 error): set `STRUCT_METHOD = "json_schema"` in `src/agents/router.py`, `src/agents/analysts/news.py`, `fundamentals.py`, `technicals.py`, re-run, and note the change in the Definition of Done. Unit tests are unaffected (the fake LLM accepts either method).

- [ ] **Step 3: Commit**

```bash
git add tests/agents/test_struct_method_live.py
git commit -m "test(llm): add live probe for quick-tier function-calling support"
```

---

### Task 12: Full WP-B suite green (no network)

**Files:** none (verification gate)

- [ ] **Step 1: Run the whole WP-B test surface, live deselected**

Run: `python -m pytest tests/tools tests/agents -v -m "not live"`
Expected: all PASS — tool wrappers (firecrawl 6, yfinance 4, tradingview 3, tool_error 1) + nodes (router 4, news 3, fundamentals 2, technicals 2). No network access occurred.

- [ ] **Step 2: Run the full repo suite to confirm no regression**

Run: `python -m pytest -q -m "not live"`
Expected: Foundation tests (settings/cost/factory/recorder/schemas/state/graph/smoke) + all WP-B tests PASS.

- [ ] **Step 3: Lint**

Run: `ruff check src/tools src/agents`
Expected: no errors. Fix any before proceeding.

---

### Task 13: Wire real nodes into `build_graph` (coordinated with WP-D)

**Files:**
- Edit: `src/graph.py`

> **Ownership note:** `build_graph` is owned by **WP-D** (it evolves `build_graph(debate_mode)` and the bull/bear/facilitator wiring). This task changes ONLY the four node *registrations* WP-B owns (router + three analysts), leaving WP-D's edges and debate nodes untouched. If WP-D has not merged its `build_graph` changes, this edit still composes because it only swaps the `g.add_node(...)` callables for the four WP-B nodes; the stub edges from the Foundation graph remain valid. Coordinate merge order: if WP-D merges first, re-apply this same swap on top of WP-D's `build_graph`.

- [ ] **Step 1: Replace the stub node definitions/imports for the four WP-B nodes**

In `src/graph.py`, delete the local stub functions `router`, `_analyst` (and its three usages) and import the real nodes at the top:

```python
from src.agents.router import router
from src.agents.analysts.news import news_analyst
from src.agents.analysts.fundamentals import fundamentals_analyst
from src.agents.analysts.technicals import technicals_analyst
```

Then in `build_graph`, replace the analyst registration loop:

```python
    g.add_node("router", router)
    g.add_node("news_analyst", news_analyst)
    g.add_node("fundamentals_analyst", fundamentals_analyst)
    g.add_node("technicals_analyst", technicals_analyst)
```

Leave the edge wiring (`router -> *_analyst`, `*_analyst -> bull/bear`, etc.) and the remaining stub nodes (bull/bear/facilitator/trader/risk_*/reporter) exactly as the Foundation/WP-D version has them. The analyst node names already match the frozen contract (`news_analyst`, `fundamentals_analyst`, `technicals_analyst`).

- [ ] **Step 2: Guard the import so the graph still compiles in a partial checkout**

If a parallel branch has not merged WP-B yet, a bare import would break `build_graph`. To keep the graph importable, wrap the four imports in a try/except that falls back to the existing stubs (keep the stub fns in the file, renamed `_stub_router`, `_stub_analyst`):

```python
try:
    from src.agents.router import router
    from src.agents.analysts.news import news_analyst
    from src.agents.analysts.fundamentals import fundamentals_analyst
    from src.agents.analysts.technicals import technicals_analyst
    _REAL_NODES = True
except ImportError:  # WP-B not merged in this checkout
    _REAL_NODES = False
```

and register conditionally:

```python
    if _REAL_NODES:
        g.add_node("router", router)
        g.add_node("news_analyst", news_analyst)
        g.add_node("fundamentals_analyst", fundamentals_analyst)
        g.add_node("technicals_analyst", technicals_analyst)
    else:
        g.add_node("router", _stub_router)
        g.add_node("news_analyst", _stub_analyst("news"))
        g.add_node("fundamentals_analyst", _stub_analyst("fundamentals"))
        g.add_node("technicals_analyst", _stub_analyst("technicals"))
```

(Coordinate with WP-D so only one of WP-B / WP-D owns the final shape of this block; this guard is the safe interim.)

- [ ] **Step 3: Update the skeleton test to tolerate real async nodes (compile-only)**

The Foundation `tests/test_graph_skeleton.py` invokes the graph synchronously and asserts 12 metric rows. With real nodes, `app.invoke` would hit the network. Add a compile-only assertion and mark the live end-to-end run as opt-in. Append:

```python
# tests/test_graph_wiring.py
from src.graph import build_graph


def test_graph_compiles_with_real_nodes():
    app = build_graph()
    nodes = set(app.get_graph().nodes)
    assert {"router", "news_analyst", "fundamentals_analyst", "technicals_analyst"} <= nodes
```

> Do NOT modify the existing Foundation `test_graph_skeleton.py` end-to-end test here — WP-I owns reconciling the stub end-to-end test with mocked real nodes (integration layer). This task only adds a non-network compile/wiring assertion.

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_graph_wiring.py -v && ruff check src/graph.py`
Expected: PASS (1 test), no lint errors.

- [ ] **Step 5: Commit**

```bash
git add src/graph.py tests/test_graph_wiring.py
git commit -m "feat(graph): wire real router + analyst nodes (guarded for partial checkout)"
```

---

## Dependencies

- **Must be merged first:** the **Foundation plan** (`2026-05-29-foundation-and-state-contract.md`). WP-B imports `get_settings`, `get_llm`, `CostTracker`, `AnalystReport`, `FinalDecision`, `AgentState`, and the stub `src/graph.py`. None of these may be redefined here.
- **WP-C (memory)** — optional, soft dependency. The router's cache short-circuit imports `from src.memory.cache import get_cached_verdict` inside `_get_cached_verdict`, guarded by `try/except ImportError`. If WP-C is not merged, the router runs with no cache (returns `None`). No code change needed when WP-C lands.
- **WP-D (debate + `build_graph`)** — coordination dependency for **Task 13 only**. `build_graph` is WP-D-owned; Task 13 changes only the four WP-B node registrations and is written to compose whether WP-D merges before or after (the `_REAL_NODES` guard keeps the graph importable in a partial checkout). Tasks 1–12 are fully independent and can be developed/tested in parallel with all other WPs.
- **Develop-in-parallel strategy:** All tool wrappers and nodes are unit-tested with mocked SDKs and a mocked `get_llm`, so WP-B needs no other WP merged to reach green on Tasks 1–12. Only Task 13 touches a shared file; do it last and rebase onto WP-D if WP-D landed first.

## Definition of Done

- [ ] `pyproject.toml` pins `firecrawl-py==4.28.2` (`web`), `yfinance==0.2.66` + `tradingview-ta==3.3.0` (`data`); `pip install -e ".[web,data,dev]"` resolves; `from firecrawl import Firecrawl` imports.
- [ ] `src/tools/{__init__,firecrawl,yfinance,tradingview}.py` exist; `search_news`/`scrape_article`, `fetch_fundamentals`, `fetch_technicals` return typed dataclasses and raise `ToolError` (never a silent `except`) on failure; tradingview keeps an exchange-fallback retry with exponential backoff.
- [ ] `src/agents/router.py` defines `TickerResolution` locally and an async `router` node that resolves ticker/screener/exchange via `get_llm("quick").with_structured_output(TickerResolution, method=STRUCT_METHOD)`, emits a `model_plan`, and short-circuits on a guarded cached verdict.
- [ ] `src/agents/analysts/{news,fundamentals,technicals}.py` each provide an async node that calls its tool via `await asyncio.to_thread(...)`, summarizes into an `AnalystReport` via the quick tier, writes `{"analyst_reports": {"<name>": report.model_dump()}, "run_metrics": tracker.totals()["per_node"]}`, and degrades to a `confidence=0.0` report on `ToolError`/empty data without calling the LLM.
- [ ] Every node creates exactly one `CostTracker(node_name)` and returns `run_metrics`.
- [ ] `python -m pytest tests/tools tests/agents -m "not live"` is green; no unit test touches the network.
- [ ] Each external has exactly one `@pytest.mark.live` test, skipped unless `RUN_LIVE=1`; the `live` marker is registered in `pyproject.toml`.
- [ ] Task 11 live probe was run once: `STRUCT_METHOD` is locked to `function_calling` (or recorded as `json_schema` here if the quick model lacked tool calling). **Decision recorded:** `function_calling` (update if the probe failed).
- [ ] `build_graph()` registers the four real WP-B nodes (guarded for partial checkout); `tests/test_graph_wiring.py` confirms they are present; `ruff check src/tools src/agents src/graph.py` is clean.
