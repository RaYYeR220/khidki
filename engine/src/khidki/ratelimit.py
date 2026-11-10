"""Small in-process token-bucket rate limiter (one service instance)."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, rate_per_min: float, burst: int, max_keys: int = 50_000):
        self.rate = rate_per_min / 60.0
        self.burst = burst
        self.max_keys = max_keys
        self._b: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._b) > self.max_keys:
                self._b.clear()
            tokens, last = self._b.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < 1:
                self._b[key] = (tokens, now)
                return False
            self._b[key] = (tokens - 1, now)
            return True
