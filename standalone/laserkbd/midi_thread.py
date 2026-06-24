"""MIDI input thread.

Opens the keyboard (matched by name substring), registers an rtmidi callback that
updates KeyState, and reconnects if the port disappears. The note handling folds in
the bugs logged against the original script:

  * channel-agnostic: match on the status nibble (status & 0xF0), not a fixed value
  * note-on with velocity 0 is treated as note-off
  * the note->key index is range-checked before use (no negative-index wrap, no
    IndexError swallowed by a bare except)
"""

from __future__ import annotations

import logging
import threading
import time

import rtmidi

from .config import ConfigHolder
from .state import KeyState

log = logging.getLogger(__name__)

NOTE_ON = 0x90
NOTE_OFF = 0x80
RECONNECT_INTERVAL = 1.0


def list_input_ports() -> list[str]:
    """Return the names of the available MIDI input ports, for the web-UI picker.

    Returns [] (and logs) if the backend can't enumerate ports, so the caller never
    has to special-case failure. Importing this module already requires rtmidi; the
    web UI imports it lazily so --dry-run (no rtmidi) can degrade to an empty list.
    """
    try:
        return rtmidi.MidiIn().get_ports()
    except Exception as exc:  # backend/driver errors are non-fatal for a listing
        log.warning("could not list MIDI input ports: %s", exc)
        return []


class MidiThread(threading.Thread):
    def __init__(self, state: KeyState, config: ConfigHolder, stop_event: threading.Event):
        super().__init__(name="midi", daemon=True)
        self._state = state
        self._config = config
        self._stop = stop_event
        self._midi_in = rtmidi.MidiIn()
        self._connected = False
        self._connected_name = ""  # name of the currently open port, for live re-pick
        self._callback_set = False

    # -- callback ---------------------------------------------------------------
    def _on_message(self, event, _data=None) -> None:
        message, _timestamp = event
        if len(message) < 3:
            return
        status, note, velocity = message[0], message[1], message[2]
        kind = status & 0xF0
        if kind not in (NOTE_ON, NOTE_OFF):
            return

        cfg = self._config.get()
        index = note - cfg.base_note
        if not (0 <= index < cfg.key_count):
            return  # out of playable range — ignore instead of wrapping/crashing

        if kind == NOTE_ON and velocity > 0:
            self._state.press(index, velocity)
        else:  # NOTE_OFF, or NOTE_ON with velocity 0 (== release)
            self._state.release(index)

    # -- connection management --------------------------------------------------
    def _find_port(self, name: str) -> int | None:
        ports = self._midi_in.get_ports()
        if not ports:
            return None
        if name:
            for i, p in enumerate(ports):
                if name.lower() in p.lower():
                    return i
            return None
        return 0  # no filter configured: take the first input

    def _try_connect(self) -> None:
        cfg = self._config.get()
        port = self._find_port(cfg.midi_port_name)
        if port is None:
            return
        try:
            # A callback survives close_port(), and set_callback() raises if one is
            # already registered — so clear any leftover before (re)connecting.
            if self._callback_set:
                self._midi_in.cancel_callback()
                self._callback_set = False
            self._midi_in.open_port(port)
            self._midi_in.set_callback(self._on_message)
            self._callback_set = True
            self._connected = True
            self._connected_name = self._midi_in.get_port_name(port)
            log.info("MIDI connected: %s", self._connected_name)
        except (rtmidi.SystemError, rtmidi.InvalidPortError, ValueError) as exc:
            log.warning("MIDI open failed: %s", exc)

    def run(self) -> None:
        log.info("MIDI thread started")
        while not self._stop.is_set():
            if not self._connected:
                self._try_connect()
            else:
                # rtmidi delivers messages via the callback on its own thread;
                # here we watch for the device vanishing, and for the user picking a
                # different keyboard in the web UI (midi_port_name no longer matches
                # the open port) — in which case we drop and reconnect to the new one.
                name = self._config.get().midi_port_name
                if not self._midi_in.is_port_open():
                    log.warning("MIDI port lost; will reconnect")
                    self._connected = False
                elif name and name.lower() not in self._connected_name.lower():
                    log.info("MIDI device changed to %r; switching", name)
                    self._midi_in.close_port()
                    self._connected = False
            self._stop.wait(RECONNECT_INTERVAL)
        self._midi_in.close_port()
        log.info("MIDI thread stopped")
