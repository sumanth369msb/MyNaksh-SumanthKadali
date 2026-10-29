import re
from datetime import datetime, timezone
from typing import Optional

from app.brain.models import MemoryFact

STOPWORDS = {
    "a", "an", "the", "in", "on", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "but", "if", "or", "because", "as", "until", "while", "of",
    "and", "so", "than", "too", "very", "can", "will", "just", "should",
    "now", "i", "my", "me", "we", "our", "you", "your", "he", "she",
    "it", "they", "them", "what", "which", "who", "whom", "this", "that",
    "these", "those", "am",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower())) - STOPWORDS


TYPE_KEYWORDS = {
    "goal": {"career", "job", "work", "goal", "interview", "promotion"},
    "preference": {"prefer", "language", "hindi", "english"},
    "interest": {"interested", "entrepreneurship", "startup"},
    "profile": {"name", "born", "birth", "zodiac", "age"},
    "memory": set(),
}


def _fact_ts(fact: MemoryFact) -> float:
    dt = fact.updated_at
    return dt.timestamp() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).timestamp()


class ContextSelector:
    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def select(
        self,
        message: str,
        profile: Optional[object],
        facts: list[MemoryFact],
        recent_turns: list,
    ) -> tuple[list[MemoryFact], list[str]]:
        query_tokens = _tokens(message)
        scored = []
        now_ts = datetime.now(timezone.utc).timestamp()

        for fact in facts:
            meta_str = " ".join(f"{k} {v}" for k, v in fact.metadata.items()) if fact.metadata else ""
            fact_tokens = _tokens(f"{fact.type} {fact.key} {fact.value} {meta_str}")
            overlap = len(query_tokens & fact_tokens)
            score = float(overlap)
            if fact.type in TYPE_KEYWORDS and (TYPE_KEYWORDS[fact.type] & query_tokens):
                score += 2.0
            if any(k in message.lower() for k in ("career", "job")) and fact.type == "goal":
                score += 3.0
            if any(k in message.lower() for k in ("language", "prefer")) and fact.type == "preference":
                score += 3.0

            # Only apply confidence weighting and recency boost if baseline relevance score is > 0
            if score > 0:
                score += fact.confidence * 0.5
                fact_ts = _fact_ts(fact)
                age_seconds = max(0.0, now_ts - fact_ts)
                recency_boost = 0.5 / (1.0 + age_seconds / 86400.0)
                score += recency_boost

            scored.append((score, fact))

        scored.sort(key=lambda item: (item[0], _fact_ts(item[1])), reverse=True)
        positive_facts = [fact for score, fact in scored if score > 0]
        has_positive_relevance = len(positive_facts) > 0

        if has_positive_relevance:
            selected = positive_facts[: self.top_k]
        elif facts:
            # Fallback to most recent facts without marking positive relevance
            selected = sorted(facts, key=_fact_ts, reverse=True)[: min(self.top_k, len(facts))]
        else:
            selected = []

        context_used = []
        if profile is not None:
            context_used.append("user_profile")
        if has_positive_relevance:
            context_used.append("shared_brain")
        if len(recent_turns) > 1:
            context_used.append("conversation_history")
        if any(k in message.lower() for k in ("career", "job")) and any(f.type == "goal" for f in selected):
            context_used.append("career_goal")
        if any(k in message.lower() for k in ("language", "prefer")) and any(f.type == "preference" for f in selected):
            context_used.append("language_preference")

        return selected, context_used
