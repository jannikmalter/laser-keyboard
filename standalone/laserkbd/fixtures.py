"""Fixture / DMX-channel mapping.

This is the addressing that used to live in the QLC+ workspace: four BeamBar 10R
bars (13 channels each, base addresses 0/13/26/39), with the 10 individual beams
sitting at channel offset 3 within each bar. Keys map onto beams in order:

    key index -> bar = index // beams_per_bar, beam = index % beams_per_bar

Channels are 0-based indices into the DMX universe (channel 1 == index 0).
"""

from __future__ import annotations

from .config import Config

# Channel 1 of each bar is a mode selector. Per the BeamBar 10R MK3 manual's DMX chart
# (see info.md), the per-beam brightness channels (4-13) are honoured ONLY when channel
# 1 is in 200-255. At its default 0 the bar is in "laser off" mode and the beams stay
# dark. We hold every active bar's channel 1 here so the beams respond.
DMX_MODE_PER_BEAM = 255


def beam_channel(cfg: Config, key_index: int) -> int | None:
    """DMX channel index for a given key, or None if the key has no beam."""
    bar = key_index // cfg.beams_per_bar
    beam = key_index % cfg.beams_per_bar
    if bar >= len(cfg.bar_base_addresses):
        return None
    return cfg.bar_base_addresses[bar] + cfg.beam_channel_offset + beam


def active_bar_bases(cfg: Config) -> list[int]:
    """Base addresses (== channel 1 index) of bars that have at least one key mapped.

    These are the channels that must be driven to DMX_MODE_PER_BEAM each frame to put
    the bars into per-beam DMX mode."""
    bases: set[int] = set()
    for key in range(cfg.key_count):
        bar = key // cfg.beams_per_bar
        if bar < len(cfg.bar_base_addresses):
            bases.add(cfg.bar_base_addresses[bar])
    return sorted(bases)


def universe_size(cfg: Config) -> int:
    """Highest channel we address, rounded up to an even byte count. The special
    ArtNet node can be told to forward fewer than 512 channels (which is what lets
    the tick rate exceed 44 Hz), so we send only as many channels as we use."""
    highest = 0
    for key in range(cfg.key_count):
        ch = beam_channel(cfg, key)
        if ch is not None:
            highest = max(highest, ch + 1)
    for base in active_bar_bases(cfg):  # channel 1 of each bar must fit too
        highest = max(highest, base + 1)
    # ArtNet wants an even length; clamp to the 512-channel DMX maximum.
    size = highest + (highest % 2)
    return max(2, min(512, size))
