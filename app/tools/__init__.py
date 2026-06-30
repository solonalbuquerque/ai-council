"""Build the list of tools enabled for a conversation."""
from app.tools.apify import apify_tool
from app.tools.base import Tool
from app.tools.web import web_fetch_tool, web_search_tool


def filter_tools_for_participant(
    tools: list[Tool], config: dict, pkey: str,
) -> list[Tool]:
    """Restrict tools per participant when config.tools_for is set."""
    tools_for = (config or {}).get("tools_for")
    if not tools_for:
        return tools
    allowed = tools_for.get(pkey)
    if allowed is None:
        base = pkey.split(":", 1)[0] if ":" in pkey else pkey
        allowed = tools_for.get(base)
    if allowed is None:
        return []
    allowed_set = set(allowed)
    return [t for t in tools if t.name in allowed_set]


def build_tools(config: dict, mcp_tools: list[Tool] | None = None) -> list[Tool]:
    config = config or {}
    tools: list[Tool] = []
    if config.get("web", True):
        tools += [web_search_tool, web_fetch_tool]
    if config.get("apify", False):
        tools.append(apify_tool)
    if config.get("mcp", False) and mcp_tools:
        tools += mcp_tools
    return tools
