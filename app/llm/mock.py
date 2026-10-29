import json
import re


class MockLLMProvider:
    async def generate(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 512) -> str:
        user_msg = ""
        context = ""
        for m in messages:
            if m.get("role") == "user":
                user_msg = m.get("content", "")
            if m.get("role") == "system":
                context = m.get("content", "")
        if "career" in user_msg.lower():
            if "career" in context.lower() or "goal" in context.lower():
                return "Based on your career goals, focus on skill-building, networking, and targeted applications aligned with your transition timeline."
            return "I don't have your career details yet, but I can help once you share your goals."
        if "remember" in user_msg.lower():
            return "I remember the long-term details you shared earlier and will use them to personalize advice."
        if "why" in user_msg.lower():
            return "Because your recent context and stated goals point toward a focused, step-by-step transition."
        return f"I understand: {user_msg}. How can I help further?"

    async def extract_facts(self, text: str) -> list[dict]:
        return []
