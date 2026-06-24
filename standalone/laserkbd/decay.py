"""Simulated-piano decay curve (R33).

Pure functions, no state: the renderer calls beam_brightness() once per key per
tick. Keeping the decay closed-form (a function of elapsed time since the strike)
rather than an integrated per-tick decrement means the renderer stays stateless,
is immune to tick jitter, and reflects a live config change to the bounds at once.

Shape: on a strike the beam is at full brightness and eases to off along an S-curve
(smootherstep) over a finite duration, so it reaches exactly zero. MIDI velocity
selects that duration: a soft hit decays fast, a hard hit lingers for many seconds.
Note-off is handled by the caller (velocity drops to 0 -> beam off immediately).
"""

from __future__ import annotations


def _smootherstep(u: float) -> float:
    """Ken Perlin's smootherstep on [0, 1]: 6u^5 - 15u^4 + 10u^3.

    An S-curve that is flat (zero slope) at both ends, giving a brief hold at full
    brightness after the strike and a soft settle into off."""
    u = 0.0 if u < 0.0 else 1.0 if u > 1.0 else u
    return u * u * u * (u * (u * 6.0 - 15.0) + 10.0)


def decay_duration(velocity: int, min_s: float, max_s: float) -> float:
    """Seconds the beam takes to decay, scaled linearly by velocity (1..127)."""
    frac = (max(1, min(127, velocity)) - 1) / 126.0
    return min_s + frac * (max_s - min_s)


def beam_brightness(velocity: int, elapsed: float, master: int,
                    min_s: float, max_s: float) -> int:
    """Brightness 0..master for a held key, `elapsed` seconds after its strike.

    Returns master at the moment of the strike and eases to 0 over the velocity-
    selected duration; stays 0 once fully decayed even while the key is still held."""
    if velocity <= 0:
        return 0
    duration = decay_duration(velocity, min_s, max_s)
    if duration <= 0.0:
        return 0
    u = elapsed / duration
    return round(master * (1.0 - _smootherstep(u)))
