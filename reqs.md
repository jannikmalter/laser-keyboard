# laser-keyboard — Requirements

Status: Active · Updated: 2026-06-24 (R33–R37 added)

## Goals
Why this exists. Everything below traces to one of these.

- **G1** — The core installation: each MIDI key lights one individual laser beam,
  and chords trigger bonus effects, for live hands-on play (the working QLC+ build).
- **G2** — A self-contained Raspberry Pi / ArtNet appliance that runs the same
  installation with no PC and no QLC+. Design detail in `reqs/G2.md`.

## Out of scope
What this deliberately will *not* do (stops scope creep).

- Hard real-time timing measures (PREEMPT_RT kernel, `isolcpus`, core pinning) —
  out of scope unless timing problems actually appear; the jitter budget is generous.
- Effects in the standalone build's Milestone 1 — deferred to Milestone 2 (see `todo.md`).

## Requirements
One row each. Use "shall". `Type`: F=function, Q=quality, C=constraint.
QLC+ items (R1–R14) are **as-built** — recorded from the shipped code, `Done` ☑ with
the code as evidence. Standalone items (R15–R32) trace to **G2**; see status note below.

| ID  | Type | Requirement                                                                          | Pri | Goal | Done |
|-----|------|--------------------------------------------------------------------------------------|-----|------|------|
| R1  | F    | The system shall read note input from a MIDI keyboard.                               | M   | G1   | ☑    |
| R2  | F    | The system shall forward a cleaned note stream to QLC+ via a virtual MIDI port (loopMIDI). | M | G1 | ☑ |
| R3  | F    | The system shall auto-connect on startup and poll/reconnect once per second if a port drops. | S | G1 | ☑ |
| R4  | F    | The system shall exit cleanly on Ctrl+C, closing both MIDI ports.                    | S   | G1   | ☑    |
| R5  | F    | The system shall map each playable key to one laser beam (32 keys, notes 41–72, offset −41 → index 0–31). | M | G1 | ☑ |
| R6  | F    | The system shall send `NOTE_ON` on the key's beam channel on key press.              | M   | G1   | ☑    |
| R7  | F    | The system shall send `NOTE_OFF` on the key's beam channel on key release.           | M   | G1   | ☑    |
| R8  | F    | The system shall define chords as sets of key indices (A1, B1, C1, D1, E1, F1, G1, F2). | S | G1 | ☑ |
| R9  | F    | The system shall detect when all keys of a chord are held simultaneously.            | S   | G1   | ☑    |
| R10 | F    | The system shall send `NOTE_ON` on channel `100 + chord_index` on a completed chord, and `NOTE_OFF` when broken. | S | G1 | ☑ |
| R11 | F    | The system shall trigger a "full" effect on channel `50` when 12 or more keys are held at once. | C | G1 | ☑ |
| R12 | C    | The QLC+ workspace shall patch 4× BeamBar 10R (13-channel mode) + Generic RGB fixtures. | M | G1 | ☑ |
| R13 | F    | The QLC+ workspace shall map MIDI note input channels to per-beam DMX channels via virtual-console sliders. | M | G1 | ☑ |
| R14 | F    | The QLC+ workspace shall provide scenes (`haus*`, `par*`, `strobe*`) and RGBMatrix effects (`wave1/2`, `gewitter`, `rainbow`, red/green/blue chases). | S | G1 | ☑ |
| R15 | F    | The standalone build shall run from its own entry point (`python -m laserkbd`).      | M   | G2   | ☑    |
| R16 | F    | The MIDI thread shall select the keyboard by name and handle notes robustly: mask the MIDI channel (`status & 0xF0`), treat note-on velocity 0 as note-off, and guard the note range before indexing (folds in B1–B6). | M | G2 | ☑ |
| R17 | F    | The system shall hold thread-safe key state for 32 keys (`state.py`).                | M   | G2   | ☑    |
| R18 | F    | The DMX thread shall compute lighting and send ArtNet on one synchronized, free-running, configurable tick (monotonic deadline loop, `dmx_thread.py`). | M | G2 | ☑ |
| R19 | Q    | The tick rate shall be user-configurable and not capped at 44 Hz (the node forwards a reduced channel count). | S | G2 | ☑ |
| R20 | F    | ArtNet output shall support a configurable target — broadcast or a specific unicast IP — selectable from the web UI. | M | G2 | ☑ |
| R21 | F    | The system shall send on a configurable ArtNet universe.                             | M   | G2   | ☑    |
| R22 | F    | The web UI shall offer ArtPoll device discovery: a button lists replying nodes (ArtPollReply); selecting one uses its IP as the unicast target. | S | G2 | ☑ |
| R23 | F    | The fixture/DMX mapping (4× BeamBar 10R: base addresses 0/13/26/39, per-beam offsets) shall live in Python config, not QLC+. | M | G2 | ☑ |
| R24 | F    | The Flask web interface shall provide a live log view and a settings editor.         | M   | G2   | ☑    |
| R25 | F    | The system shall provide a dry-run mode (`--dry-run`): simulated keyboard + suppressed ArtNet, for testing the web UI without hardware. | S | G2 | ☑ |
| R26 | C    | Settings shall persist across restarts (config file on disk).                        | S   | G2   | ☑    |
| R27 | C    | The system shall run on boot as a systemd service (`laser-keyboard.service`) with MIDI auto-reconnect. | S | G2 | ☑ |
| R28 | F    | The system shall shut all threads down cleanly on stop (SIGINT/SIGTERM → stop event → join). | M | G2 | ☑ |
| R29 | Q    | The standalone build shall survive a USB disconnect of the MIDI keyboard: the MIDI thread shall catch the disconnect without crashing the process, release held key state so no beam stays stuck on, and auto-reconnect (by name) when the keyboard is replugged. | M | G2 | ☑ |
| R30 | Q    | The standalone build shall survive interruption of network access: ArtNet send errors (network down/host unreachable) shall be caught and logged without stalling or crashing the render loop, and output shall resume automatically when the network returns. | M | G2 | ☐ |
| R31 | Q    | The standalone build shall survive power loss: on power restoration the appliance shall boot and resume operation unattended (systemd auto-start), and the on-disk config shall not be left corrupt by an abrupt power cut (atomic write/replace). | M | G2 | ☐ |
| R32 | F    | The web UI shall list discovered MIDI input ports and let the user select one as the keyboard (sets `midi_port_name`). | S | G2 | ☑ |
| R33 | F    | The standalone build shall implement a simulated-piano decay effect: on note-on, the beam lights at full brightness and decays over time following an S-curve; MIDI velocity controls the decay duration (soft hit → fast decay, hard hit → slow decay, scaling over many seconds); on note-off the beam switches off immediately. | M | G2 | ☑ |
| R34 | F    | The standalone build shall count note-on events and log keypresses-per-minute with a timestamp to a log file, enabling post-night analysis of keyboard usage. | M | G2 | ☐ |
| R35 | Q    | The web UI shall be visually improved: better margins, typography, labelling, and overall layout. | S | G2 | ☐ |
| R36 | F    | The web UI shall display a time-series graph of keypresses per minute (X-axis: time, Y-axis: presses/min), drawn from the data logged by R34. | S | G2 | ☐ |
| R37 | F    | The web UI shall maintain a live WebSocket connection: active keys/laser states shall update in real time, and the log view shall stream new entries as they arrive. | C | G2 | ☐ |

