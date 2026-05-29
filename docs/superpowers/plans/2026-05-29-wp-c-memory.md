# WP-C: Memory (embedded Chroma + local fastembed + deterministic verdict cache) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the memory layer — a thin embedded-Chroma wrapper, a local `fastembed` embedder, and a **deterministic** cross-run verdict cache — exposing exactly the `src/memory/{store,embeddings,cache}.py` interface frozen in COORDINATION §4. Research payloads do NOT flow through this layer; the vector store is a cross-run verdict cache + future reflection log only.

**Architecture:** `embeddings.py` wraps `fastembed.TextEmbedding` (BGE-small, CPU, no API key) behind a tiny `Embedder` protocol so the backend is swappable later (e.g. Ollama Cloud `/v1/embeddings`). `store.py` wraps `chromadb.PersistentClient` (persisted at `settings.chroma_dir`) and exposes get-or-create-collection + add (with precomputed embeddings and `ts` metadata) + a **metadata `where` query** (no similarity). `cache.py` builds `store_verdict`/`get_cached_verdict` on top: freshness is computed deterministically from the stored `ts` field against an injectable clock — fixing the old code's defect of using semantic similarity for recency. A clearly-marked STRETCH `reflection.py` reuses the same store to log realized forward returns.

**Tech Stack:** Python 3.13, `chromadb==1.5.9`, `fastembed==0.8.0`, `pydantic==2.12.5` (from Foundation — `FinalDecision`), `pytest==8.4.2`, `pytest-asyncio` (dev, from Foundation).

---

## Context for the implementer

This WP codes against the **frozen contract** from `2026-05-29-foundation-and-state-contract.md`. Do NOT redefine any frozen symbol — import it:

- `from src.config.settings import get_settings` — provides `settings.chroma_dir` and `settings.embedding_model` (default `"BAAI/bge-small-en-v1.5"`).
- `from src.llm.schemas import FinalDecision` — `FinalDecision(action: Literal["BUY","SELL","HOLD"], conviction: float[0..1], score: int[0..100], rationale: str)`. `.model_dump()` serializes it; `FinalDecision(**d)` rehydrates it.

Do NOT import from the legacy `src/memory.py` (it is being replaced and will be deleted by WP-I). Your new package `src/memory/` supersedes it.

**Critical design rules (from spec §5.2 + COORDINATION §4/§6):**
1. The vector store is a **cross-run verdict cache + reflection log ONLY**. Analyst/research payloads now live in typed state — never store them here.
2. Cache freshness is a **deterministic metadata query**: `collection.get(where={"ticker": ticker})`, then pick the newest row by its stored integer `ts` (epoch seconds) and compare age to `max_age_min`. **NOT** `query(query_texts=...)` similarity. This is the explicit fix for a flagged defect in the old code.
3. Embeddings default to **local `fastembed`** (BGE-small, CPU, key-free) for reproducibility, behind a swap seam.
4. **No network in unit tests.** Tests run fastembed locally (it downloads the model to a cache on first use — see Task 3 note) and Chroma against a `tmp_path` `PersistentClient`. Tests must NOT use real wall-clock for freshness assertions; inject a `now` epoch into the cache functions.

### Verified library facts (via Context7, 2026-05-29)

**chromadb 1.5.9** (latest; `pip index versions chromadb` → 1.5.9):
- `client = chromadb.PersistentClient(path="./chroma")` — on-disk persistence.
- `collection = client.get_or_create_collection(name)` — idempotent get-or-create.
- `collection.add(ids=[...], documents=[...], metadatas=[...], embeddings=[...])` — **precomputed embeddings are accepted directly via the `embeddings=` kwarg; no `embedding_function` is required when you supply vectors yourself** (confirmed by the cookbook batching example that passes `embeddings=list(...)` with no EF). We therefore create collections WITHOUT an embedding function and always pass our own fastembed vectors. `ids` must be unique strings; re-adding an existing id errors, so we mint a fresh UUID id per verdict.
- `collection.get(where={...}, include=["metadatas","documents"])` — **deterministic metadata filter** (MongoDB-style operators: `$eq`, `$gt`, etc.). Returns a dict `{"ids":[...], "metadatas":[...], "documents":[...], ...}`. We use this for freshness, NOT `.query()`.
- Metadata values must be scalars (str/int/float/bool) — store `ts` as `int` epoch seconds and the verdict as a JSON string in `documents`.

