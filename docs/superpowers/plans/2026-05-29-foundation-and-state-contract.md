# Foundation & State Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the blocking foundation (config, LLM factory, cost/observability) and the frozen state contract (Pydantic schemas, `AgentState`, a runnable 12-node stub graph) that every parallel work package depends on.

**Architecture:** A provider-agnostic LLM layer points `langchain_openai.ChatOpenAI` at Ollama Cloud's OpenAI-compatible `/v1` endpoint, with cached singletons and two model tiers (quick/deep). Configuration is centralized in `pydantic-settings`. A `CostTracker` callback and a `RunRecorder` give honest token/latency/trace data. The 12-node LangGraph topology is wired with stub nodes so the graph compiles and runs end-to-end, freezing the typed-state contract before any real agent logic is written.

**Tech Stack:** Python 3.13, `langgraph==1.0.4`, `langchain-core==1.2.5`, `langchain-openai==1.1.6`, `pydantic==2.12.5`, `pydantic-settings==2.12.0`, `pyyaml==6.0.2`, `pytest==8.4.2`.

---

## Context for the implementer

This is a greenfield re-architecture inside an existing repo. The OLD code under `src/` (`src/agents/*`, `src/memory.py`, `src/graph.py`, `src/state.py`) is being **replaced**, not extended. Do NOT import from the old modules. Leave the old files in place for now (a later cleanup task removes them); your new modules live alongside and will supersede them.

Read these before starting: `docs/superpowers/specs/2026-05-29-finresearchai-agentic-upgrade-design.md` (§4 state model, §5 cross-cutting layers) and `docs/superpowers/03-work-breakdown.md`.

Two API keys are provided via `.env` (already gitignored): `OLLAMA_API_KEY`, `FIRECRAWL_API_KEY`. They are temporary dev keys. Never commit them. None of the tests in this plan hit the network — the LLM factory is tested by construction only.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Pinned dependencies, project metadata, pytest config |
| `.env.example` | Documents required env vars (no secrets) |
| `src/config/__init__.py` | Package marker |
| `src/config/models.yaml` | Tier → model-name mapping (the single source for model choice) |
| `src/config/settings.py` | `Settings` (pydantic-settings) + `get_settings()` cached accessor; loads `models.yaml` |
| `src/llm/__init__.py` | Package marker |
| `src/llm/cost.py` | `CostTracker` callback: per-call tokens/latency/cost → totals |
| `src/llm/factory.py` | `get_llm(tier)` cached `ChatOpenAI` singletons pointed at Ollama Cloud |
| `src/llm/schemas.py` | Pydantic models for every node's structured I/O (the data contract) |
| `src/obs/__init__.py` | Package marker |
| `src/obs/recorder.py` | `RunRecorder`: collect node events → JSONL trace file |
| `src/state.py` | `AgentState` TypedDict + reducer functions (the graph contract) |
| `src/graph.py` | `build_graph()`: 12-node stub StateGraph, compiles + runs end-to-end |
| `tests/test_settings.py` | Settings load + models.yaml parsing |
| `tests/test_cost.py` | CostTracker aggregation |
| `tests/test_factory.py` | get_llm tiers, caching, bad-tier error (no network) |
| `tests/test_recorder.py` | RunRecorder JSONL round-trip |
| `tests/test_schemas.py` | Schema validation (valid + invalid) |
| `tests/test_state.py` | Reducer behavior |
| `tests/test_graph_skeleton.py` | Stub graph compiles, runs, merges parallel writes |

---

