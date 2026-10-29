from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Optional

from app.core.config import settings


class ConversationTurn:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
        self.timestamp = time.time()


class ShortTermMemory:
    def __init__(self, max_messages: int | None = None, ttl_seconds: int | None = None):
        self.max_messages = max_messages or settings.short_term_max_messages
        self.ttl_seconds = ttl_seconds or settings.short_term_ttl_seconds
        self._sessions: dict[str, deque[ConversationTurn]] = defaultdict(lambda: deque(maxlen=self.max_messages))
        self._last_access: dict[str, float] = {}
        self._lock: asyncio.Lock | None = None

    async def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def add(self, session_id: str, role: str, content: str) -> None:
        async with await self._get_lock():
            self._evict_expired()
            self._sessions[session_id].append(ConversationTurn(role, content))
            self._last_access[session_id] = time.time()

    async def get(self, session_id: str, limit: Optional[int] = None) -> list[ConversationTurn]:
        async with await self._get_lock():
            self._evict_expired()
            turns = list(self._sessions.get(session_id, ()))
            if limit is not None:
                turns = turns[-limit:]
            self._last_access[session_id] = time.time()
            return turns

    async def clear(self, session_id: str) -> None:
        async with await self._get_lock():
            self._sessions.pop(session_id, None)
            self._last_access.pop(session_id, None)

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, ts in self._last_access.items() if now - ts > self.ttl_seconds]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._last_access.pop(sid, None)