**fastembed 0.8.0** (latest; `pip index versions fastembed` → 0.8.0):
- `from fastembed import TextEmbedding`
- `model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")`
- `model.embed(documents: list[str])` returns a **generator** of `numpy.float32` arrays. Materialize with `list(model.embed([...]))`.
- **BGE-small-en-v1.5 output dimension = 384** (confirmed in Getting-Started: `len(embeddings_list[0]) # Vector of 384 dimensions`).
- Embeddings are deterministic for the same input + model (CPU ONNX, no sampling) — relied on by the embeddings test.
- Chroma wants a `list[float]`; convert each numpy array with `.tolist()`.

**Decision recorded:** precomputed-embeddings path (we own the embedder) — NOT a Chroma `embedding_function`. This keeps the embedding backend swappable in one place (`embeddings.py`) and keeps Chroma a dumb store.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Add pinned `chromadb`/`fastembed` to the `memory` optional-deps group (edit only) |
| `src/memory/__init__.py` | Package marker |
| `src/memory/embeddings.py` | `Embedder` protocol + `FastEmbedEmbedder` (BGE-small) + `get_embedder()` swap seam |
| `src/memory/store.py` | `VectorStore`: thin `PersistentClient` wrapper (get-or-create, add w/ `ts`, metadata `where` query) |
| `src/memory/cache.py` | `get_cached_verdict` / `store_verdict` — deterministic recency from `ts` |
| `src/memory/reflection.py` | **STRETCH (optional):** log past verdict + realized forward return; read prior outcomes |
| `tests/test_embeddings.py` | Fixed-dim (384) + determinism + swap-seam |
| `tests/test_store.py` | tmp-dir PersistentClient: add + `where` query + `ts` round-trip |
| `tests/test_cache.py` | fresh hit / stale miss / empty miss with injected `now`; metadata-query-not-similarity assertion |
| `tests/test_reflection.py` | **STRETCH:** outcome round-trip |

---

### Task 1: Add pinned memory dependencies

**Files:**
- Edit: `pyproject.toml`

The Foundation `pyproject.toml` left a commented placeholder under `[project.optional-dependencies]`:
```toml
# memory  = ["chromadb>=0.5", "fastembed>=0.4"]
```
Replace it with a real, pinned group. Versions verified via Context7 + `pip index versions` on 2026-05-29 (latest: `chromadb 1.5.9`, `fastembed 0.8.0`).

- [ ] **Step 1: Edit `pyproject.toml`** — under `[project.optional-dependencies]`, remove the `# memory  = ...` comment line and add (place it just above the `dev = [` block):

```toml
memory = [
    "chromadb==1.5.9",
    "fastembed==0.8.0",
]
```

- [ ] **Step 2: Install the group**

Run: `pip install -e ".[memory]"`
Expected: resolves and installs `chromadb==1.5.9`, `fastembed==0.8.0` (plus their transitive deps: `onnxruntime`, `tokenizers`, `numpy`, etc.). No errors.

- [ ] **Step 3: Verify imports resolve**

