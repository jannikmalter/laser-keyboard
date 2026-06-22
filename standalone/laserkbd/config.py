"""Configuration: a dataclass of settings, plus JSON load/save and a thread-safe
holder so the web and DMX threads can read/swap settings safely.

See reqs.md -> "Settings exposed in the web UI" for the intended editable fields.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class Config:
    # --- MIDI ---------------------------------------------------------------
    midi_port_name: str = ""        # substring match; "" = first available input
    base_note: int = 41             # MIDI note that maps to key index 0
    key_count: int = 32             # number of playable keys

    # --- ArtNet -------------------------------------------------------------
    artnet_mode: str = "broadcast"  # "broadcast" | "unicast"
    artnet_ip: str = "255.255.255.255"   # used when mode == "unicast"
    artnet_universe: int = 0
    artnet_port: int = 6454
    tick_hz: float = 100.0          # DMX render + send rate (see jitter budget)
    master_brightness: int = 255    # 0-255, global dimmer

    # --- Fixture mapping (the BeamBar addressing that used to live in QLC+) --
    bar_base_addresses: list[int] = field(default_factory=lambda: [0, 13, 26, 39])
    beams_per_bar: int = 10
    beam_channel_offset: int = 3    # first beam channel within a 13-ch bar

    # --- Web / logging ------------------------------------------------------
    web_host: str = "0.0.0.0"
    web_port: int = 8088   # 8080 is commonly taken/reserved on Windows; change if busy
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: Path) -> "Config":
        """Load from JSON, ignoring unknown keys and keeping defaults for missing."""
        if not path.exists():
            log.info("no config at %s, using defaults", path)
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("could not read config %s (%s); using defaults", path, exc)
            return cls()
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in raw.items() if k in known}
        return cls(**clean)

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic-ish: avoid a half-written config on crash
        log.info("config saved to %s", path)


class ConfigHolder:
    """Thread-safe container for the current Config. Readers call get(); the web
    thread calls update() to swap in a new Config and persist it."""

    def __init__(self, config: Config, path: Path):
        self._lock = threading.Lock()
        self._config = config
        self._path = path

    def get(self) -> Config:
        with self._lock:
            return self._config

    def update(self, **changes) -> Config:
        with self._lock:
            data = asdict(self._config)
            data.update(changes)
            self._config = Config(**data)
            self._config.save(self._path)
            return self._config
