# Requirements & Tracking

Single source of truth for requirements, goals, todos and bugs. Update this file as
development progresses: add new requirements as they are conceived, check them off as
they ship, and log bugs as they are found and fixed.

Status legend: `[x]` done · `[ ]` open · `[~]` in progress

## Requirements

### MIDI bridge
- [x] Read note input from a MIDI keyboard
- [x] Forward a cleaned note stream to QLC+ via a virtual MIDI port (loopMIDI)
- [x] Auto-connect on startup and poll/reconnect once per second if a port drops
- [x] Exit cleanly on Ctrl+C, closing both MIDI ports

### Per-key laser control
- [x] Map each playable key to one individual laser beam (32 keys, notes 41–72,
      offset −41 into a 0–31 index range)
- [x] On key press, send `NOTE_ON` on the key's beam channel to QLC+
- [x] On key release, send `NOTE_OFF` on the key's beam channel

### Chord detection (bonus effects)
- [x] Define chords as sets of key indices (`A1`, `B1`, `C1`, `D1`, `E1`, `F1`,
      `G1`, `F2`)
- [x] Detect when all keys of a chord are held simultaneously
- [x] On a completed chord, send `NOTE_ON` on channel `100 + chord_index` to trigger
      the matching QLC+ effect; send `NOTE_OFF` when the chord is broken

### Full-keyboard bonus
- [x] When 12 or more keys are held at once, trigger a "full" effect on channel `50`

### QLC+ side (`laserkeyboard.qxw`)
- [x] Patch 4× BeamBar 10R laser bars (13-channel mode) + Generic RGB fixtures
- [x] Map MIDI note input channels to per-beam DMX channels via virtual-console sliders
- [x] Provide scenes (`haus*`, `par*`, `strobe*`) and RGBMatrix effects (`wave1/2`,
      `gewitter`, `rainbow`, red/green/blue chases)

## Bugs

### Open
- [ ] **note_on velocity 0 not treated as note-off** — keyboards that send
      "note on, velocity 0" on release leave the beam stuck on. Match on status byte
      only ignores velocity. (`qlcplus/laserkeyboard.py:46-58`)
- [ ] **Out-of-range notes fail silently** — notes > 72 raise `IndexError` (dropped
      by the bare `except`); notes < 41 produce a negative index that NumPy wraps,
      silently lighting the wrong beam. No range guard before indexing `keys`.
      (`qlcplus/laserkeyboard.py:48-53`)
- [ ] **Redundant MIDI flood / function retriggering** — every note event re-sends
      `NOTE_ON`/`NOTE_OFF` for all chord channels (100–107) and channel 50 regardless
      of state change, re-triggering active QLC+ functions and spamming loopMIDI.
      Needs edge detection (only send on transitions). (`qlcplus/laserkeyboard.py:60-74`)
- [ ] **Hardwired to MIDI channel 7** — status bytes `150`/`134` only match channel
      7; should mask the channel (`status & 0xF0 == 0x90` / `0x80`).
      (`qlcplus/laserkeyboard.py:46`)
- [ ] **Bare `except: pass` hides all errors** — masks the bugs above; should at
      least log. (`qlcplus/laserkeyboard.py:75-76`)
- [ ] **Connection check doesn't detect disconnects** — `get_port_name(port)` looks
      up a name by index and returns a value even after the device is unplugged or
      reindexed, so auto-reconnect is largely cosmetic.
      (`qlcplus/laserkeyboard.py:90`, `:107`)

### Won't fix / by design
- Velocity is discarded (always forwards 127). Acceptable while beams are on/off only.

## Goals / Todos

### Standalone Raspberry Pi ArtNet version (v2)

Make the laser keyboard a self-contained appliance that needs no PC running QLC+.
A Raspberry Pi 3B+ (PoE) lives inside the keyboard enclosure; the keyboard connects
to the Pi over USB, and the whole unit reaches the rest of the installation over a
single network cable (PoE = power + data). The Python script generates **ArtNet**
(DMX-over-UDP) directly, replacing QLC+ + loopMIDI + the DMX-USB interface.

This is a **new script**, separate from `laserkeyboard.py` (the existing QLC+ build
stays as-is for reference / fallback). The new build also folds in the bug fixes
listed above so they aren't reintroduced.

**Architecture**
- **MIDI thread** — open the keyboard, read note on/off, maintain key state.
- **DMX thread** — runs on a **free-running, configurable tick**. Lighting
  calculation and ArtNet send happen together on the same tick (in sync), so every
  computed frame is the frame that goes out — no drift between animation and output.
  Use a monotonic deadline loop so timing doesn't drift; aim for reasonably steady
  ticks rather than hard real-time (see jitter budget below). (Outputting a full
  frame every tick also makes the QLC+ "redundant-message" bug moot by design.)
