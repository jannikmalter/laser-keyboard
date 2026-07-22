# laser-keyboard — Internal documentation

Auto-loaded with `CLAUDE.md`. How this project works, for anyone editing it.
For requirements/status see `reqs.md`; for the outward overview see `README.md`.

## What this is

An interactive lighting installation. A person plays a **MIDI keyboard**; a Python
program interprets the notes so that each key lights one individual **laser beam**,
and certain chords trigger bonus effects.

There are **two builds** of the same installation:

- **`qlcplus/`** — the original, PC-tethered build. Python cleans up the keyboard's
  MIDI and forwards it to **QLC+**, which owns the fixtures, effects and DMX output.

  ```
  MIDI keyboard ──► qlcplus/laserkeyboard.py ──► loopMIDI ──► QLC+ ──► DMX (USB) ──► laser bars
  ```

- **`standalone/`** — the self-contained rewrite. A Raspberry Pi 3B+ inside the
  keyboard enclosure runs the `laserkbd` package and emits **ArtNet** directly — no
  PC, no QLC+. Three threads: MIDI input, a ~100 Hz DMX/ArtNet render loop, and a
  Flask web UI. In development (Milestone 1); see `reqs.md`.

  ```
  MIDI keyboard ──USB──► Raspberry Pi (laserkbd) ──ArtNet/UDP──► node ──DMX──► laser bars
  ```

## Architecture / repository layout

```
qlcplus/      laserkeyboard.py (MIDI bridge) + laserkeyboard.qxw (QLC+ workspace) + requirements.txt
standalone/   laserkbd package, requirements.txt, systemd unit — the ArtNet build
reqs.md       requirements, roadmap and bug tracker for both builds
```

The QLC+ side does **not** speak DMX: `laserkeyboard.py` only emits a cleaned-up MIDI
note stream, and all fixture patching, scenes, effects and the MIDI→DMX mapping live
in `qlcplus/laserkeyboard.qxw`. The standalone build replaces that whole chain with
Python + ArtNet (the fixture mapping moves into `standalone/laserkbd/`).

## Running it

**QLC+ build** (`qlcplus/`) — requires Windows with
[loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) running and QLC+
open with `laserkeyboard.qxw`:

```bash
cd qlcplus
pip install -r requirements.txt
python laserkeyboard.py
```

Ports are hard-coded by index near the top of `qlcplus/laserkeyboard.py`:
`midi_in_port = 0` (the keyboard) and `midi_out_port = 2` (loopMIDI). These indices
depend on the machine's MIDI device order and often need adjusting on a new setup.
The script polls once per second and auto-reconnects if a port drops.

