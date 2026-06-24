"""Simulated-piano decay curve (R33).

Pure functions, no state: the renderer calls beam_brightness() once per key per
tick. Keeping the decay closed-form (a function of elapsed time since the strike)
rather than an integrated per-tick decrement means the renderer stays stateless,
is immune to tick jitter, and reflects a live config change to the bounds at once.

Shape: on a strike the beam is at full brightness and decays **exponentially** —
brightness = master * 2^(-elapsed / half_life) — so it halves every half_life and
rounds down to 0 in the tail (a held key eventually reads off, no explicit cutoff
needed). MIDI velocity selects the half-life: a soft hit fades fast, a hard hit
lingers. Note-off is handled by the caller (velocity drops to 0 -> beam off at once).

We use exponential rather than the original smootherstep S-curve: in practice the
keyboard tends to send full velocity, and the S-curve's flat top near t=0 hid the
decay; exponential drops immediately and reads as decaying right away.
"""

from __future__ import annotations


def decay_half_life(velocity: int, min_s: float, max_s: float) -> float:
    """Half-life in seconds, scaled linearly by velocity (1..127)."""
    frac = (max(1, min(127, velocity)) - 1) / 126.0
    return min_s + frac * (max_s - min_s)


def beam_brightness(velocity: int, elapsed: float, master: int,
                    min_s: float, max_s: float) -> int:
    """Brightness 0..master for a held key, `elapsed` seconds after its strike.

    Returns master at the moment of the strike and halves every half-life, rounding
    to 0 once it falls below half a step; stays effectively off while still held."""
    if velocity <= 0:
        return 0
    half_life = decay_half_life(velocity, min_s, max_s)
    if half_life <= 0.0:
        return 0
    if elapsed <= 0.0:
        return master  # at/just before the strike; avoid a >master overshoot
    return round(master * 2.0 ** (-elapsed / half_life))
