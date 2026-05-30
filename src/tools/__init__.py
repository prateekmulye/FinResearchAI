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
