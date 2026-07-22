"""Flask web interface: edit settings, run ArtPoll discovery, view logs.

Kept intentionally simple (server-rendered, vanilla JS only): a dark, themed single
page with a status strip, two live strips (32-key input + 40-beam laser output),
grouped/labelled settings, the MIDI + ArtNet device scanners and the log view.

Live updates (R37) ride two WebSockets opened by the page: `/ws` streams the DMX
thread's per-tick binary frame (see live.py) which the page paints on requestAnimationFrame,
and `/logs` streams new log lines as JSON. Both are registered via flask-sock; if it is
not installed the routes are skipped and the page degrades to its page-load snapshot.
Runs on the Flask dev server (threaded), which is fine for a single-user appliance on a
trusted network — see the README before exposing it wider.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from flask import Flask, redirect, render_template_string, request, url_for

if TYPE_CHECKING:
    from .dmx_thread import DmxThread

from . import artnet, fixtures
from .config import ConfigHolder
from .live import LiveBus
from .log_buffer import RingBufferHandler
from .state import KeyState
from .usage import UsageLog

try:
    from flask_sock import Sock
except ImportError:  # WebSocket live feed (R37) degrades gracefully if flask-sock is absent
    Sock = None

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
 header .dot{width:.7rem;height:.7rem;border-radius:50%;background:#444a57;
   transition:background .25s,box-shadow .25s} /* grey = no live connection */
 header .dot.live{background:var(--accent);box-shadow:0 0 10px 2px var(--accent)}
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

 .viz{display:flex;flex-direction:column;gap:.55rem;margin-bottom:1.5rem}
 .viz-row{display:flex;align-items:center;gap:.7rem}
 .viz-lbl{width:3.2rem;flex:none;font-size:.7rem;text-transform:uppercase;
   letter-spacing:.06em;color:var(--muted);text-align:right}
 .strip{flex:1;display:flex;gap:3px;height:42px;align-items:flex-end}
 .strip.dots{height:24px;align-items:center;gap:4px}
 /* key row (R42): full-height clickable cells; click or drag to play */
 .strip.keys{height:46px;align-items:stretch;user-select:none;touch-action:none}
 .beam{flex:1;border-radius:4px;background:#23262f;cursor:pointer;
   transition:background .08s ease,box-shadow .08s ease}
 .beam:hover{background:#2e3340}
 .beam.on{background:linear-gradient(var(--accent-soft),var(--accent));
   box-shadow:0 0 8px 1px var(--accent)}
 /* laser output: a red dot per beam, brightness driven live by --b (0..1) */
 .dot{flex:1;max-width:18px;aspect-ratio:1;border-radius:50%;
   background:rgba(255,43,70,calc(.10 + .90*var(--b,0)));
   box-shadow:0 0 calc(11px*var(--b,0)) rgba(255,43,70,calc(.85*var(--b,0)))}
 /* chord row (R42): one button per configured chord; hold to trigger */
 .chords{flex:1;display:flex;flex-wrap:wrap;gap:6px;user-select:none;touch-action:none}
 .chord{background:var(--panel-2);border:1px solid var(--line);color:var(--ink);
   border-radius:8px;padding:.3rem .6rem;font-size:.82rem;font-weight:600;cursor:pointer;
   display:flex;flex-direction:column;align-items:center;gap:.05rem;line-height:1.15;min-width:3.2rem}
 .chord .ck{font-size:.64rem;font-weight:400;color:var(--muted)}
 .chord:hover{border-color:var(--accent-soft)}
 .chord.pressing{background:var(--accent);border-color:var(--accent);color:#fff}
 .chord.pressing .ck{color:rgba(255,255,255,.8)}

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
 /* all-lasers-on setup toggle (R43): muted when off, glowing accent when on */
 .toggle{flex:none;background:var(--panel-2);border:1px solid var(--line);color:var(--ink);
   font-weight:600;padding:.35rem .7rem;font-size:.78rem;white-space:nowrap}
 .toggle:hover{background:var(--panel-2);border-color:var(--accent-soft)}
 .toggle.active{background:var(--accent);border-color:var(--accent);color:#fff;
   box-shadow:0 0 10px 1px var(--accent)}
 .toggle.active:hover{background:var(--accent-soft);border-color:var(--accent-soft)}
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

 /* keypress-usage graph (R36): inline SVG, drawn with vanilla JS, no external lib */
 .usage{width:100%;height:170px;display:block;background:var(--panel-2);
   border:1px solid var(--line);border-radius:8px}
</style></head><body>
<div class="wrap">

 <header>
  <span id="conn" class="dot" title="live connection"></span>
  <h1>laser-keyboard</h1>
  <span class="badge">v{{ version }}</span>
 </header>

 <div class="status">
  <div class="stat"><div class="k">Keys held</div><div class="v accent">{{ held }} / {{ cfg.key_count }}</div></div>
  <div class="stat"><div class="k">Sending to</div><div class="v">{{ target }}</div></div>
  <div class="stat"><div class="k">Universe</div><div class="v">{{ cfg.artnet_universe }}</div></div>
  <div class="stat"><div class="k">Tick rate</div><div class="v">{{ cfg.tick_hz }} Hz</div></div>
 </div>

 <div class="viz">
  <div class="viz-row">
   <span class="viz-lbl">Lasers</span>
   <div id="lasers" class="strip dots">
    {% for _ in range(beam_count) %}<span class="dot"></span>{% endfor %}
   </div>
   <button type="button" id="allon" class="toggle {{ 'active' if all_on }}"
     title="toggle all 40 beams on for setup / aiming">All on</button>
  </div>
  <div class="viz-row">
   <span class="viz-lbl">Keys</span>
   <div id="keys" class="strip keys">
    {% for v in beams %}<span class="beam {{ 'on' if v > 0 }}" data-i="{{ loop.index0 }}"></span>{% endfor %}
   </div>
  </div>
  <div class="viz-row">
   <span class="viz-lbl">Chords</span>
   {% if chords %}
    <div id="chords" class="chords">
     {% for c in chords %}
      <button type="button" class="chord" data-keys="{{ c.idxs|join(',') }}">{{ c.name
        }}<span class="ck">{{ c.idxs|join(' · ') }}</span></button>
     {% endfor %}
    </div>
   {% else %}
    <div class="chords"><span class="empty" style="margin:0">no chords configured</span></div>
   {% endif %}
  </div>
 </div>

 <section>
  <h2>Keyboard usage · presses per minute</h2>
  <svg id="usage" class="usage" preserveAspectRatio="none"></svg>
  <p id="usage-cap" class="empty" style="margin:.55rem 0 0">loading…</p>
 </section>

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
  <div id="logbox" class="logs">{{ logs }}</div>
 </section>

</div>

<script>
(function(){
 // ---- live key + laser feed (binary frames over /ws) --------------------
 var keyEls   = Array.prototype.slice.call(document.querySelectorAll('#keys .beam'));
 var laserEls = Array.prototype.slice.call(document.querySelectorAll('#lasers .dot'));
 var conn = document.getElementById('conn');
 var latest = null, queued = false;

 function paint(){
   queued = false;
   if(!latest) return;
   var d = new Uint8Array(latest), p = 0;
   var K = d[p++];
   for(var i=0;i<K;i++){ var v=d[p++], el=keyEls[i]; if(el) el.classList.toggle('on', v>0); }
   var B = d[p++];
   for(var j=0;j<B;j++){ var b=d[p++], le=laserEls[j];
     if(le) le.style.setProperty('--b', (b/255).toFixed(3)); }
 }
 // Coalesce 100 Hz of frames down to the display refresh: keep only the newest.
 function schedule(){ if(!queued){ queued=true; requestAnimationFrame(paint); } }

 function wsURL(path){
   return (location.protocol==='https:'?'wss':'ws')+'://'+location.host+path;
 }

 function connectFrames(){
   var ws = new WebSocket(wsURL('/ws'));
   ws.binaryType = 'arraybuffer';
   ws.onopen    = function(){ conn.classList.add('live'); };
   ws.onmessage = function(e){ latest = e.data; schedule(); };
   ws.onclose   = function(){ conn.classList.remove('live'); setTimeout(connectFrames, 1000); };
   ws.onerror   = function(){ try{ ws.close(); }catch(_){} };
 }

 // ---- live log stream (JSON lines over /logs) ---------------------------
 var logbox = document.getElementById('logbox');
 var MAX_LOG_LINES = 500;   // cap the box so streamed lines can't grow it unbounded (B9)
 function connectLogs(){
   var ws = new WebSocket(wsURL('/logs'));
   ws.onmessage = function(e){
     var msg; try{ msg = JSON.parse(e.data); }catch(_){ return; }
     if(!msg.lines || !msg.lines.length) return;
     var atBottom = logbox.scrollTop + logbox.clientHeight >= logbox.scrollHeight - 4;
     logbox.textContent += (logbox.textContent ? '\\n' : '') + msg.lines.join('\\n');
     var lines = logbox.textContent.split('\\n');
     if(lines.length > MAX_LOG_LINES)
       logbox.textContent = lines.slice(lines.length - MAX_LOG_LINES).join('\\n');
     if(atBottom) logbox.scrollTop = logbox.scrollHeight;
   };
   ws.onclose = function(){ setTimeout(connectLogs, 1000); };
   ws.onerror = function(){ try{ ws.close(); }catch(_){} };
 }

 // ---- interactive virtual keyboard (R42) --------------------------------
 // Click a key, or drag with the pointer held across the key row, to play; hold a
 // chord button to strike all its keys. Input rides the /input WebSocket (B9) so a
 // glissando doesn't fire an HTTP request (and a werkzeug log line) per key crossed;
 // it presses/releases the same KeyState the MIDI thread drives, so the live feed
 // paints it back. Falls back to POST if the socket is down (e.g. no flask-sock).
 var INPUT_VELOCITY = 100;   // mouse has no velocity; use a medium-hard strike
 var inputWS = null;
 function connectInput(){
   var ws = new WebSocket(wsURL('/input'));
   ws.onopen  = function(){ inputWS = ws; };
   ws.onclose = function(){ inputWS = null; setTimeout(connectInput, 1000); };
   ws.onerror = function(){ try{ ws.close(); }catch(_){} };
 }
 function sendInput(keys, down){
   if(!keys || !keys.length) return;
   var msg = JSON.stringify({keys:keys, down:down, velocity:INPUT_VELOCITY});
   if(inputWS && inputWS.readyState === 1){
     try{ inputWS.send(msg); return; }catch(_){}
   }
   fetch('/input', {method:'POST', headers:{'Content-Type':'application/json'},
     body:msg, keepalive:true}).catch(function(){});
 }

 var keysWrap = document.getElementById('keys');
 var dragging = false, curKey = -1;
 function keyAt(x, y){
   var el = document.elementFromPoint(x, y);
   if(el && el.classList.contains('beam') && el.dataset.i !== undefined)
     return parseInt(el.dataset.i, 10);
   return -1;   // pointer is off the key row
 }
 function setKey(i){           // one key held at a time while sliding (glissando)
   if(i === curKey) return;
   if(curKey >= 0) sendInput([curKey], false);   // release the one we left
   curKey = i;
   if(curKey >= 0) sendInput([curKey], true);     // strike the one we entered
 }
 keysWrap.addEventListener('pointerdown', function(e){
   dragging = true;
   try{ keysWrap.setPointerCapture(e.pointerId); }catch(_){}
   setKey(keyAt(e.clientX, e.clientY));
   e.preventDefault();
 });
 keysWrap.addEventListener('pointermove', function(e){
   if(dragging) setKey(keyAt(e.clientX, e.clientY));
 });
 function endDrag(){ if(dragging){ dragging = false; setKey(-1); } }
 window.addEventListener('pointerup', endDrag);
 window.addEventListener('pointercancel', endDrag);

 Array.prototype.forEach.call(document.querySelectorAll('.chord'), function(btn){
   var keys = (btn.dataset.keys || '').split(',')
     .filter(function(s){ return s !== ''; }).map(Number);
   var held = false;
   function down(e){ e.preventDefault(); if(held) return; held = true;
     btn.classList.add('pressing'); sendInput(keys, true); }
   function up(){ if(!held) return; held = false;
     btn.classList.remove('pressing'); sendInput(keys, false); }
   btn.addEventListener('pointerdown', down);
   btn.addEventListener('pointerup', up);
   btn.addEventListener('pointerleave', up);   // slide off the button -> release
   btn.addEventListener('pointercancel', up);
 });

 // ---- keypress-usage graph (R36): inline SVG, no external chart lib ------
 var SVGNS = 'http://www.w3.org/2000/svg';
 var usageSvg = document.getElementById('usage');
 var usageCap = document.getElementById('usage-cap');
 var usagePoints = [];
 function svgEl(name, attrs){
   var el = document.createElementNS(SVGNS, name);
   for(var k in attrs) el.setAttribute(k, attrs[k]);
   return el;
 }
 function fmtClock(ms){
   var d = new Date(ms);
   function p(n){ return (n<10?'0':'')+n; }
   return p(d.getHours())+':'+p(d.getMinutes());
 }
 function drawUsage(){
   if(!usageSvg) return;
   while(usageSvg.firstChild) usageSvg.removeChild(usageSvg.firstChild);
   var W = usageSvg.clientWidth || 600, H = usageSvg.clientHeight || 170;
   usageSvg.setAttribute('viewBox', '0 0 '+W+' '+H);
   var pts = usagePoints;
   if(!pts.length){
     if(usageCap) usageCap.textContent =
       'no data yet — the first point appears after a minute of play';
     return;
   }
   var padL=34, padR=10, padT=12, padB=20;
   var t0=pts[0][0], t1=pts[pts.length-1][0];
   var maxC=1, total=0;
   for(var i=0;i<pts.length;i++){ if(pts[i][1]>maxC) maxC=pts[i][1]; total+=pts[i][1]; }
   var spanT = Math.max(60000, t1-t0);
   var plotW=W-padL-padR, plotH=H-padT-padB;
   function X(t){ return padL + (t-t0)/spanT*plotW; }
   function Y(c){ return padT + (1 - c/maxC)*plotH; }
   // horizontal gridlines + y labels at max and 0
   [maxC, 0].forEach(function(c){
     var yy = Y(c);
     usageSvg.appendChild(svgEl('line', {x1:padL, y1:yy, x2:W-padR, y2:yy,
       stroke:'#2a2e3b', 'stroke-width':1}));
     var tx = svgEl('text', {x:padL-5, y:yy+3, fill:'#9097a6', 'font-size':10,
       'text-anchor':'end'});
     tx.textContent = c; usageSvg.appendChild(tx);
   });
   // filled area + top line
   var area='M '+X(t0).toFixed(1)+' '+Y(0).toFixed(1), line='';
   for(var j=0;j<pts.length;j++){
     var px=X(pts[j][0]).toFixed(1), py=Y(pts[j][1]).toFixed(1);
     area += ' L '+px+' '+py;
     line += (j?' L ':'M ')+px+' '+py;
   }
   area += ' L '+X(t1).toFixed(1)+' '+Y(0).toFixed(1)+' Z';
   usageSvg.appendChild(svgEl('path', {d:area, fill:'rgba(255,43,70,.18)', stroke:'none'}));
   usageSvg.appendChild(svgEl('path', {d:line, fill:'none', stroke:'#ff6076',
     'stroke-width':1.5, 'stroke-linejoin':'round', 'stroke-linecap':'round'}));
   // x time labels at both ends
   var lx = svgEl('text', {x:padL, y:H-6, fill:'#9097a6', 'font-size':10,
     'text-anchor':'start'}); lx.textContent = fmtClock(t0); usageSvg.appendChild(lx);
   var rx = svgEl('text', {x:W-padR, y:H-6, fill:'#9097a6', 'font-size':10,
     'text-anchor':'end'}); rx.textContent = fmtClock(t1); usageSvg.appendChild(rx);
   if(usageCap) usageCap.textContent =
     pts.length+' min · '+total+' presses total · peak '+maxC+'/min';
 }
 function fetchUsage(){
   fetch('/usage.json').then(function(r){ return r.json(); })
     .then(function(d){ usagePoints = d.points || []; drawUsage(); })
     .catch(function(){});
 }
 var usageResizeT;
 window.addEventListener('resize', function(){
   clearTimeout(usageResizeT); usageResizeT = setTimeout(drawUsage, 150);
 });
 fetchUsage();
 setInterval(fetchUsage, 60000);   // a new point lands each minute

 // ---- all-lasers-on setup toggle (R43) ----------------------------------
 var allonBtn = document.getElementById('allon');
 if(allonBtn){
   allonBtn.addEventListener('click', function(){
     fetch('/lasers/all-on', {method:'POST'}).then(function(r){ return r.json(); })
       .then(function(d){ allonBtn.classList.toggle('active', !!d.on); })
       .catch(function(){});
     // the live /ws feed paints the lit beams back, so no manual dot update needed
   });
 }

 logbox.scrollTop = logbox.scrollHeight;
 connectFrames();
 connectLogs();
 connectInput();
})();
</script>
</body></html>
"""