- **Tick rate may exceed the ~44 Hz DMX ceiling.** The target ArtNet node can be
  configured to send fewer DMX channels per universe, which raises the achievable
  DMX refresh rate above the standard 512-channel limit. The Python tick rate is
  therefore a free choice, bounded by the node's channel count and the Pi's CPU, not
  by a hardcoded 44 Hz. **Target: ~100 Hz.**
- **Jitter budget is generous — don't over-engineer.** At ~100 Hz (10 ms period),
  even ±50% jitter (±5 ms) is imperceptible for this installation, so heavy
  real-time measures (PREEMPT_RT kernel, `isolcpus`, core pinning) are **out of scope
  unless problems actually appear**. "Reasonable" effort only: a monotonic
  deadline-based loop, keep the DMX tick lean, and avoid obvious GIL stalls.
- **Web thread (Flask)** — small interface to edit settings and view logs.
- Thread-safe shared state (key state + settings) with a lock or queue; config
  persisted to disk so settings survive a restart.

**Milestone 1 — per-key beams over ArtNet** (effects deferred, see Milestone 2)

Scaffolding is in place under `standalone/` (package `laserkbd`); `[~]` items have a
working skeleton, verified by compile + unit smoke tests, but still need validation
on real hardware (Pi + keyboard + ArtNet node). `[ ]` items are not done.

- [~] New standalone script with its own entry point (`python -m laserkbd`)
- [~] MIDI thread: select keyboard by name; robust note handling — mask the MIDI
      channel (`status & 0xF0`), treat note-on velocity 0 as note-off, guard the
      note range before indexing (folds in the open bugs above)
- [~] Thread-safe key state (32 keys) (`state.py`)
- [~] DMX thread: lighting calculation + ArtNet send on one synchronized,
      free-running, configurable tick (monotonic deadline loop, `dmx_thread.py`)
- [~] Tick rate is user-configurable and not capped at 44 Hz (the node can send a
      reduced channel count to allow higher refresh rates)
- [~] ArtNet output: configurable target — **broadcast** or a specific **unicast
      IP**, selectable from the web UI
- [~] Configurable ArtNet **universe** to send on (verified packet split)
- [~] ArtPoll **device discovery** — a web-UI button sends an ArtPoll and lists all
      nodes that reply (ArtPollReply); selecting a device uses its IP as the unicast
      target (needs a real node to validate discovery)
- [~] Fixture/DMX mapping in config — the 4× BeamBar 10R addressing (base addresses
      0/13/26/39, per-beam channel offsets) now lives in Python, not QLC+
- [~] Flask web interface: live log view + settings editor
- [x] Settings persisted across restarts (config file on disk, round-trip tested)
- [~] Run on boot as a systemd service (`laser-keyboard.service`); MIDI auto-reconnect
- [~] Clean shutdown of all threads on stop (SIGINT/SIGTERM -> stop event -> join)

Remaining before Milestone 1 can be called done: end-to-end test on the Pi with a
real keyboard and ArtNet node, and confirm the chosen ArtNet approach (raw sockets
here) works with the actual node and discovery.

**Milestone 2 — effects (deferred)**
- [ ] Chord-triggered effects, rendered in Python in the DMX thread
- [ ] Full-keyboard (12+ keys) bonus effect
- [ ] Effect parity with the old QLC+ set as desired (waves, rainbow, gewitter,
      strobe, chases) via a small effects engine

**Open decisions** (resolve during implementation)
- ArtNet library — must support sending DMX **and** ArtPoll/ArtPollReply discovery
  (or fall back to hand-rolling ArtPoll). Candidate: `stupidArtnet`; confirm it can
  receive ArtPollReply, otherwise add a small raw-UDP poller. TBD.
- Settings exposed in the web UI — at least: ArtNet target mode (broadcast/unicast),
  selected/entered unicast IP, universe, tick rate, fixture base addresses, master
  brightness, MIDI device selection, log level.
- Config file location and format (e.g. JSON/YAML next to the script).
- Whether to run Flask in a separate thread (simplest) or separate process — given
  the generous jitter budget, a thread is likely fine; revisit only if the web UI
  visibly disturbs the tick.

**Decided**
- Language: **Python** — no rewrite in C/Go/Rust. Stick with the existing stack and
  do reasonably well on timing rather than over-optimizing.
- Target tick rate **~100 Hz**, user-configurable. Generous jitter budget (±50% is
  imperceptible here), so no hard-real-time work unless problems show up.
- Milestone 1 ships per-key beams only; effects come later (Milestone 2).
- Web stack: Flask.
- ArtNet target is selectable between broadcast and a specific unicast IP; the IP can
  be entered directly or picked from an ArtPoll discovery list. Universe is
  configurable.
