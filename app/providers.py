"""Provedores (API ou CLI local) com loop de uso de ferramentas.

Modo API: chama o modelo via SDK. Modo CLI: delega ao binário instalado na
máquina (claude, codex, gemini, deepseek) — autenticação fica no CLI.
"""
import json
import os
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.catalog import estimate
from app.cli_runner import cli_available, run_cli

MAX_TOOL_ITERS = 6


@dataclass
class RunResult:
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0


class Provider:
    def __init__(self, pkey: str, label: str, model: str):
        self.pkey = pkey
        self.label = label
        self.model = model

    async def run(self, system, user_prompt, tools, emit) -> RunResult:
        raise NotImplementedError


async def _step(emit, kind, payload):
    if emit:
        await emit(kind, payload)


class OpenAICompatProvider(Provider):
    """OpenAI, DeepSeek e Gemini (endpoint compatível)."""

    def __init__(self, pkey, label, model, api_key, base_url):
        super().__init__(pkey, label, model)
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def run(self, system, user_prompt, tools, emit) -> RunResult:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
        oai_tools = [
            {"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools
        ]
        by_name = {t.name: t for t in tools}
        res = RunResult()

        for _ in range(MAX_TOOL_ITERS):
            kwargs = {"model": self.model, "messages": messages, "temperature": 0.7}
            if oai_tools:
                kwargs["tools"] = oai_tools
            resp = await self.client.chat.completions.create(**kwargs)

            u = resp.usage
            if u:
                res.input_tokens += getattr(u, "prompt_tokens", 0) or 0
                res.output_tokens += getattr(u, "completion_tokens", 0) or 0

            msg = resp.choices[0].message
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    res.tool_calls += 1
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    await _step(emit, "tool_call", {"tool": name, "args": args})
                    tool = by_name.get(name)
                    try:
                        out = await tool.run(**args) if tool else f"Ferramenta {name} indisponível."
                    except Exception as e:
                        out = f"Erro na ferramenta {name}: {e}"
                    await _step(emit, "tool_result", {"tool": name, "preview": out[:400]})
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id, "content": out[:8000]})
                continue

            res.text = msg.content or ""
            break

        res.cost_usd = estimate(self.model, res.input_tokens, res.output_tokens)
        return res


class AnthropicProvider(Provider):
    def __init__(self, pkey, label, model, api_key):
        super().__init__(pkey, label, model)
        self.client = AsyncAnthropic(api_key=api_key)

    async def run(self, system, user_prompt, tools, emit) -> RunResult:
        messages = [{"role": "user", "content": user_prompt}]
        anth_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        by_name = {t.name: t for t in tools}
        res = RunResult()

        for _ in range(MAX_TOOL_ITERS):
            kwargs = {
                "model": self.model, "max_tokens": 2000,
                "system": system, "messages": messages,
            }
            if anth_tools:
                kwargs["tools"] = anth_tools
            resp = await self.client.messages.create(**kwargs)

            u = resp.usage
            if u:
                res.input_tokens += getattr(u, "input_tokens", 0) or 0
                res.output_tokens += getattr(u, "output_tokens", 0) or 0

            if resp.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": resp.content})
                results = []
                for b in resp.content:
                    if b.type == "tool_use":
                        res.tool_calls += 1
                        await _step(emit, "tool_call", {"tool": b.name, "args": b.input})
                        tool = by_name.get(b.name)
                        try:
                            out = await tool.run(**(b.input or {})) if tool else f"Ferramenta {b.name} indisponível."
                        except Exception as e:
                            out = f"Erro na ferramenta {b.name}: {e}"
                        await _step(emit, "tool_result", {"tool": b.name, "preview": out[:400]})
                        results.append({
                            "type": "tool_result", "tool_use_id": b.id, "content": out[:8000]})
                messages.append({"role": "user", "content": results})
                continue

            res.text = "".join(b.text for b in resp.content if b.type == "text")
            break

        res.cost_usd = estimate(self.model, res.input_tokens, res.output_tokens)
        return res


class CLIProvider(Provider):
    """Executa via CLI local (sem loop de ferramentas)."""

    async def run(self, system, user_prompt, tools, emit) -> RunResult:
        if tools and emit:
            await _step(emit, "tool_call", {"tool": "_info", "args": {"msg": "Modo CLI: ferramentas desativadas"}})
        text, err = await run_cli(self.pkey, system, user_prompt, self.model)
        res = RunResult()
        if err:
            res.text = f"[Erro CLI] {err}"
            if emit:
                await _step(emit, "tool_result", {"tool": "_cli", "preview": err[:400]})
            return res
        res.text = text
        # estimativa grosseira — CLIs não expõem contagem de tokens
        res.input_tokens = len(system + user_prompt) // 4
        res.output_tokens = len(text) // 4
        res.cost_usd = estimate(self.model, res.input_tokens, res.output_tokens)
        return res


# ---- fábrica ----
def make_provider(pkey: str, model: str) -> Provider | None:
    if cli_available(pkey):
        labels = {"claude": "Claude", "gpt": "ChatGPT", "gemini": "Gemini", "deepseek": "DeepSeek"}
        return CLIProvider(pkey, labels.get(pkey, pkey), model)
    if pkey == "claude" and os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider("claude", "Claude", model, os.environ["ANTHROPIC_API_KEY"])
    if pkey == "gpt" and os.getenv("OPENAI_API_KEY"):
        return OpenAICompatProvider(
            "gpt", "ChatGPT", model, os.environ["OPENAI_API_KEY"], "https://api.openai.com/v1")
    if pkey == "gemini" and os.getenv("GEMINI_API_KEY"):
        return OpenAICompatProvider(
            "gemini", "Gemini", model, os.environ["GEMINI_API_KEY"],
            "https://generativelanguage.googleapis.com/v1beta/openai/")
    if pkey == "deepseek" and os.getenv("DEEPSEEK_API_KEY"):
        return OpenAICompatProvider(
            "deepseek", "DeepSeek", model, os.environ["DEEPSEEK_API_KEY"], "https://api.deepseek.com")
    return None


def available_providers() -> list[str]:
    out = []
    for pkey, env_key in [
        ("claude", "ANTHROPIC_API_KEY"),
        ("gpt", "OPENAI_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("deepseek", "DEEPSEEK_API_KEY"),
    ]:
        if cli_available(pkey) or os.getenv(env_key):
            out.append(pkey)
    return out
