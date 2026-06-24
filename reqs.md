# laser-keyboard — Requirements

Status: Active · Updated: 2026-06-24 (R38–R41 added: standalone chords + effects)

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
| R30 | Q    | The standalone build shall survive interruption of network access: ArtNet send errors (network down/host unreachable) shall be caught and logged without stalling or crashing the render loop, and output shall resume automatically when the network returns. | M | G2 | ☑ |
| R31 | Q    | The standalone build shall survive power loss: on power restoration the appliance shall boot and resume operation unattended (systemd auto-start), and the on-disk config shall not be left corrupt by an abrupt power cut (atomic write/replace). | M | G2 | ☑ |
| R32 | F    | The web UI shall list discovered MIDI input ports and let the user select one as the keyboard (sets `midi_port_name`). | S | G2 | ☑ |
| R33 | F    | The standalone build shall implement a simulated-piano decay effect: on note-on the beam lights at full brightness and decays over time; the decay shape (linear or exponential) and its per-velocity time bounds (`t_min`/`t_max`) shall be selectable in the web UI and persisted (R24/R26); MIDI velocity controls the decay time (soft hit → fast decay, hard hit → slow decay); on note-off the beam switches off immediately. | M | G2 | ☑ |
| R34 | F    | The standalone build shall count note-on events and log keypresses-per-minute with a timestamp to a log file, enabling post-night analysis of keyboard usage. | M | G2 | ☐ |
| R35 | Q    | The web UI shall be visually improved: better margins, typography, labelling, and overall layout. | S | G2 | ☐ |
| R36 | F    | The web UI shall display a time-series graph of keypresses per minute (X-axis: time, Y-axis: presses/min), drawn from the data logged by R34. | S | G2 | ☐ |
| R37 | F    | The web UI shall maintain a live WebSocket connection: active keys/laser states shall update in real time, and the log view shall stream new entries as they arrive. | C | G2 | ☐ |
| R38 | F    | The standalone build shall detect chords — configured sets of key indices recognised as triggered when all their keys are held simultaneously (the standalone counterpart to R8/R9), evaluated from key state on each DMX tick with edge detection (trigger on completion, clear on release). | S | G2 | ☐ |
| R39 | F    | The standalone build shall provide a chord-triggered effects engine: a recognised chord (R38) activates a named effect that the DMX thread renders over all 40 beams (4 bars × 10), composited with the per-key beams; the effect deactivates when the chord is released. Effects are closed-form animations driven by elapsed time since trigger (like `decay.py`), so the renderer stays stateless. | S | G2 | ☐ |
| R40 | F    | The effects engine shall provide a "laser lightning" effect: while active, all 40 beams flash on/off at random and fast (re-randomised at a configurable flash rate, independent of the tick rate). | C | G2 | ☐ |
| R41 | F    | The effects engine shall provide a "left-right wave" effect: while active, beams light in quick succession left→right→left, each beam fading with a decay tuned so it is nearly fully decayed by the time the sweep returns to it. | C | G2 | ☐ |

**Standalone status note (R15–R32).** Milestone 1 was validated on real hardware
(Pi + keyboard + ArtNet node + BeamBar 10R) on 2026-06-24: keys drive the correct
beams, including the channel-1 per-beam mode fix (R23), with both unicast and broadcast
output (R20), a >44 Hz tick (R19), ArtPoll discovery (R22) and clean shutdown (R28).
R15–R32 are all ☑ — the appliance runs on boot via systemd (R27, validated after
fixing the unit's `User=`), survives a USB keyboard unplug (R29, validated by a real
unplug: laser switched off, then reconnected), and survives loss of the PoE cable
(R30 + R31, validated 2026-06-24). Because the Pi is PoE-powered, pulling the one
network cable cuts power and network together: ArtNet send errors are caught in
`artnet.ArtNetSender.send` so the render loop keeps ticking, and on replug the unit
boots unattended and resumes with an intact (atomically written) config. Milestone 1
is therefore complete; remaining standalone work is Milestone 2 (effects) plus the
new R34–R37. Design home for the resilience items: the "Resilience" section in
`reqs/G2.md`. (There is no committed automated test suite; verification is by use +
`--dry-run`.)

**R33 (simulated-piano decay).** Implemented: `state.py` stamps a monotonic onset on
each strike; `decay.py` holds the closed-form curve; `dmx_thread._render()` applies
it per beam each tick. The shape is selectable via `decay_mode` (`"exponential"` =
`master · 2^(−elapsed/t)`, halving every `t` and rounding to 0 in the tail;
`"linear"` = ramp from full to 0 over `t`). `t` scales with velocity between
`decay_t_min_s`/`decay_t_max_s` (0.2 s soft → 1.0 s hard; for exponential `t` is the
half-life, so ~50% brightness ~1 s after a full-velocity hit). All three are editable
in the web UI and persisted. We started with a smootherstep S-curve but dropped it
after on-hardware testing — the keyboard tends to fire full velocity and the S-curve's
flat top hid the decay. **Confirmed working on hardware (2026-06-24)** in exponential
mode. R34–R37 (usage logging, web polish/graph, live WebSocket) remain ☐.

**R38–R41 (standalone chords + effects).** Milestone 2's first slice: bring chord
handling — present in the QLC+ build as R8–R11 — into the standalone build, plus a
small effects engine and the first two effects (laser lightning, left-right wave).
Design home: the "Milestone 2 — effects" section in `reqs/G2.md`, which also covers
how effects address the full 40-beam array (vs. the 32 playable keys), how they
composite with per-key beams, and the open decisions (chord definitions, chord→effect
mapping, web-UI exposure). The full-keyboard (12+ keys) bonus (QLC+ R11) is a
later slice and stays a `todo.md` item for now.

**Implemented (2026-06-24), pending hardware confirmation.** `effects.py` (closed-form
lightning + wave), `config.chords` + effect params, `fixtures.all_beam_channels` /
`all_bar_bases` (full 40-beam addressing) + a widened `universe_size`, and
`DmxThread._update_chords` / `_overlay_effects` (edge-detected chords, max-composite
overlay). The four numeric effect params are live-editable in the web UI; the chord→effect
map is `config.json`-only for now. Verified by dry simulation (chord trigger/clear edges,
both effects' output, frame compositing); **not yet run on the Pi + bars** — boxes stay ☐
until confirmed on hardware (as R33 was). NOTE: because effects address all 40 beams,
the ArtNet node must forward ≥52 channels (up from the key-only ~44).

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
