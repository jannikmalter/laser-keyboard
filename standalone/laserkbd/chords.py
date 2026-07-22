"""Chord-quality detection (R38).

Reduces the currently held key indices to their pitch classes (mod 12) and, if they
form exactly a major or minor triad, names the quality. This is deliberately quality-
based rather than a fixed set of key indices: *every* major chord (any root, any
inversion or voicing, octave doublings folded in) reads as "major", and every minor
chord as "minor". The DMX thread maps the quality to an effect (config.chord_effects,
default major -> wave, minor -> lightning).

A plain triad only: exactly three distinct pitch classes. A fourth distinct pitch class
(e.g. a seventh) cancels detection, and augmented / diminished / suspended triads match
neither quality -- only the true major and minor triads fire.
"""

from __future__ import annotations

from typing import Iterable, Optional

MAJOR = "major"
MINOR = "minor"


def quality(held: Iterable[int]) -> Optional[str]:
    """Return "major", "minor", or None for the held key indices.

    The held notes are reduced to distinct pitch classes (mod 12). A major triad stacks
    up 4 then 3 semitones from its root, a minor triad 3 then 4 (both leave a 5 back to
    the root, so the *unordered* gaps {3,4,5} are identical -- only the order tells them
    apart). Each rotation is tested so the root can be any of the three pitch classes,
    which makes detection invariant to inversion, voicing and octave doubling.
    """
    pcs = sorted({int(i) % 12 for i in held})
    if len(pcs) != 3:
        return None
    a, b, c = pcs
    gaps = (b - a, c - b, 12 - c + a)   # the three cyclic gaps; they sum to 12
    for r in range(3):
        first, second = gaps[r], gaps[(r + 1) % 3]
        if (first, second) == (4, 3):
            return MAJOR
        if (first, second) == (3, 4):
            return MINOR
    return None
