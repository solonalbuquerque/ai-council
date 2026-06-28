"""Abstração de ferramenta usada por todos os provedores."""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema (object)
    func: Callable[..., Awaitable[str]]

    async def run(self, **kwargs: Any) -> str:
        return await self.func(**kwargs)
