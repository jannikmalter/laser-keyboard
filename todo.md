# Todos

Work items. Reference the ID they advance.

- [x] End-to-end test the standalone build on the Pi with a real keyboard and ArtNet
      node; confirmed on 2026-06-24 — raw-socket ArtNet (unicast + broadcast), >44 Hz
      tick, ArtPoll discovery, and per-beam BeamBar output all work. (R15–R28, R32, G2)
- [x] Run-on-boot via the systemd unit on the Pi — works after setting the unit's
      User= to the real account (lichtfetisch); a wrong user fails with 217/USER. (R27)
- [x] Set each bar's channel 1 to 200–255 in the DMX output so the per-beam channels
      (4–13) are actually honoured (per the BeamBar manual's DMX chart). Done in
      fixtures.active_bar_bases() + dmx_thread._render(); validated on hardware. (R23)
- [x] Implement simulated-piano decay: velocity-driven brightness envelope in the DMX
      render loop. Done in decay.py (selectable exponential/linear over a velocity-scaled
      decay time) + state.py onset timestamps + dmx_thread._render(); mode/decay_t_min_s/
      decay_t_max_s editable in the web UI and persisted. Confirmed working on hardware
      2026-06-24 (exponential). (R33)
- [ ] Keypresses-per-minute counter: log count + timestamp to file every minute. (R34)
- [ ] Web UI visual polish: margins, typography, labels. (R35)
- [ ] Web UI keypresses-per-minute graph (time-series, drawn from R34 log). (R36)
- [ ] Live WebSocket feed: push key/laser state and log stream to the browser. (R37)
- [ ] Chord detection: edge-detected, evaluated each DMX tick from KeyState; active
      chords held in the DMX thread (standalone counterpart to QLC+ R8/R9). (R38)
- [ ] Effects engine: whole-40-beam channel enumeration + drive all 4 bars' channel 1
      to per-beam mode; closed-form effects overlaid in dmx_thread._render() at the
      existing TODO(milestone-2) lines, composited (max) with per-key beams. (R39)
- [ ] Effect: laser lightning — all 40 beams flash random/fast at a configurable
      flash rate, decoupled from tick_hz. (R40)
- [ ] Effect: left-right wave — Larson sweep 0→39→0, per-beam decay tuned to the sweep
      period so a beam nearly fully decays before the head returns. (R41)
- [ ] Milestone 2 (later): full-keyboard (12+ keys) bonus effect (QLC+ R11 counterpart). (G2)
- [ ] Milestone 2 (later): effect parity with the old QLC+ set as desired (waves,
      rainbow, gewitter, strobe, chases) via the same engine. (G2)
- [x] Resilience: survive USB MIDI keyboard disconnect — catch the disconnect, release
      held key state, auto-reconnect by name. Done in midi_thread (_port_gone/_disconnect
      + state.release_all); verified on the Pi by a real unplug (laser off, reconnected). (R29)
- [x] Resilience: survive network interruption — ArtNet send errors caught in
      artnet.ArtNetSender.send (loop keeps ticking), output resumes on reconnect.
      Validated 2026-06-24 by pulling the PoE cable. (R30)
- [x] Resilience: survive power loss — atomic config write (R26) + systemd auto-start
      (R27); validated 2026-06-24 by pulling the PoE cable (cuts power + network at once
      on the PoE Pi): boots unattended and resumes clean. (R31)
- [ ] Decide whether to fix B1–B6 in the QLC+ build or accept they are superseded by
      the standalone build (R16). (B1–B6)
- [x] Dry-run mode for testing the web UI without hardware. (R25)
- [x] Persist settings across restarts. (R26)
