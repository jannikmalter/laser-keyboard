"""Shared key state between the MIDI thread (writer) and the DMX thread (reader).

Kept deliberately small and lock-guarded. For each key we store its held velocity
(0 = released, 1-127 = held) and the monotonic timestamp it was last struck. The
renderer uses both to drive the simulated-piano decay (R33): velocity picks the
decay duration, and now - onset gives the elapsed time along the decay curve.

The timestamp uses time.monotonic() (not wall-clock) so elapsed time is immune to
clock jumps (NTP, the Pi resyncing on boot); the renderer must read the same clock.
"""

from __future__ import annotations

import threading
import time


class KeyState:
    def __init__(self, key_count: int):
        self._lock = threading.Lock()
        self._velocity = [0] * key_count    # 0 = released, 1-127 = held velocity
        self._onset = [0.0] * key_count     # time.monotonic() of the last strike

    def press(self, index: int, velocity: int) -> None:
        with self._lock:
            if 0 <= index < len(self._velocity):
                self._velocity[index] = max(1, min(127, velocity))
                # Reset the onset on every strike so re-hitting a held key restarts
                # its decay (a re-struck string), matching the piano metaphor.
                self._onset[index] = time.monotonic()

    def release(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._velocity):
                self._velocity[index] = 0

    def release_all(self) -> None:
        """Clear every held key. Used on MIDI disconnect so no beam stays stuck on
        (the held velocities can't be cleared by note-off once the keyboard is gone)."""
        with self._lock:
            for i in range(len(self._velocity)):
                self._velocity[i] = 0

    def snapshot(self) -> list[tuple[int, float]]:
        """Return a copy of per-key (velocity, onset) for the renderer to read.

        Velocity and onset are copied together under one lock so the renderer never
        sees a velocity from one strike paired with an onset from another."""
        with self._lock:
            return list(zip(self._velocity, self._onset))

    def held_count(self) -> int:
        with self._lock:
            return sum(1 for v in self._velocity if v > 0)
