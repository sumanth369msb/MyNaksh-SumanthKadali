from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    async def generate(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 512) -> str: ...
    async def extract_facts(self, text: str) -> list[dict]: ...
