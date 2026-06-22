# laser-keyboard

Interactive lighting installation: play a MIDI keyboard and each key lights an
individual laser beam. A Python script interprets the keyboard, and QLC+ drives the
fixtures over DMX. Detected chords trigger bonus effects.

## Signal flow

```
MIDI keyboard ──► laserkeyboard.py ──► loopMIDI ──► QLC+ ──► DMX/USB ──► laser bars + RGB fixtures
```

The Python script does not speak DMX. It translates raw keyboard input into a clean
MIDI note stream; QLC+ consumes that stream and maps it to DMX channels. All fixture
patching, scenes and effects live in the `.qxw` workspace.

## Hardware / software

- MIDI keyboard (sends note-on/off on MIDI channel 7)
- 4× BeamBar 10R laser bars (13-channel mode, 10 beams each) + Generic RGB fixtures
- DMX USB Pro interface
- Windows + [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) (virtual MIDI port)
- [QLC+](https://www.qlcplus.org/) 4.13+
- Python 3 with `python-rtmidi` and `numpy`

## Run

1. Start loopMIDI and open `laserkeyboard.qxw` in QLC+ (operate mode).
2. Install deps and start the bridge:

   ```bash
   pip install -r requirements.txt
   python laserkeyboard.py
   ```

Set the port indices near the top of `laserkeyboard.py` to match your machine:
`midi_in_port` (keyboard) and `midi_out_port` (loopMIDI). The script polls once per
second and auto-reconnects if a port drops. Ctrl+C to exit.

## How it maps

- Incoming notes are offset by `-41` into a 32-key array → 32 individual laser beams.
  Each note is forwarded to QLC+, where a virtual-console slider drives one beam.
- **Chords:** `ACCS` defines chords as triples of key indices. When every key of a
  chord is held, the script fires `NOTE_ON` on channel `100 + i` to trigger the
  matching QLC+ effect; releasing it sends `NOTE_OFF`.
- **Bonus:** holding 12+ keys at once triggers a "full" effect on channel `50`.

## Files

| File | Purpose |
|------|---------|
| `laserkeyboard.py` | Keyboard → MIDI bridge with chord detection |
| `laserkeyboard.qxw` | QLC+ workspace (fixtures, scenes, effects, MIDI→DMX map) |
