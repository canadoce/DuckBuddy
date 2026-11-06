# -*- coding: utf-8 -*-
"""duckweb: a page on the phone for what Xiaobai hears, says and means (2026-10-17).

Served by the robot on the local network (http://<robot>:8088, standard library only). It shows the
conversation — your words as it heard them, its duck-speak and what it meant (the brain's `meaning`,
until now only in lifed's log) — its state, battery, heat, whether the online brain is reachable,
and the network it is on; and it lets you type to it, ask it to scan a Wi-Fi QR code, or see what
the camera sees.

It only asks lifed and visiond (their sockets); it never talks to robotd. Typed words are taken as
said with its name, so the command words work from here as they do by voice.

    python3 duckweb.py [--port 8088] [--lifed /tmp/lifed.sock] [--vision /tmp/visiond.sock]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# the duck's name on the page comes from its persona (tools/persona, ~/persona on the robot)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona"))
from persona import load as load_persona  # noqa: E402


def rpc(path: str, method: str, params: dict | None = None, timeout: float = 3.0):
    """One JSON-RPC call over a unix socket; None if nobody answers."""
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(timeout)
        s.connect(path)
        s.sendall((json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                              ensure_ascii=False) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.split(b"\n")[0]).get("result")
    except (OSError, ValueError):
        return None


def network() -> dict:
    """The Wi-Fi it is on and its address."""
    out = {"ssid": None, "ip": None}
    try:
        p = subprocess.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi"], capture_output=True, text=True,
                           timeout=3)
        for line in p.stdout.splitlines():
            if line.startswith("yes:"):
                out["ssid"] = line[4:].replace("\\:", ":")
        p = subprocess.run(["ip", "-4", "-o", "addr", "show", "wlan0"], capture_output=True, text=True, timeout=3)
        parts = p.stdout.split()
        if "inet" in parts:
            out["ip"] = parts[parts.index("inet") + 1].split("/")[0]
    except (OSError, subprocess.SubprocessError):
        pass
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "duckweb/1"

    def log_message(self, fmt, *args):     # quiet: the page polls every second
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        a = self.server.args
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.replace("Xiaobai", NAME).encode(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json({"life": rpc(a.lifed, "life.state"), "vision": rpc(a.vision, "vision.state"),
                        "net": network(), "now": time.time()})
        elif self.path.startswith("/api/look/"):
            pid = self.path.rsplit("/", 1)[-1].split(".")[0]
            path = os.path.join("/tmp/visiond-looks", pid + ".jpg")
            if pid.isdigit() and os.path.exists(path):
                with open(path, "rb") as f:
                    self._send(200, f.read(), "image/jpeg")
            else:
                self._send(404, b"gone", "text/plain")
        elif self.path.startswith("/api/photo.jpg"):
            path = "/tmp/visiond-photo.jpg"
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._send(200, f.read(), "image/jpeg")
            else:
                self._send(404, b"no photo yet", "text/plain")
        else:
            self._send(404, b"not here", "text/plain")

    def do_POST(self):
        a = self.server.args
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/api/say":
            text = str(body.get("text", "")).strip()[:100]
            if not text:
                return self._json({"ok": False, "reason": "empty"}, 400)
            res = rpc(a.lifed, "life.event", {"type": "say", "text": text, "addressed": True, "named": True})
            self._json({"ok": res is not None})
        elif self.path == "/api/scan":
            res = rpc(a.lifed, "life.event", {"type": "say", "text": "connect to wifi", "addressed": True, "named": True})  # lifed's voice command words for "join a network"
            self._json({"ok": res is not None})
        elif self.path == "/api/volume":
            try:
                v = max(20, min(100, int(body.get("value"))))
            except (TypeError, ValueError):
                return self._json({"ok": False, "reason": "value"}, 400)
            res = rpc(a.lifed, "life.event", {"type": "volume", "set": v})
            self._json({"ok": res is not None})
        elif self.path == "/api/missions":
            mode = str(body.get("mode", ""))
            if mode not in ("dry", "real"):
                return self._json({"ok": False, "reason": "mode"}, 400)
            res = rpc(a.lifed, "life.event", {"type": "missions_mode", "mode": mode})
            self._json({"ok": res is not None, "mode": (res or {}).get("mode")})
        elif self.path == "/api/photo":
            res = rpc(a.vision, "vision.photo", {}, timeout=15.0)
            self._json({"ok": bool(res and res.get("ok")), "reason": (res or {}).get("reason")})
        else:
            self._json({"ok": False, "reason": "unknown"}, 404)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Xiaobai</title>
<style>
:root { --bg:#f6f4ef; --card:#fff; --ink:#24221f; --mute:#8a857c; --duck:#fff3c4; --you:#dcefff; --line:#e7e2d8;
        --ok:#2f8f4e; --warn:#c77700; --bad:#c43c3c; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#1b1a18; --card:#262421; --ink:#eeeae2; --mute:#9a958b; --duck:#4a3f1c; --you:#1f3b52; --line:#3a3732; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font: 16px/1.45 -apple-system, "PingFang SC", "Noto Sans SC", sans-serif; }
header { position:sticky; top:0; background:var(--bg); padding:12px 16px 8px; border-bottom:1px solid var(--line); z-index:1; }
h1 { margin:0 0 6px; font-size:20px; }
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip { background:var(--card); border:1px solid var(--line); border-radius:999px; padding:2px 10px; font-size:13px; color:var(--mute); }
.chip b { color:var(--ink); font-weight:600; }
.ok { color:var(--ok)!important } .warn { color:var(--warn)!important } .bad { color:var(--bad)!important }
main { padding:12px 16px 120px; max-width:720px; margin:0 auto; }
.convo { font-size:13px; color:var(--mute); margin:4px 0 10px; }
.msg { display:flex; margin:8px 0; }
.msg.you { justify-content:flex-end; }
.bubble { max-width:82%; padding:8px 12px; border-radius:14px; background:var(--card); border:1px solid var(--line); }
.you .bubble { background:var(--you); }
.duck .bubble { background:var(--duck); }
.say { font-size:13px; color:var(--mute); }
.meaning { font-size:16px; }
.meta { font-size:11px; color:var(--mute); margin-top:2px; }
footer { position:fixed; left:0; right:0; bottom:0; background:var(--bg); border-top:1px solid var(--line); padding:10px 16px; }
.row { display:flex; gap:8px; max-width:720px; margin:0 auto; }
input { flex:1; min-width:0; font-size:16px; padding:10px 12px; border-radius:10px; border:1px solid var(--line); background:var(--card); color:var(--ink); }
button { font-size:15px; padding:10px 12px; border-radius:10px; border:1px solid var(--line); background:var(--card); color:var(--ink); }
button.primary { background:#f2c94c; border-color:#e0b53a; color:#24221f; }
.tools { display:flex; gap:8px; max-width:720px; margin:8px auto 0; }
.tools button { flex:1; font-size:14px; padding:8px; }
.vol { display:flex; align-items:center; gap:8px; max-width:720px; margin:8px auto 0; font-size:14px; color:var(--mute); }
.vol input { flex:1; }
.mission { max-width:720px; margin:8px auto; padding:10px 12px; border:1px solid var(--line); border-radius:12px; background:var(--card); font-size:14px; }
.mhead { margin-bottom:4px; }
.mmode { max-width:720px; margin:8px auto 0; font-size:14px; }
.mmode button { font-size:13px; padding:4px 10px; margin-left:6px; }
.mmode b.bad { color:#c0392b; }
.mstep { padding:2px 0; }
.mstep.done { color:var(--mute); }
.mstep.running { font-weight:600; }
.mstep.failed { color:#c0392b; }
.mnote { color:var(--mute); font-size:12px; }
img.look { display:block; width:100%; max-width:320px; border-radius:10px; margin:6px 0; border:1px solid var(--line); }
#photo { display:none; width:100%; border-radius:12px; margin:8px 0; border:1px solid var(--line); }
.empty { color:var(--mute); text-align:center; margin-top:40px; }
</style></head>
<body>
<header>
  <h1>🦆 Xiaobai</h1>
  <div class="chips" id="chips"></div>
</header>
<main>
  <div class="convo" id="convo"></div>
  <div id="mission"></div>
  <img id="photo" alt="What Xiaobai sees">
  <div id="log"><div class="empty">No conversation yet. Call "Xiaobai", or type below.</div></div>
</main>
<footer>
  <div class="row">
    <input id="text" placeholder="Say to Xiaobai…" enterkeyhint="send" autocomplete="off">
    <button class="primary" id="send">Send</button>
  </div>
  <div class="tools">
    <button id="scan">📶 Scan QR to join Wi-Fi</button>
    <button id="look">📷 See what it sees</button>
  </div>
  <div class="vol">🔈<input type="range" id="vol" min="20" max="100" step="5" value="100" aria-label="Volume">🔊<span id="volv"></span></div>
</footer>
<script>
const STATE = {OFF:"no torque", WAKING:"waking up", IDLE:"idle", ATTENDING:"listening to you", PLAYING:"walking",
               RESTING:"resting", SLEEPING:"sleeping", FALLEN:"fallen", TIRED:"battery empty"};
const EMO = {"happy":"😄","curious":"🤔","coy":"🥺","shy":"😳","sleepy":"😪","sad":"😢","surprised":"😮"};  // keys are the emotion names lifed sends
const VIA = {brain:"brain", small:"small brain", vision:"eyes", eyes:"brain looking at a picture", mission:"mission"};
const MSTATE = {proposed:"waiting for you to say \"start\"", running:"running", paused:"paused", done:"done", failed:"failed", cancelled:"cancelled"};
const MSTEP = {pending:"·", running:"▶", done:"✓", failed:"✗"};
function modeLine(L) {
  const real = L.missions_mode === "real";
  const tof = L.tof_m == null ? "no data" : (L.tof_m === "far" ? "clear ahead" : `${L.tof_m} m ahead`);
  return `<div class="mmode">🧭 Mission mode: <b class="${real ? "bad" : ""}">${real ? "real (it will really walk)" : "dry run (it will not move)"}</b>
    <button id="mswitch">${real ? "Back to dry run" : "Switch to real"}</button> <span class="mnote">ToF: ${tof}</span></div>`;
}
async function switchMode(L) {
  const toReal = L.missions_mode !== "real";
  if (toReal && !confirm("In real mode, Xiaobai will really walk after you say the route and then \"start\". Make sure it stands on open, flat ground, you are next to it, and you can say \"stop\" or touch the gamepad at any moment. Go on?")) return;
  await post("/api/missions", {mode: toReal ? "real" : "dry"});
  setTimeout(refresh, 300);
}
function missionCard(M) {
  if (!M) return "";
  const rows = M.steps.map(s => `<div class="mstep ${s.status}">${MSTEP[s.status] || "·"} ${esc(s.words)}${s.note ? ` <span class="mnote">${esc(s.note)}</span>` : ""}</div>`).join("");
  const sim = M.sim ? ` · simulated position (${M.sim.x}, ${M.sim.y}) m, heading ${M.sim.yaw_deg}°, ${M.sim.posture === "sitting" ? "sitting" : "standing"}` : "";
  return `<div class="mission"><div class="mhead">🧭 Mission${M.mode === "dry" ? " (dry run, it will not really move)" : ""}: <b>${MSTATE[M.state] || M.state}</b>${M.why ? " (" + esc(M.why) + ")" : ""}</div>${rows}
    <div class="mnote">Position certainty: ±${M.sigma_m} m, ±${M.sigma_deg}°${sim}</div></div>`;
}
const INTENT = {sleep:"sleep", rest:"rest", sit:"sit down", stand:"stand up", wake:"wake up", net:"join a network", bye:"goodbye", chat:"chat", unclear:"unclear"};
const ACT = {ignore:"ignore", command:"as a command", small:"small brain answers", nod:"nod", brain:"brain answers"};
const SEEN = {looking_at_duck:"looking at it", waving:"waving", thumbs_up:"thumbs up", reaching:"reaching out", passing:"passing by", busy:"busy", unclear:"cannot tell"};
function jevNote(j) {
  if (!j || j.for_duck == null) return "";
  return ` · Jev: said to me ${Math.round(j.for_duck * 100)}% · ${INTENT[j.intent] || j.intent || "?"}${j.action ? " → " + (ACT[j.action] || j.action) : ""}`;
}
let lastKey = "";
function chip(label, value, cls) { return `<span class="chip">${label} <b class="${cls||""}">${value}</b></span>`; }
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function hhmm(t) { const d = new Date(t * 1000); return d.toLocaleTimeString("zh-CN", {hour:"2-digit", minute:"2-digit"}); }
async function refresh() {
  let s;
  try { s = await (await fetch("/api/state")).json(); } catch (e) {
    document.getElementById("chips").innerHTML = chip("Connection", "cannot reach Xiaobai", "bad"); return; }
  const L = s.life || {}, net = s.net || {}, V = s.vision || {};
  const c = [];
  c.push(chip("State", STATE[L.state] || (s.life ? L.state : "lifed is not running"), s.life ? "" : "bad"));
  if (L.battery_pct != null) c.push(chip("Battery", Math.round(L.battery_pct) + "%", L.battery_pct < 20 ? "bad" : L.battery_pct < 35 ? "warn" : "ok"));
  if (L.max_c != null) c.push(chip("Hottest", Math.round(L.max_c) + "°C", L.max_c >= 65 ? "bad" : L.max_c >= 58 ? "warn" : ""));
  c.push(chip("Brain", L.brain_online === false ? "offline · using small brain" : "online", L.brain_online === false ? "warn" : "ok"));
  c.push(chip("Network", net.ssid ? esc(net.ssid) + (net.ip ? " · " + net.ip : "") : "not connected", net.ssid ? "" : "bad"));
  if (L.clock) c.push(chip("Time", L.clock));
  const VOL = L.volume;
  if (VOL) {
    c.push(chip("Volume", VOL.now + "%" + (VOL.night_cap ? " (night)" : "")));
    const el = document.getElementById("vol");
    if (!volDragging) el.value = VOL.user;
    document.getElementById("volv").textContent = VOL.user + "%";
  }
  const J = L.jev;
  if (J) c.push(chip("Jev", J.mode === "off" ? "off" : `${J.mode === "shadow" ? "shadow" : "on"} · ${J.ok} times${J.fallback ? " · fell back " + J.fallback : ""}`,
                     J.mode === "off" ? "" : (J.ok ? "ok" : "warn")));
  const look = V.last_look;
  if (look && look.via === "jev") c.push(chip("Just saw", look.present ? "someone · " + (SEEN[look.activity] || look.activity) : "nobody"));
  if (V.mode === "scan_qr" || L.scanning) c.push(chip("Eyes", "looking for a QR code…", "warn"));
  document.getElementById("chips").innerHTML = c.join("");
  document.getElementById("convo").textContent = L.convo_s_left > 0
    ? `In a conversation, still listening for ${Math.round(L.convo_s_left)} s` : "Call “Xiaobai” to start a conversation";
  document.getElementById("mission").innerHTML = (L.missions_mode ? modeLine(L) : "") + missionCard(L.mission);
  const sw = document.getElementById("mswitch");
  if (sw) sw.onclick = () => switchMode(L);
  const d = L.dialog || [];
  const key = d.map(x => x.t + x.who + (x.jev ? "j" : "")).join("|");
  if (key !== lastKey) {
    lastKey = key;
    const html = d.slice().reverse().map(x => x.who === "you"
      ? `<div class="msg you"><div class="bubble"><div class="meaning">${esc(x.text)}</div><div class="meta">${hhmm(x.t)}${x.command ? " · command" : ""}${esc(jevNote(x.jev))}</div></div></div>`
      : `<div class="msg duck"><div class="bubble"><div class="meaning">${EMO[x.emotion] || ""} ${esc(x.meaning || x.text)}</div>
           ${x.photo ? `<img class="look" src="/api/look/${encodeURIComponent(x.photo)}.jpg" alt="What it saw" onerror="this.remove()">` : ""}
           <div class="say">Duck-speak: ${esc(x.text)}</div><div class="meta">${hhmm(x.t)} · ${VIA[x.via] || ""}</div></div></div>`).join("");
    document.getElementById("log").innerHTML = html || '<div class="empty">No conversation yet. Call "Xiaobai", or type below.</div>';
  }
}
async function post(path, body) {
  try { return await (await fetch(path, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body || {})})).json(); }
  catch (e) { return {ok:false}; }
}
document.getElementById("send").onclick = async () => {
  const el = document.getElementById("text"); const text = el.value.trim(); if (!text) return;
  el.value = ""; await post("/api/say", {text}); setTimeout(refresh, 300);
};
document.getElementById("text").addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("send").click(); });
let volDragging = false;
const volEl = document.getElementById("vol");
volEl.oninput = () => { volDragging = true; document.getElementById("volv").textContent = volEl.value + "%"; };
volEl.onchange = async () => { await post("/api/volume", {value: Number(volEl.value)}); volDragging = false; setTimeout(refresh, 300); };
document.getElementById("scan").onclick = async () => { await post("/api/scan"); setTimeout(refresh, 300); };
document.getElementById("look").onclick = async () => {
  const b = document.getElementById("look"); b.disabled = true; b.textContent = "📷 Taking a photo…";
  const r = await post("/api/photo");
  b.disabled = false; b.textContent = "📷 See what it sees";
  const img = document.getElementById("photo");
  if (r.ok) { img.src = "/api/photo.jpg?" + Date.now(); img.style.display = "block"; }
  else { alert("Cannot take a photo: " + (r.reason || "the eyes are not running")); }
};
refresh(); setInterval(refresh, 1000);
</script>
</body></html>
"""
# the page is written with Xiaobai's name; it shows whichever duck's persona is installed
NAME = load_persona().name



def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--lifed", default="/tmp/lifed.sock")
    ap.add_argument("--vision", default="/tmp/visiond.sock")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.bind, a.port), Handler)
    srv.args = a
    print(time.strftime("%H:%M:%S"), f"duckweb on http://{a.bind}:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
