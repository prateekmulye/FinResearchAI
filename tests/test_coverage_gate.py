# tests/test_coverage_gate.py
"""Coverage is OPT-IN. This test only verifies pytest-cov is installed and the
[tool.coverage.run] config targets src/. To ENFORCE a threshold, run:

    pytest --cov=src --cov-report=term-missing --cov-fail-under=60 -m "not live"

That command is intentionally NOT part of default CI (Task 5) so incremental
integration isn't blocked by coverage; flip it on once all WPs are merged.
"""
import tomllib
from pathlib import Path


def test_pytest_cov_is_installed():
    import importlib.util

    assert importlib.util.find_spec("pytest_cov") is not None, "pytest-cov not installed (in [dev])"


def test_coverage_config_targets_src():
    root = Path(__file__).resolve().parents[1]
    with open(root / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["tool"]["coverage"]["run"]["source"] == ["src"]
