"""In-memory ring buffer of recent log records, so the web UI can show logs without
a file tail. Attached as a logging.Handler alongside the console handler.
"""

from __future__ import annotations

import collections
import logging
import threading


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 500):
        super().__init__()
        self._lock = threading.Lock()
        self._records: collections.deque[str] = collections.deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:  # pragma: no cover - never let logging crash a thread
            return
        with self._lock:
            self._records.append(line)

    def lines(self) -> list[str]:
        with self._lock:
            return list(self._records)