Run: `python -c "import chromadb, fastembed; print(chromadb.__version__, fastembed.__version__)"`
Expected: prints `1.5.9 0.8.0`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(memory): add pinned chromadb + fastembed optional-deps group"
```

---

### Task 2: Package marker

**Files:**
- Create: `src/memory/__init__.py`

> NOTE: the legacy file is `src/memory.py` (a module). Creating the package `src/memory/` shadows it. Python prefers the package over the module when both exist on the path; the legacy module becomes unreachable, which is intended (WP-I deletes it). Do not edit the legacy module.

- [ ] **Step 1: Create `src/memory/__init__.py`** (empty package marker)

```python
```

- [ ] **Step 2: Confirm the package shadows the legacy module**

Run: `python -c "import src.memory, inspect, os; print(os.path.basename(os.path.dirname(src.memory.__file__)))"`
Expected: prints `memory` (i.e. resolved to the package dir, not `memory.py`).

- [ ] **Step 3: Commit**

```bash
git add src/memory/__init__.py
git commit -m "feat(memory): add memory package marker (shadows legacy module)"
```

---

### Task 3: Local fastembed embedder + swap seam

**Files:**
- Create: `src/memory/embeddings.py`
- Test: `tests/test_embeddings.py`

> **First-run note:** `TextEmbedding(...)` downloads the BGE-small ONNX model (~67 MB) to fastembed's cache on first construction; subsequent runs are offline. CI must allow this one-time download (or pre-warm the cache). This is NOT a per-request network call — it is a model fetch, consistent with "local, key-free."

- [ ] **Step 1: Write the failing test**

```python
# tests/test_embeddings.py
import pytest
from src.memory.embeddings import (
    Embedder,
    FastEmbedEmbedder,
    get_embedder,
    BGE_SMALL_DIM,
)


def test_bge_small_dim_constant_is_384():
    assert BGE_SMALL_DIM == 384


def test_embed_returns_fixed_dim_vectors():
    emb = FastEmbedEmbedder()
    vectors = emb.embed(["hello world", "second document"])
    assert isinstance(vectors, list)
    assert len(vectors) == 2
    assert all(len(v) == BGE_SMALL_DIM for v in vectors)
    assert all(isinstance(x, float) for x in vectors[0])  # plain python floats, not numpy


def test_embed_is_deterministic_for_same_input():
    emb = FastEmbedEmbedder()
    a = emb.embed(["deterministic text"])[0]
    b = emb.embed(["deterministic text"])[0]
    assert a == b


def test_embed_one_is_single_vector():
    emb = FastEmbedEmbedder()
    v = emb.embed_one("just one")
    assert len(v) == BGE_SMALL_DIM


def test_get_embedder_returns_embedder_protocol_impl():
    emb = get_embedder()
    assert isinstance(emb, Embedder)  # runtime-checkable protocol


def test_get_embedder_is_cached_singleton():
    assert get_embedder() is get_embedder()


