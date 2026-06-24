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
tick, so a beam is lit only if it is written this tick — released beams fall to off
with no per-frame persistence. Each tick it sets every active bar's channel 1 to
per-beam mode (see the BeamBar note below), then drives the per-key beams via the
**simulated-piano decay** (R33):

- `state.py` stores, per key, the held velocity (`0` = released) **and** a
  `time.monotonic()` onset stamped on each strike (re-pressing a held key resets the
  onset → re-struck string). Velocity and onset are snapshotted together under one
  lock so the renderer never pairs mismatched values.
- `decay.py` is the pure curve: brightness `= master · (1 − smootherstep(elapsed /
  duration))`, where `duration` scales linearly with velocity between
  `decay_min_s` and `decay_max_s`. Smootherstep over a **finite** duration is an
  S-curve that reaches exactly 0, so the beam truly goes dark; it's evaluated
  closed-form each tick (no integrated state), making it jitter-proof and instantly
  responsive to a live config change. (This is a stylized look — a real piano string
  decays exponentially, the opposite shape near t=0 — but R33 specifies an S-curve.)
- **Note-off is immediate:** release sets velocity to 0, and the renderer skips
  velocity-0 keys, so the beam switches off at once regardless of the decay. A key
  held past its full decay also reads 0 (the string went silent while held).

The `now` passed into `_render()` is a `time.monotonic()` reading from the loop —
the same clock `state.py` stamps onsets with, so `elapsed = now − onset` is correct
and immune to wall-clock jumps.

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
