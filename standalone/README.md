# laser-keyboard — standalone (Raspberry Pi / ArtNet)

Self-contained version of the laser keyboard that runs on a Raspberry Pi 3B+ inside
the keyboard enclosure and emits **ArtNet** directly — no PC, no QLC+, no loopMIDI.
The keyboard connects to the Pi over USB; the unit reaches the rig over one network
cable (PoE). See [`../reqs.md`](../reqs.md) for the full requirements and roadmap.

> **Status: scaffolding.** Milestone 1 (per-key beams over ArtNet) is wired up and
> runnable. Chord and full-keyboard effects are Milestone 2 and currently stubbed
> (`TODO(milestone-2)` in `dmx_thread.py`).

## Architecture

```
MIDI keyboard ──USB──► Pi ──► laserkbd ──ArtNet/UDP──► node ──DMX──► laser bars
```

Three threads share state (`laserkbd/`):

| Module | Thread | Role |
|--------|--------|------|
| `midi_thread.py` | MIDI | read the keyboard, update `KeyState` |
| `dmx_thread.py`  | DMX  | render a DMX frame from `KeyState`, send ArtNet on a ~100 Hz tick |
| `web.py`         | web  | Flask UI: settings, MIDI + ArtPoll device scan, logs |
| `config.py` · `state.py` · `fixtures.py` · `artnet.py` · `log_buffer.py` | — | shared support |

## System dependencies (Linux / Raspberry Pi)

`python-rtmidi` is compiled from source on Linux and needs the ALSA development
headers and a C toolchain, or `pip install` fails with
`ERROR: Dependency "alsa" not found (tried pkg-config)`. On Raspberry Pi OS / Debian:

```bash
sudo apt update
sudo apt install libasound2-dev pkg-config build-essential python3-dev
# optional: libjack-dev   # adds the JACK backend / silences the JACK-not-found warning
```

Not needed for `--dry-run` (which doesn't import `python-rtmidi`) or on Windows
(rtmidi ships prebuilt wheels there).

## Run (dev)

```bash
cd standalone
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m laserkbd                  # optional: --config /path/to/config.json
```

Then open `http://<host>:8088` (the default `web_port`; change it in the config if
busy). Settings are saved to `config.json` next to the package and reloaded on restart.

### Dry-run (test the web UI without hardware)

```bash
python -m laserkbd --dry-run     # only needs flask, not python-rtmidi
```

Dry-run replaces the keyboard with a simulator that sweeps a single beam (so the UI
shows live "keys held" activity and the render loop logs a status line every couple
of seconds) and suppresses all ArtNet output — nothing is put on the network. Use it
to develop and test the web interface on any machine, no Pi/keyboard/node required.

## Run on the Pi (systemd)

Edit paths/user in `laser-keyboard.service`, then:

```bash
sudo cp laser-keyboard.service /etc/systemd/system/
sudo systemctl enable --now laser-keyboard
journalctl -u laser-keyboard -f
```

## Configuration

All settings live in `config.json` (see `laserkbd/config.py` for fields and
defaults). Key ones:

- **MIDI keyboard** — `midi_port_name` (substring match; empty = first input). Use the
  web UI's *Scan MIDI devices* button to list input ports and pick one; the choice
  takes effect on the next MIDI (re)connect.
- **ArtNet target** — `artnet_mode` `broadcast`/`unicast`, `artnet_ip`, `artnet_universe`.
  Use the web UI's *ArtPoll & scan* button to discover nodes and pick one.
- **Tick rate** — `tick_hz` (default 100). Can exceed 44 Hz because the node forwards
  a reduced channel count.
- **Fixture mapping** — `bar_base_addresses` (default `[0,13,26,39]`),
  `beams_per_bar`, `beam_channel_offset` — the BeamBar addressing that used to live
  in the QLC+ workspace.

## Notes

- The Flask **dev server** is used for simplicity; it's fine for a single-user
  appliance on a trusted network. Don't expose it to untrusted networks as-is.
- ArtPoll discovery is reliable only when the Pi shares a subnet/interface with the
  ArtNet nodes.
