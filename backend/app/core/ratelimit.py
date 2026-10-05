"""Fixed-window rate limiter: Redis when reachable, in-process fallback otherwise."""
from __future__ import annotations

import logging
import threading
import time

from app.config.settings import get_settings

log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self._mem: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._redis_checked = False

    def _client(self):
        if not self._redis_checked:
            self._redis_checked = True
            try:
                import redis

                c = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.3, socket_timeout=0.3)
                c.ping()
                self._redis = c
            except Exception:
                log.info("rate limiter: Redis unavailable, using in-process counters")
        return self._redis

    def hit(self, key: str, limit: int, window_sec: int = 60) -> tuple[bool, int]:
        """Returns (allowed, remaining)."""
        bucket = int(time.time() // window_sec)
        rkey = f"rl:{key}:{bucket}"
        c = self._client()
        if c is not None:
            try:
                n = c.incr(rkey)
                if n == 1:
                    c.expire(rkey, window_sec + 1)
                return n <= limit, max(limit - n, 0)
            except Exception:
                pass
        with self._lock:
            count, _ = self._mem.get(rkey, (0, 0.0))
            count += 1
            self._mem[rkey] = (count, time.time())
            if len(self._mem) > 10_000:
                cutoff = time.time() - 2 * window_sec
                self._mem = {k: v for k, v in self._mem.items() if v[1] > cutoff}
        return count <= limit, max(limit - count, 0)

    def reset(self) -> None:
        with self._lock:
            self._mem.clear()


limiter = RateLimiter()
