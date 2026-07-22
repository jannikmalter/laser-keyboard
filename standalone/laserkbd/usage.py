"""Keypress usage logging (R34) + data source for the web graph (R36).

Counts note-on events (keypresses) and, once a wall-clock minute, appends the count for
the minute that just ended to a plain-text log file — one line per minute:

    2026-07-22 14:33\t42

so a night of play can be analysed afterwards. The same per-minute series is kept in
memory (loaded from the file on startup) and served to the web UI, which draws it as an
inline-SVG graph (no external chart library, so it works with no internet access).

Threading: `record()` is called from the MIDI and web threads on every keypress and only
bumps an integer under a short lock. A single `run()` loop (its own thread) wakes on each
wall-clock minute boundary, snapshots+resets the counter and appends one line. The count
comes through `KeyState.on_press`, so both the physical keyboard and the virtual web
keyboard (R42) are counted at the one choke point.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# In-memory retention cap: one point per minute, so 14 days is ~20k points — trivial to
# hold and well past the ~3-day runs we expect. The on-disk file is append-only and not
# truncated (a 3-day night is ~4320 lines); if it ever grows past this we keep the tail.
_MAX_POINTS = 14 * 24 * 60

_TS_FMT = "%Y-%m-%d %H:%M"


class UsageLog:
    """Per-minute keypress counter with a text-file backing store and an in-memory series."""

    def __init__(self, path: Path, max_points: int = _MAX_POINTS):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._count = 0   # presses in the current, not-yet-flushed minute
        # (minute_epoch_seconds, count), oldest first.
        self._history: collections.deque[tuple[int, int]] = collections.deque(maxlen=max_points)
        self._load()

    # -- counting -------------------------------------------------------------
    def record(self) -> None:
        """Count one keypress (note-on). Called from the MIDI + web threads via
        KeyState.on_press; kept to a single locked increment so it stays cheap."""
        with self._lock:
            self._count += 1

    # -- persistence ----------------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("could not read usage log %s (%s)", self._path, exc)
            return
        loaded = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # "<YYYY-MM-DD HH:MM><tab or spaces><count>": split the trailing count off the
            # right so the space inside the timestamp doesn't confuse the parse.
            try:
                ts_str, count_str = line.rsplit(None, 1)
                epoch = int(datetime.strptime(ts_str.strip(), _TS_FMT).timestamp())
                count = int(count_str)
            except ValueError:
                continue   # skip a malformed/partial line rather than fail startup
            self._history.append((epoch, count))
            loaded += 1
        if loaded:
            log.info("loaded %d minute(s) of keypress history from %s", loaded, self._path)

    def _append_line(self, epoch: int, count: int) -> None:
        line = "%s\t%d\n" % (datetime.fromtimestamp(epoch).strftime(_TS_FMT), count)
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            log.warning("could not append to usage log %s (%s)", self._path, exc)

    def _flush(self, minute_epoch: int) -> None:
        with self._lock:
            count = self._count
            self._count = 0
        self._history.append((minute_epoch, count))
        self._append_line(minute_epoch, count)

    # -- data for the web graph ----------------------------------------------
    def history(self) -> list[tuple[int, int]]:
        """A copy of the (minute_epoch_seconds, count) series, oldest first."""
        with self._lock:
            return list(self._history)

    # -- periodic driver (run in its own thread) ------------------------------
    def run(self, stop_event: threading.Event) -> None:
        """Flush one line per wall-clock minute until stopped. Aligns to the minute so
        timestamps land on :00; the partial minute in progress at shutdown is dropped
        (an incomplete count would skew the graph)."""
        log.info("keypress usage logging to %s", self._path)
        while not stop_event.is_set():
            now = time.time()
            next_boundary = (int(now // 60) + 1) * 60
            if stop_event.wait(next_boundary - now):
                break   # stopping: don't write an incomplete final minute
            self._flush(next_boundary - 60)   # the minute [b-60, b) that just ended
