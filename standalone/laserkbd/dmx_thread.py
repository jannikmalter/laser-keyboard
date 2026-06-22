"""DMX render + ArtNet send thread.

A free-running monotonic deadline loop ticks at config.tick_hz (target ~100 Hz).
On every tick it renders one DMX frame from the current key state and sends it as
ArtNet. Render and send share the tick so the frame computed is the frame sent.

Milestone 1 renders per-key beams only (on/off scaled by master brightness). Chord
and full-keyboard effects are Milestone 2 — see render() TODOs.
"""

from __future__ import annotations

import logging
import threading
import time

from . import fixtures
from .artnet import ArtNetSender
from .config import Config, ConfigHolder
from .state import KeyState

log = logging.getLogger(__name__)


class DmxThread(threading.Thread):
    def __init__(self, state: KeyState, config: ConfigHolder, stop_event: threading.Event):
        super().__init__(name="dmx", daemon=True)
        self._state = state
        self._config = config
        self._stop = stop_event
        self._sender = ArtNetSender()

    def _render(self, cfg: Config) -> bytes:
        """Map held keys onto beam channels. Returns the DMX byte frame."""
        frame = bytearray(fixtures.universe_size(cfg))
        velocities = self._state.snapshot()
        for index, velocity in enumerate(velocities):
            if velocity <= 0:
                continue
            channel = fixtures.beam_channel(cfg, index)
            if channel is not None and channel < len(frame):
                # Milestone 1: simple on/off at master brightness.
                # TODO(milestone-2): velocity-/effect-driven brightness curves.
                frame[channel] = cfg.master_brightness

        # TODO(milestone-2): overlay chord-triggered effects here.
        # TODO(milestone-2): overlay full-keyboard (held_count >= 12) bonus effect.
        return bytes(frame)

    def _target_ip(self, cfg: Config) -> str:
        if cfg.artnet_mode == "unicast":
            return cfg.artnet_ip
        return "255.255.255.255"

    def run(self) -> None:
        log.info("DMX thread started")
        next_tick = time.perf_counter()
        while not self._stop.is_set():
            cfg = self._config.get()
            period = 1.0 / max(1.0, cfg.tick_hz)

            frame = self._render(cfg)
            self._sender.send(self._target_ip(cfg), cfg.artnet_universe, frame)

            next_tick += period
            now = time.perf_counter()
            sleep = next_tick - now
            if sleep > 0:
                self._stop.wait(sleep)
            elif sleep < -period:
                # Fell more than a full period behind (e.g. config change or a
                # scheduler hiccup): resync rather than firing a catch-up burst.
                next_tick = now
        self._sender.close()
        log.info("DMX thread stopped")
