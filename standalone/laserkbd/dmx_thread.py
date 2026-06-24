"""DMX render + ArtNet send thread.

A free-running monotonic deadline loop ticks at config.tick_hz (target ~100 Hz).
On every tick it renders one DMX frame from the current key state and sends it as
ArtNet. Render and send share the tick so the frame computed is the frame sent.

Per-key beams use the simulated-piano decay (R33): a strike lights the beam at full
brightness and it decays (exponential or linear, configurable) over a velocity-
selected time (see decay.py); note-off is immediate. Chord and full-keyboard effects
are still Milestone 2 — see render() TODOs.
"""

from __future__ import annotations

import logging
import threading
import time

from . import decay, effects, fixtures, live
from .artnet import ArtNetSender
from .config import Config, ConfigHolder
from .live import LiveBus
from .state import KeyState

log = logging.getLogger(__name__)


class DmxThread(threading.Thread):
    def __init__(self, state: KeyState, config: ConfigHolder,
                 stop_event: threading.Event, dry_run: bool = False,
                 live_bus: LiveBus | None = None):
        super().__init__(name="dmx", daemon=True)
        self._state = state
        self._config = config
        self._stop = stop_event
        self._dry_run = dry_run
        self._live = live_bus
        self._sender = ArtNetSender(dry_run=dry_run)
        # Chord index -> monotonic trigger time. The one piece of effect state the DMX
        # thread keeps; effects themselves are closed-form over now - trigger (R38/R39).
        self._active_chords: dict[int, float] = {}

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

        held: set[int] = set()
        for index, (velocity, onset) in enumerate(self._state.snapshot()):
            if velocity <= 0:
                continue  # released: leave the channel at 0 (beam off)
            held.add(index)
            # Simulated-piano decay (R33): full brightness at the strike, decaying to
            # off (exponential or linear) over a velocity-selected time. Note-off is the
            # velocity <= 0 case above (immediate off, no decay).
            brightness = decay.beam_brightness(
                velocity, now - onset, cfg.master_brightness,
                cfg.decay_mode, cfg.decay_t_min_s, cfg.decay_t_max_s)
            if brightness <= 0:
                continue  # fully decayed while held: beam off
            channel = fixtures.beam_channel(cfg, index)
            if channel is not None and channel < len(frame):
                frame[channel] = brightness

        # Chord-triggered effects (R38-R41): detect, then overlay onto the frame.
        self._update_chords(cfg, held, now)
        if self._active_chords:
            self._overlay_effects(cfg, frame, now)
        # TODO(milestone-2): overlay full-keyboard (held_count >= 12) bonus effect.
        return bytes(frame)

    def _update_chords(self, cfg: Config, held: set[int], now: float) -> None:
        """Edge-detect chords from the held keys: stamp a trigger time when a chord
        first completes, drop it when any of its keys is released (R38)."""
        for i, chord in enumerate(cfg.chords):
            keys = chord.get("keys", [])
            complete = bool(keys) and held.issuperset(keys)
            if complete and i not in self._active_chords:
                self._active_chords[i] = now   # just completed -> start its effect
            elif not complete and i in self._active_chords:
                del self._active_chords[i]      # broken -> effect ends
        # A live config edit can shrink cfg.chords; forget any now-stale indices.
        for i in [i for i in self._active_chords if i >= len(cfg.chords)]:
            del self._active_chords[i]

    def _overlay_effects(self, cfg: Config, frame: bytearray, now: float) -> None:
        """Render each active chord's effect over the full 40-beam array and composite
        it onto the frame, taking the per-channel max so held per-key beams still read
        through (R39). Effects can light any bar, so put every bar in per-beam mode."""
        for base in fixtures.all_bar_bases(cfg):
            if base < len(frame):
                frame[base] = fixtures.DMX_MODE_PER_BEAM
        channels = fixtures.all_beam_channels(cfg)
        # Oldest-triggered first; later effects max over earlier ones.
        for i in sorted(self._active_chords, key=self._active_chords.__getitem__):
            chord = cfg.chords[i]
            levels = effects.render(chord.get("effect", ""), now - self._active_chords[i],
                                    len(channels), cfg)
            for beam, level in enumerate(levels):
                if level <= 0 or beam >= len(channels):
                    continue
                ch = channels[beam]
                if ch < len(frame) and level > frame[ch]:
                    frame[ch] = min(255, level)

    def _target_ip(self, cfg: Config) -> str:
        if cfg.artnet_mode == "unicast":
            return cfg.artnet_ip
        return "255.255.255.255"

    def _publish_live(self, cfg: Config, frame: bytes) -> None:
        """Publish a live-viz snapshot for the web UI (R37): key velocities (input) and
        the 40 rendered beam brightnesses (output, read back out of the DMX frame)."""
        keys = [v for v, _ in self._state.snapshot()]
        beams = [frame[ch] if ch < len(frame) else 0
                 for ch in fixtures.all_beam_channels(cfg)]
        self._live.publish(live.encode_frame(keys, beams))

    def run(self) -> None:
        log.info("DMX thread started%s", " (dry-run: not sending)" if self._dry_run else "")
        next_tick = time.perf_counter()
        last_status = next_tick
        while not self._stop.is_set():
            cfg = self._config.get()
            period = 1.0 / max(1.0, cfg.tick_hz)

            frame = self._render(cfg, time.monotonic())
            self._sender.send(self._target_ip(cfg), cfg.artnet_universe, frame)
            # Live viz (R37): only build/publish a frame while a browser is watching, so
            # the feed adds nothing to the render loop during a normal show.
            if self._live is not None and self._live.active():
                self._publish_live(cfg, frame)

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