**Standalone status note (R15–R32).** Milestone 1 was validated on real hardware
(Pi + keyboard + ArtNet node + BeamBar 10R) on 2026-06-24: keys drive the correct
beams, including the channel-1 per-beam mode fix (R23), with both unicast and broadcast
output (R20), a >44 Hz tick (R19), ArtPoll discovery (R22) and clean shutdown (R28).
R15–R29 and R32 are ☑ — the appliance now also runs on boot via systemd (R27,
validated after fixing the unit's `User=`) and survives a USB keyboard unplug (R29,
validated by a real unplug: laser switched off, then reconnected). Still open:
- **R30** — survive network interruption. ArtNet send errors are already caught in
  `artnet.ArtNetSender.send` (logged, loop keeps ticking), but this is not yet
  validated by actually downing the network/node.
- **R31** — survive power loss. Both mechanisms exist (atomic config write R26 ☑ +
  systemd auto-start R27 ☑); needs a pull-the-plug confirmation that it resumes clean.
Design home for R30–R31: the "Resilience" section in `reqs/G2.md`.
(There is no committed automated test suite; verification is by use + `--dry-run`.)

**R33 (simulated-piano decay).** Implemented: `state.py` stamps a monotonic onset on
each strike; `decay.py` holds the closed-form S-curve (smootherstep over a finite,
velocity-scaled duration → reaches exactly 0); `dmx_thread._render()` applies it per
beam each tick. Bounds are `decay_min_s`/`decay_max_s` in config (0.3 s soft → 8 s
hard). Verified via the render path (decay shape, instant note-off); on-hardware
feel-tuning of the bounds is expected. R34–R37 (usage logging, web polish/graph,
live WebSocket) remain ☐.

## Bugs
Deviations from a requirement. `Ref` = the requirement broken. All are in the **QLC+
build** (`qlcplus/laserkeyboard.py`); the standalone build (R16) fixes this class by
design but does not close them in the QLC+ build.

| ID | Bug                                                                                  | Ref | Sev | Done |
|----|--------------------------------------------------------------------------------------|-----|-----|------|
| B1 | note-on velocity 0 not treated as note-off → beam stuck on (matches status byte only, ignores velocity). `qlcplus/laserkeyboard.py:46-58` | R7 | Md | ☐ |
| B2 | Out-of-range notes fail silently: notes > 72 raise `IndexError` (swallowed); notes < 41 give a negative index NumPy wraps, lighting the wrong beam. No range guard. `qlcplus/laserkeyboard.py:48-53` | R5 | Md | ☐ |
| B3 | Redundant MIDI flood: every note event re-sends `NOTE_ON`/`NOTE_OFF` for all chord channels (100–107) and channel 50 regardless of state change, re-triggering functions and spamming loopMIDI. Needs edge detection. `qlcplus/laserkeyboard.py:60-74` | R6 | Lo | ☐ |
| B4 | Hardwired to MIDI channel 7: status bytes `150`/`134` only match channel 7; should mask the channel (`status & 0xF0 == 0x90` / `0x80`). `qlcplus/laserkeyboard.py:46` | R1 | Md | ☐ |
| B5 | Bare `except: pass` hides all errors, masking B1–B4; should at least log. `qlcplus/laserkeyboard.py:75-76` | R5 | Lo | ☐ |
| B6 | Connection check doesn't detect disconnects: `get_port_name(port)` returns a name by index even after the device is unplugged/reindexed, so auto-reconnect is largely cosmetic. `qlcplus/laserkeyboard.py:90`, `:107` | R3 | Md | ☐ |

---
*Pri:* M/S/C (must/should/could). *Sev:* Hi/Md/Lo. IDs are permanent — never reuse.
*Detail files: `reqs/<ID>.md` — see `reqs/G2.md` for the standalone build's design.*
*Work items live in `todo.md`.*
