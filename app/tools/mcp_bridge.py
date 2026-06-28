"""Ponte com servidores MCP (EXPERIMENTAL).

Lê uma lista de servidores (mcp_servers.json), conecta via stdio usando o SDK
oficial `mcp`, lista as ferramentas de cada um e as expõe como Tool. Servidores
podem ser instalados sob demanda usando `npx -y <pacote>` como comando.

É o ponto mais dependente do seu ambiente: precisa de Node/npx na imagem (já
incluso no Dockerfile) e que cada servidor inicialize corretamente. Tudo aqui é
defensivo — se algo falhar, o app continua sem as ferramentas MCP.
"""
from contextlib import AsyncExitStack

from app.tools.base import Tool


class MCPManager:
    def __init__(self):
        self.stack: AsyncExitStack | None = None
        self.tools: list[Tool] = []

    async def start(self, servers: list[dict]):
        servers = [s for s in (servers or []) if s.get("enabled", True)]
        if not servers:
            return
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as e:  # SDK ausente
            print("MCP SDK indisponível:", e)
            return

        self.stack = AsyncExitStack()
        for s in servers:
            name = s.get("name") or s.get("command", "mcp")
            try:
                params = StdioServerParameters(
                    command=s["command"], args=s.get("args", []), env=s.get("env")
                )
                read, write = await self.stack.enter_async_context(stdio_client(params))
                session = await self.stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listed = await session.list_tools()
                for t in listed.tools:
                    self.tools.append(self._wrap(session, name, t))
                print(f"MCP '{name}': {len(listed.tools)} ferramenta(s).")
            except Exception as e:
                print(f"Falha ao iniciar MCP '{name}': {e}")

    def _wrap(self, session, server_name: str, t) -> Tool:
        async def fn(**kwargs):
            res = await session.call_tool(t.name, kwargs)
            parts = []
            for b in getattr(res, "content", []) or []:
                parts.append(getattr(b, "text", str(b)))
            return "\n".join(parts)[:8000]

        schema = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
        return Tool(
            f"mcp__{server_name}__{t.name}",
            (getattr(t, "description", None) or "Ferramenta MCP")[:300],
            schema,
            fn,
        )

    async def stop(self):
        if self.stack:
            try:
                await self.stack.aclose()
            except Exception:
                pass
