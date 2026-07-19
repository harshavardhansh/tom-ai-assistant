"""Key-value cache used for conversation memory and (optionally) hot answers.
Redis in production; an in-process dict in dev/test."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from app.config import Settings, get_settings


class Cache(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[str]: ...

    @abstractmethod
    def set(self, key: str, value: str, ttl_s: Optional[int] = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def incr(self, key: str, ttl_s: int) -> int:
        """Increment an integer counter, setting `ttl_s` on first increment.
        Used by the rate limiter (OWASP LLM10 Unbounded Consumption)."""


class MemoryCache(Cache):
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, Optional[float]]] = {}

    def get(self, key: str) -> Optional[str]:
        item = self._store.get(key)
        if not item:
            return None
        value, expiry = item
        if expiry and time.time() > expiry:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl_s: Optional[int] = None) -> None:
        expiry = time.time() + ttl_s if ttl_s else None
        self._store[key] = (value, expiry)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def incr(self, key: str, ttl_s: int) -> int:
        current = self.get(key)
        value = (int(current) if current else 0) + 1
        # Preserve the window expiry set on first increment.
        expiry = self._store[key][1] if current else time.time() + ttl_s
        self._store[key] = (str(value), expiry)
        return value


class RedisCache(Cache):  # pragma: no cover - needs Redis
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        return self._r.get(key)

    def set(self, key: str, value: str, ttl_s: Optional[int] = None) -> None:
        self._r.set(key, value, ex=ttl_s)

    def delete(self, key: str) -> None:
        self._r.delete(key)

    def incr(self, key: str, ttl_s: int) -> int:
        # Atomic in Redis: INCR + set the window expiry on first increment.
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl_s, nx=True)
        value, _ = pipe.execute()
        return int(value)


def get_cache(settings: Optional[Settings] = None) -> Cache:
    settings = settings or get_settings()
    if settings.cache_backend == "redis" and settings.redis_url:
        return RedisCache(settings.redis_url)
    return MemoryCache()
