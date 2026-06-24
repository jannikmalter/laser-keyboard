"""Live visualisation bus (R37).

The DMX thread publishes a tiny snapshot every tick — 32 key velocities (the input)
plus the 40 rendered laser-beam brightnesses (the output, decay + effects included) —
and the web thread's WebSocket handler streams it to the browser. This is a separate,
far smaller stream than ArtNet: 2 + 32 + 40 = 74 bytes/frame, so even at the full tick
rate (~100 Hz ≈ 7 kB/s) it is a fraction of the DMX payload.

`LiveBus` keeps only the latest frame and a sequence counter; a WebSocket handler waits
on the condition and sends when the frame changes (publish() is a no-op when the frame
is identical, so an idle keyboard generates no traffic).
"""

from __future__ import annotations

import threading
from typing import Iterable


def encode_frame(keys: Iterable[int], beams: Iterable[int]) -> bytes:
    """Pack key velocities + beam brightnesses into the wire frame.

    Layout: [K][key_0..key_{K-1}][B][beam_0..beam_{B-1}], every value a single byte
    (0-255). Lengths are sent inline so the client stays correct if key_count changes.
    """
    keys = [max(0, min(255, int(v))) for v in keys]
    beams = [max(0, min(255, int(b))) for b in beams]
    out = bytearray()
    out.append(len(keys) & 0xFF)
    out.extend(keys)
    out.append(len(beams) & 0xFF)
    out.extend(beams)
    return bytes(out)


class LiveBus:
    """Latest-frame pub/sub for the live visualisation. One writer (the DMX thread),
    any number of readers (WebSocket handlers). Readers block until the frame changes."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame = b""
        self._seq = 0

    def publish(self, frame: bytes) -> None:
        """Store a new frame and wake waiters. Identical frames are dropped so a static
        scene (no keys held, no effect) produces no traffic."""
        with self._cond:
            if frame == self._frame:
                return
            self._frame = frame
            self._seq += 1
            self._cond.notify_all()

    def snapshot(self) -> tuple[int, bytes]:
        with self._cond:
            return self._seq, self._frame

    def wait_next(self, last_seq: int, timeout: float) -> tuple[int, bytes]:
        """Block until the frame changes past `last_seq` (or `timeout` elapses), then
        return the current (seq, frame). On timeout the seq is unchanged, which the
        caller can resend as a keepalive to notice a dropped connection."""
        with self._cond:
            if self._seq == last_seq:
                self._cond.wait(timeout)
            return self._seq, self._frame
