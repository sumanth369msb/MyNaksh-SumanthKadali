from __future__ import annotations

import hashlib
import json
import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._store: dict[str, tuple[float, Any]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < self._now():
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self.max_size:
            oldest = min(self._store.items(), key=lambda item: item[1][0])[0]
            del self._store[oldest]
        self._store[key] = (self._now() + self.ttl, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @staticmethod
    def make_key(*parts: Any) -> str:
        raw = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()
