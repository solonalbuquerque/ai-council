"""Ferramentas de web: busca e leitura de página."""
import os

import httpx
from bs4 import BeautifulSoup

from app.tools.base import Tool

_UA = "Mozilla/5.0 (compatible; AICouncil/1.0)"


async def _web_search(query: str, max_results: int = 5) -> str:
    max_results = max(1, min(int(max_results), 10))
    key = os.getenv("TAVILY_API_KEY")
    if key:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.tavily.com/search",
                json={"api_key": key, "query": query, "max_results": max_results},
            )
            r.raise_for_status()
            data = r.json()
        out = [
            f"- {it.get('title')}\n  {it.get('url')}\n  {(it.get('content') or '')[:300]}"
            for it in data.get("results", [])
        ]
        return "RESULTADOS:\n" + "\n".join(out) if out else "Sem resultados."

    # Fallback sem chave: DuckDuckGo HTML (best-effort, pode quebrar).
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": _UA}) as c:
        r = await c.get("https://html.duckduckgo.com/html/", params={"q": query})
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for res in soup.select(".result")[:max_results]:
        a = res.select_one(".result__a")
        sn = res.select_one(".result__snippet")
        if a:
            out.append(
                f"- {a.get_text(strip=True)}\n  {a.get('href')}\n  "
                f"{(sn.get_text(strip=True) if sn else '')[:300]}"
            )
    return "RESULTADOS:\n" + "\n".join(out) if out else "Sem resultados (fallback DDG)."


async def _web_fetch(url: str, max_chars: int = 3000) -> str:
    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": _UA}, follow_redirects=True
    ) as c:
        r = await c.get(url)
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.extract()
    text = " ".join(soup.get_text(" ").split())
    return text[:max(500, int(max_chars))]


web_search_tool = Tool(
    "web_search",
    "Busca na web por uma consulta e retorna títulos, URLs e trechos.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "termo de busca"},
            "max_results": {"type": "integer", "description": "1 a 10"},
        },
        "required": ["query"],
    },
    _web_search,
)

web_fetch_tool = Tool(
    "web_fetch",
    "Baixa e extrai o texto principal de uma URL.",
    {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
    _web_fetch,
)
