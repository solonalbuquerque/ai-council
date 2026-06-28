"""Gera título resumido via qualquer agente disponível."""
import re

from app.catalog import PROVIDER_CATALOG
from app.providers import available_providers, make_provider

PLACEHOLDER = "Uma nova conversa"
MAX_LEN = 80

_SYSTEM = (
    "Você resume objetivos em títulos curtos. "
    "Responda com UMA única linha (máximo 80 caracteres), sem aspas, sem markdown, sem explicação."
)


def _default_model(pkey: str) -> str | None:
    models = PROVIDER_CATALOG.get(pkey, {}).get("models", [])
    return models[0] if models else None


def _clean_title(text: str) -> str:
    line = (text or "").strip().split("\n")[0].strip()
    line = re.sub(r'^["\'`]+|["\'`]+$', "", line)
    line = re.sub(r"^#+\s*", "", line)
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    if len(line) > MAX_LEN:
        line = line[:77] + "…"
    return line


async def generate_title(goal: str, participants: list[dict] | None = None) -> str:
    """Tenta gerar título com o primeiro agente disponível; senão mantém placeholder."""
    goal = (goal or "").strip()
    if not goal:
        return PLACEHOLDER

    user = f"Objetivo:\n{goal}\n\nTítulo:"
    candidates = participants or [{"pkey": k, "model": _default_model(k)} for k in available_providers()]

    for item in candidates:
        pkey = item.get("pkey")
        model = item.get("model") or _default_model(pkey or "")
        if not pkey or not model:
            continue
        prov = make_provider(pkey, model)
        if not prov:
            continue
        try:
            res = await prov.run(_SYSTEM, user, [], None)
            title = _clean_title(res.text)
            if title and len(title) > 3 and not title.lower().startswith("[erro"):
                return title
        except Exception:
            continue

    return PLACEHOLDER
