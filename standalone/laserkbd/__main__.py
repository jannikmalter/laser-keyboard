"""Entry point: `python -m laserkbd [--config PATH]`.

Wires up logging, shared state, the MIDI and DMX threads, and the Flask web UI, then
blocks until SIGINT/SIGTERM and shuts everything down cleanly.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, Config, ConfigHolder
from .dmx_thread import DmxThread
from .log_buffer import RingBufferHandler
from .midi_thread import MidiThread
from .state import KeyState
from .web import create_app

log = logging.getLogger(__name__)


def setup_logging(level: str) -> RingBufferHandler:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                            datefmt="%H:%M:%S")
    ring = RingBufferHandler()
    ring.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers = [console, ring]
    return ring


def main() -> None:
    parser = argparse.ArgumentParser(prog="laserkbd")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                        help="path to config.json")
    args = parser.parse_args()

    config = Config.load(args.config)
    ring = setup_logging(config.log_level)
    log.info("laser-keyboard standalone starting (config: %s)", args.config)

    holder = ConfigHolder(config, args.config)
    state = KeyState(config.key_count)
    stop_event = threading.Event()

    midi = MidiThread(state, holder, stop_event)
    dmx = DmxThread(state, holder, stop_event)
    midi.start()
    dmx.start()

    # Flask dev server runs in a daemon thread so the main thread can wait on signals.
    app = create_app(state, holder, ring)
    web = threading.Thread(
        target=lambda: app.run(host=config.web_host, port=config.web_port,
                               threaded=True, use_reloader=False),
        name="web", daemon=True)
    web.start()
    log.info("web UI on http://%s:%s", config.web_host, config.web_port)

    def shutdown(signum, _frame):
        log.info("signal %s received, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    stop_event.wait()
    midi.join(timeout=3)
    dmx.join(timeout=3)
    log.info("stopped")


if __name__ == "__main__":
    main()
