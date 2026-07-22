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
from .live import LiveBus
from .log_buffer import RingBufferHandler
from .state import KeyState
from .usage import UsageLog
from .web import create_app

# MidiThread is imported lazily in main() so that --dry-run works without rtmidi.

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
    # Quiet the Flask dev server's per-request access log (B9): every web request — incl.
    # high-frequency virtual-keyboard input — was logged at INFO, and those lines streamed
    # back to the browser's log view, feeding a flood that bogged the page down.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    return ring


def main() -> None:
    parser = argparse.ArgumentParser(prog="laserkbd")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                        help="path to config.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="run without real hardware (simulated keyboard, ArtNet "
                             "output suppressed) — for testing the web UI")
    args = parser.parse_args()

    ring = setup_logging("INFO")
    config = Config.load(args.config)  # logged via the handlers set up just above
    logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    log.info("laser-keyboard standalone starting (config: %s)", args.config)
    if args.dry_run:
        log.info("DRY RUN: simulated keyboard, ArtNet output suppressed")

    holder = ConfigHolder(config, args.config)
    # Keypress usage log (R34): resolve a relative path next to the config file.
    usage_path = Path(config.keypress_log_file)
    if not usage_path.is_absolute():
        usage_path = args.config.parent / usage_path
    usage = UsageLog(usage_path)
    # on_press counts every strike (physical MIDI + virtual web keyboard) at one choke point.
    state = KeyState(config.key_count, on_press=usage.record)
    live_bus = LiveBus()   # DMX thread publishes frames; web streams them (R37)
    stop_event = threading.Event()

    if args.dry_run:
        from .sim import SimulatedMidiThread
        midi = SimulatedMidiThread(state, holder, stop_event)
    else:
        from .midi_thread import MidiThread
        midi = MidiThread(state, holder, stop_event)
    dmx = DmxThread(state, holder, stop_event, dry_run=args.dry_run, live_bus=live_bus)
    midi.start()
    dmx.start()

    # Per-minute keypress flusher (R34): its own thread, joined on shutdown.
    usage_thread = threading.Thread(target=usage.run, args=(stop_event,),
                                    name="usage", daemon=True)
    usage_thread.start()

    # Flask dev server runs in a daemon thread so the main thread can wait on signals.
    app = create_app(state, holder, ring, live_bus, usage, dmx)

    def run_web():
        try:
            app.run(host=config.web_host, port=config.web_port,
                    threaded=True, use_reloader=False)
        except OSError as exc:
            log.error("web UI could not start on %s:%s (%s)", config.web_host,
                      config.web_port, exc)
            log.error("the port is likely in use or reserved — set a free \"web_port\" "
                      "in %s and restart", args.config)

    web = threading.Thread(target=run_web, name="web", daemon=True)
    web.start()
    log.info("web UI starting on http://%s:%s", config.web_host, config.web_port)

    def shutdown(signum, _frame):
        log.info("signal %s received, shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    stop_event.wait()
    midi.join(timeout=3)
    dmx.join(timeout=3)
    usage_thread.join(timeout=3)
    log.info("stopped")


if __name__ == "__main__":
    main()
