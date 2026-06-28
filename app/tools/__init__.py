"""Monta a lista de ferramentas habilitadas para uma conversa."""
from app.tools.apify import apify_tool
from app.tools.base import Tool
from app.tools.web import web_fetch_tool, web_search_tool


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
