"""WP-11 deploy-artifact guards — cheap string/YAML asserts that keep CI honest
without needing Docker.

What is locked down:
  * Dockerfile installs the db extra (the bare ``.[api]`` install broke the image
    the moment src/api started importing src/warehouse in WP-5) plus the web/data
    extras the collector + analysts need at runtime; ships migrations + alembic.ini;
    bakes the fastembed model; runs as a non-root user.
  * docker/entrypoint.sh migrates (alembic upgrade head) BEFORE exec'ing uvicorn.
  * docker-compose.prod.yml exposes ONLY Caddy to the host; POSTGRES_PASSWORD is
    required (no default baked into the prod file).
  * Caddyfile carries the security headers, the /api reverse proxy, and the SPA
    fallback.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "docker" / "entrypoint.sh"
COMPOSE_PROD = ROOT / "docker-compose.prod.yml"
COMPOSE_DEV = ROOT / "docker-compose.yml"
CADDYFILE = ROOT / "Caddyfile"


# ---------------------------------------------------------------- Dockerfile
class TestDockerfile:
    @pytest.fixture()
    def text(self) -> str:
        return DOCKERFILE.read_text(encoding="utf-8")

    def test_installs_db_extra_not_bare_api(self, text: str) -> None:
        # The WP-5 regression: src/api imports src/warehouse, so an image built
        # with only ".[api]" dies on import (no sqlalchemy). The runtime needs
        # api+db, plus web+data for the analysts' tools and the collector.
        assert not re.search(
            r'pip install[^\n]*"\.\[api\]"', text
        ), "bare .[api] install is the known-broken image"
        m = re.search(r'pip install [^\n]*"\.\[([a-z,]+)\]"', text)
        assert m, "expected a pip install \".[<extras>]\" line"
        extras = set(m.group(1).split(","))
        assert {"api", "db", "web", "data"} <= extras, f"missing extras: {extras}"

    def test_multi_stage_targets(self, text: str) -> None:
        for target in ("web-builder", "py-builder", "runtime", "caddy"):
            assert re.search(rf"^FROM \S+ AS {target}$", text, re.M), f"missing stage {target}"

    def test_web_is_built_not_copied_as_source(self, text: str) -> None:
        assert "npm ci" in text and "npm run build" in text
        # The runtime stage must NOT carry web source; only the caddy stage takes dist.
        runtime = text.split("AS runtime")[1].split("\nFROM ")[0]
        assert "COPY web" not in runtime, "runtime stage must not copy web source"

    def test_runtime_ships_migrations_and_alembic_ini(self, text: str) -> None:
        runtime = text.split("AS runtime")[1].split("\nFROM ")[0]
        assert "COPY migrations" in runtime
        assert "alembic.ini" in runtime

    def test_runtime_bakes_fastembed_model(self, text: str) -> None:
        assert "FASTEMBED_CACHE_PATH" in text, "pin the cache dir (default is /tmp)"
        assert "from fastembed import TextEmbedding" in text
        assert "BAAI/bge-small-en-v1.5" in text
        # The bake must happen after USER appuser so the cache is readable at runtime.
        runtime = text.split("AS runtime")[1].split("\nFROM ")[0]
        assert runtime.index("USER appuser") < runtime.index("from fastembed import")

    def test_runtime_is_non_root_and_uses_entrypoint(self, text: str) -> None:
        runtime = text.split("AS runtime")[1].split("\nFROM ")[0]
        assert "USER appuser" in runtime
        assert "entrypoint.sh" in runtime

    def test_caddy_stage_ships_caddyfile_and_dist(self, text: str) -> None:
        caddy = text.split("AS caddy")[1]
        assert "COPY Caddyfile /etc/caddy/Caddyfile" in caddy
        assert re.search(r"COPY --from=web-builder \S*/dist /srv", caddy)


# ------------------------------------------------------------- entrypoint.sh
class TestEntrypoint:
    @pytest.fixture()
    def text(self) -> str:
        return ENTRYPOINT.read_text(encoding="utf-8")

    def test_is_posix_sh_and_executable(self, text: str) -> None:
        assert text.startswith("#!/bin/sh")
        assert os.access(ENTRYPOINT, os.X_OK), "entrypoint.sh must be executable"

    def test_migrates_before_uvicorn(self, text: str) -> None:
        assert "alembic upgrade head" in text
        assert text.index("alembic upgrade head") < text.index("uvicorn")

    def test_migration_is_gated_on_database_url_and_retried(self, text: str) -> None:
        assert "DATABASE_URL" in text, "migrations only run when the warehouse is configured"
        assert re.search(r"\b(for|while)\b", text), "expected a retry/wait loop for the db"

    def test_execs_uvicorn(self, text: str) -> None:
        assert re.search(r"^exec uvicorn src\.api\.main:app", text, re.M)

    def test_fails_rather_than_serving_unmigrated(self, text: str) -> None:
        # Retry exhaustion must exit non-zero, never fall through to uvicorn.
        assert "exit 1" in text
        assert text.index("exit 1") < text.index("exec uvicorn")


# ---------------------------------------------------- docker-compose.prod.yml
class TestComposeProd:
    @pytest.fixture()
    def raw(self) -> str:
        return COMPOSE_PROD.read_text(encoding="utf-8")

    @pytest.fixture()
    def services(self, raw: str) -> dict:
        return yaml.safe_load(raw)["services"]

    def test_three_services(self, services: dict) -> None:
        assert set(services) == {"caddy", "app", "db"}

    def test_only_caddy_publishes_host_ports(self, services: dict) -> None:
        assert "ports" not in services["app"], "app must stay internal (Caddy fronts it)"
        assert "ports" not in services["db"], "db must stay internal"
        published = {str(p) for p in services["caddy"]["ports"]}
        assert any(p.startswith("80:") for p in published)
        assert any(p.startswith("443:") for p in published)

    def test_postgres_password_is_required_no_default(self, raw: str) -> None:
        # ${POSTGRES_PASSWORD:?...} makes compose refuse to start without it; a
        # ":-" default would silently ship a guessable password.
        assert "${POSTGRES_PASSWORD:?" in raw
        assert "POSTGRES_PASSWORD:-" not in raw

    def test_app_env_wiring(self, services: dict) -> None:
        env = services["app"]["environment"]
        assert env["DATABASE_URL"].endswith("@db:5432/finresearch")
        assert str(env["TRUST_PROXY"]) == "1"
        assert str(env["COLLECTOR_ENABLED"]) == "1"
        assert env["RUNS_DIR"] == "/app/runs"
        assert "ALLOWED_ORIGINS" in env
        for key in ("OLLAMA_API_KEY", "FIRECRAWL_API_KEY", "ADMIN_TOKEN"):
            assert key in env

    def test_dependency_and_restart_policy(self, services: dict) -> None:
        assert services["caddy"]["depends_on"]["app"]["condition"] == "service_healthy"
        assert services["app"]["depends_on"]["db"]["condition"] == "service_healthy"
        for name in ("caddy", "app", "db"):
            assert services[name]["restart"] == "unless-stopped"

    def test_app_and_db_have_healthchecks(self, services: dict) -> None:
        assert "healthcheck" in services["app"]
        assert "healthcheck" in services["db"]

    def test_db_is_pgvector_pg16(self, services: dict) -> None:
        assert services["db"]["image"] == "pgvector/pgvector:pg16"

    def test_dev_compose_untouched_db_only(self) -> None:
        dev = yaml.safe_load(COMPOSE_DEV.read_text(encoding="utf-8"))
        assert set(dev["services"]) == {"db"}, "docker-compose.yml stays the dev-only db"


# -------------------------------------------------------------------- Caddyfile
class TestCaddyfile:
    @pytest.fixture()
    def text(self) -> str:
        return CADDYFILE.read_text(encoding="utf-8")

    def test_domain_from_env_with_port_80_fallback(self, text: str) -> None:
        assert "{$CADDY_DOMAIN::80}" in text

    def test_security_headers(self, text: str) -> None:
        for header in (
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "X-Frame-Options",
            "Content-Security-Policy",
        ):
            assert header in text, f"missing {header}"

    def test_csp_allows_self_connect_for_sse(self, text: str) -> None:
        csp = next(line for line in text.splitlines() if "Content-Security-Policy" in line)
        assert "connect-src 'self'" in csp
        assert "default-src 'self'" in csp

    def test_api_and_healthz_proxy_to_app(self, text: str) -> None:
        assert "/api/*" in text
        assert "/healthz" in text
        assert "reverse_proxy app:7860" in text

    def test_sse_streaming_is_unbuffered(self, text: str) -> None:
        # flush_interval -1 disables proxy buffering — without it Caddy batches
        # the token SSE stream and the live cockpit stops feeling live.
        assert "flush_interval -1" in text

    def test_spa_fallback_and_caching(self, text: str) -> None:
        assert "try_files {path} /index.html" in text
        assert "file_server" in text
        assert "immutable" in text, "hashed /assets/* should be long-cached"
        assert "no-cache" in text, "index.html must not be cached"
