# Todos

Work items. Reference the ID they advance.

- [ ] End-to-end test the standalone build on the Pi with a real keyboard and ArtNet
      node; confirm the raw-socket ArtNet approach, ArtPoll discovery, and the MIDI
      device picker / live device-switch work. (R15–R28, R32, G2)
- [ ] Milestone 2: chord-triggered effects, rendered in Python in the DMX thread. (G2)
- [ ] Milestone 2: full-keyboard (12+ keys) bonus effect. (G2)
- [ ] Milestone 2: effect parity with the old QLC+ set as desired (waves, rainbow,
      gewitter, strobe, chases) via a small effects engine. (G2)
- [ ] Resilience: survive USB MIDI keyboard disconnect — catch the disconnect, release
      held key state, auto-reconnect by name. (R29)
- [ ] Resilience: survive network interruption — guard ArtNet sends so the render loop
      keeps ticking and resumes output when the link returns. (R30)
- [ ] Resilience: survive power loss — systemd auto-start on boot + atomic config
      write/replace so an abrupt cut can't corrupt settings. (R31, R26, R27)
- [ ] Decide whether to fix B1–B6 in the QLC+ build or accept they are superseded by
      the standalone build (R16). (B1–B6)
- [x] Dry-run mode for testing the web UI without hardware. (R25)
- [x] Persist settings across restarts. (R26)
