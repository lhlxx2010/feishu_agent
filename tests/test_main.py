import pytest
from main import mcp


def test_mcp_tool_registration():
    """Verify that tools are correctly registered with FastMCP."""
    # FastMCP stores tools in ._tool_manager._tools (internal API, but useful for verification)
    # Or typically exposes list_tools()

    tools = mcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]

    assert "get_active_tasks" in tool_names
    assert "create_task" in tool_names


def test_get_active_tasks_metadata():
    """Verify tool metadata (description, args)."""
    tools = mcp._tool_manager.list_tools()
    tool = next(t for t in tools if t.name == "get_active_tasks")

    assert "活跃" in tool.description or "active" in tool.description.lower()
    # tool.parameters is the JSON Schema dict
    assert "project" in tool.parameters["properties"]
    assert tool.parameters["required"] == ["project"]
