"""Standalone Raspberry Pi laser-keyboard (ArtNet) — see ../../reqs.md, Milestone 1.

Reads a MIDI keyboard and emits ArtNet directly, with no QLC+ in the loop. Three
cooperating threads share state:

    MIDI thread  -> updates key state from the keyboard
    DMX thread   -> renders a DMX frame from key state and sends ArtNet on a tick
    Web thread   -> Flask UI for settings + logs (started from __main__)

Milestone 1 covers the per-key beam mapping; chord/full-keyboard effects are
deferred to Milestone 2 and marked with TODO(milestone-2).
"""

__version__ = "0.1.0"
