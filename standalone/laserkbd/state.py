"""Shared key state between the MIDI thread (writer) and the DMX thread (reader).

Kept deliberately small and lock-guarded. Velocity is stored but currently unused
by the renderer (Milestone 1 treats beams as on/off); it's here so velocity-driven
brightness is a cheap addition later.
"""

from __future__ import annotations

import threading


class KeyState:
    def __init__(self, key_count: int):
        self._lock = threading.Lock()
        self._velocity = [0] * key_count  # 0 = released, 1-127 = held velocity

    def press(self, index: int, velocity: int) -> None:
        with self._lock:
            if 0 <= index < len(self._velocity):
                self._velocity[index] = max(1, min(127, velocity))

    def release(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._velocity):
                self._velocity[index] = 0

    def snapshot(self) -> list[int]:
        """Return a copy of per-key velocities for the renderer to read."""
        with self._lock:
            return list(self._velocity)

    def held_count(self) -> int:
        with self._lock:
            return sum(1 for v in self._velocity if v > 0)
