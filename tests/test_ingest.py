# tests/test_ingest.py
"""High-level write-through ingest API (WP-3): disabled no-ops, idempotent
instrument upserts, fundamentals/news mapping, incremental price refresh,
timestamp normalization, and degrade-on-error (the ingest layer never raises)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.warehouse.db import session_scope
from src.warehouse.ingest import (
    _run_summary_text,
    ensure_instrument,
    fundamentals_stale,
    prices_stale,
    record_fundamentals,
    record_news,
    record_run_finish,
    record_run_start,
    refresh_prices,
)
from src.warehouse.models import FundamentalsSnapshot, Instrument, NewsItem, PriceBar, Run

NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


async def _count(model) -> int:
    async with session_scope() as session:
        return (
            await session.execute(select(func.count()).select_from(model))
        ).scalar_one()


def _bars(n: int, start: datetime, *, naive: bool = False) -> list[dict]:
    rows = []
    for i in range(n):
        ts = start + timedelta(days=i)
        if naive:
            ts = ts.replace(tzinfo=None)
        rows.append(
            {"ts": ts, "open": 1.0 + i, "high": 2.0 + i, "low": 0.5 + i,
             "close": 1.5 + i, "volume": 100 + i}
        )
    return rows


def _make_fetch(batches: list[list[dict]]):
    """Async fake fetch recording the ``start`` it was called with."""
    calls: list[datetime | None] = []
    queue = list(batches)

    async def _fetch(ticker: str, start: datetime | None) -> list[dict]:
        calls.append(start)
        return queue.pop(0) if queue else []

    return _fetch, calls


# ------------------------------------------------------- disabled => no-ops


async def test_disabled_warehouse_all_functions_noop():
    # env_isolation (autouse) scrubbed DATABASE_URL -> warehouse disabled.
    assert await ensure_instrument("AAPL", "NASDAQ", "america") is None
    assert await record_fundamentals("AAPL", "NASDAQ", "america", {"market_cap": 1.0}) is False
    assert await record_news("AAPL", "NASDAQ", "america", [{"title": "t", "url": "u"}]) == 0
    assert await fundamentals_stale("AAPL", "NASDAQ") is False
    assert await prices_stale("AAPL", "NASDAQ") is False

    fetch, calls = _make_fetch([_bars(3, NOW)])
    assert await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch) == 0
    assert calls == [], "disabled warehouse must never invoke the price fetcher"


# ----------------------------------------------------------- ensure_instrument


async def test_ensure_instrument_idempotent(sqlite_warehouse):
    first = await ensure_instrument("AAPL", "NASDAQ", "america", name="Apple Inc.")
    second = await ensure_instrument("AAPL", "NASDAQ", "america")
    assert first is not None
    assert second == first
    assert await _count(Instrument) == 1
    # Re-upsert without optionals must not clobber existing optional fields.
    async with session_scope() as session:
        row = (await session.execute(select(Instrument))).scalar_one()
        assert row.name == "Apple Inc."


async def test_ensure_instrument_db_error_degrades_to_none(sqlite_warehouse, monkeypatch, caplog):
    from src.warehouse import ingest as ingest_mod

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(ingest_mod, "session_scope", _boom)
    with caplog.at_level("WARNING"):
        assert await ensure_instrument("AAPL", "NASDAQ", "america") is None
    assert any("ensure_instrument" in r.message for r in caplog.records)


# --------------------------------------------------------- record_fundamentals


async def test_record_fundamentals_maps_known_keys_and_payload(sqlite_warehouse):
    snapshot = {
        "ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology",
        "trailing_pe": 28.0, "revenue_growth": 0.05, "profit_margins": 0.25,
        "market_cap": 2.7e12, "beta": 1.2,
    }
    assert await record_fundamentals("AAPL", "NASDAQ", "america", snapshot) is True
    async with session_scope() as session:
        snap = (await session.execute(select(FundamentalsSnapshot))).scalar_one()
        assert snap.market_cap == 2.7e12
        assert snap.pe_ratio == 28.0           # trailing_pe maps to pe_ratio
        assert snap.eps is None                # not in the yfinance snapshot
        assert snap.revenue_growth == 0.05
        assert snap.profit_margin == 0.25      # profit_margins maps to profit_margin
        assert snap.payload == snapshot        # full dict preserved
        assert snap.ts.tzinfo is not None
        inst = (await session.execute(select(Instrument))).scalar_one()
        assert inst.id == snap.instrument_id
        assert inst.name == "Apple Inc."
        assert inst.sector == "Technology"


async def test_record_fundamentals_db_error_degrades(sqlite_warehouse, monkeypatch, caplog):
    from src.warehouse import ingest as ingest_mod

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(ingest_mod, "session_scope", _boom)
    with caplog.at_level("WARNING"):
        assert await record_fundamentals("AAPL", "NASDAQ", "america", {}) is False


# ---------------------------------------------------------------- record_news


async def test_record_news_dedupes_by_url(sqlite_warehouse):
    items = [
        {"title": "Apple beats", "url": "https://x.com/a", "snippet": "strong q"},
        {"title": "Apple beats (syndicated)", "url": "https://x.com/a"},
        {"title": "Apple guidance", "url": "https://x.com/b", "source": "x.com"},
    ]
    assert await record_news("AAPL", "NASDAQ", "america", items) == 3  # attempted
    assert await _count(NewsItem) == 2  # deduped on url_hash

    # Re-ingesting the same items inserts nothing new.
    await record_news("AAPL", "NASDAQ", "america", items)
    assert await _count(NewsItem) == 2


async def test_record_news_uses_aware_published_ts_else_now(sqlite_warehouse):
    published = datetime(2026, 6, 1, 9, 30, tzinfo=UTC)
    items = [
        {"title": "dated", "url": "https://x.com/dated", "published": published},
        {"title": "naive-dated", "url": "https://x.com/naive",
         "published": datetime(2026, 6, 1, 9, 30)},  # naive -> ignored, now() used
        {"title": "undated", "url": "https://x.com/undated"},
    ]
    await record_news("AAPL", "NASDAQ", "america", items)
    async with session_scope() as session:
        rows = {r.title: r for r in (await session.execute(select(NewsItem))).scalars()}
    assert rows["dated"].ts == published
    for title in ("naive-dated", "undated"):
        assert rows[title].ts.tzinfo is not None
        assert rows[title].ts > published


async def test_record_news_skips_items_without_url(sqlite_warehouse):
    items = [{"title": "no url"}, {"title": "ok", "url": "https://x.com/ok"}]
    assert await record_news("AAPL", "NASDAQ", "america", items) == 1
    assert await _count(NewsItem) == 1


# ------------------------------------------------- WP-9 embedding write path


class _BoomEmbedder:
    def embed(self, texts):
        raise RuntimeError("onnx exploded")

    def embed_one(self, text):
        raise RuntimeError("onnx exploded")


async def _news_rows() -> dict[str, NewsItem]:
    async with session_scope() as session:
        return {r.title: r for r in (await session.execute(select(NewsItem))).scalars()}


async def test_record_news_stores_embeddings_when_embedder_available(
    sqlite_warehouse, warehouse_fake_embedder
):
    items = [
        {"title": "Apple beats", "url": "https://x.com/a", "snippet": "strong q"},
        {"title": "Apple guidance", "url": "https://x.com/b"},  # no snippet
    ]
    assert await record_news("AAPL", "NASDAQ", "america", items) == 2
    rows = await _news_rows()
    # Embedded text is title (+ snippet when present, joined); JSON-text roundtrip
    # on sqlite must come back as list[float] of the model dimension.
    expected_a = warehouse_fake_embedder.vector("Apple beats\nstrong q")
    expected_b = warehouse_fake_embedder.vector("Apple guidance")
    for title, expected in (("Apple beats", expected_a), ("Apple guidance", expected_b)):
        embedding = rows[title].embedding
        assert isinstance(embedding, list)
        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)
        assert embedding == expected
    # One batched embed call, outside the session (can't assert timing, but batching).
    assert warehouse_fake_embedder.calls == [["Apple beats\nstrong q", "Apple guidance"]]


async def test_record_news_without_embedder_stores_rows_with_null_embedding(
    sqlite_warehouse,
):
    # autouse no_real_embedder pins the seam to None.
    items = [{"title": "Apple beats", "url": "https://x.com/a", "snippet": "s"}]
    assert await record_news("AAPL", "NASDAQ", "america", items) == 1
    rows = await _news_rows()
    assert rows["Apple beats"].embedding is None


async def test_record_news_embedder_failure_still_stores_rows(sqlite_warehouse):
    from src.warehouse.embeddings import set_embedder_for_testing

    set_embedder_for_testing(_BoomEmbedder())
    items = [{"title": "Apple beats", "url": "https://x.com/a"}]
    assert await record_news("AAPL", "NASDAQ", "america", items) == 1
    rows = await _news_rows()
    assert rows["Apple beats"].embedding is None


async def _run_row(run_id: str) -> Run:
    async with session_scope() as session:
        return (
            await session.execute(select(Run).where(Run.run_id == run_id))
        ).scalar_one()


async def test_record_run_finish_embeds_finished_run_with_report(
    sqlite_warehouse, warehouse_fake_embedder
):
    decision = {"action": "BUY", "conviction": 0.8, "score": 78, "rationale": "upside"}
    report = "# AAPL\n" + "body " * 400  # > 1000 chars: summary truncates
    await record_run_start("run-emb-1", "AAPL", "on")
    assert await record_run_finish(
        "run-emb-1", status="finished", final_decision=decision, report=report
    ) is True
    run = await _run_row("run-emb-1")
    expected = warehouse_fake_embedder.vector(_run_summary_text(report, decision))
    assert run.embedding == expected
    assert len(run.embedding) == 384
    # The embedded summary is bounded: ~1000 report chars + decision parts.
    embedded_text = warehouse_fake_embedder.calls[-1][0]
    assert report[:1000] in embedded_text
    assert "BUY" in embedded_text and "upside" in embedded_text
    assert len(embedded_text) < 1200


@pytest.mark.parametrize(
    ("status", "report"),
    [("error", "partial report"), ("aborted", None), ("finished", None)],
)
async def test_record_run_finish_skips_embedding_unless_finished_with_report(
    sqlite_warehouse, warehouse_fake_embedder, status, report
):
    run_id = f"run-noemb-{status}-{bool(report)}"
    await record_run_start(run_id, "AAPL", "on")
    assert await record_run_finish(run_id, status=status, report=report) is True
    run = await _run_row(run_id)
    assert run.embedding is None
    assert warehouse_fake_embedder.calls == []


async def test_record_run_finish_without_embedder_still_finishes(sqlite_warehouse):
    await record_run_start("run-emb-none", "AAPL", "on")
    assert await record_run_finish(
        "run-emb-none", status="finished", report="done report"
    ) is True
    run = await _run_row("run-emb-none")
    assert run.status == "finished"
    assert run.embedding is None


async def test_record_run_finish_embedder_failure_still_finishes(sqlite_warehouse):
    from src.warehouse.embeddings import set_embedder_for_testing

    set_embedder_for_testing(_BoomEmbedder())
    await record_run_start("run-emb-boom", "AAPL", "on")
    assert await record_run_finish(
        "run-emb-boom", status="finished", report="done report"
    ) is True
    run = await _run_row("run-emb-boom")
    assert run.status == "finished"
    assert run.embedding is None


def test_run_summary_text_truncates_and_includes_decision():
    text = _run_summary_text("R" * 5000, {"action": "SELL", "rationale": "overvalued"})
    assert text.startswith("R" * 1000)
    assert "R" * 1001 not in text
    assert "SELL" in text
    assert "overvalued" in text
    # No decision -> just the truncated report.
    assert _run_summary_text("short report", None) == "short report"


# -------------------------------------------------------------- refresh_prices


async def test_refresh_prices_inserts_then_fetches_incrementally(sqlite_warehouse):
    first_batch = _bars(5, NOW - timedelta(days=10))
    second_batch = _bars(2, NOW - timedelta(days=5))
    fetch, calls = _make_fetch([first_batch, second_batch])

    inserted = await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch)
    assert inserted == 5
    assert await _count(PriceBar) == 5
    # First call: no bars yet -> backfill window start (period_days ago).
    assert calls[0] is not None

    inserted = await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch)
    assert inserted == 2
    # Second call is incremental: start AT the newest stored ts (not after it),
    # so the newest day — possibly a partial intraday bar — is re-fetched.
    newest_first = max(b["ts"] for b in first_batch)
    assert calls[1] == newest_first


async def test_refresh_prices_refetches_newest_and_corrects_partial_bar(sqlite_warehouse):
    """A partial intraday bar must not be frozen forever: the second refresh
    re-requests from the newest stored ts and the corrected OHLCV wins
    (ON CONFLICT DO UPDATE), without duplicating the row."""
    partial = _bars(3, NOW - timedelta(days=3))
    corrected = {**partial[-1], "close": 99.0, "high": 99.5, "volume": 999}
    fetch, calls = _make_fetch([partial, [corrected]])

    assert await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch) == 3
    assert await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch) == 1
    assert calls[1] == partial[-1]["ts"]  # re-fetch starts at the newest stored day

    assert await _count(PriceBar) == 3  # corrected in place, not duplicated
    async with session_scope() as session:
        rows = {bar.ts: bar for bar in (await session.execute(select(PriceBar))).scalars()}
    row = rows[partial[-1]["ts"]]
    assert row.close == 99.0  # corrected close wins
    assert row.high == 99.5
    assert row.volume == 999


async def test_refresh_prices_normalizes_naive_timestamps(sqlite_warehouse):
    fetch, _ = _make_fetch([_bars(3, NOW - timedelta(days=3), naive=True)])
    assert await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch) == 3
    async with session_scope() as session:
        for bar in (await session.execute(select(PriceBar))).scalars():
            assert bar.ts.tzinfo is not None
            assert bar.ts.utcoffset() == timedelta(0)


async def test_refresh_prices_fetch_error_degrades_to_zero(sqlite_warehouse, caplog):
    async def _boom(ticker, start):
        raise RuntimeError("yfinance down")

    with caplog.at_level("WARNING"):
        assert await refresh_prices("AAPL", "NASDAQ", "america", fetch=_boom) == 0
    assert any("refresh_prices" in r.message for r in caplog.records)
    assert await _count(PriceBar) == 0


async def test_refresh_prices_empty_fetch_returns_zero(sqlite_warehouse):
    fetch, _ = _make_fetch([[]])
    assert await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch) == 0


# ----------------------------------------------------------- freshness helpers


async def test_fundamentals_stale_lifecycle(sqlite_warehouse):
    # Unknown instrument -> stale (nothing recorded yet).
    assert await fundamentals_stale("AAPL", "NASDAQ") is True

    await record_fundamentals("AAPL", "NASDAQ", "america", {"market_cap": 1.0})
    assert await fundamentals_stale("AAPL", "NASDAQ") is False
    # A tighter window makes the same snapshot stale.
    assert await fundamentals_stale("AAPL", "NASDAQ", max_age_hours=0) is True


async def test_prices_stale_lifecycle(sqlite_warehouse):
    assert await prices_stale("AAPL", "NASDAQ") is True

    fresh = [{"ts": datetime.now(UTC), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}]
    fetch, _ = _make_fetch([fresh])
    await refresh_prices("AAPL", "NASDAQ", "america", fetch=fetch)
    assert await prices_stale("AAPL", "NASDAQ") is False
    assert await prices_stale("AAPL", "NASDAQ", max_age_hours=0) is True


async def test_prices_stale_ignores_non_daily_bars(sqlite_warehouse):
    """Staleness must agree with refresh_prices (which only stores 1d bars): a
    fresh intraday bar at another interval must not mask daily staleness."""
    from src.warehouse.repos import bulk_upsert_price_bars, upsert_instrument

    async with session_scope() as session:
        inst = await upsert_instrument(
            session, ticker="AAPL", exchange="NASDAQ", screener="america"
        )
        await bulk_upsert_price_bars(
            session,
            inst.id,
            [{"ts": datetime.now(UTC), "interval": "1h", "open": 1.0, "high": 1.0,
              "low": 1.0, "close": 1.0}],
        )
    assert await prices_stale("AAPL", "NASDAQ") is True  # no 1d bars yet


async def test_stale_helpers_db_error_degrades_to_false(sqlite_warehouse, monkeypatch, caplog):
    from src.warehouse import ingest as ingest_mod

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(ingest_mod, "session_scope", _boom)
    with caplog.at_level("WARNING"):
        # False => callers skip the redundant fetch instead of hammering a dead DB.
        assert await fundamentals_stale("AAPL", "NASDAQ") is False
        assert await prices_stale("AAPL", "NASDAQ") is False
