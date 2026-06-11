# tests/test_ci_artifacts.py
"""WP-12 CI/CD artifact guards — string/YAML asserts over the GitHub Actions
workflows and the Dependabot config (companion to test_deploy_artifacts.py).

What is locked down:
  * ci.yml carries the five-job pipeline (test / web / db-integration /
    security / e2e-smoke), the pgvector service for the real `-m db` run, the
    security trio (gitleaks + pip-audit + npm audit), the trivy image gate,
    and never references real API-key secrets.
  * e2e-smoke is fenced off PRs (push-to-main + workflow_dispatch only) and
    boots the prod compose stack with APP_FAKE_LLM=1.
  * deploy.yml is a green NO-OP until the repo variable DEPLOY_ENABLED is
    'true'; it pushes BOTH GHCR targets and parameterizes SSH via secrets.
  * dependabot.yml covers all four ecosystems weekly, with grouped updates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_YML = ROOT / ".github" / "workflows" / "deploy.yml"
DEPENDABOT_YML = ROOT / ".github" / "dependabot.yml"


def _triggers(workflow: dict) -> Any:
    # yaml.safe_load parses the bare `on:` key as boolean True (YAML 1.1).
    return workflow.get("on", workflow.get(True))


def _steps_text(job: dict) -> str:
    # width=inf: stop safe_dump folding long scalars mid-substring.
    return yaml.safe_dump(job.get("steps", []), width=float("inf"))


# -------------------------------------------------------------------- ci.yml
class TestCiWorkflow:
    @pytest.fixture()
    def raw(self) -> str:
        return CI_YML.read_text(encoding="utf-8")

    @pytest.fixture()
    def wf(self, raw: str) -> dict:
        return yaml.safe_load(raw)

    @pytest.fixture()
    def jobs(self, wf: dict) -> dict:
        return wf["jobs"]

    def test_parses_with_all_five_jobs(self, jobs: dict) -> None:
        assert {"test", "web", "db-integration", "security", "e2e-smoke"} <= set(jobs)

    def test_backend_job_unchanged_matrix_and_offline_selection(self, jobs: dict) -> None:
        test = jobs["test"]
        assert test["strategy"]["matrix"]["python-version"] == ["3.11", "3.13"]
        assert 'pytest -q -m "not live and not db"' in _steps_text(test)

    def test_web_job_runs_full_frontend_gauntlet(self, jobs: dict) -> None:
        web = jobs["web"]
        assert web["defaults"]["run"]["working-directory"] == "web"
        text = _steps_text(web)
        assert "actions/setup-node" in text
        assert "node-version: '22'" in text
        assert "cache: npm" in text
        assert "web/package-lock.json" in text
        for cmd in ("npm ci", "npm run lint", "npm run typecheck",
                    "npm run test:run", "npm run build"):
            assert cmd in text, f"web job missing `{cmd}`"

    def test_db_job_uses_pgvector_service_and_db_marker(self, jobs: dict) -> None:
        db = jobs["db-integration"]
        svc = db["services"]["postgres"]
        assert svc["image"] == "pgvector/pgvector:pg16"
        assert "pg_isready" in svc["options"]
        assert "5432:5432" in [str(p) for p in svc["ports"]]
        text = _steps_text(db)
        assert "pytest -q -m db" in text, "db job must run the db-marked tests"
        assert "postgresql+asyncpg://" in text
        assert "localhost:5432" in text

    def test_security_job_runs_gitleaks_pip_audit_npm_audit(self, jobs: dict) -> None:
        text = _steps_text(jobs["security"])
        assert "gitleaks/gitleaks-action@" in text
        assert "pip-audit" in text
        assert "npm audit --audit-level=high" in text
        # gitleaks needs the full history to scan past commits.
        assert "fetch-depth: 0" in text
        # Vuln escapes must be explicit --ignore-vuln pins, never a soft job.
        assert "continue-on-error" not in text

    def test_e2e_smoke_is_fenced_off_prs(self, jobs: dict) -> None:
        cond = jobs["e2e-smoke"]["if"]
        assert "workflow_dispatch" in cond
        assert "refs/heads/main" in cond
        assert "pull_request" not in cond
        assert "timeout-minutes" in jobs["e2e-smoke"]

    def test_e2e_smoke_boots_prod_compose_in_fake_mode(self, jobs: dict) -> None:
        smoke = jobs["e2e-smoke"]
        assert str(smoke["env"]["APP_FAKE_LLM"]) == "1"
        text = _steps_text(smoke)
        assert "docker-compose.prod.yml build" in text
        assert "up -d --wait" in text
        assert "/api/analyze" in text and "event: done" in text
        assert "/api/library" in text
        assert "/healthz" in text
        assert "down -v" in text, "the stack must be torn down"

    def test_trivy_gate_pinned_with_severity_and_exit_code(self, jobs: dict) -> None:
        text = _steps_text(jobs["e2e-smoke"])
        assert "aquasecurity/trivy-action@" in text
        assert "trivy-action@master" not in text, "pin a trivy-action release"
        assert "CRITICAL,HIGH" in text
        assert "exit-code: '1'" in text
        assert "ignore-unfixed: true" in text
        # Escapes live in .trivyignore, each with a justification + removal
        # condition; the file must exist as long as the workflow points at it.
        assert "trivyignores: .trivyignore" in text
        assert (ROOT / ".trivyignore").is_file()

    def test_no_real_api_key_secrets_ever_reach_ci(self, raw: str) -> None:
        # The only secret CI may touch is the ephemeral GITHUB_TOKEN.
        assert "secrets.OLLAMA_API_KEY" not in raw
        assert "secrets.FIRECRAWL_API_KEY" not in raw

    def test_triggers_include_dispatch_for_manual_smoke(self, wf: dict) -> None:
        assert "workflow_dispatch" in _triggers(wf)


# ---------------------------------------------------------------- deploy.yml
class TestDeployWorkflow:
    @pytest.fixture()
    def raw(self) -> str:
        return DEPLOY_YML.read_text(encoding="utf-8")

    @pytest.fixture()
    def wf(self, raw: str) -> dict:
        return yaml.safe_load(raw)

    def test_every_job_gated_on_deploy_enabled_variable(self, wf: dict) -> None:
        # A repo *variable* (vars context) — secrets can't be used in `if:`.
        for name, job in wf["jobs"].items():
            assert "vars.DEPLOY_ENABLED == 'true'" in job["if"], (
                f"job {name} must be a no-op until DEPLOY_ENABLED=true"
            )

    def test_triggers_on_ci_success_for_main_and_dispatch(self, wf: dict) -> None:
        on = _triggers(wf)
        assert "workflow_dispatch" in on
        wr = on["workflow_run"]
        assert wr["workflows"] == ["CI"]
        assert wr["types"] == ["completed"]
        assert wr["branches"] == ["main"]
        # workflow_run fires on failed CI too; the job gate must filter it.
        assert "workflow_run.conclusion == 'success'" in wf["jobs"]["build-push"]["if"]

    def test_pushes_both_ghcr_targets(self, wf: dict) -> None:
        text = _steps_text(wf["jobs"]["build-push"])
        assert "ghcr.io/prateekmulye/finresearchai-app" in text
        assert "ghcr.io/prateekmulye/finresearchai-caddy" in text
        assert "target: runtime" in text
        assert "target: caddy" in text
        assert wf["permissions"]["packages"] == "write"

    def test_deploy_ssh_parameterized_via_secrets(self, wf: dict) -> None:
        deploy = wf["jobs"]["deploy"]
        assert deploy["needs"] == "build-push"
        text = _steps_text(deploy)
        for secret in ("secrets.VPS_HOST", "secrets.VPS_USER", "secrets.VPS_SSH_KEY"):
            assert secret in text, f"missing {secret}"
        assert "git pull --ff-only" in text
        assert "docker-compose.prod.yml up -d --build" in text


# ------------------------------------------------------------- dependabot.yml
class TestDependabot:
    @pytest.fixture()
    def updates(self) -> list[dict]:
        cfg = yaml.safe_load(DEPENDABOT_YML.read_text(encoding="utf-8"))
        assert cfg["version"] == 2
        return cfg["updates"]

    def test_covers_all_four_ecosystems(self, updates: list[dict]) -> None:
        ecosystems = {u["package-ecosystem"] for u in updates}
        assert ecosystems == {"pip", "npm", "github-actions", "docker"}

    def test_npm_points_at_web_others_at_root(self, updates: list[dict]) -> None:
        by_eco = {u["package-ecosystem"]: u for u in updates}
        assert by_eco["npm"]["directory"] == "/web"
        for eco in ("pip", "github-actions", "docker"):
            assert by_eco[eco]["directory"] == "/"

    def test_weekly_cadence_and_grouped_updates(self, updates: list[dict]) -> None:
        for u in updates:
            assert u["schedule"]["interval"] == "weekly"
            assert u.get("groups"), f"{u['package-ecosystem']} updates must be grouped"
