# tests/test_legacy_removed.py
"""Guards the legacy cleanup (WP-I Task 6). These modules were the old
Pinecone-as-message-bus architecture; they must NOT exist or import.

If any of these pass-imports succeed, the legacy code was re-introduced —
fail loudly so CI catches it.
"""
import importlib
import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Module import paths that must NO LONGER resolve.
LEGACY_MODULES = [
    "src.agents.manager",
    "src.agents.analyst",
    "src.agents.researchers.tavily",
    "src.agents.researchers.tradingview",
    "src.agents.researchers.yfinance_agent",
    "src.memory",  # old single-file Pinecone module (new code is the src/memory/ PACKAGE)
]

# Files/dirs that must NO LONGER exist on disk.
LEGACY_PATHS = [
    "src/agents/manager.py",
    "src/agents/analyst.py",
    "src/agents/researchers",
    "main.py",
    "app.py",
    "requirements.txt",
    "tests/test_flow.py",
    "tests/test_international.py",
    "tests/test_ui_logic.py",
]


@pytest.mark.parametrize("path", LEGACY_PATHS)
def test_legacy_path_deleted(path):
    assert not (_REPO_ROOT / path).exists(), f"legacy path still present: {path}"


def _can_find(mod: str) -> bool:
    """find_spec raises ModuleNotFoundError if a PARENT package is missing; treat as 'not found'."""
    try:
        return importlib.util.find_spec(mod) is not None
    except ModuleNotFoundError:
        return False


@pytest.mark.parametrize("mod", LEGACY_MODULES)
def test_legacy_module_not_importable(mod):
    # src.memory becomes a PACKAGE in the new architecture; only the OLD single-file
    # module is forbidden. A package directory is allowed — distinguish by checking
    # that no MODULE file (src/memory.py) exists for the single-file legacy ones.
    if mod == "src.memory":
        assert not (_REPO_ROOT / "src" / "memory.py").exists(), (
            "legacy src/memory.py file still present (new code must be the src/memory/ package)"
        )
        return
    spec = importlib.util.find_spec(mod) if _can_find(mod) else None
    assert spec is None, f"legacy module still importable: {mod}"
