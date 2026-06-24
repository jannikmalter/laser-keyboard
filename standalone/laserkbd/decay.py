"""Simulated-piano decay curve (R33).

Pure functions, no state: the renderer calls beam_brightness() once per key per
tick. Keeping the decay closed-form (a function of elapsed time since the strike)
rather than an integrated per-tick decrement means the renderer stays stateless,
is immune to tick jitter, and reflects a live config change to the bounds at once.

On a strike the beam is at full brightness and decays toward off; MIDI velocity
selects the decay time `t` (a soft hit fades fast, a hard hit lingers). Two shapes,
chosen by `mode`:

  * "exponential" — brightness = master * 2^(-elapsed / t); halves every `t` and
    rounds to 0 in the tail (a held key eventually reads off, no explicit cutoff).
    `t` is the half-life. This is the default — the keyboard tends to send full
    velocity, and an exponential drop reads as decaying right away.
  * "linear" — brightness ramps straight from master to 0 over `t` seconds, then
    stays off. `t` is the full fade duration.

Note-off is handled by the caller (velocity drops to 0 -> beam off immediately).
"""

from __future__ import annotations

EXPONENTIAL = "exponential"
LINEAR = "linear"


def decay_time(velocity: int, min_s: float, max_s: float) -> float:
    """Decay time `t` in seconds, scaled linearly by velocity (1..127)."""
    frac = (max(1, min(127, velocity)) - 1) / 126.0
    return min_s + frac * (max_s - min_s)


def beam_brightness(velocity: int, elapsed: float, master: int,
                    mode: str, min_s: float, max_s: float) -> int:
    """Brightness 0..master for a held key, `elapsed` seconds after its strike.

    Returns master at the moment of the strike and decays per `mode` over the
    velocity-selected time; stays effectively off once decayed, while still held."""
    if velocity <= 0:
        return 0
    t = decay_time(velocity, min_s, max_s)
    if t <= 0.0:
        return 0
    if elapsed <= 0.0:
        return master  # at/just before the strike; avoid a >master overshoot
    if mode == LINEAR:
        frac = 1.0 - elapsed / t
        return round(master * frac) if frac > 0.0 else 0
    # exponential (default): halve every half-life `t`
    return round(master * 2.0 ** (-elapsed / t))
