"""Rate limiting with an in-memory default and an optional Redis backend seam.

Default is a per-key sliding-window counter held in process memory (fine for a
single HF Space replica). If REDIS_URL is set AND the `redis` package imports,
a Redis-backed limiter is used so multiple replicas share one budget. The import
is guarded: a missing package or bad URL degrades gracefully to in-memory.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Protocol


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool:
        """Return True if `key` is within budget (and consume one slot), else False."""
        ...


class InMemoryRateLimiter:
    """Sliding-window limiter: at most `limit` hits per `window_s` seconds per key."""

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_s
        q = self._hits[key]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


class RedisRateLimiter:
    """Redis-backed fixed-window counter (INCR + EXPIRE). Shared across replicas."""

    def __init__(self, client, limit: int, window_s: int) -> None:
        self._client = client
        self.limit = limit
        self.window_s = window_s

    def allow(self, key: str) -> bool:
        bucket = int(time.time() // self.window_s)
        rkey = f"rl:{key}:{bucket}"
        try:
            count = self._client.incr(rkey)
            if count == 1:
                self._client.expire(rkey, self.window_s)
            return count <= self.limit
        except Exception:
            # Never let a Redis hiccup take down the API: fail open at the edge.
            return True


def get_rate_limiter(limit: int, window_s: int) -> RateLimiter:
    """Return a Redis limiter if REDIS_URL + redis package are available, else in-memory."""
    url = os.getenv("REDIS_URL")
    if url:
        try:
            import redis  # guarded import: optional dependency

            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            return RedisRateLimiter(client, limit=limit, window_s=window_s)
        except Exception:
            pass  # missing package / unreachable server -> degrade to in-memory
    return InMemoryRateLimiter(limit=limit, window_s=window_s)
