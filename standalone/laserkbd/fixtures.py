"""Fixture / DMX-channel mapping.

This is the addressing that used to live in the QLC+ workspace: four BeamBar 10R
bars (13 channels each, base addresses 0/13/26/39), with the 10 individual beams
sitting at channel offset 3 within each bar. Keys map onto beams in order:

    key index -> bar = index // beams_per_bar, beam = index % beams_per_bar

Channels are 0-based indices into the DMX universe (channel 1 == index 0).
"""

from __future__ import annotations

from .config import Config


def beam_channel(cfg: Config, key_index: int) -> int | None:
    """DMX channel index for a given key, or None if the key has no beam."""
    bar = key_index // cfg.beams_per_bar
    beam = key_index % cfg.beams_per_bar
    if bar >= len(cfg.bar_base_addresses):
        return None
    return cfg.bar_base_addresses[bar] + cfg.beam_channel_offset + beam


def universe_size(cfg: Config) -> int:
    """Highest channel we address, rounded up to an even byte count. The special
    ArtNet node can be told to forward fewer than 512 channels (which is what lets
    the tick rate exceed 44 Hz), so we send only as many channels as we use."""
    highest = 0
    for key in range(cfg.key_count):
        ch = beam_channel(cfg, key)
        if ch is not None:
            highest = max(highest, ch + 1)
    # ArtNet wants an even length; clamp to the 512-channel DMX maximum.
    size = highest + (highest % 2)
    return max(2, min(512, size))
