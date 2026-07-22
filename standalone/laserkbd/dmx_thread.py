"""DMX render + ArtNet send thread.

A free-running monotonic deadline loop ticks at config.tick_hz (target ~100 Hz).
On every tick it renders one DMX frame from the current key state and sends it as
ArtNet. Render and send share the tick so the frame computed is the frame sent.

Per-key beams use the simulated-piano decay (R33): a strike lights the beam at full
brightness and it decays (exponential or linear, configurable) over a velocity-
selected time (see decay.py); note-off does not cut the beam — the fade keeps playing
past release. On top of that, chord-triggered
effects (R38-R41) are overlaid: the held chord's quality (major/minor, see chords.py)
maps to a full-array effect (effects.py). The full-keyboard (12+ keys) bonus is the one
piece still Milestone 2 — see render()'s remaining TODO.
"""

from __future__ import annotations

import logging
import threading
import time

from . import chords, decay, effects, fixtures, live
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
        # Effect name -> monotonic trigger time. The one piece of effect state the DMX
        # thread keeps; effects themselves are closed-form over now - trigger (R38/R39).
        self._active_effects: dict[str, float] = {}

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
        for index, (velocity, onset, is_held) in enumerate(self._state.snapshot()):
            if is_held:
                held.add(index)          # physical key state, for chord detection
            if velocity <= 0:
                continue  # never struck: leave the channel at 0 (beam off)
            # Simulated-piano decay (R33): full brightness at the strike, decaying to
            # off (exponential or linear) over a velocity-selected time. Note-off does
            # NOT cut the beam — velocity/onset persist past release so the fade keeps
            # playing (only `is_held` above clears, ending the key's held state).
            brightness = decay.beam_brightness(
                velocity, now - onset, cfg.master_brightness,
                cfg.decay_mode, cfg.decay_t_min_s, cfg.decay_t_max_s)
            if brightness <= 0:
                continue  # fully decayed while held: beam off
            channel = fixtures.beam_channel(cfg, index)
            if channel is not None and channel < len(frame):
                frame[channel] = brightness

        # Chord-triggered effects (R38-R41): detect the held chord's quality, then
        # overlay its mapped effect onto the frame.
        self._update_effects(cfg, held, now)
        if self._active_effects:
            self._overlay_effects(cfg, frame, now)
        # TODO(milestone-2): overlay full-keyboard (held_count >= 12) bonus effect.
        return bytes(frame)

    def _update_effects(self, cfg: Config, held: set[int], now: float) -> None:
        """Edge-detect the effect driven by the held chord's quality (R38/R39). The held
        keys form at most one major/minor triad (chords.quality), which cfg.chord_effects
        maps to at most one effect: stamp a trigger time when that effect first becomes
        active, drop it when the chord is released or its quality changes."""
        wanted = cfg.chord_effects.get(chords.quality(held) or "")
        for name in [n for n in self._active_effects if n != wanted]:
            del self._active_effects[name]     # chord released/changed -> effect ends
        if wanted and wanted not in self._active_effects:
            self._active_effects[wanted] = now  # chord just completed -> start its effect

    def _overlay_effects(self, cfg: Config, frame: bytearray, now: float) -> None:
        """Render each active effect over the full 40-beam array and composite it onto
        the frame, taking the per-channel max so held per-key beams still read through
        (R39). Effects can light any bar, so put every bar in per-beam mode."""
        for base in fixtures.all_bar_bases(cfg):
            if base < len(frame):
                frame[base] = fixtures.DMX_MODE_PER_BEAM
        channels = fixtures.all_beam_channels(cfg)
        # Oldest-triggered first; later effects max over earlier ones.
        for name in sorted(self._active_effects, key=self._active_effects.__getitem__):
            levels = effects.render(name, now - self._active_effects[name],
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
        keys = [v if h else 0 for v, _, h in self._state.snapshot()]
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