**Standalone build** (`standalone/`) — see `standalone/README.md`; runs with
`python -m laserkbd` and serves a web UI on port 8088 (configurable via `web_port`).
On Linux/Pi, `python-rtmidi` compiles from source and needs the ALSA dev headers plus
a C toolchain first (`sudo apt install libasound2-dev pkg-config build-essential
python3-dev`); without them `pip install` fails with `Dependency "alsa" not found`.
Not needed for `--dry-run` (rtmidi isn't imported) or on Windows (prebuilt wheels).
This is a setup prerequisite for R27 (run on the Pi); see `standalone/README.md`.

## How the standalone render works

The render loop in `dmx_thread._render()` rebuilds a **fresh zeroed** DMX frame every
tick, so a beam is lit only if it is written this tick — a fully-decayed beam is simply
not written, so it's off, with no per-frame persistence. Each tick it sets every active
bar's channel 1 to per-beam mode (see the BeamBar note below), then drives the per-key
beams via the **simulated-piano decay** (R33):

- `state.py` stores, per key, the strike velocity (`1–127`), a `time.monotonic()` onset
  stamped on each strike (re-pressing a held key resets the onset → re-struck string),
  **and** a separate `held` flag that is true only while the key is physically pressed.
  Velocity/onset are kept even after release (only `held` clears) so the beam keeps
  decaying past note-off (see the note-off bullet). All three are snapshotted together
  under one lock so the renderer never pairs mismatched values; `held` (not velocity)
  is what drives chord detection, held-count and the input-row viz.
- `decay.py` is the pure curve, evaluated closed-form each tick (no integrated
  state), so it's jitter-proof and instantly responsive to a live config change. The
  shape is selectable via `decay_mode`:
  - **exponential** (default): `master · 2^(−elapsed / t)` — halves every `t`,
    rounds to 0 in the tail (so a held key reads off without an explicit cutoff).
  - **linear**: ramps straight from `master` to 0 over `t`, then off.

  `t` scales linearly with velocity between `decay_t_min_s` and `decay_t_max_s`
  (0.2 s soft → 1.0 s hard; for exponential `t` is the half-life, so ~50% brightness
  ~1 s after a full-velocity hit). All three are editable in the web UI and persisted.
  (We started with a smootherstep S-curve but switched: the keyboard tends to send
  full velocity and the S-curve's flat top hid the decay.)
- **Note-off keeps fading:** release does **not** cut the beam. `release()` only clears
  the `held` flag; velocity/onset persist, so the renderer keeps evaluating the same
  decay curve and the fade plays out to off exactly as for a held key. A key held (or
  released) past its full decay reads 0 (the string went silent). On MIDI disconnect
  `release_all()` clears the held flags and the beams fade out — nothing stays stuck on
  (R29). (This replaced the earlier immediate-off behaviour on 2026-07-20, by request.)

The `now` passed into `_render()` is a `time.monotonic()` reading from the loop —
the same clock `state.py` stamps onsets with, so `elapsed = now − onset` is correct
and immune to wall-clock jumps.

## Chord-triggered effects (R38–R41)

After the per-key beams, `_render()` overlays **chord-triggered effects** — the
standalone counterpart to the QLC+ chord handling, but rendered in Python.

- **Detection (`chords.py` + `_update_effects`).** Detection is by chord **quality**, not
  a fixed key set. `chords.quality(held)` reduces the held keys to distinct pitch classes
  (mod 12) and returns `"major"` ({root, +4, +7}), `"minor"` ({root, +3, +7}) or `None` —
  so *every* major chord (any root, any inversion/voicing, octave doublings folded in)
  reads as major and every minor chord as minor. It's a plain triad only: exactly three
  distinct pitch classes, so a fourth (e.g. a seventh) cancels it, and aug/dim/sus match
  neither. (Major vs minor share the unordered gap set {3,4,5}; `quality` tells them apart
  by testing each rotation for the ordered pair (4,3)→major or (3,4)→minor.) `config
  .chord_effects` maps the quality name → effect name (default `major → wave`,
  `minor → lightning`). Each tick `_update_effects` edge-detects: the held quality maps to
  at most one effect; when that effect first becomes active it's stamped with the current
  monotonic time in `DmxThread._active_effects` (effect name → trigger time), and it's
  dropped when the chord breaks or its quality changes. That trigger time is **the only
  effect state the DMX thread keeps** — the effects themselves are closed-form over
  `now − trigger`. (At most one quality is held at once, so at most one effect is active.)
- **Effects (`effects.py`).** Like `decay.py`, each effect is a pure function of
  elapsed time → a per-beam brightness array over **all 40 beams** (4 bars × 10), not
  just the 32 playable keys. `effects.render(name, elapsed, beam_count, cfg)` dispatches:
  - **`"lightning"`** (R40): all beams flash on/off at random. RNG is seeded by the
    flash-window index `int(elapsed · lightning_flash_hz)`, so the pattern is fixed
    within one flash and identical regardless of `tick_hz`. `lightning_on_fraction`
    sets how many beams are lit per flash.
  - **`"wave"`** (R41): a triangle "head" sweeps beam 0 → max → 0 over `wave_period_s`,
    each beam fading exponentially since the head last passed it. Both passes per cycle
    (rightward at phase `f/2`, leftward at `1 − f/2`) are computed closed-form, so the
    trailing comet is exact; `wave_decay_s ≈ wave_period_s` leaves a beam nearly off by
    the time the head returns.
- **Overlay (`_overlay_effects`).** Effects can light any bar, so it drives **all**
  bars' channel 1 to per-beam mode (`fixtures.all_bar_bases`) and writes onto the full
  beam set (`fixtures.all_beam_channels`). It **max-composites** per channel, so a held
  per-key beam still reads through a sparse effect. Because effects address all 40
  beams, `fixtures.universe_size()` now spans every beam (≈52 channels) — the ArtNet
  node must be configured to forward at least that many channels.
- **Config / web UI.** `chord_effects` (the quality→effect map) lives in `config.json`
  only for now; the numeric effect params (`lightning_flash_hz`, `lightning_on_fraction`,
  `wave_period_s`, `wave_decay_s`) are in the web settings editor and persisted, so the
  look can be tuned live on hardware. The full-keyboard (12+ keys) bonus is not built
  yet (`TODO(milestone-2)` in `_render`).

## Web UI & live visualisation (R35/R37)

The Flask page (`web.py`) is a single server-rendered dark page (vanilla JS only, no
framework). Settings are grouped into labelled sections from `_GROUPS` (each field
carries a human label + a unit hint); `_EDITABLE` — the name→caster map the POST
handler uses — is derived from `_GROUPS`, so adding a setting is one entry.

The page shows three stacked viz rows (top → bottom): a **40-beam laser-output row** (one
red dot per beam, brightness driven live), a **32-key input row** (lit when a key is held),
and a **chord row** (one button per configured chord). The top two strips update live over
two WebSockets, registered via **flask-sock** in `_register_websockets` (skipped with a
warning if flask-sock is absent — the page then just shows its page-load snapshot):

- **`/ws`** streams the live frame at the full tick rate. Each tick — **only while a
  browser is watching** (`LiveBus.active()`, so a normal show with no UI open adds nothing
  to the render loop) — the DMX thread calls `_publish_live`. `active()` is a **ref-count
  of connected `/ws` clients** (the handler calls `add_consumer()`/`remove_consumer()`
  around its loop), *not* a "recently published" heuristic — so while a browser is
  connected the thread publishes on **every** tick even through an idle spell, and a strike
  after silence shows up at once (was B8: the old `_last_wait`-TTL gate went stale during
  the WS handler's 10 s idle wait and the feed took up to 10 s to resume). `_publish_live`
  packs **key velocities** (the input, from `state.snapshot()`) and the **40 beam
  brightnesses** (the
  output, read back out of the just-rendered DMX frame so decay + effects are included)
  via `live.encode_frame` → a 74-byte message `[K][32 velocities][B][40 brightnesses]`. It
  posts to a `LiveBus` (`live.py`): a latest-frame condition-variable pub/sub that **drops
  identical frames** (an idle keyboard → no traffic) and wakes the WS handler, which sends
  on change (and resends as a keepalive every 10 s so a dead client is noticed). At 100 Hz
  this is ~7 kB/s — far below ArtNet. The browser keeps only the newest frame and paints
  it on `requestAnimationFrame`, decoupling the tick rate from the ~60 Hz display.
- **`/logs`** streams new log lines as JSON. `RingBufferHandler` (`log_buffer.py`) gained
  a monotonic counter + a blocking `wait_since(last_total, timeout)`; the page renders the
  backlog server-side and the socket appends lines emitted after connect (auto-scrolls if
  already at the bottom).

The header dot is a connection indicator (grey → red when `/ws` is open); both sockets
auto-reconnect after 1 s. The `LiveBus` is created in `__main__`, handed to both the
`DmxThread` (publisher) and `create_app` (consumer). Works under `--dry-run` too, so the
visualisation can be exercised without hardware.

### Interactive input (R42)

The viz is also an **input**: the page plays the same `KeyState` the MIDI thread drives,
so a mouse/touch press is indistinguishable downstream from a physical key — decay, chord
detection and effects all just work.

- **Backend.** Each event is `{"keys":[idx,...], "down":bool, "velocity":int}` applied by
  the shared `_apply_input(state, data)` helper, which calls `state.press(idx, velocity)` /
  `state.release(idx)` for each index (those already guard the range); a chord is simply its
  constituent keys. Mouse has no velocity, so the client sends a fixed medium-hard strike
  (`INPUT_VELOCITY = 100`). Two transports feed the same helper: the **`/input` WebSocket**
  (preferred, registered in `_register_websockets`) and a **`POST /input`** fallback used
  only when flask-sock is absent or the socket is down. The WebSocket was the fix for **B9**:
  with POST, a glissando fired two requests per key crossed and werkzeug logged every one at
  INFO; those access-log lines streamed back over `/logs` into the browser's log box (an
  unbounded `textContent +=`), bogging the page down the longer you played. The WebSocket
  produces no access log; werkzeug's logger is also pinned to WARNING in `setup_logging`, and
  the client caps the log box at 500 lines — three independent guards against that flood.
- **Key row** (`#keys .beam`, each tagged `data-i`): `pointerdown` captures the pointer and
  strikes the key under it; `pointermove` while held slides the strike — **one key at a
  time**, releasing the one left and striking the one entered (a glissando). `pointerup`/
  `pointercancel` on `window` ends the drag and releases. The cells are full-height so the
  hit target is the whole row (it no longer grows-on-press like the old bar viz).
- **Chord row** (`.chord` buttons): since detection is now quality-based (R38) there's no
  fixed chord list, so `render()` builds one **example triad per configured quality** from
  `cfg.chord_effects` — `{idxs, name}` (e.g. `major → wave` on keys `0·4·7`, `minor →
  lightning` on `0·3·7`; `idxs`/`name` dodge Jinja resolving `chord.keys` to the dict's
  `.keys` method). Holding a button presses those keys (so the held triad triggers its
  effect exactly as a MIDI-played one would); releasing or sliding off (`pointerleave`)
  releases them. Any transposition of the example would trigger the same effect.
- **Stuck-key safety:** a press that never gets its release (tab closed mid-drag) is
  self-healing — a held key still decays to off in the renderer (R33), and physical play or
  a reload clears the state — so no explicit server-side timeout is needed.

There is **no new visualisation state**: the live `/ws` feed paints the pressed keys/beams
back, so the click and the lit beam are the same round trip the MIDI path uses.

## All-lasers-on setup toggle (R43)

For aiming and positioning the bars you need every beam lit regardless of what's being
played. The **"All on" button** next to the Lasers row `POST`s `/lasers/all-on`, which
flips a transient `threading.Event` (`DmxThread._all_on`) and returns `{on: bool}` so the
button reflects the state. While set, `_render` calls `_light_all` **last** (after per-key
beams and effects), driving all four bars to per-beam mode and every one of the 40 beam
channels to `master_brightness`, so it overrides everything. It is deliberately **not** in
`Config` — it must never persist across a restart (a booted appliance must not come up with
all lasers on). No extra viz plumbing: the live `/ws` feed reads beams back out of the
rendered frame, so the laser row lights up as confirmation. Works under `--dry-run`.

## Keypress usage logging & graph (R34/R36)

`usage.py` records how much the keyboard is played, for post-night analysis, and feeds a
graph on the web page.

- **Counting.** `UsageLog.record()` bumps a per-minute counter. It's wired to
  `KeyState.on_press` (a new optional callback fired once per in-range strike, **outside**
  the state lock so it can take its own lock without nesting), so *every* note-on is counted
  at the single `state.press()` choke point — physical MIDI and the virtual web keyboard
  (R42) alike. Note-off is not a keypress, so only strikes count; a re-struck held key
  counts again (it's a new note-on).
- **Per-minute flush.** A dedicated thread (`UsageLog.run()`, started and joined in
  `__main__` under the shared `stop_event`, R28) sleeps to each wall-clock minute boundary,
  then snapshots+resets the counter and appends one line
  `YYYY-MM-DD HH:MM\tcount` to the log file. Timestamps land on `:00`; the partial minute
  in progress at shutdown is dropped (an incomplete count would skew the graph).
- **File + in-memory series.** The file is append-only (a 3-day night ≈ 4320 lines; not
  rotated). The same series is held in memory (a deque capped at 14 days) and **loaded from
  the file on startup**, so a restart mid-run keeps the history. The log path is
  `config.keypress_log_file` (default `keypresses.log` next to `config.json`; relative paths
  resolve there). It is **config-only, not in the web form**: `UsageLog` captures the path
  at startup, so editing it live wouldn't move existing data.
- **Web graph.** `GET /usage.json` returns `{"points": [[epoch_ms, count], ...]}` (oldest
  first). The page draws it as an **inline-SVG** area+line chart built with vanilla JS
  (`drawUsage`) — **no external chart library**, so it works with no internet access. It's
  refetched every 60 s (a new point per minute) and redrawn on resize; the caption shows
  total presses and peak/min. Works under `--dry-run` too (the simulated keyboard drives
  `state.press`, so the counter and graph populate without hardware).

## How the QLC+ mapping works

- **Note offset:** incoming notes are shifted by `-41` so the playable range becomes
  indices `0..31` in the `keys` array (32 keys → 32 individual laser beams).
- **Status bytes:** the keyboard sends on MIDI channel 7, so note-on arrives as
  status `150` (0x96) and note-off as `134` (0x86). These exact values are matched
  explicitly — a different keyboard/channel will send different status bytes.
- **Per-key beams:** on note-on the script forwards `NOTE_ON [note, 127]` to QLC+,
  which maps each note channel to a virtual-console slider driving one beam's DMX
  channel (see the `<Slider>` / `<Input ... Channel=...>` entries in the `.qxw`).
- **Chord detection:** `ACCS` lists chords as triples of key indices (`A1`, `B1`,
  ... `F2`). The numpy step (`accords - keys*accords`, summed and clipped) yields 0
  for a chord only when **all** its keys are held. A completed chord sends `NOTE_ON`
  on channel `offset + i` (`offset = 100`, so channels `100..107`) to fire the
  matching QLC+ effect; releasing it sends `NOTE_OFF`.
- **Bonus:** holding **12+ keys** at once triggers channel `50` (a "full" effect).

The QLC+ side groups the four `BeamBar 10R` fixtures (13-channel mode, 10 beams
each) into the `bars` fixture group, plus Generic RGB fixtures, and provides scenes
(`haus*`, `par*`, `strobe*`) and RGBMatrix effects (`wave1/2`, `gewitter`,
`rainbow`, red/green/blue chases).

## Conventions / gotchas

- In the QLC+ build, `midi_event()` wraps its whole body in a bare `try/except: pass`,
  so MIDI parsing errors are silently swallowed. Keep this in mind when debugging — a
  malformed message or an out-of-range note index just disappears. (The standalone
  build fixes this class of bug by design.) Tracked as B1–B6 in `reqs.md`.
- There is no linter, CI, or committed test suite; both builds are run by hand. The
  standalone build can be byte-compiled (`python -m compileall standalone/laserkbd`)
  and exercised end to end with `python -m laserkbd --dry-run` (no hardware needed).
- `.qxw` files are XML; they're normally edited inside the QLC+ app, but small,
  targeted edits by hand are fine if you preserve the structure.

## Reference

- **`docs/laserworld-beambar-10r-mk3-manual.pdf`** — the Laserworld BeamBar 10R MK3
  manual (EN/DE/FR). The DMX-relevant parts are extracted just below; read the PDF
  for safety, mounting, master/slave and menu details.
- Build-specific usage lives in `qlcplus/README.md` and `standalone/README.md`.

### BeamBar 10R MK3 — DMX control chart (13 channels)

Each bar occupies **13 DMX channels** and has **10 laser beams**. From the manual's
"DMX Control Chart" / "Tabelle zur DMX-Ansteuerung" (p. 10 EN / p. 18 DE):

| Ch | Value   | Function                                                    |
|----|---------|-------------------------------------------------------------|
| 1  | 0–49    | laser off                                                   |
| 1  | 50–99   | sound-to-light mode                                         |
| 1  | 100–149 | automatic mode                                              |
| 1  | 150–199 | **DMX mode** — channels 2→3 valid (program/effect playback) |
| 1  | 200–255 | **DMX mode** — channels 4→13 valid (per-beam control)       |
| 2  | 0–255   | program / effect selection                                  |
| 3  | 0–255   | speed (slow→fast, 21 levels)                                |
| 4  | 0–255   | beam 1 brightness (weak→bright)                             |
| 5  | 0–255   | beam 2 brightness                                           |
| 6  | 0–255   | beam 3 brightness                                           |
| 7  | 0–255   | beam 4 brightness                                           |
| 8  | 0–255   | beam 5 brightness                                           |
| 9  | 0–255   | beam 6 brightness                                           |
| 10 | 0–255   | beam 7 brightness                                           |
| 11 | 0–255   | beam 8 brightness                                           |
| 12 | 0–255   | beam 9 brightness                                           |
| 13 | 0–255   | beam 10 brightness                                          |

Channels 4–13 each drive **one laser output, left to right (front view)**.

**Critical for per-beam control (channel 1 = mode select):** the per-beam brightness
channels (4–13) are honoured **only when channel 1 is set to 200–255**. At the
default value 0 the bar is in "laser off" mode and ignores the beam channels. The
standalone build handles this: every frame, `dmx_thread._render()` drives each active
bar's channel 1 to `fixtures.DMX_MODE_PER_BEAM` (255) — see `fixtures.active_bar_bases()`.
Adjacent bars must not overlap this 13-channel block (base addresses 0/13/26/39 give
four non-overlapping bars).

**Addressing:** set each bar's DMX start address in its menu (`Addr` → `A001`…). The
standalone config models this as `bar_base_addresses` (0-based: address `A001` = index
0), with channel 1 at the base index (the mode channel) and beams at
`beam_channel_offset` (3) → channels 4–13.

### Technical data (from the manual, p. 28)

- **BeamBar 10R MK3:** 10× 120 mW red (638 nm), 1.200 mW total guaranteed output.
- Laser class **3B**; beam 3 mm / 1.1 mrad.
- Power: 100–250 V AC, 50/60 Hz, 50 W, fuse 3 A/250 V.
- Dimensions 1000 × 160 × 80 mm; weight 9 kg. Indoor use only.
