"""Small in-process token-bucket rate limiter (one service instance)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict


class RateLimiter:
    def __init__(self, rate_per_min: float, burst: int, max_keys: int = 50_000):
        self.rate = rate_per_min / 60.0
        self.burst = burst
        self.max_keys = max_keys
        self._b: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            while len(self._b) >= self.max_keys and key not in self._b:
                self._b.popitem(last=False)  # evict the least recently seen key
            tokens, last = self._b.get(key, (float(self.burst), now))
            self._b[key] = (tokens, last)
            self._b.move_to_end(key)
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < 1:
                self._b[key] = (tokens, now)
                return False
            self._b[key] = (tokens - 1, now)
            return True
