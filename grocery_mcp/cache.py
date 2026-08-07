"""Small in-process TTL cache for storefront catalog responses."""
from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = max(ttl_seconds, 0)
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if self._ttl <= 0:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if self._ttl <= 0:
            return
        self._entries[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._entries.clear()