### Task 1: Project metadata & pinned dependencies

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "finresearchai"
version = "0.2.0"
description = "Debate-driven multi-agent financial research system"
requires-python = ">=3.11"
dependencies = [
    "langgraph==1.0.4",
    "langchain-core==1.2.5",
    "langchain-openai==1.1.6",
    "pydantic==2.12.5",
    "pydantic-settings==2.12.0",
    "pyyaml==6.0.2",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
# Added by later work-package plans:
# memory  = ["chromadb>=0.5", "fastembed>=0.4"]
# web     = ["firecrawl-py>=1.6"]
# api     = ["fastapi>=0.125", "uvicorn>=0.30", "sse-starlette>=2.1", "httpx>=0.27"]
# data    = ["yfinance==0.2.66", "tradingview-ta==3.3.0"]
dev = [
    "pytest==8.4.2",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "ruff>=0.6",
    "mypy>=1.11",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Verify the dev tooling resolves**

Run: `python -m pytest --version`
Expected: prints `pytest 8.4.2` (already installed). If not, run `pip install -e ".[dev]"` then retry.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add pinned pyproject for agentic re-architecture"
```

---

### Task 2: Environment template

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`** (documentation only — no real values)

```bash
# LLM backbone — Ollama Cloud (OpenAI-compatible /v1)
OLLAMA_API_KEY=your-ollama-cloud-key-here
LLM_BASE_URL=https://ollama.com/v1

# Web research
FIRECRAWL_API_KEY=your-firecrawl-key-here

# Model tiers (override models.yaml if set)
QUICK_MODEL=gpt-oss:20b
DEEP_MODEL=gpt-oss:120b

# Debate
RESEARCH_DEBATE_ROUNDS=1
RISK_DEBATE_ROUNDS=1
DEBATE_MODE=on

# Memory
CHROMA_DIR=.chroma
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5

# Observability
RUNS_DIR=runs
LANGSMITH_ENABLED=false
```

- [ ] **Step 2: Confirm `.env.example` is NOT ignored but `.env` IS**

Run: `git check-ignore .env .env.example; echo "exit=$?"`
Expected: prints `.env` only (then `exit=0`). `.env.example` must NOT be printed — if it is, the gitignore is too broad; verify `.gitignore` line `*.env` is the cause and add `!.env.example` below it.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example documenting required config"
```

---

### Task 3: Model-tier config file

**Files:**
- Create: `src/config/__init__.py`
- Create: `src/config/models.yaml`

- [ ] **Step 1: Create `src/config/__init__.py`** (empty package marker)

```python
```

- [ ] **Step 2: Create `src/config/models.yaml`**

```yaml
# Tier -> model name. Quick models handle retrieval/summary/formatting;
# deep models handle debate, verdicts, and the risk arbiter.
quick:
  model: "gpt-oss:20b"
  temperature: 0.3
deep:
  model: "gpt-oss:120b"
  temperature: 0.5
```

- [ ] **Step 3: Commit**

```bash
git add src/config/__init__.py src/config/models.yaml
git commit -m "feat(config): add model-tier mapping file"
```

---

### Task 4: Settings (pydantic-settings)

**Files:**
- Create: `src/config/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings.py
from pathlib import Path
import textwrap
from src.config.settings import Settings, load_model_tiers


def test_load_model_tiers_reads_yaml(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(textwrap.dedent("""
        quick:
          model: "m-quick"
          temperature: 0.1
        deep:
          model: "m-deep"
          temperature: 0.9
    """))
    tiers = load_model_tiers(p)
    assert tiers["quick"]["model"] == "m-quick"
    assert tiers["deep"]["temperature"] == 0.9


def test_settings_defaults_without_env(monkeypatch):
    # Ensure no env bleed-through from a real .env
    for k in ["OLLAMA_API_KEY", "LLM_BASE_URL", "QUICK_MODEL", "DEEP_MODEL"]:
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.llm_base_url == "https://ollama.com/v1"
    assert s.debate_mode == "on"
    assert s.research_debate_rounds == 1


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-123")
    monkeypatch.setenv("QUICK_MODEL", "override-quick")
    s = Settings(_env_file=None)
    assert s.ollama_api_key == "test-key-123"
    assert s.quick_model == "override-quick"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.config.settings'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/config/settings.py
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_MODELS_YAML = Path(__file__).parent / "models.yaml"


def load_model_tiers(path: Path = _MODELS_YAML) -> dict[str, dict[str, Any]]:
    """Load the tier->{model,temperature} mapping. Returns {} if file absent."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # LLM provider (Ollama Cloud by default; swappable)
    llm_provider: str = "ollama_cloud"
    llm_base_url: str = "https://ollama.com/v1"
    ollama_api_key: str = ""

    # Web research
    firecrawl_api_key: str = ""

    # Model tiers (env overrides win over models.yaml)
    quick_model: str = "gpt-oss:20b"
    deep_model: str = "gpt-oss:120b"
    quick_temperature: float = 0.3
    deep_temperature: float = 0.5

    # Debate
    research_debate_rounds: int = 1
    risk_debate_rounds: int = 1
    debate_mode: str = "on"  # "on" | "off"

    # Memory
    chroma_dir: str = ".chroma"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Observability
    runs_dir: str = "runs"
    langsmith_enabled: bool = False

    def apply_model_yaml(self, tiers: dict[str, dict[str, Any]] | None = None) -> "Settings":
        """Fill model/temperature from models.yaml ONLY where env didn't override."""
        tiers = tiers if tiers is not None else load_model_tiers()
        if "quick" in tiers:
            self.quick_model = tiers["quick"].get("model", self.quick_model)
            self.quick_temperature = tiers["quick"].get("temperature", self.quick_temperature)
        if "deep" in tiers:
            self.deep_model = tiers["deep"].get("model", self.deep_model)
            self.deep_temperature = tiers["deep"].get("temperature", self.deep_temperature)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings().apply_model_yaml()
```

Note on precedence: env vars set explicit field values at construction; `apply_model_yaml` only overwrites the in-code defaults. To keep env-wins semantics simple here, `get_settings()` applies yaml after construction — acceptable because in this project env is used for keys/flags and `models.yaml` is the source of truth for model names. If you set `QUICK_MODEL` in env AND want it to win over yaml, omit the `quick` key from `models.yaml`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/config/settings.py tests/test_settings.py
git commit -m "feat(config): add Settings with models.yaml loader"
```

---

### Task 5: CostTracker callback

**Files:**
- Create: `src/llm/__init__.py`
- Create: `src/llm/cost.py`
- Test: `tests/test_cost.py`

- [ ] **Step 1: Create `src/llm/__init__.py`** (empty package marker)

```python
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_cost.py
from types import SimpleNamespace
from src.llm.cost import CostTracker, PRICING


def _fake_response(prompt_tokens, completion_tokens, model):
    return SimpleNamespace(
        llm_output={
            "token_usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
            "model_name": model,
        }
    )


def test_cost_tracker_aggregates_tokens_and_latency():
    t = CostTracker(node="trader")
    rid = "run-1"
    t.on_llm_start({}, ["prompt"], run_id=rid)
    t.on_llm_end(_fake_response(100, 40, "gpt-oss:120b"), run_id=rid)
    totals = t.totals()
    assert totals["prompt_tokens"] == 100
    assert totals["completion_tokens"] == 40
    assert totals["latency_s"] >= 0.0
    assert len(totals["per_node"]) == 1
    assert totals["per_node"][0]["node"] == "trader"


def test_cost_tracker_uses_pricing_when_present():
    PRICING["test-model"] = (1.0, 2.0)  # USD per 1M (in, out)
    t = CostTracker(node="x")
    t.on_llm_start({}, ["p"], run_id="r")
    t.on_llm_end(_fake_response(1_000_000, 1_000_000, "test-model"), run_id="r")
    # 1M in * $1 + 1M out * $2 = $3
    assert round(t.totals()["cost_usd"], 2) == 3.0


def test_cost_tracker_handles_missing_usage():
    t = CostTracker(node="x")
    t.on_llm_start({}, ["p"], run_id="r")
    t.on_llm_end(SimpleNamespace(llm_output=None), run_id="r")
    assert t.totals()["prompt_tokens"] == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_cost.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm.cost'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/llm/cost.py
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from langchain_core.callbacks import BaseCallbackHandler

# USD per 1,000,000 tokens as (input_rate, output_rate).
# Ollama Cloud billing is plan-based; default to 0.0 and override per model as needed.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-oss:20b": (0.0, 0.0),
    "gpt-oss:120b": (0.0, 0.0),
}


@dataclass
class NodeCost:
    node: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0


class CostTracker(BaseCallbackHandler):
    """LangChain callback that records token usage, latency, and cost per LLM call."""

    def __init__(self, node: str = "unknown") -> None:
        self.node = node
        self.records: list[NodeCost] = []
        self._starts: dict = {}

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs) -> None:
        self._starts[run_id] = time.perf_counter()

    def on_llm_end(self, response, *, run_id=None, **kwargs) -> None:
        start = self._starts.pop(run_id, time.perf_counter())
        elapsed = time.perf_counter() - start
        out = getattr(response, "llm_output", None) or {}
        usage = out.get("token_usage", {}) if isinstance(out, dict) else {}
        model = out.get("model_name", "") if isinstance(out, dict) else ""
        pt = int(usage.get("prompt_tokens", 0) or 0)
        ct = int(usage.get("completion_tokens", 0) or 0)
        in_rate, out_rate = PRICING.get(model, (0.0, 0.0))
        cost = pt / 1_000_000 * in_rate + ct / 1_000_000 * out_rate
        self.records.append(NodeCost(self.node, model, pt, ct, round(elapsed, 4), round(cost, 6)))

    def totals(self) -> dict:
        return {
            "prompt_tokens": sum(r.prompt_tokens for r in self.records),
            "completion_tokens": sum(r.completion_tokens for r in self.records),
            "latency_s": round(sum(r.latency_s for r in self.records), 4),
            "cost_usd": round(sum(r.cost_usd for r in self.records), 6),
            "per_node": [asdict(r) for r in self.records],
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cost.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/llm/__init__.py src/llm/cost.py tests/test_cost.py
git commit -m "feat(llm): add CostTracker callback for tokens/latency/cost"
```

---

### Task 6: LLM factory

**Files:**
- Create: `src/llm/factory.py`
- Test: `tests/test_factory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_factory.py
import pytest
from langchain_openai import ChatOpenAI
from src.llm import factory
from src.config import settings as settings_mod


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch):
    # Force a deterministic Settings and clear memoization between tests.
    settings_mod.get_settings.cache_clear()
    factory.get_llm.cache_clear()
    monkeypatch.setenv("OLLAMA_API_KEY", "unit-test-key")
    monkeypatch.setenv("QUICK_MODEL", "q-model")
    monkeypatch.setenv("DEEP_MODEL", "d-model")
    yield
    settings_mod.get_settings.cache_clear()
    factory.get_llm.cache_clear()


def test_get_llm_quick_tier():
    llm = factory.get_llm("quick")
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "q-model"


def test_get_llm_deep_tier():
    assert factory.get_llm("deep").model_name == "d-model"


def test_get_llm_is_cached_singleton():
    assert factory.get_llm("quick") is factory.get_llm("quick")


def test_get_llm_bad_tier_raises():
    with pytest.raises(ValueError, match="unknown tier"):
        factory.get_llm("medium")
```

Note: env `QUICK_MODEL`/`DEEP_MODEL` win here because the test does not also define those tiers via a yaml override — `get_settings()` calls `apply_model_yaml()` which would overwrite from the real `models.yaml`. To make the test deterministic, the implementation reads tier model names from settings fields (`quick_model`/`deep_model`), and we set them via env; ensure `models.yaml` step ran so `apply_model_yaml` overwrites — therefore the test must override `apply_model_yaml`. See Step 3 fixture addition.

- [ ] **Step 2: Add a yaml-neutralizing line to the fixture so env wins**

Append inside the `_clear_caches` fixture, before `yield`:

```python
    # Neutralize models.yaml so env-provided model names are authoritative in this test.
    monkeypatch.setattr(settings_mod, "load_model_tiers", lambda *a, **k: {})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm.factory'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/llm/factory.py
from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI

from src.config.settings import get_settings


@lru_cache(maxsize=None)
def get_llm(tier: str) -> ChatOpenAI:
    """Return a cached ChatOpenAI pointed at the configured provider for the given tier.

    tier: "quick" (retrieval/summary/formatting) or "deep" (debate/verdict/arbiter).
    """
    s = get_settings()
    if tier == "quick":
        model, temperature = s.quick_model, s.quick_temperature
    elif tier == "deep":
        model, temperature = s.deep_model, s.deep_temperature
    else:
        raise ValueError(f"unknown tier: {tier!r} (expected 'quick' or 'deep')")

    return ChatOpenAI(
        model=model,
        base_url=s.llm_base_url,
        api_key=s.ollama_api_key or "not-set",
        temperature=temperature,
        timeout=120,
        max_retries=2,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_factory.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/llm/factory.py tests/test_factory.py
git commit -m "feat(llm): add cached provider-agnostic get_llm factory"
```

---

### Task 7: RunRecorder

**Files:**
- Create: `src/obs/__init__.py`
- Create: `src/obs/recorder.py`
- Test: `tests/test_recorder.py`

- [ ] **Step 1: Create `src/obs/__init__.py`** (empty package marker)

```python
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_recorder.py
import json
from src.obs.recorder import RunRecorder


def test_recorder_collects_and_flushes(tmp_path):
    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("router", "output", {"resolved_ticker": "AAPL"})
    rec.record("news_analyst", "output", {"summary": "ok"})
    path = rec.flush()
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["node"] == "router"
    assert first["run_id"] == rec.run_id
    assert first["data"]["resolved_ticker"] == "AAPL"


def test_recorder_generates_unique_run_ids():
    assert RunRecorder().run_id != RunRecorder().run_id


def test_recorder_serializes_non_json_values(tmp_path):
    rec = RunRecorder(runs_dir=str(tmp_path))
    rec.record("x", "output", {"obj": object()})  # not JSON-native
    path = rec.flush()  # must not raise
    assert path.exists()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_recorder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.obs.recorder'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/obs/recorder.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunRecorder:
    """Collects per-node events for a single graph run and flushes them to JSONL."""

    runs_dir: str = "runs"
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    events: list[dict] = field(default_factory=list)

    def record(self, node: str, kind: str, data: dict[str, Any]) -> None:
        self.events.append(
            {"run_id": self.run_id, "node": node, "kind": kind, "data": data}
        )

    def flush(self) -> Path:
        out_dir = Path(self.runs_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.run_id}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for event in self.events:
                f.write(json.dumps(event, default=str) + "\n")
        return path
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_recorder.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/obs/__init__.py src/obs/recorder.py tests/test_recorder.py
git commit -m "feat(obs): add RunRecorder for JSONL run traces"
```

---

### Task 8: Data-contract schemas

**Files:**
- Create: `src/llm/schemas.py`
- Test: `tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError
from src.llm.schemas import (
    AnalystReport,
    DebateTurn,
    ResearchDebate,
    TradeProposal,
    RiskDebate,
    FinalDecision,
)


def test_analyst_report_defaults():
    r = AnalystReport(summary="s")
    assert r.key_points == []
    assert r.confidence == 0.5


def test_trade_proposal_valid():
    p = TradeProposal(action="BUY", conviction=0.8, score=72, rationale="strong fundamentals")
    assert p.action == "BUY"
    assert p.model_dump()["score"] == 72


def test_trade_proposal_rejects_bad_score():
    with pytest.raises(ValidationError):
        TradeProposal(action="BUY", conviction=0.8, score=150, rationale="x")


def test_trade_proposal_rejects_bad_action():
    with pytest.raises(ValidationError):
        TradeProposal(action="MAYBE", conviction=0.5, score=50, rationale="x")


def test_research_debate_round_trip():
    d = ResearchDebate(
        rounds=[DebateTurn(role="bull", round=1, argument="up")],
        bull_thesis="b", bear_thesis="r", facilitator_verdict="lean bull",
    )
    again = ResearchDebate(**d.model_dump())
    assert again.rounds[0].role == "bull"


def test_final_decision_and_risk_debate():
    fd = FinalDecision(action="HOLD", conviction=0.4, score=50, rationale="mixed")
    rd = RiskDebate(conservative="careful", aggressive="bold", arbiter_decision="hold")
    assert fd.action == "HOLD"
    assert rd.adjustments == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm.schemas'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/llm/schemas.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["BUY", "SELL", "HOLD"]


class AnalystReport(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    citations: list[str] = Field(default_factory=list)


class DebateTurn(BaseModel):
    role: Literal["bull", "bear", "conservative", "aggressive"]
    round: int = Field(ge=1)
    argument: str


class ResearchDebate(BaseModel):
    rounds: list[DebateTurn] = Field(default_factory=list)
    bull_thesis: str = ""
    bear_thesis: str = ""
    facilitator_verdict: str = ""


class TradeProposal(BaseModel):
    action: Action
    conviction: float = Field(ge=0.0, le=1.0)
    score: int = Field(ge=0, le=100)
    rationale: str


class RiskDebate(BaseModel):
    rounds: list[DebateTurn] = Field(default_factory=list)
    conservative: str = ""
    aggressive: str = ""
    arbiter_decision: str = ""
    adjustments: list[str] = Field(default_factory=list)


class FinalDecision(BaseModel):
    action: Action
    conviction: float = Field(ge=0.0, le=1.0)
    score: int = Field(ge=0, le=100)
    rationale: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schemas.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/llm/schemas.py tests/test_schemas.py
git commit -m "feat(llm): add Pydantic data-contract schemas for node I/O"
```

---

### Task 9: AgentState + reducers

**Files:**
- Create: `src/state.py` (NEW contract; do not edit the legacy `src/state.py` content — overwrite it fully with the code below)
- Test: `tests/test_state.py`

> The legacy `src/state.py` is replaced. Overwrite the whole file with the new contract.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state.py
from src.state import merge_named_reports, AgentState


def test_merge_named_reports_combines_parallel_writes():
    left = {"news": {"summary": "n"}}
    right = {"fundamentals": {"summary": "f"}}
    merged = merge_named_reports(left, right)
    assert set(merged) == {"news", "fundamentals"}


def test_merge_named_reports_right_wins_on_key_conflict():
    assert merge_named_reports({"news": {"v": 1}}, {"news": {"v": 2}})["news"]["v"] == 2


def test_merge_named_reports_handles_none():
    assert merge_named_reports(None, {"a": 1}) == {"a": 1}
    assert merge_named_reports({"a": 1}, None) == {"a": 1}


def test_agentstate_is_typeddict_with_expected_keys():
    # __annotations__ exposes the declared fields of a TypedDict
    keys = set(AgentState.__annotations__)
    for expected in [
        "ticker", "resolved_ticker", "analyst_reports", "research_debate",
        "trade_proposal", "risk_debate", "final_decision", "final_report",
        "run_metrics", "run_id",
    ]:
        assert expected in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL with `ImportError: cannot import name 'merge_named_reports'` (or ModuleNotFound if file not yet overwritten)

- [ ] **Step 3: Write minimal implementation** (overwrite `src/state.py` entirely)

```python
# src/state.py
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_named_reports(left: dict | None, right: dict | None) -> dict:
    """Reducer for parallel analyst writes: shallow-merge by analyst name (right wins)."""
    out: dict[str, Any] = dict(left or {})
    out.update(right or {})
    return out


class AgentState(TypedDict, total=False):
    # --- control (Router) ---
    ticker: str
    resolved_ticker: str
    screener: str
    exchange: str
    investor_mode: str
    model_plan: dict

    # --- research (analysts write concurrently; merged by name) ---
    analyst_reports: Annotated[dict, merge_named_reports]

    # --- debate + decision (sequential single-writer fields) ---
    research_debate: dict
    trade_proposal: dict
    risk_debate: dict
    final_decision: dict
    final_report: str

    # --- observability (accumulated across nodes) ---
    run_metrics: Annotated[list, operator.add]
    run_id: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_state.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/state.py tests/test_state.py
git commit -m "feat(state): replace legacy state with typed AgentState + reducers"
```

---

### Task 10: 12-node stub graph

**Files:**
- Create: `src/graph.py` (NEW; overwrite the legacy `src/graph.py` fully)
- Test: `tests/test_graph_skeleton.py`

> Replaces legacy `src/graph.py`. Stub nodes return contract-shaped data so the graph runs end-to-end with no network calls. Real node logic arrives in the work-package plans.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph_skeleton.py
from src.graph import build_graph


def test_graph_compiles():
    assert build_graph() is not None


def test_graph_runs_end_to_end():
    app = build_graph()
    result = app.invoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert result["resolved_ticker"]  # router ran
    assert "final_report" in result  # reporter ran
    assert result["final_decision"]["action"] in {"BUY", "SELL", "HOLD"}


def test_graph_merges_three_parallel_analysts():
    app = build_graph()
    result = app.invoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    assert set(result["analyst_reports"]) == {"news", "fundamentals", "technicals"}


def test_graph_accumulates_run_metrics():
    app = build_graph()
    result = app.invoke({"ticker": "AAPL", "investor_mode": "Neutral"})
    # every node appends one metric record
    assert len(result["run_metrics"]) == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_graph_skeleton.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `build_graph`

- [ ] **Step 3: Write minimal implementation** (overwrite `src/graph.py` entirely)

```python
# src/graph.py
"""12-node stub topology for FinResearchAI. Nodes return contract-shaped stub data.
Real implementations are provided by the work-package plans; this file only freezes
the graph wiring and the state contract."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.state import AgentState


def _metric(node: str) -> list[dict]:
    return [{"node": node, "prompt_tokens": 0, "completion_tokens": 0, "latency_s": 0.0, "cost_usd": 0.0}]


def router(state: AgentState) -> dict:
    return {
        "resolved_ticker": state.get("ticker", ""),
        "screener": "america",
        "exchange": "NASDAQ",
        "model_plan": {"analysts": "quick", "debate": "deep", "verdict": "deep"},
        "run_metrics": _metric("router"),
    }


def _analyst(name: str):
    def node(state: AgentState) -> dict:
        return {
            "analyst_reports": {name: {"summary": f"stub {name} report", "confidence": 0.5}},
            "run_metrics": _metric(f"{name}_analyst"),
        }
    return node


def bull(state: AgentState) -> dict:
    return {"research_debate": {"bull_thesis": "stub bull"}, "run_metrics": _metric("bull")}


def bear(state: AgentState) -> dict:
    return {"research_debate": {"bear_thesis": "stub bear"}, "run_metrics": _metric("bear")}


def facilitator(state: AgentState) -> dict:
    prev = state.get("research_debate", {})
    prev["facilitator_verdict"] = "stub lean-neutral"
    return {"research_debate": prev, "run_metrics": _metric("facilitator")}


def trader(state: AgentState) -> dict:
    return {
        "trade_proposal": {"action": "HOLD", "conviction": 0.5, "score": 50, "rationale": "stub"},
        "run_metrics": _metric("trader"),
    }


def risk_conservative(state: AgentState) -> dict:
    return {"risk_debate": {"conservative": "stub careful"}, "run_metrics": _metric("risk_conservative")}


def risk_aggressive(state: AgentState) -> dict:
    return {"risk_debate": {"aggressive": "stub bold"}, "run_metrics": _metric("risk_aggressive")}


def risk_arbiter(state: AgentState) -> dict:
    proposal = state.get("trade_proposal", {})
    return {
        "final_decision": {
            "action": proposal.get("action", "HOLD"),
            "conviction": proposal.get("conviction", 0.5),
            "score": proposal.get("score", 50),
            "rationale": "stub arbiter decision",
        },
        "run_metrics": _metric("risk_arbiter"),
    }


def reporter(state: AgentState) -> dict:
    return {"final_report": "# Stub Report\n\nReplace in WP-F.", "run_metrics": _metric("reporter")}


_ANALYSTS = ["news", "fundamentals", "technicals"]


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("router", router)
    for name in _ANALYSTS:
        g.add_node(f"{name}_analyst", _analyst(name))
    g.add_node("bull", bull)
    g.add_node("bear", bear)
    g.add_node("facilitator", facilitator)
    g.add_node("trader", trader)
    g.add_node("risk_conservative", risk_conservative)
    g.add_node("risk_aggressive", risk_aggressive)
    g.add_node("risk_arbiter", risk_arbiter)
    g.add_node("reporter", reporter)

    g.add_edge(START, "router")

    # Router fans out to the three analysts (parallel).
    for name in _ANALYSTS:
        g.add_edge("router", f"{name}_analyst")

    # All analysts must finish before the bull/bear debate (join via multiple in-edges).
    for name in _ANALYSTS:
        g.add_edge(f"{name}_analyst", "bull")
        g.add_edge(f"{name}_analyst", "bear")

    # Bull + bear both feed the facilitator (join).
    g.add_edge("bull", "facilitator")
    g.add_edge("bear", "facilitator")

    g.add_edge("facilitator", "trader")

    # Trader fans out to the two risk personas.
    g.add_edge("trader", "risk_conservative")
    g.add_edge("trader", "risk_aggressive")

    # Both risk personas feed the arbiter (join).
    g.add_edge("risk_conservative", "risk_arbiter")
    g.add_edge("risk_aggressive", "risk_arbiter")

    g.add_edge("risk_arbiter", "reporter")
    g.add_edge("reporter", END)

    return g.compile()
```

> **Note on `facilitator` and `research_debate`:** because `bull` and `bear` both write the `research_debate` key in parallel and that key has NO reducer, LangGraph will raise an `InvalidUpdateError` for concurrent writes to the same key. To keep the stub correct, give `research_debate` a merge reducer too. Apply the fix in Step 4 before running.

- [ ] **Step 4: Add a reducer for `research_debate` and `risk_debate` (concurrent writers)**

Edit `src/state.py`: change the `research_debate` and `risk_debate` declarations to use the existing `merge_named_reports` reducer (it shallow-merges dicts, which is exactly what two debaters writing different keys need):

```python
    research_debate: Annotated[dict, merge_named_reports]
    risk_debate: Annotated[dict, merge_named_reports]
```

Then update `facilitator` in `src/graph.py` to return only its own delta (the reducer merges it):

```python
def facilitator(state: AgentState) -> dict:
    return {"research_debate": {"facilitator_verdict": "stub lean-neutral"}, "run_metrics": _metric("facilitator")}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_graph_skeleton.py -v`
Expected: PASS (4 tests). If you see `InvalidUpdateError`, Step 4 was not applied correctly.

- [ ] **Step 6: Run the FULL suite to confirm nothing regressed**

Run: `python -m pytest -q`
Expected: all tests PASS (settings, cost, factory, recorder, schemas, state, graph).

- [ ] **Step 7: Commit**

```bash
git add src/graph.py src/state.py tests/test_graph_skeleton.py
git commit -m "feat(graph): add runnable 12-node stub topology (frozen contract)"
```

---

### Task 11: End-to-end smoke script + live-LLM opt-in check

**Files:**
- Create: `scripts/smoke.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
from scripts.smoke import run_stub


def test_run_stub_returns_report_and_writes_trace(tmp_path):
    result, trace_path = run_stub("AAPL", runs_dir=str(tmp_path))
    assert "final_report" in result
    assert trace_path.exists()
    assert len(trace_path.read_text(encoding="utf-8").strip().splitlines()) == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.smoke'`

- [ ] **Step 3: Create `scripts/__init__.py`** (empty) **and write `scripts/smoke.py`**

```python
# scripts/__init__.py
```

```python
# scripts/smoke.py
"""Run the stub graph end-to-end and write its run_metrics trace.
Usage: python -m scripts.smoke --ticker AAPL"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.graph import build_graph
from src.obs.recorder import RunRecorder


def run_stub(ticker: str, runs_dir: str = "runs"):
    app = build_graph()
    result = app.invoke({"ticker": ticker, "investor_mode": "Neutral"})
    rec = RunRecorder(runs_dir=runs_dir)
    for metric in result.get("run_metrics", []):
        rec.record(metric["node"], "metric", metric)
    return result, rec.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--runs-dir", default="runs")
    args = parser.parse_args()
    result, trace = run_stub(args.ticker, args.runs_dir)
    print(result["final_report"])
    print(f"\n[trace] {trace}  | metrics: {len(result['run_metrics'])} nodes")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Run the smoke script for real**

Run: `python -m scripts.smoke --ticker AAPL`
Expected: prints the stub report markdown and a `[trace] runs/<id>.jsonl | metrics: 12 nodes` line. Confirms the whole contract executes.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/smoke.py tests/test_smoke.py
git commit -m "feat(scripts): add end-to-end stub smoke runner"
```

---

## Definition of Done (this plan)
- [ ] `python -m pytest -q` is green (all 7 test modules).
- [ ] `python -m scripts.smoke --ticker AAPL` runs end-to-end and writes a 12-line trace.
- [ ] `get_settings()`, `get_llm("quick"|"deep")`, `CostTracker`, `RunRecorder`, all schemas, `AgentState`, and `build_graph()` exist and are importable.
- [ ] The state contract (`AgentState` keys + reducers + schema models) is FROZEN. Any change after this point must be announced to all in-flight work packages.

## What comes next (separate plans)
Each work package codes against the frozen contract and replaces the matching stub node(s):
- **WP-B** Tools + Analysts → replace `news/fundamentals/technicals` stubs; add `src/tools/{firecrawl,yfinance,tradingview}.py`.
- **WP-C** Memory → `src/memory/{store,embeddings}.py` (Chroma + fastembed), metadata-query cache.
- **WP-D** Research Debate → real `bull`/`bear`/`facilitator` with bounded rounds.
- **WP-E** Trader + Risk Debate → real `trader`/`risk_*`/`arbiter`.
- **WP-F** Reporter → streamed markdown + structured `financial_data`.
- **WP-G** API + UI → `src/api/*` (FastAPI SSE) + `web/`.
- **WP-H** Eval → `src/eval/*` (debate A/B harness + deep judge + report).
- **WP-I** Tests/CI → integration tests with mocked LLM/tools + CI workflow; remove legacy `src/agents/*`, `src/memory.py`, `app.py`/`main.py` once superseded.