def _apply_input(state: KeyState, data: dict) -> None:
    """Apply one virtual-keyboard input message to the shared KeyState (R42). Body:
    {"keys": [idx, ...], "down": bool, "velocity": int}. Presses or releases the given
    key indices — a chord is just its constituent keys; press()/release() guard the
    range. Shared by the /input WebSocket (preferred) and the POST fallback (B9)."""
    down = bool(data.get("down"))
    try:
        velocity = int(data.get("velocity", 100) or 100)
    except (TypeError, ValueError):
        velocity = 100
    for k in data.get("keys", []):
        try:
            idx = int(k)
        except (TypeError, ValueError):
            continue
        if down:
            state.press(idx, velocity)
        else:
            state.release(idx)


def _register_websockets(app: Flask, state: KeyState, live_bus: LiveBus | None,
                         log_buffer: RingBufferHandler) -> None:
    """Register the live feed (R37): /ws streams binary key+laser frames, /logs streams
    new log lines as JSON, and /input receives virtual-keyboard events (R42/B9). No-op if
    flask-sock is unavailable, so the page still works (the strips stay at their page-load
    snapshot and input falls back to POST). The /ws and /logs handlers block on their
    source and resend on a 10 s timeout so a dropped client is noticed and cleaned up."""
    if Sock is None:
        log.warning("flask-sock not installed; live WebSocket feed disabled")
        return
    sock = Sock(app)

    @sock.route("/input")
    def ws_input(ws):  # pragma: no cover - exercised over a real socket
        """Virtual-keyboard input over a WebSocket (R42/B9). Each text message is one
        JSON event {keys, down, velocity}. Preferred over POST so a glissando doesn't fire
        a request (and a werkzeug access-log line) per key crossed."""
        while True:
            try:
                raw = ws.receive()
            except Exception:
                break
            if raw is None:   # client disconnected
                break
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue
            _apply_input(state, data)

    @sock.route("/ws")
    def ws_frames(ws):  # pragma: no cover - exercised over a real socket
        if live_bus is None:
            return
        live_bus.add_consumer()   # mark a browser watching -> DMX thread publishes every tick
        seq, frame = live_bus.snapshot()
        try:
            ws.send(frame)
            while True:
                seq, frame = live_bus.wait_next(seq, timeout=10.0)
                ws.send(frame)   # changed frame, or a keepalive resend on timeout
        except Exception:
            pass
        finally:
            live_bus.remove_consumer()

    @sock.route("/logs")
    def ws_logs(ws):  # pragma: no cover - exercised over a real socket
        last = log_buffer.total()   # page already shows the backlog; stream from here
        try:
            while True:
                last, new = log_buffer.wait_since(last, timeout=10.0)
                ws.send(json.dumps({"lines": new}))   # empty list = keepalive
        except Exception:
            pass


