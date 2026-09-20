from agent.tools.runtime import ToolResult


def list_tools() -> ToolResult:
    return ToolResult(True, "tools.list", {}, "Available tools")
