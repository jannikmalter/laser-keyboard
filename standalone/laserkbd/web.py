"""Flask web interface: edit settings, run ArtPoll discovery, view logs.

Kept intentionally simple (server-rendered, no JS framework). The logs view
auto-refreshes via a meta refresh. Runs on the Flask dev server, which is fine for a
single-user appliance on a trusted network — see the README before exposing it wider.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, fields

from flask import Flask, redirect, render_template_string, request, url_for

from . import artnet
from .config import Config, ConfigHolder
from .log_buffer import RingBufferHandler
from .state import KeyState

log = logging.getLogger(__name__)

# Fields the UI is allowed to edit, with a parser for each form value.
_EDITABLE = {
    "midi_port_name": str,
    "base_note": int,
    "key_count": int,
    "artnet_mode": str,
    "artnet_ip": str,
    "artnet_universe": int,
    "tick_hz": float,
    "master_brightness": int,
    "decay_mode": str,
    "decay_t_min_s": float,
    "decay_t_max_s": float,
    "log_level": str,
}

_PAGE = """
<!doctype html><html><head><title>laser-keyboard</title>
<style>
 body{font-family:sans-serif;max-width:820px;margin:1.5rem auto;padding:0 1rem}
 fieldset{margin-bottom:1rem} label{display:inline-block;width:11rem}
 input,select{padding:.2rem} .logs{background:#111;color:#0f0;padding:.6rem;
 font-family:monospace;font-size:.8rem;height:16rem;overflow:auto;white-space:pre-wrap}
 table{border-collapse:collapse} td,th{border:1px solid #ccc;padding:.2rem .5rem}
</style></head><body>
<h1>laser-keyboard <small>v{{ version }}</small></h1>
<p>keys held: <b>{{ held }}</b> / {{ cfg.key_count }} &middot; sending to
   <b>{{ target }}</b> universe <b>{{ cfg.artnet_universe }}</b> @ {{ cfg.tick_hz }} Hz</p>

<form method="post" action="{{ url_for('settings') }}">
 <fieldset><legend>Settings</legend>
  {% for name, value in editable.items() %}
   <div><label>{{ name }}</label>
   {% if name == 'artnet_mode' %}
     <select name="artnet_mode">
       <option value="broadcast" {{ 'selected' if value=='broadcast' }}>broadcast</option>
       <option value="unicast" {{ 'selected' if value=='unicast' }}>unicast</option>
     </select>
   {% elif name == 'decay_mode' %}
     <select name="decay_mode">
       <option value="exponential" {{ 'selected' if value=='exponential' }}>exponential</option>
       <option value="linear" {{ 'selected' if value=='linear' }}>linear</option>
     </select>
   {% else %}
     <input name="{{ name }}" value="{{ value }}">
   {% endif %}
   </div>
  {% endfor %}
  <button type="submit">Save</button>
 </fieldset>
</form>

<form method="post" action="{{ url_for('midi_scan') }}">
 <fieldset><legend>MIDI devices</legend>
  <button type="submit">Scan MIDI devices</button>
  {% if midi_ports %}
   <table><tr><th>Port</th><th></th></tr>
   {% for p in midi_ports %}
    <tr><td>{{ p }}</td>
        <td>{% if p == cfg.midi_port_name %}<b>in use</b>{% else %}
            <a href="{{ url_for('use_midi', name=p) }}">use</a>{% endif %}</td></tr>
   {% endfor %}</table>
  {% elif midi_scanned %}
   <p>No MIDI input ports found.</p>
  {% endif %}
 </fieldset>
</form>

<form method="post" action="{{ url_for('artpoll') }}">
 <fieldset><legend>ArtNet devices</legend>
  <button type="submit">Send ArtPoll &amp; scan</button>
  {% if devices %}
   <table><tr><th>IP</th><th>Name</th><th></th></tr>
   {% for d in devices %}
    <tr><td>{{ d.ip }}</td><td>{{ d.short_name }}</td>
        <td><a href="{{ url_for('use_device', ip=d.ip) }}">use</a></td></tr>
   {% endfor %}</table>
  {% elif scanned %}
   <p>No devices replied.</p>
  {% endif %}
 </fieldset>
</form>

<fieldset><legend>Logs</legend>
 <div class="logs">{{ logs }}</div>
</fieldset>
</body></html>
"""


def create_app(state: KeyState, config: ConfigHolder, log_buffer: RingBufferHandler) -> Flask:
    app = Flask(__name__)
    # Last discovery result, kept in memory so it survives the redirect after a scan.
    app.config["_devices"] = []
    app.config["_scanned"] = False
    app.config["_midi_ports"] = []
    app.config["_midi_scanned"] = False

    from . import __version__

    def render():
        cfg = config.get()
        editable = {name: getattr(cfg, name) for name in _EDITABLE}
        target = cfg.artnet_ip if cfg.artnet_mode == "unicast" else "broadcast"
        return render_template_string(
            _PAGE,
            version=__version__,
            cfg=cfg,
            editable=editable,
            held=state.held_count(),
            target=target,
            devices=app.config["_devices"],
            scanned=app.config["_scanned"],
            midi_ports=app.config["_midi_ports"],
            midi_scanned=app.config["_midi_scanned"],
            logs="\n".join(log_buffer.lines()),
        )

    @app.get("/")
    def index():
        return render()

    @app.post("/settings")
    def settings():
        changes = {}
        for name, caster in _EDITABLE.items():
            if name in request.form and request.form[name] != "":
                try:
                    changes[name] = caster(request.form[name])
                except (TypeError, ValueError):
                    log.warning("ignoring bad value for %s: %r", name, request.form[name])
        if changes:
            config.update(**changes)
            log.info("settings updated: %s", ", ".join(changes))
        return redirect(url_for("index"))

    @app.post("/midi-scan")
    def midi_scan():
        log.info("MIDI device scan requested")
        try:
            # Lazy import: --dry-run runs without rtmidi, so don't require it here.
            from .midi_thread import list_input_ports
            ports = list_input_ports()
        except ImportError:
            log.warning("rtmidi not available; cannot list MIDI ports (dry-run?)")
            ports = []
        app.config["_midi_ports"] = ports
        app.config["_midi_scanned"] = True
        log.info("MIDI scan found %d input port(s)", len(ports))
        return redirect(url_for("index"))

    @app.get("/use-midi")
    def use_midi():
        name = request.args.get("name", "")
        config.update(midi_port_name=name)
        log.info("MIDI keyboard set to %r", name)
        return redirect(url_for("index"))

    @app.post("/artpoll")
    def artpoll():
        log.info("ArtPoll scan requested")
        app.config["_devices"] = artnet.discover_nodes()
        app.config["_scanned"] = True
        log.info("ArtPoll found %d device(s)", len(app.config["_devices"]))
        return redirect(url_for("index"))

    @app.get("/use/<ip>")
    def use_device(ip: str):
        config.update(artnet_mode="unicast", artnet_ip=ip)
        log.info("ArtNet target set to unicast %s", ip)
        return redirect(url_for("index"))

    return app
