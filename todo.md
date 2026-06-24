# Todos

Work items. Reference the ID they advance.

- [x] End-to-end test the standalone build on the Pi with a real keyboard and ArtNet
      node; confirmed on 2026-06-24 — raw-socket ArtNet (unicast + broadcast), >44 Hz
      tick, ArtPoll discovery, and per-beam BeamBar output all work. (R15–R28, R32, G2)
- [ ] Test run-on-boot via the systemd unit on the Pi (not yet exercised). (R27)
- [x] Set each bar's channel 1 to 200–255 in the DMX output so the per-beam channels
      (4–13) are actually honoured (per the BeamBar manual's DMX chart). Done in
      fixtures.active_bar_bases() + dmx_thread._render(); pending hardware validation. (R23)
- [ ] Milestone 2: chord-triggered effects, rendered in Python in the DMX thread. (G2)
- [ ] Milestone 2: full-keyboard (12+ keys) bonus effect. (G2)
- [ ] Milestone 2: effect parity with the old QLC+ set as desired (waves, rainbow,
      gewitter, strobe, chases) via a small effects engine. (G2)
- [x] Resilience: survive USB MIDI keyboard disconnect — catch the disconnect, release
      held key state, auto-reconnect by name. Done in midi_thread (_port_gone/_disconnect
      + state.release_all), verified in simulation. (R29)
- [ ] Verify R29 on the Pi: physically unplug/replug the keyboard mid-play; confirm no
      beam sticks on and it reconnects. (R29)
- [ ] Resilience: survive network interruption — guard ArtNet sends so the render loop
      keeps ticking and resumes output when the link returns. (R30)
- [ ] Resilience: survive power loss — systemd auto-start on boot + atomic config
      write/replace so an abrupt cut can't corrupt settings. (R31, R26, R27)
- [ ] Decide whether to fix B1–B6 in the QLC+ build or accept they are superseded by
      the standalone build (R16). (B1–B6)
- [x] Dry-run mode for testing the web UI without hardware. (R25)
- [x] Persist settings across restarts. (R26)
