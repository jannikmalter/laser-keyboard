# laser-keyboard

An interactive lighting installation: play a MIDI keyboard and each key lights an
individual laser beam from a set of laser bars. Detected chords trigger bonus
effects. Built for live, hands-on play.

The project comes in two flavours:

| Version | Where it runs | Output | Status |
|---------|---------------|--------|--------|
| **[`qlcplus/`](qlcplus/)** | A PC next to the rig | MIDI → [QLC+](https://www.qlcplus.org/) → DMX/USB | Working, in use |
| **[`standalone/`](standalone/)** | A Raspberry Pi inside the keyboard | MIDI → ArtNet (no PC, no QLC+) | In development (Milestone 1) |

## The two builds

### QLC+ version — [`qlcplus/`](qlcplus/)

The original, PC-tethered setup. A Python script cleans up the keyboard's MIDI and
forwards it to QLC+ via a virtual MIDI port; QLC+ owns the fixtures, scenes, effects
and the DMX output.

```
MIDI keyboard ──► laserkeyboard.py ──► loopMIDI ──► QLC+ ──► DMX/USB ──► laser bars
```

### Standalone version — [`standalone/`](standalone/)

A self-contained appliance: a Raspberry Pi 3B+ (PoE) lives inside the keyboard
enclosure and generates **ArtNet** directly — no PC, no QLC+, no virtual MIDI. The
whole unit reaches the rest of the installation over a single network cable. It runs
three threads (MIDI input, a ~100 Hz DMX/ArtNet render loop, and a Flask web UI for
settings and logs) and folds in the fixes for the QLC+ version's known bugs.

```
MIDI keyboard ──USB──► Raspberry Pi (laserkbd) ──ArtNet/UDP──► node ──DMX──► laser bars
```

## Hardware

- MIDI keyboard
- 4× BeamBar 10R laser bars (13-channel mode, 10 beams each) + some RGB fixtures
- DMX output: a DMX-USB Pro interface (QLC+ version) or an ArtNet node (standalone)

## Repository layout

```
qlcplus/      PC + QLC+ build (Python MIDI bridge + .qxw workspace)
standalone/   Raspberry Pi + ArtNet build (laserkbd package)
reqs.md       Requirements, roadmap and bug tracker for both builds
CLAUDE.md     Notes for working in this repo
```

See [`reqs.md`](reqs.md) for the requirements, the standalone roadmap (effects are a
later milestone), and the logged bugs.

## Getting started

Pick a build and follow its README:

- **[`qlcplus/README.md`](qlcplus/README.md)** — run with QLC+ on a PC
- **[`standalone/README.md`](standalone/README.md)** — run on a Raspberry Pi
