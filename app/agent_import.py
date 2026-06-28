"""Importação de agentes/personas a partir de URLs (GitHub, web)."""
import re
from urllib.parse import urlparse, unquote

import httpx
from bs4 import BeautifulSoup

_UA = "Mozilla/4.0 (compatible; AICouncil/1.0)"
_MAX_CHARS = 8000


def _github_blob_to_raw(url: str) -> str:
    """Converte github.com/.../blob/... em raw.githubusercontent.com."""
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+?)(?:\?.*)?$",
        url,
        re.I,
    )
    if m:
        owner, repo, branch, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    return url


def _guess_name(url: str, text: str) -> str:
    path = unquote(urlparse(url).path)
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    if filename.lower().endswith((".md", ".txt", ".markdown")):
        filename = filename.rsplit(".", 1)[0]
    if filename and filename not in ("blob", "raw", "README"):
        name = filename.replace("-", " ").replace("_", " ").strip()
        if name:
            return name[:120]

    for line in text.splitlines()[:20]:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:120]
        m = re.match(r"^name\s*[:=]\s*(.+)$", line, re.I)
        if m:
            return m.group(1).strip()[:120]
    return "Agente importado"


def _extract_text(content: str, content_type: str) -> str:
    ct = (content_type or "").lower()
    if "html" in ct or content.lstrip().startswith("<"):
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        article = soup.find("article") or soup.find("main") or soup.body
        text = " ".join((article or soup).get_text("\n").split())
    else:
        text = content.strip()
    return text[:_MAX_CHARS]


async def import_agent_from_url(url: str) -> dict:
    """Baixa conteúdo da URL e retorna name + description para revisão."""
    url = (url or "").strip()
    if not url:
        raise ValueError("URL vazia.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL deve usar http ou https.")

    fetch_url = _github_blob_to_raw(url)
    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": _UA}, follow_redirects=True
    ) as client:
        resp = await client.get(fetch_url)
        resp.raise_for_status()

    text = _extract_text(resp.text, resp.headers.get("content-type", ""))
    if not text:
        raise ValueError("Não foi possível extrair texto da URL.")

    return {
        "name": _guess_name(fetch_url, text),
        "description": text,
        "source_url": url,
    }
