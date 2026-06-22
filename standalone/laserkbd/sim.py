"""Keyboard simulator for --dry-run.

Drives KeyState with a single "beam" that sweeps across the keys, so the web UI
shows changing activity (held count, rendered channels) without a real keyboard
attached. Deliberately tiny — it only writes to KeyState, exactly like the real MIDI
thread's callback does, so the rest of the pipeline is exercised unchanged.
"""

from __future__ import annotations

import logging
import threading

from .config import ConfigHolder
from .state import KeyState

log = logging.getLogger(__name__)


class SimulatedMidiThread(threading.Thread):
    def __init__(self, state: KeyState, config: ConfigHolder,
                 stop_event: threading.Event, step: float = 0.4):
        super().__init__(name="sim", daemon=True)
        self._state = state
        self._config = config
        self._stop = stop_event
        self._step = step

    def run(self) -> None:
        log.info("simulated keyboard started (dry-run): sweeping a single beam")
        index = 0
        previous: int | None = None
        while not self._stop.is_set():
            key_count = self._config.get().key_count
            if previous is not None:
                self._state.release(previous)
            self._state.press(index, velocity=100)
            previous = index
            index = (index + 1) % max(1, key_count)
            self._stop.wait(self._step)
        if previous is not None:
            self._state.release(previous)
        log.info("simulated keyboard stopped")
