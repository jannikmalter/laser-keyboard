# CLAUDE.md

Guidance for working in this repository.

## What this is

An interactive lighting installation. A person plays a **MIDI keyboard**; a Python
script interprets the notes and drives **laser bars** (and bonus effects) through
**QLC+** (Q Light Controller Plus). Each keyboard key maps to one individual laser
beam. As a bonus, the script detects when certain chords are played and triggers
extra QLC+ effects.

```
MIDI keyboard ──► Python (laserkeyboard.py) ──► loopMIDI (virtual MIDI cable) ──► QLC+ ──► DMX (USB) ──► laser bars + RGB fixtures
```

The Python script does **not** speak DMX. It only translates keyboard input into a
cleaned-up MIDI note stream that QLC+ consumes as its input. All fixture patching,
scenes, effects and the MIDI→DMX mapping live in the QLC+ workspace (`.qxw`).

## Files

- **`laserkeyboard.py`** — the script that runs the installation. Edit this for
  behavior changes.
- **`laserkeyboard.qxw`** — the QLC+ workspace (open in QLC+ 4.13+). Defines the
  fixtures, virtual console, scenes, RGB matrix effects, and the MIDI input → DMX
  channel mapping.

These two files are the whole project.

## Running it

Requires Windows with [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html)
running (provides the virtual MIDI port) and QLC+ open with `laserkeyboard.qxw`.

```bash
pip install -r requirements.txt
python laserkeyboard.py
```

Ports are hard-coded by index near the top of `laserkeyboard.py`:
`midi_in_port = 0` (the keyboard) and `midi_out_port = 2` (loopMIDI). These indices
depend on the machine's MIDI device order and often need adjusting on a new setup.
The script polls once per second and auto-reconnects if a port drops.

## How the mapping works

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

## Notes / gotchas

- `midi_event()` wraps its whole body in a bare `try/except: pass`, so MIDI parsing
  errors are silently swallowed. Keep this in mind when debugging — a malformed
  message or an out-of-range note index just disappears.
- There is no test suite, linter config, or build step. It's run by hand.
- `.qxw` files are XML; they're normally edited inside the QLC+ app, but small,
  targeted edits by hand are fine if you preserve the structure.
