"""In-memory ring buffer of recent log records, so the web UI can show logs without
a file tail. Attached as a logging.Handler alongside the console handler.

Besides the snapshot used to render the page, the buffer supports a blocking
`wait_since()` so the web thread can stream new lines over a WebSocket (R37) without
polling: each emit bumps a total counter and wakes any waiter.
"""

from __future__ import annotations

import collections
import logging
import threading


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 500):
        super().__init__()
        self._cond = threading.Condition()
        self._records: collections.deque[str] = collections.deque(maxlen=capacity)
        self._total = 0   # lines ever emitted (monotonic; survives ring eviction)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:  # pragma: no cover - never let logging crash a thread
            return
        with self._cond:
            self._records.append(line)
            self._total += 1
            self._cond.notify_all()

    def lines(self) -> list[str]:
        with self._cond:
            return list(self._records)

    def total(self) -> int:
        with self._cond:
            return self._total

    def wait_since(self, last_total: int, timeout: float) -> tuple[int, list[str]]:
        """Block until more lines exist than `last_total` (or `timeout`), then return
        the new total and the lines added since. If the caller fell further behind than
        the ring holds, only the retained tail is returned (older lines are lost)."""
        with self._cond:
            if self._total == last_total:
                self._cond.wait(timeout)
            new_count = self._total - last_total
            if new_count <= 0:
                return self._total, []
            new_count = min(new_count, len(self._records))
            new = list(self._records)[-new_count:]
            return self._total, new