def test_swap_seam_accepts_injected_backend():
    class FakeEmbedder:
        def embed(self, texts):
            return [[0.0, 1.0, 2.0] for _ in texts]

        def embed_one(self, text):
            return [0.0, 1.0, 2.0]

    fake = FakeEmbedder()
    assert isinstance(fake, Embedder)  # structural match satisfies the protocol
    assert fake.embed(["a", "b"]) == [[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.memory.embeddings'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/memory/embeddings.py
"""Local, key-free text embeddings (fastembed / BGE-small) behind a swap seam.

The vector backend is isolated here so it can be swapped later (e.g. an
Ollama Cloud /v1/embeddings client) without touching store.py or cache.py.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol, runtime_checkable

from fastembed import TextEmbedding

from src.config.settings import get_settings

# BAAI/bge-small-en-v1.5 produces 384-dimensional vectors (verified via Context7).
BGE_SMALL_DIM = 384


@runtime_checkable
class Embedder(Protocol):
    """Swap seam: any backend providing these two methods is a valid embedder."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Default embedder: local fastembed TextEmbedding (CPU, no API key)."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or get_settings().embedding_model
        # Constructing TextEmbedding downloads the ONNX model on first use,
        # then runs fully offline. Deterministic for a given input + model.
        self._model = TextEmbedding(model_name=self.model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # .embed() returns a generator of numpy float32 arrays; convert to
        # plain python float lists for Chroma compatibility + JSON safety.
        return [vec.tolist() for vec in self._model.embed(texts)]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Cached default embedder. Swap seam: change this to return a different
    Embedder implementation (e.g. an Ollama Cloud embeddings client) to switch
    backends; callers depend only on the Embedder protocol."""
    return FastEmbedEmbedder()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_embeddings.py -v`
Expected: PASS (7 tests). First run may pause ~10-30s downloading the model.

- [ ] **Step 5: Commit**

```bash
git add src/memory/embeddings.py tests/test_embeddings.py
git commit -m "feat(memory): add local fastembed embedder with swap seam"
```

---

### Task 4: Thin Chroma store wrapper

**Files:**
- Create: `src/memory/store.py`
- Test: `tests/test_store.py`

The store is deliberately dumb: it owns the `PersistentClient`, get-or-create-collection, an `add` that stamps an integer `ts`, and a `query_by` that uses Chroma's metadata `where` filter. It computes embeddings via the injected `Embedder` (defaults to `get_embedder()`). Collections are created WITHOUT an embedding function — we always supply precomputed vectors.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
from src.memory.store import VectorStore


class FakeEmbedder:
    """Deterministic stub embedder — avoids the fastembed model download in unit tests."""

    def embed(self, texts):
        return [[float(len(t)), 1.0, 2.0] for t in texts]

    def embed_one(self, text):
        return [float(len(text)), 1.0, 2.0]


def _store(tmp_path):
    return VectorStore(persist_dir=str(tmp_path), collection="verdicts", embedder=FakeEmbedder())


def test_add_then_query_by_metadata(tmp_path):
    s = _store(tmp_path)
    s.add(doc="hello", metadata={"ticker": "AAPL", "ts": 100})
    rows = s.query_by({"ticker": "AAPL"})
    assert len(rows) == 1
    assert rows[0]["document"] == "hello"
    assert rows[0]["metadata"]["ticker"] == "AAPL"
    assert rows[0]["metadata"]["ts"] == 100


def test_query_by_filters_out_other_tickers(tmp_path):
    s = _store(tmp_path)
    s.add(doc="a", metadata={"ticker": "AAPL", "ts": 1})
    s.add(doc="t", metadata={"ticker": "TSLA", "ts": 2})
    rows = s.query_by({"ticker": "TSLA"})
    assert len(rows) == 1
    assert rows[0]["document"] == "t"


def test_query_by_empty_when_no_match(tmp_path):
    s = _store(tmp_path)
    s.add(doc="a", metadata={"ticker": "AAPL", "ts": 1})
    assert s.query_by({"ticker": "NVDA"}) == []


def test_add_generates_unique_ids(tmp_path):
    s = _store(tmp_path)
    s.add(doc="a", metadata={"ticker": "AAPL", "ts": 1})
    s.add(doc="b", metadata={"ticker": "AAPL", "ts": 2})  # must NOT collide / overwrite
    rows = s.query_by({"ticker": "AAPL"})
    assert len(rows) == 2


def test_persistence_across_instances(tmp_path):
    s1 = _store(tmp_path)
    s1.add(doc="persisted", metadata={"ticker": "AAPL", "ts": 5})
    s2 = _store(tmp_path)  # new client, same dir + collection
    rows = s2.query_by({"ticker": "AAPL"})
    assert len(rows) == 1
    assert rows[0]["document"] == "persisted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.memory.store'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/memory/store.py
"""Thin embedded-Chroma wrapper used by the verdict cache and (stretch) reflection.

Design rules:
- The store holds a cross-run verdict cache + future reflection log ONLY.
  Research/analyst payloads live in typed state, never here.
- We supply our OWN precomputed embeddings (from an Embedder), so collections
  are created without a Chroma embedding_function.
- Recency/filtering is done via Chroma's metadata `where` filter (deterministic),
  never via similarity search.
"""
from __future__ import annotations

import uuid
from typing import Any

import chromadb

from src.config.settings import get_settings
from src.memory.embeddings import Embedder, get_embedder


class VectorStore:
    def __init__(
        self,
        persist_dir: str | None = None,
        collection: str = "verdicts",
        embedder: Embedder | None = None,
    ) -> None:
        self._dir = persist_dir or get_settings().chroma_dir
        self._embedder = embedder or get_embedder()
        self._client = chromadb.PersistentClient(path=self._dir)
        # No embedding_function: we always pass precomputed embeddings.
        self._collection = self._client.get_or_create_collection(collection)

    def add(self, doc: str, metadata: dict[str, Any]) -> str:
        """Add one document with precomputed embedding + scalar metadata.

        `metadata` values must be scalars (str/int/float/bool). Returns the id.
        """
        doc_id = uuid.uuid4().hex
        embedding = self._embedder.embed_one(doc)
        self._collection.add(
            ids=[doc_id],
            documents=[doc],
            metadatas=[metadata],
            embeddings=[embedding],
        )
        return doc_id

    def query_by(self, where: dict[str, Any]) -> list[dict[str, Any]]:
        """Deterministic metadata query (NOT similarity). Returns a list of
        {"id", "document", "metadata"} dicts (possibly empty)."""
        res = self._collection.get(where=where, include=["documents", "metadatas"])
        ids = res.get("ids") or []
        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        out: list[dict[str, Any]] = []
        for i in range(len(ids)):
            out.append(
                {
                    "id": ids[i],
                    "document": docs[i] if i < len(docs) else None,
                    "metadata": metas[i] if i < len(metas) else {},
                }
            )
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_store.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/memory/store.py tests/test_store.py
git commit -m "feat(memory): add thin Chroma store wrapper (metadata-query, precomputed embeddings)"
```

---

### Task 5: Deterministic verdict cache

**Files:**
- Create: `src/memory/cache.py`
- Test: `tests/test_cache.py`

This is the frozen COORDINATION §4 interface. `store_verdict` writes a `FinalDecision` as a JSON document with `{"ticker","ts"}` metadata. `get_cached_verdict` pulls all rows for the ticker via the **metadata `where` filter**, picks the newest by `ts`, and returns the `FinalDecision` only if `(now - ts) <= max_age_min*60`. Time is injectable (`now` epoch + `clock` callable) so tests never touch the wall clock.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache.py
import json

from src.llm.schemas import FinalDecision
from src.memory import cache as cache_mod
from src.memory.cache import get_cached_verdict, store_verdict


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 2.0, 3.0] for _ in texts]

    def embed_one(self, text):
        return [1.0, 2.0, 3.0]


class FakeStore:
    """In-memory stand-in for VectorStore that records calls.

    `query_by` ONLY honors a metadata `where` filter — it has no similarity
    path at all, which is what we assert the cache relies on.
    """

    def __init__(self):
        self.rows = []
        self.query_calls = []
        self.add_calls = []

    def add(self, doc, metadata):
        self.add_calls.append((doc, metadata))
        self.rows.append({"id": str(len(self.rows)), "document": doc, "metadata": metadata})
        return self.rows[-1]["id"]

    def query_by(self, where):
        self.query_calls.append(where)
        return [r for r in self.rows if all(r["metadata"].get(k) == v for k, v in where.items())]


def _decision(action="BUY", score=70):
    return FinalDecision(action=action, conviction=0.8, score=score, rationale="r")


def test_store_then_fresh_hit():
    store = FakeStore()
    store_verdict("AAPL", _decision(), store=store, now=1000)
    got = get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000 + 30 * 60)  # 30 min old
    assert got is not None
    assert isinstance(got, FinalDecision)
    assert got.action == "BUY"
    assert got.score == 70


def test_stale_miss():
    store = FakeStore()
    store_verdict("AAPL", _decision(), store=store, now=1000)
    got = get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000 + 61 * 60)  # 61 min old
    assert got is None


def test_empty_miss():
    store = FakeStore()
    assert get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000) is None


def test_picks_newest_by_ts():
    store = FakeStore()
    store_verdict("AAPL", _decision(action="SELL", score=10), store=store, now=1000)
    store_verdict("AAPL", _decision(action="BUY", score=90), store=store, now=2000)  # newer
    got = get_cached_verdict("AAPL", max_age_min=1000, store=store, now=2000)
    assert got.action == "BUY"
    assert got.score == 90


def test_store_writes_ticker_and_ts_metadata():
    store = FakeStore()
    store_verdict("TSLA", _decision(), store=store, now=4242)
    doc, meta = store.add_calls[0]
    assert meta["ticker"] == "TSLA"
    assert meta["ts"] == 4242
    assert json.loads(doc)["action"] == "BUY"  # verdict serialized as JSON document


def test_freshness_uses_metadata_where_not_similarity():
    """Regression guard for the old defect: recency must be a metadata `where`
    query keyed by ticker, NOT a semantic similarity search."""
    store = FakeStore()
    store_verdict("AAPL", _decision(), store=store, now=1000)
    get_cached_verdict("AAPL", max_age_min=60, store=store, now=1000)
    assert store.query_calls == [{"ticker": "AAPL"}]
    # FakeStore has no query_texts/similarity method — the cache cannot have used one.
    assert not hasattr(store, "query")


def test_default_store_is_constructed_lazily(monkeypatch):
    """When no store is injected, the cache builds a VectorStore on demand."""
    built = {}

    class SpyStore(FakeStore):
        def __init__(self):
            super().__init__()
            built["yes"] = True

    monkeypatch.setattr(cache_mod, "VectorStore", SpyStore)
    store_verdict("NVDA", _decision(), now=7)  # no store= kwarg
    assert built.get("yes") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.memory.cache'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/memory/cache.py
"""Deterministic cross-run verdict cache.

Freshness is computed from a stored integer `ts` (epoch seconds) via a metadata
`where` query keyed by ticker — NOT semantic similarity. This is the explicit
fix for the old code's defect of using similarity search for recency.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from src.llm.schemas import FinalDecision
from src.memory.store import VectorStore

_COLLECTION = "verdicts"


def _get_store(store: Any | None) -> Any:
    return store if store is not None else VectorStore(collection=_COLLECTION)


def store_verdict(
    ticker: str,
    decision: FinalDecision,
    *,
    store: Any | None = None,
    now: int | None = None,
    clock: Callable[[], float] = time.time,
) -> None:
    """Persist a FinalDecision for `ticker`, stamped with epoch `ts`."""
    store = _get_store(store)
    ts = int(now if now is not None else clock())
    doc = json.dumps(decision.model_dump())
    store.add(doc=doc, metadata={"ticker": ticker, "ts": ts})


def get_cached_verdict(
    ticker: str,
    max_age_min: int,
    *,
    store: Any | None = None,
    now: int | None = None,
    clock: Callable[[], float] = time.time,
) -> FinalDecision | None:
    """Return the newest cached FinalDecision for `ticker` if it is younger than
    `max_age_min`; otherwise None. Uses a deterministic metadata `where` query."""
    store = _get_store(store)
    rows = store.query_by({"ticker": ticker})  # metadata filter, NOT similarity
    if not rows:
        return None
    newest = max(rows, key=lambda r: r["metadata"].get("ts", 0))
    ts = int(newest["metadata"].get("ts", 0))
    current = int(now if now is not None else clock())
    if current - ts > max_age_min * 60:
        return None
    return FinalDecision(**json.loads(newest["document"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cache.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/memory/cache.py tests/test_cache.py
git commit -m "feat(memory): add deterministic verdict cache (metadata-query recency)"
```

---

### Task 6: Cache integration test against real Chroma (tmp dir)

**Files:**
- Edit: `tests/test_cache.py` (append one integration test)

The unit tests above use a FakeStore. Add ONE test that exercises the full path through a real `VectorStore` + Chroma `PersistentClient` in a `tmp_path`, still with a fake embedder (so no model download) and an injected `now`.

- [ ] **Step 1: Append the integration test to `tests/test_cache.py`**

```python
def test_cache_end_to_end_against_real_chroma(tmp_path):
    from src.memory.store import VectorStore

    store = VectorStore(persist_dir=str(tmp_path), collection="verdicts", embedder=FakeEmbedder())
    store_verdict("AAPL", _decision(action="HOLD", score=55), store=store, now=10_000)

    fresh = get_cached_verdict("AAPL", max_age_min=60, store=store, now=10_000 + 10 * 60)
    assert fresh is not None and fresh.action == "HOLD" and fresh.score == 55

    stale = get_cached_verdict("AAPL", max_age_min=5, store=store, now=10_000 + 10 * 60)
    assert stale is None

    missing = get_cached_verdict("ZZZZ", max_age_min=60, store=store, now=10_000)
    assert missing is None
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python -m pytest tests/test_cache.py -v`
Expected: PASS (8 tests total now).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cache.py
git commit -m "test(memory): add end-to-end verdict cache test against real Chroma"
```

---

### Task 7: Full-suite regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the whole memory test set**

Run: `python -m pytest tests/test_embeddings.py tests/test_store.py tests/test_cache.py -v`
Expected: all PASS (7 + 5 + 8 = 20 tests).

- [ ] **Step 2: Run the entire suite to confirm no Foundation regressions**

Run: `python -m pytest -q`
Expected: all PASS (Foundation modules + the three new memory modules). The memory package shadowing the legacy `src/memory.py` must not break Foundation tests (Foundation does not import memory).

- [ ] **Step 3: Confirm no `.chroma` litter from tests**

Run: `git status --porcelain`
Expected: only the intended new/edited files appear — NO `.chroma/` directory (tests use `tmp_path`; the default-dir path is only constructed in `test_default_store_is_constructed_lazily`, which uses a SpyStore and never touches disk). If a stray store dir appears, ensure no test omitted the `store=`/`persist_dir=` injection.

---

### Task 8 (STRETCH — OPTIONAL): Reflection log

> **This task is explicitly optional.** Implement only if WP-C has slack after the cache lands. It is additive, behind the same `VectorStore`, and changes none of the frozen interface. Skip cleanly if out of scope — nothing downstream depends on it yet.

**Files:**
- Create: `src/memory/reflection.py`
- Test: `tests/test_reflection.py`

Minimal scope: store a past verdict together with a realized forward return for a ticker, and retrieve prior outcomes for that ticker (newest first). Reuses the store's metadata `where` query; no similarity.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reflection.py
from src.llm.schemas import FinalDecision
from src.memory.reflection import log_outcome, get_prior_outcomes


class FakeStore:
    def __init__(self):
        self.rows = []

    def add(self, doc, metadata):
        self.rows.append({"id": str(len(self.rows)), "document": doc, "metadata": metadata})
        return self.rows[-1]["id"]

    def query_by(self, where):
        return [r for r in self.rows if all(r["metadata"].get(k) == v for k, v in where.items())]


def _decision():
    return FinalDecision(action="BUY", conviction=0.7, score=65, rationale="r")


def test_log_and_retrieve_outcome():
    store = FakeStore()
    log_outcome("AAPL", _decision(), forward_return=0.05, store=store, now=100)
    outcomes = get_prior_outcomes("AAPL", store=store)
    assert len(outcomes) == 1
    assert outcomes[0]["forward_return"] == 0.05
    assert outcomes[0]["decision"].action == "BUY"
    assert outcomes[0]["ts"] == 100


def test_outcomes_sorted_newest_first():
    store = FakeStore()
    log_outcome("AAPL", _decision(), forward_return=0.01, store=store, now=100)
    log_outcome("AAPL", _decision(), forward_return=0.09, store=store, now=300)
    outcomes = get_prior_outcomes("AAPL", store=store)
    assert [o["ts"] for o in outcomes] == [300, 100]


def test_outcomes_filtered_by_ticker():
    store = FakeStore()
    log_outcome("AAPL", _decision(), forward_return=0.01, store=store, now=100)
    log_outcome("TSLA", _decision(), forward_return=0.02, store=store, now=200)
    assert len(get_prior_outcomes("TSLA", store=store)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reflection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.memory.reflection'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/memory/reflection.py
"""STRETCH: reflection log — store a past verdict + realized forward return,
retrieve prior outcomes for a ticker. Reuses VectorStore + metadata `where`
query (no similarity). Behind the same store; additive to the frozen contract.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

from src.llm.schemas import FinalDecision
from src.memory.store import VectorStore

_COLLECTION = "reflections"


def _get_store(store: Any | None) -> Any:
    return store if store is not None else VectorStore(collection=_COLLECTION)


def log_outcome(
    ticker: str,
    decision: FinalDecision,
    forward_return: float,
    *,
    store: Any | None = None,
    now: int | None = None,
    clock: Callable[[], float] = time.time,
) -> None:
    """Persist {decision, realized forward_return} for later reflection."""
    store = _get_store(store)
    ts = int(now if now is not None else clock())
    doc = json.dumps(decision.model_dump())
    store.add(
        doc=doc,
        metadata={"ticker": ticker, "ts": ts, "forward_return": float(forward_return)},
    )


def get_prior_outcomes(ticker: str, *, store: Any | None = None) -> list[dict[str, Any]]:
    """Return prior outcomes for `ticker`, newest first, via metadata query.

    Each item: {"decision": FinalDecision, "forward_return": float, "ts": int}.
    """
    store = _get_store(store)
    rows = store.query_by({"ticker": ticker})
    out: list[dict[str, Any]] = []
    for r in rows:
        meta = r["metadata"]
        out.append(
            {
                "decision": FinalDecision(**json.loads(r["document"])),
                "forward_return": float(meta.get("forward_return", 0.0)),
                "ts": int(meta.get("ts", 0)),
            }
        )
    out.sort(key=lambda o: o["ts"], reverse=True)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reflection.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/memory/reflection.py tests/test_reflection.py
git commit -m "feat(memory): add stretch reflection log (verdict + forward return)"
```

---

## Dependencies

- **Depends on Foundation only** (`2026-05-29-foundation-and-state-contract.md` must be merged first):
  - `src.config.settings.get_settings` → `chroma_dir`, `embedding_model`.
  - `src.llm.schemas.FinalDecision` → the cached verdict shape (frozen).
- **No dependency on any sibling WP.** WP-C is a leaf used by others.
- **Consumers** (WP-B router, WP-E risk_arbiter) treat memory as an injected dependency and mock it; per COORDINATION §4 their calls are guarded (`try/except ImportError` or feature flag) so the graph runs if WP-C is not yet merged. Nothing here imports those WPs.
- **Parallel development:** if Foundation's `FinalDecision`/`get_settings` are not yet merged, stub them locally behind the identical signatures (`FinalDecision` Pydantic model with `action/conviction/score/rationale`; a `get_settings()` returning an object with `.chroma_dir` and `.embedding_model`) and delete the stub once Foundation lands. The public interface this WP exposes (`get_cached_verdict`, `store_verdict`, `VectorStore`, `get_embedder`) must not change.

## Definition of Done

- [ ] `pyproject.toml` `[project.optional-dependencies].memory` pins `chromadb==1.5.9` and `fastembed==0.8.0`; `pip install -e ".[memory]"` succeeds.
- [ ] `src/memory/{__init__,embeddings,store,cache}.py` exist; `cache.py` exposes EXACTLY the COORDINATION §4 interface: `get_cached_verdict(ticker, max_age_min) -> FinalDecision | None` and `store_verdict(ticker, decision: FinalDecision) -> None`.
- [ ] Embeddings are local fastembed (BGE-small, 384-dim), deterministic, and behind a `get_embedder()` swap seam returning an `Embedder` protocol impl.
- [ ] `store.py` wraps `chromadb.PersistentClient` at `settings.chroma_dir`, get-or-creates a collection, adds with precomputed embeddings + scalar `ts` metadata, and queries via a metadata `where` filter.
- [ ] Cache freshness is a **deterministic metadata query** keyed by ticker + newest `ts` vs `max_age_min` — proven by `test_freshness_uses_metadata_where_not_similarity` (asserts `query_calls == [{"ticker": ...}]` on a fake store with no similarity method).
- [ ] Cache tests cover fresh hit, stale miss, empty miss, newest-by-`ts`, and metadata round-trip — all with an injected `now` (no wall-clock in assertions). One end-to-end test runs against a real Chroma `PersistentClient` in `tmp_path`.
- [ ] `python -m pytest -q` is green; no stray `.chroma/` directory in `git status`.
- [ ] (STRETCH, optional) `reflection.py` logs verdict + forward return and retrieves prior outcomes newest-first, reusing the same store and metadata query.