def create_app(state: KeyState, config: ConfigHolder, log_buffer: RingBufferHandler,
               live_bus: LiveBus | None = None, usage: UsageLog | None = None,
               dmx: "DmxThread | None" = None) -> Flask:
    app = Flask(__name__)
    # Last discovery result, kept in memory so it survives the redirect after a scan.
    app.config["_devices"] = []
    app.config["_scanned"] = False
    app.config["_midi_ports"] = []
    app.config["_midi_scanned"] = False
    _register_websockets(app, state, live_bus, log_buffer)

    from . import __version__

    def render():
        cfg = config.get()
        editable = {name: getattr(cfg, name) for name in _EDITABLE}
        target = cfg.artnet_ip if cfg.artnet_mode == "unicast" else "broadcast"
        beams = [v if h else 0 for v, _, h in state.snapshot()]
        # Chord buttons (R42): detection is quality-based now (R38), so there's no fixed
        # chord list to enumerate. Offer one example triad per configured quality that a
        # UI user can hold to trigger its effect. `idxs`/`name` avoid Jinja's dict-`.keys`
        # method clash. Any transposition of these would trigger the same effect.
        _example = {"major": [0, 4, 7], "minor": [0, 3, 7]}
        chords = [{"idxs": _example[q], "name": "%s → %s" % (q, eff)}
                  for q, eff in cfg.chord_effects.items() if q in _example]
        return render_template_string(
            _PAGE,
            version=__version__,
            cfg=cfg,
            groups=_GROUPS,
            editable=editable,
            beams=beams,
            chords=chords,
            beam_count=len(fixtures.all_beam_channels(cfg)),
            all_on=(dmx.all_on() if dmx is not None else False),
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

    @app.get("/usage.json")
    def usage_data():
        """Keypress-per-minute series for the graph (R36): [[epoch_ms, count], ...],
        oldest first. Epoch in ms so the browser can feed it straight to Date()."""
        points = usage.history() if usage is not None else []
        return {"points": [[epoch * 1000, count] for epoch, count in points]}

    @app.post("/lasers/all-on")
    def toggle_all_on():
        """Toggle the all-lasers-on setup aid (R43). Transient DMX-thread state, not
        persisted. Returns the new state so the button can reflect it."""
        on = dmx.toggle_all_on() if dmx is not None else False
        log.info("all lasers on: %s", "ON" if on else "off")
        return {"on": on}

    @app.post("/input")
    def input_keys():
        """Virtual-keyboard input fallback (R42). The page prefers the /input WebSocket
        (B9) and only POSTs here when flask-sock is absent or the socket is down. Shares
        _apply_input with the WebSocket handler."""
        _apply_input(state, request.get_json(silent=True) or {})
        return ("", 204)

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
