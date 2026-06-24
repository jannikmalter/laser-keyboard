"""DMX render + ArtNet send thread.

A free-running monotonic deadline loop ticks at config.tick_hz (target ~100 Hz).
On every tick it renders one DMX frame from the current key state and sends it as
ArtNet. Render and send share the tick so the frame computed is the frame sent.

Per-key beams use the simulated-piano decay (R33): a strike lights the beam at full
brightness and it decays exponentially with a velocity-selected half-life (see
decay.py); note-off is immediate. Chord and full-keyboard effects are still
Milestone 2 — see render() TODOs.
"""

from __future__ import annotations

import logging
import threading
import time

from . import decay, fixtures
from .artnet import ArtNetSender
from .config import Config, ConfigHolder
from .state import KeyState

log = logging.getLogger(__name__)


class DmxThread(threading.Thread):
    def __init__(self, state: KeyState, config: ConfigHolder,
                 stop_event: threading.Event, dry_run: bool = False):
        super().__init__(name="dmx", daemon=True)
        self._state = state
        self._config = config
        self._stop = stop_event
        self._dry_run = dry_run
        self._sender = ArtNetSender(dry_run=dry_run)

    def _render(self, cfg: Config, now: float) -> bytes:
        """Map held keys onto beam channels. Returns the DMX byte frame.

        `now` is a time.monotonic() reading, the same clock KeyState stamps onsets
        with, so elapsed = now - onset drives the decay curve (R33). The frame is a
        fresh zeroed buffer each tick: a released or fully-decayed beam is simply not
        written, so it is off — values do not persist between frames."""
        frame = bytearray(fixtures.universe_size(cfg))

        # Put every bar into per-beam DMX mode (channel 1 = 200-255), otherwise the
        # bar ignores the beam channels and stays dark. See fixtures.DMX_MODE_PER_BEAM.
        for base in fixtures.active_bar_bases(cfg):
            if base < len(frame):
                frame[base] = fixtures.DMX_MODE_PER_BEAM

        for index, (velocity, onset) in enumerate(self._state.snapshot()):
            if velocity <= 0:
                continue  # released: leave the channel at 0 (beam off)
            # Simulated-piano decay (R33): full brightness at the strike, easing to
            # off along an S-curve over a velocity-selected duration. Note-off is the
            # velocity <= 0 case above (immediate off, no decay).
            brightness = decay.beam_brightness(
                velocity, now - onset, cfg.master_brightness,
                cfg.half_life_min_s, cfg.half_life_max_s)
            if brightness <= 0:
                continue  # fully decayed while held: beam off
            channel = fixtures.beam_channel(cfg, index)
            if channel is not None and channel < len(frame):
                frame[channel] = brightness

        # TODO(milestone-2): overlay chord-triggered effects here.
        # TODO(milestone-2): overlay full-keyboard (held_count >= 12) bonus effect.
        return bytes(frame)

    def _target_ip(self, cfg: Config) -> str:
        if cfg.artnet_mode == "unicast":
            return cfg.artnet_ip
        return "255.255.255.255"

    def run(self) -> None:
        log.info("DMX thread started%s", " (dry-run: not sending)" if self._dry_run else "")
        next_tick = time.perf_counter()
        last_status = next_tick
        while not self._stop.is_set():
            cfg = self._config.get()
            period = 1.0 / max(1.0, cfg.tick_hz)

            frame = self._render(cfg, time.monotonic())
            self._sender.send(self._target_ip(cfg), cfg.artnet_universe, frame)

            now = time.perf_counter()
            if self._dry_run and now - last_status >= 2.0:
                lit = sum(1 for b in frame if b)
                log.info("dry-run tick: %.0f Hz, %d/%d channels lit, target %s uni %d",
                         cfg.tick_hz, lit, len(frame), self._target_ip(cfg),
                         cfg.artnet_universe)
                last_status = now

            next_tick += period
            now = time.perf_counter()  # re-read: the status log above may have taken time
            sleep = next_tick - now
            if sleep > 0:
                self._stop.wait(sleep)
            elif sleep < -period:
                # Fell more than a full period behind (e.g. config change or a
                # scheduler hiccup): resync rather than firing a catch-up burst.
                next_tick = now
        self._sender.close()
        log.info("DMX thread stopped")
