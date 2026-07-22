"""Shared key state between the MIDI thread (writer) and the DMX thread (reader).

Kept deliberately small and lock-guarded. For each key we store its strike velocity
(1-127) and the monotonic timestamp it was last struck, plus a separate `held` flag
that is True only while the key is physically pressed. The renderer uses velocity +
onset to drive the simulated-piano decay (R33): velocity picks the decay duration, and
now - onset gives the elapsed time along the decay curve.

Note-off does *not* zero the velocity: it only clears `held`, so the beam keeps
following its decay curve to off exactly as a held key does (release no longer cuts the
beam). The `held` flag is what reflects the physical keyboard — it drives chord
detection, held-count and the input-row visualisation — while velocity/onset live on to
finish the fade.

The timestamp uses time.monotonic() (not wall-clock) so elapsed time is immune to
clock jumps (NTP, the Pi resyncing on boot); the renderer must read the same clock.
"""

from __future__ import annotations

import threading
import time


class KeyState:
    def __init__(self, key_count: int):
        self._lock = threading.Lock()
        self._velocity = [0] * key_count    # last strike velocity; kept after release
        self._onset = [0.0] * key_count     # time.monotonic() of the last strike
        self._held = [False] * key_count    # True only while physically pressed

    def press(self, index: int, velocity: int) -> None:
        with self._lock:
            if 0 <= index < len(self._velocity):
                self._velocity[index] = max(1, min(127, velocity))
                # Reset the onset on every strike so re-hitting a held key restarts
                # its decay (a re-struck string), matching the piano metaphor.
                self._onset[index] = time.monotonic()
                self._held[index] = True

    def release(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._velocity):
                # Only clear the held flag. Deliberately keep velocity/onset so the beam
                # keeps decaying past note-off — the fade plays out like a held key (R33).
                self._held[index] = False

    def release_all(self) -> None:
        """Clear every held key. Used on MIDI disconnect: the held velocities can't be
        cleared by note-off once the keyboard is gone, so drop the held flags. The beams
        then fade out on their decay curve rather than staying stuck on."""
        with self._lock:
            for i in range(len(self._held)):
                self._held[i] = False

    def snapshot(self) -> list[tuple[int, float, bool]]:
        """Return a copy of per-key (velocity, onset, held) for the renderer to read.

        The three are copied together under one lock so the renderer never sees a
        velocity from one strike paired with an onset (or held flag) from another."""
        with self._lock:
            return list(zip(self._velocity, self._onset, self._held))

    def held_count(self) -> int:
        with self._lock:
            return sum(1 for h in self._held if h)
