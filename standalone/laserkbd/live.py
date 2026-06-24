"""Live visualisation bus (R37).

The DMX thread publishes a tiny snapshot each tick — 32 key velocities (the input) plus
the 40 rendered laser-beam brightnesses (the output, decay + effects included) — and the
web thread streams it to the browser over a WebSocket. This is a separate, far smaller
stream than ArtNet: 2 + 32 + 40 = 74 bytes/frame, pushed at the full tick rate.

`LiveBus` keeps only the latest frame and a sequence counter; a WebSocket handler waits
on the condition and is woken every time the frame changes (publish() drops identical
frames, so an idle keyboard generates no traffic). `active()` reports whether a browser
is currently watching, so the DMX thread can skip the snapshot work entirely when no one
is connected — the normal case during a show — keeping the render loop lean.
"""

from __future__ import annotations

import threading
import time
from typing import Iterable

# How long after a reader last waited we still consider a browser "connected" and keep
# publishing. A little slack so a momentary stall doesn't drop the feed.
_CONSUMER_TTL_S = 2.0


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
    """Latest-frame pub/sub for the live visualisation. One writer (the DMX thread), any
    number of readers (WebSocket handlers). Readers block until the frame changes."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame = b""
        self._seq = 0
        self._last_wait = 0.0   # monotonic time a reader last waited (drives active())

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
        """Current (seq, frame); also marks a consumer present (see active())."""
        with self._cond:
            self._last_wait = time.monotonic()
            return self._seq, self._frame

    def wait_next(self, last_seq: int, timeout: float) -> tuple[int, bytes]:
        """Block until the frame changes past `last_seq` (or `timeout` elapses), then
        return the current (seq, frame). On timeout the seq is unchanged, which the
        caller can resend as a keepalive to notice a dropped connection."""
        with self._cond:
            self._last_wait = time.monotonic()
            if self._seq == last_seq:
                self._cond.wait(timeout)
                self._last_wait = time.monotonic()
            return self._seq, self._frame

    def active(self) -> bool:
        """True if a reader has waited recently — i.e. a browser is watching. The DMX
        thread skips building/publishing frames when this is False, so the live feed adds
        no work to the render loop unless someone is actually looking at the UI."""
        with self._cond:
            return (time.monotonic() - self._last_wait) < _CONSUMER_TTL_S
