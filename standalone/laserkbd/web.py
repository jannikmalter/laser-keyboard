"""Flask web interface: edit settings, run ArtPoll discovery, view logs.

Kept intentionally simple (server-rendered, no JS framework): a dark, themed single
page with a status strip, a live beam strip (snapshot at page load), grouped/labelled
settings, the MIDI + ArtNet device scanners and the log view. Reload to refresh the
status/logs; live push is a separate item (R37). Runs on the Flask dev server, which
is fine for a single-user appliance on a trusted network — see the README before
exposing it wider.
"""

from __future__ import annotations

import logging

from flask import Flask, redirect, render_template_string, request, url_for

from . import artnet
from .config import ConfigHolder
from .log_buffer import RingBufferHandler
from .state import KeyState

log = logging.getLogger(__name__)


def _field(name, caster, label, hint="", options=None):
    return {"name": name, "caster": caster, "label": label, "hint": hint, "options": options}


# Editable settings, grouped for the UI. Each field carries a human label, a hint
# (units / meaning) and an optional fixed option list (rendered as a <select>). The
# form field name is still the raw Config attribute, so the POST handler is unchanged.
_GROUPS = [
    ("MIDI input", [
        _field("midi_port_name", str, "Keyboard port", "substring match · blank = first input"),
        _field("base_note", int, "Base note", "MIDI note mapped to key 0"),
        _field("key_count", int, "Key count", "number of playable keys"),
    ]),
    ("ArtNet output", [
        _field("artnet_mode", str, "Mode", options=["broadcast", "unicast"]),
        _field("artnet_ip", str, "Unicast IP", "used when mode = unicast"),
        _field("artnet_universe", int, "Universe"),
        _field("tick_hz", float, "Tick rate", "Hz · DMX render + send rate"),
    ]),
    ("Brightness & decay", [
        _field("master_brightness", int, "Master brightness", "0–255 global dimmer"),
        _field("decay_mode", str, "Decay mode", options=["exponential", "linear"]),
        _field("decay_t_min_s", float, "Decay · soft hit", "seconds (velocity 1)"),
        _field("decay_t_max_s", float, "Decay · hard hit", "seconds (velocity 127)"),
    ]),
    ("Chord effects", [
        _field("lightning_flash_hz", float, "Lightning flash rate", "Hz · re-randomise rate"),
        _field("lightning_on_fraction", float, "Lightning density", "0–1 · beams lit per flash"),
        _field("wave_period_s", float, "Wave period", "seconds · one full sweep"),
        _field("wave_decay_s", float, "Wave trail decay", "seconds · per-beam fade"),
    ]),
    ("Logging", [
        _field("log_level", str, "Log level", options=["DEBUG", "INFO", "WARNING", "ERROR"]),
    ]),
]

# Flat name -> caster map used when parsing the submitted form.
_EDITABLE = {f["name"]: f["caster"] for _, items in _GROUPS for f in items}

