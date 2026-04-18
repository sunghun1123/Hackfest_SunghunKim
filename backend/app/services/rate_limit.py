"""Per-device sliding-window rate limiter.

Gemini calls cost money and have quota ceilings; the photo-parse endpoint is
easy to spam with a fast-click-happy user. We keep a short history of call
timestamps per device and reject once the window is full. Single-worker
uvicorn is the MVP target so an in-process dict is safe; swap for Redis when
we horizontally scale.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str) -> bool:
        """True if under the limit (and records the call); False if over."""
        now = time.monotonic()
        bucket = self._calls[key]
        cutoff = now - self._window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._calls.clear()


# Photo parsing: 5 requests / minute / device (API.md §/parse-menu-image).
photo_parse_limiter = RateLimiter(max_calls=5, window_seconds=60.0)
