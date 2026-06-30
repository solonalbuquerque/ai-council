"""Generate a short title via any available agent."""
import re

from app.catalog import PROVIDER_CATALOG
from app.providers import available_providers, make_provider

PLACEHOLDER = "A new conversation"
MAX_LEN = 80

_SYSTEM = (
    "You summarize goals into short titles. "
    "Reply with ONE single line (max 80 characters), no quotes, no markdown, no explanation."
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
    """Try to generate a title with the first available agent; otherwise keep placeholder."""
    goal = (goal or "").strip()
    if not goal:
        return PLACEHOLDER

    user = f"Goal:\n{goal}\n\nTitle:"
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
            if title and len(title) > 3 and not title.lower().startswith(("[error", "[cli error")):
                return title
        except Exception:
            continue

    return PLACEHOLDER
