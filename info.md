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
`python -m laserkbd` and serves a web UI on port 8080.

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
- There is no linter/CI; the QLC+ build is run by hand. The standalone build has a
  few dependency-free smoke tests you can run ad hoc.
- `.qxw` files are XML; they're normally edited inside the QLC+ app, but small,
  targeted edits by hand are fine if you preserve the structure.

## Reference

No bulky reference material is consolidated under `docs/` yet. Build-specific usage
lives in `qlcplus/README.md` and `standalone/README.md`.
