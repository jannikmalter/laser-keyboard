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
- [x] Implement simulated-piano decay: S-curve brightness envelope driven by MIDI velocity
      in the DMX render loop. Done in decay.py (smootherstep over a velocity-scaled
      duration) + state.py onset timestamps + dmx_thread._render(); verified via the render
      path. On-hardware feel-tuning of decay_min_s/decay_max_s still expected. (R33)
- [ ] Keypresses-per-minute counter: log count + timestamp to file every minute. (R34)
- [ ] Web UI visual polish: margins, typography, labels. (R35)
- [ ] Web UI keypresses-per-minute graph (time-series, drawn from R34 log). (R36)
- [ ] Live WebSocket feed: push key/laser state and log stream to the browser. (R37)
- [ ] Milestone 2: chord-triggered effects, rendered in Python in the DMX thread. (G2)
- [ ] Milestone 2: full-keyboard (12+ keys) bonus effect. (G2)
- [ ] Milestone 2: effect parity with the old QLC+ set as desired (waves, rainbow,
      gewitter, strobe, chases) via a small effects engine. (G2)
- [x] Resilience: survive USB MIDI keyboard disconnect — catch the disconnect, release
      held key state, auto-reconnect by name. Done in midi_thread (_port_gone/_disconnect
      + state.release_all); verified on the Pi by a real unplug (laser off, reconnected). (R29)
- [ ] Resilience: survive network interruption — ArtNet send errors are already caught
      in artnet.ArtNetSender.send (loop keeps ticking); validate by actually downing the
      network/node and confirming output resumes. (R30)
- [ ] Resilience: survive power loss — mechanisms in place (atomic config write R26 ✓ +
      systemd auto-start R27 ✓); pull the plug mid-play and confirm it resumes clean. (R31)
- [ ] Decide whether to fix B1–B6 in the QLC+ build or accept they are superseded by
      the standalone build (R16). (B1–B6)
- [x] Dry-run mode for testing the web UI without hardware. (R25)
- [x] Persist settings across restarts. (R26)