_PAGE = """
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>laser-keyboard</title>
<style>
 :root{
   --bg:#0c0d11; --panel:#15171f; --panel-2:#1b1e29; --ink:#eceef4;
   --muted:#9097a6; --line:#2a2e3b; --accent:#ff2b46; --accent-soft:#ff6076;
   --ok:#3ddc84; --radius:12px;
 }
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--ink);line-height:1.5;
   font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
   -webkit-font-smoothing:antialiased}
 a{color:var(--accent-soft);text-decoration:none}
 a:hover{text-decoration:underline}
 .wrap{max-width:880px;margin:0 auto;padding:2rem 1.25rem 4rem}

 header{display:flex;align-items:center;gap:.75rem;margin-bottom:1.25rem}
 header .dot{width:.7rem;height:.7rem;border-radius:50%;background:var(--accent);
   box-shadow:0 0 10px 2px var(--accent)}
 h1{font-size:1.4rem;margin:0;letter-spacing:-.02em;font-weight:650}
 .badge{font-size:.72rem;color:var(--muted);border:1px solid var(--line);
   border-radius:999px;padding:.1rem .55rem}

 .status{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
   gap:.6rem;margin-bottom:1.1rem}
 .stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
   padding:.6rem .8rem}
 .stat .k{font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
 .stat .v{font-size:1.05rem;font-weight:600;margin-top:.1rem;
   overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .stat .v.accent{color:var(--accent-soft)}

 .beams{display:flex;gap:3px;margin-bottom:1.5rem;height:42px;align-items:flex-end}
 .beam{flex:1;height:18px;border-radius:3px;background:#23262f;transition:none}
 .beam.on{height:42px;background:linear-gradient(var(--accent-soft),var(--accent));
   box-shadow:0 0 8px 1px var(--accent)}

 section{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
   padding:1.1rem 1.2rem;margin-bottom:1.1rem}
 section h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;
   color:var(--muted);margin:0 0 .9rem;font-weight:600}

 .field{display:grid;grid-template-columns:1fr 12rem;gap:.5rem 1rem;align-items:center;
   padding:.45rem 0;border-top:1px solid var(--line)}
 .field:first-of-type{border-top:none}
 .field .lbl{font-size:.9rem}
 .field .hint{display:block;font-size:.74rem;color:var(--muted)}
 input,select{width:100%;background:var(--panel-2);color:var(--ink);
   border:1px solid var(--line);border-radius:8px;padding:.4rem .55rem;font-size:.88rem}
 input:focus,select:focus{outline:none;border-color:var(--accent-soft);
   box-shadow:0 0 0 2px rgba(255,96,118,.18)}

 button{background:var(--accent);color:#fff;border:none;border-radius:8px;
   padding:.5rem 1.1rem;font-size:.88rem;font-weight:600;cursor:pointer}
 button:hover{background:var(--accent-soft)}
 .actions{margin-top:1rem}
 .toolbar{display:flex;align-items:center;gap:.75rem;margin-bottom:.4rem}
 .toolbar button{background:var(--panel-2);border:1px solid var(--line);color:var(--ink);font-weight:500}
 .toolbar button:hover{border-color:var(--accent-soft)}

 table{border-collapse:collapse;width:100%;margin-top:.75rem;font-size:.86rem}
 th,td{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--line)}
 th{color:var(--muted);font-weight:600;font-size:.74rem;text-transform:uppercase;letter-spacing:.05em}
 .tag{font-size:.72rem;color:var(--ok);border:1px solid var(--ok);border-radius:999px;padding:.05rem .5rem}
 .empty{color:var(--muted);font-size:.86rem;margin:.6rem 0 0}

 .logs{background:#070809;color:#7CFC9A;border:1px solid var(--line);border-radius:8px;
   padding:.7rem .8rem;font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
   font-size:.78rem;line-height:1.45;height:17rem;overflow:auto;white-space:pre-wrap}
</style></head><body>
<div class="wrap">

 <header>
  <span class="dot"></span>
  <h1>laser-keyboard</h1>
  <span class="badge">v{{ version }}</span>
 </header>

 <div class="status">
  <div class="stat"><div class="k">Keys held</div><div class="v accent">{{ held }} / {{ cfg.key_count }}</div></div>
  <div class="stat"><div class="k">Sending to</div><div class="v">{{ target }}</div></div>
  <div class="stat"><div class="k">Universe</div><div class="v">{{ cfg.artnet_universe }}</div></div>
  <div class="stat"><div class="k">Tick rate</div><div class="v">{{ cfg.tick_hz }} Hz</div></div>
 </div>

 <div class="beams" title="live key state at page load">
  {% for v in beams %}<span class="beam {{ 'on' if v > 0 }}"></span>{% endfor %}
 </div>

 <form method="post" action="{{ url_for('settings') }}">
  {% for group, items in groups %}
   <section>
    <h2>{{ group }}</h2>
    {% for f in items %}
     <div class="field">
      <label class="lbl" for="{{ f.name }}">{{ f.label }}
       {% if f.hint %}<span class="hint">{{ f.hint }}</span>{% endif %}</label>
      {% if f.options %}
       <select id="{{ f.name }}" name="{{ f.name }}">
        {% for o in f.options %}
         <option value="{{ o }}" {{ 'selected' if editable[f.name]|string == o }}>{{ o }}</option>
        {% endfor %}
       </select>
      {% else %}
       <input id="{{ f.name }}" name="{{ f.name }}" value="{{ editable[f.name] }}">
      {% endif %}
     </div>
    {% endfor %}
   </section>
  {% endfor %}
  <div class="actions"><button type="submit">Save settings</button></div>
 </form>

 <section>
  <h2>MIDI devices</h2>
  <form method="post" action="{{ url_for('midi_scan') }}" class="toolbar">
   <button type="submit">Scan MIDI devices</button>
  </form>
  {% if midi_ports %}
   <table><tr><th>Port</th><th></th></tr>
   {% for p in midi_ports %}
    <tr><td>{{ p }}</td>
        <td>{% if p == cfg.midi_port_name %}<span class="tag">in use</span>{% else %}
            <a href="{{ url_for('use_midi', name=p) }}">use</a>{% endif %}</td></tr>
   {% endfor %}</table>
  {% elif midi_scanned %}
   <p class="empty">No MIDI input ports found.</p>
  {% endif %}
 </section>

 <section>
  <h2>ArtNet devices</h2>
  <form method="post" action="{{ url_for('artpoll') }}" class="toolbar">
   <button type="submit">Send ArtPoll &amp; scan</button>
  </form>
  {% if devices %}
   <table><tr><th>IP</th><th>Name</th><th></th></tr>
   {% for d in devices %}
    <tr><td>{{ d.ip }}</td><td>{{ d.short_name }}</td>
        <td><a href="{{ url_for('use_device', ip=d.ip) }}">use</a></td></tr>
   {% endfor %}</table>
  {% elif scanned %}
   <p class="empty">No devices replied.</p>
  {% endif %}
 </section>

 <section>
  <h2>Logs</h2>
  <div class="logs">{{ logs }}</div>
 </section>

</div>
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
        beams = [v for v, _ in state.snapshot()]
        return render_template_string(
            _PAGE,
            version=__version__,
            cfg=cfg,
            groups=_GROUPS,
            editable=editable,
            beams=beams,
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
