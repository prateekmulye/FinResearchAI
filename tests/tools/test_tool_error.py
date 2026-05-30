from src.tools import ToolError


def test_tool_error_carries_tool_and_message():
    err = ToolError("firecrawl", "boom")
    assert err.tool == "firecrawl"
    assert "firecrawl" in str(err)
    assert "boom" in str(err)
    assert isinstance(err, RuntimeError)
