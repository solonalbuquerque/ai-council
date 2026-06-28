"""Ferramenta para rodar Actors da Apify."""
import json
import os

import httpx

from app.tools.base import Tool


async def _apify_run(actor_id: str, input: dict | None = None, max_items: int = 20) -> str:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        return "APIFY_TOKEN não configurado no ambiente."
    # Apify aceita 'user/actor' como 'user~actor' na URL.
    actor = actor_id.replace("/", "~")
    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(url, params={"token": token}, json=input or {})
        r.raise_for_status()
        items = r.json()
    if isinstance(items, list):
        items = items[: max(1, int(max_items))]
    return json.dumps(items, ensure_ascii=False)[:8000]


apify_tool = Tool(
    "apify_run",
    "Executa um Actor da Apify (ex.: 'apify/web-scraper') e retorna itens do dataset.",
    {
        "type": "object",
        "properties": {
            "actor_id": {"type": "string", "description": "ex.: apify/website-content-crawler"},
            "input": {"type": "object", "description": "input do Actor"},
            "max_items": {"type": "integer"},
        },
        "required": ["actor_id"],
    },
    _apify_run,
)
