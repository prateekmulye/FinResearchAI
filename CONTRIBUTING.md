# Contributing to FinResearchAI

Thanks for your interest! This project is a portfolio flagship, but issues and PRs are
welcome.

## Development setup

```bash
git clone <repo-url> && cd FinResearchAI
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"            # all optional groups (memory, web, data, api, dev)
cp .env.example .env               # add your own OLLAMA_API_KEY / FIRECRAWL_API_KEY
```

## Quality gates (all must pass)

```bash
python -m pytest -q     # offline test suite — no network, LLMs/tools are mocked
ruff check .            # lint
mypy src                # type-check
```

- **Tests are offline by default.** Live tests (real Ollama Cloud + Firecrawl) are marked
  `@pytest.mark.live` and deselected; run one with `RUN_LIVE=1 python -m pytest -m live`.
- **TDD:** write the failing test first, confirm it fails, implement, confirm green.
- **Structured output only:** nodes use `with_structured_output(Schema, method=STRUCT_METHOD)`
  — never JSON string-scraping.
- **Degrade everywhere:** a node whose LLM/tool call fails must return a schema-shaped
  fallback plus a `zero_metrics(node)` record — one failure never aborts the graph.

## Commits & PRs

- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:` …).
- One logical change per PR; include tests for behavior changes.
- CI (ruff + mypy + offline pytest on Python 3.11/3.13) must be green before review.

## Architecture guardrails

The graph topology (12 nodes debate-on / 10 debate-off) and the cross-cutting contracts in
`src/config/settings.py`, `src/llm/{factory,cost,schemas}.py`, and `src/obs/recorder.py`
are stable interfaces — propose changes in an issue before touching them. See
`docs/superpowers/` for the design history.
