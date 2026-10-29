from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, runtime_checkable

from app.brain.models import MemoryFact
from app.core.exceptions import GraphError
from app.profile.models import UserProfile


@runtime_checkable
class GraphStore(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def upsert_user(self, profile: UserProfile) -> None: ...
    async def get_user(self, user_id: str) -> Optional[UserProfile]: ...
    async def upsert_fact(self, fact: MemoryFact) -> MemoryFact: ...
    async def get_facts(
        self, user_id: str, types: Optional[list[str]] = None, limit: int = 100
    ) -> list[MemoryFact]: ...
    async def search_facts(
        self, user_id: str, query: str, types: Optional[list[str]] = None, limit: int = 100
    ) -> list[MemoryFact]: ...
    async def delete_fact(self, user_id: str, fact_id: str) -> bool: ...
    async def clear_user(self, user_id: str) -> None: ...


class InMemoryGraphStore:
    def __init__(self):
        self._users: dict[str, UserProfile] = {}
        self._facts: dict[str, dict[str, MemoryFact]] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def upsert_user(self, profile: UserProfile) -> None:
        async with self._lock:
            existing = self._users.get(profile.user_id)
            if existing is not None:
                data = existing.model_dump()
                incoming = profile.model_dump(exclude_none=True)
                data.update(incoming)
                self._users[profile.user_id] = UserProfile(**data)
            else:
                self._users[profile.user_id] = profile

    async def get_user(self, user_id: str) -> Optional[UserProfile]:
        return self._users.get(user_id)

    async def upsert_fact(self, fact: MemoryFact) -> MemoryFact:
        async with self._lock:
            user_facts = self._facts.setdefault(fact.user_id, {})
            key = f"{fact.type}:{fact.key}"
            existing = user_facts.get(key)
            if existing is not None:
                existing.value = fact.value
                existing.relation = fact.relation
                existing.confidence = max(existing.confidence, fact.confidence)
                existing.metadata.update(fact.metadata)
                existing.updated_at = datetime.now(timezone.utc)
                existing.source = fact.source or existing.source
                user_facts[key] = existing
                return existing
            if not fact.id:
                fact.id = f"{fact.user_id}:{fact.type}:{fact.key}"
            now = datetime.now(timezone.utc)
            fact.created_at = fact.created_at or now
            fact.updated_at = now
            user_facts[key] = fact
            return fact

    async def get_facts(
        self, user_id: str, types: Optional[list[str]] = None, limit: int = 100
    ) -> list[MemoryFact]:
        user_facts = self._facts.get(user_id, {})
        facts = list(user_facts.values())
        if types:
            facts = [f for f in facts if f.type in types]
        facts.sort(key=lambda f: f.updated_at, reverse=True)
        return facts[:limit]

    async def search_facts(
        self, user_id: str, query: str, types: Optional[list[str]] = None, limit: int = 100
    ) -> list[MemoryFact]:
        facts = await self.get_facts(user_id, types=types, limit=1000)
        q = query.lower()
        tokens = set(q.split())
        scored = []
        for fact in facts:
            text = f"{fact.type} {fact.key} {fact.value} {fact.metadata}".lower()
            score = sum(1 for t in tokens if t in text)
            if q and q in text:
                score += 2
            scored.append((score, fact))
        scored.sort(key=lambda x: (x[0], x[1].updated_at.timestamp()), reverse=True)
        return [f for score, f in scored if score > 0][:limit] or facts[:limit]

    async def delete_fact(self, user_id: str, fact_id: str) -> bool:
        async with self._lock:
            user_facts = self._facts.get(user_id, {})
            for key, fact in list(user_facts.items()):
                if fact.id == fact_id:
                    del user_facts[key]
                    return True
            return False

    async def clear_user(self, user_id: str) -> None:
        async with self._lock:
            self._users.pop(user_id, None)
            self._facts.pop(user_id, None)
