from __future__ import annotations

import asyncio
import json

import httpx

from app.core.config import settings
from app.core.exceptions import LLMError, RateLimitError
from app.llm.prompts import build_fact_extraction_messages, parse_extracted_facts_json


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    async def generate(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 512) -> str:
        if not self.api_key:
            raise LLMError("OpenAI API key not configured")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers
                    )
                if response.status_code == 429:
                    raise RateLimitError("Rate limited by LLM provider")
                if response.status_code >= 500:
                    raise LLMError(f"LLM server error {response.status_code}")
                if response.status_code >= 400:
                    raise LLMError(f"LLM request failed {response.status_code}: {response.text}")
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (RateLimitError, LLMError) as exc:
                last_exc = exc
                if isinstance(exc, RateLimitError) or "server error" in str(exc):
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except Exception as exc:
                last_exc = LLMError(str(exc))
                await asyncio.sleep(2 ** attempt)
        raise last_exc or LLMError("LLM request failed")

    async def extract_facts(self, text: str) -> list[dict]:
        messages = build_fact_extraction_messages(text)
        raw = await self.generate(messages, temperature=0.0, max_tokens=512)
        return parse_extracted_facts_json(raw)

