"""Chord-triggered effects (R39-R41).

Like decay.py these are essentially closed-form: an effect maps the time *elapsed*
since its chord triggered to a per-beam brightness array (length = total beam count,
40 = 4 bars x 10). The DMX thread overlays that array onto the per-key frame. Keeping
them a pure function of elapsed time (rather than an integrated per-tick state) means
the renderer stays stateless, is immune to tick jitter, and reflects a live config
change at once -- the same design the decay curve uses.

Two effects to start:

  * "lightning" -- all beams flash on/off at random, fast. The one not-quite-pure
    case: it reads RNG, but the RNG is seeded by the flash-window index (int(elapsed *
    flash_hz)), so every tick within one flash agrees and the look is identical
    regardless of tick_hz.
  * "wave" -- a bright head sweeps beam 0 -> max -> 0 (Larson / knight-rider) leaving a
    decaying trail. Head position and each beam's "time since the head last passed" are
    both closed-form functions of elapsed time, so the trailing comet is exact and the
    decay is tuned (via wave_decay_s ~ wave_period_s) so a beam is nearly off by the
    time the head returns to it.
"""

from __future__ import annotations

import random

from .config import Config

LIGHTNING = "lightning"
WAVE = "wave"


def render(name: str, elapsed: float, beam_count: int, cfg: Config) -> list[int]:
    """Per-beam brightness (0..master) for effect `name`, `elapsed` s after trigger."""
    if beam_count <= 0:
        return []
    if name == LIGHTNING:
        return _lightning(elapsed, beam_count, cfg)
    if name == WAVE:
        return _wave(elapsed, beam_count, cfg)
    return [0] * beam_count


def _lightning(elapsed: float, beam_count: int, cfg: Config) -> list[int]:
    master = cfg.master_brightness
    # Seed by the flash-window index so the pattern is fixed within one flash and only
    # changes at the next window -- stable across ticks, independent of tick_hz.
    window = int(elapsed * max(0.1, cfg.lightning_flash_hz))
    rng = random.Random(window)
    frac = cfg.lightning_on_fraction
    return [master if rng.random() < frac else 0 for _ in range(beam_count)]


def _wave(elapsed: float, beam_count: int, cfg: Config) -> list[int]:
    master = cfg.master_brightness
    n = beam_count
    period = max(0.05, cfg.wave_period_s)   # one full 0 -> max -> 0 sweep
    decay = max(0.01, cfg.wave_decay_s)     # per-beam fade time
    cycle = (elapsed // period) * period    # start time of the current sweep cycle
    out = [0] * n
    for i in range(n):
        f = i / (n - 1) if n > 1 else 0.0   # fractional position 0..1
        # Within one cycle the triangle head sits on beam i twice: going right at
        # phase f/2 and returning left at phase 1 - f/2. Take the most recent of those
        # passes (this cycle and the previous one) to get "time since last lit".
        p_up = f / 2.0
        p_down = 1.0 - f / 2.0
        hits = (cycle + p_up * period, cycle + p_down * period,
                cycle - period + p_up * period, cycle - period + p_down * period)
        last = max(h for h in hits if h <= elapsed)
        since = elapsed - last
        out[i] = round(master * 2.0 ** (-since / decay))
    return out
