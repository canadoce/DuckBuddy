# -*- coding: utf-8 -*-
"""robotpanel: a small control page for the robot's body, for bring-up without a gamepad.

Served by the brain on the local network (http://<brain>:8090, standard library only). Four
buttons (Stand, Policy on, Policy off, Relax), a slider for the neck (it moves the head while
the robot holds home and while a policy drives), and a live line on what the
robot is doing: what drives it, how far it leans, its hottest servo and its battery. It also shows
whether lifed (the life layer, which can move the head and ask the robot to rest) is running, and
stops or starts it, so a test is not mixed with what lifed decides to do. lifed-dev follows
robotd-dev, so a robotd restart starts it again.

It talks to robotd over its socket with the same calls the gamepad uses (robot.init, robot.enable,
robot.relax, robot.head) and to systemd for lifed-dev. It never opens the servo bus.

    python3 robotpanel.py [--port 8090] [--robot /tmp/robotd.sock]
"""
from __future__ import annotations

import argparse
import json
import math
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# duck_control::JOINT_NAMES order: left leg, neck/head/mouth, right leg
JOINTS = ["left hip yaw", "left hip roll", "left hip pitch", "left knee", "left ankle",
          "neck pitch", "head pitch", "head yaw", "head roll", "mouth",
          "right hip yaw", "right hip roll", "right hip pitch", "right knee", "right ankle"]
NECK_MIN_DEG, NECK_MAX_DEG = -30.0, 15.0  # the slider's range, degrees from the home pose
LIFED_UNIT = "lifed-dev"


def rpc(path: str, method: str, params: dict | None = None, timeout: float = 3.0):
    """One JSON-RPC request over robotd's socket. Returns (result, error text)."""
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(timeout)
        s.connect(path)
        s.sendall((json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        reply = json.loads(buf.split(b"\n", 1)[0])
    except Exception as e:  # noqa: BLE001
        return None, f"robotd did not answer: {e}"
    if "error" in reply:
        return None, reply["error"].get("message", str(reply["error"]))
    return reply.get("result"), None


def unit_active(unit: str) -> bool:
    r = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True, text=True)
    return r.stdout.strip() == "active"


class Robot:
    """The latest robot.state from a subscription, and what this page last asked for."""

    def __init__(self, sock: str):
        self.sock = sock
        self.lock = threading.Lock()
        self.state = None
        self.state_at = 0.0
        self.health = None
        self.powered = False  # robotd does not report torque: this follows init/enable/relax
        self.last_t = None
        self.message = ""
        threading.Thread(target=self._subscribe, daemon=True).start()
        threading.Thread(target=self._poll_health, daemon=True).start()

    def _subscribe(self):
        while True:
            try:
                s = socket.socket(socket.AF_UNIX)
                s.connect(self.sock)
                s.sendall(b'{"jsonrpc":"2.0","id":1,"method":"robot.subscribe","params":{"hz":5}}\n')
                for line in s.makefile():
                    m = json.loads(line)
                    if m.get("method") != "robot.state":
                        continue
                    p = m["params"]
                    with self.lock:
                        # robotd starts with the joints limp: a clock that went back is a restart
                        if self.last_t is not None and p.get("t", 0) < self.last_t:
                            self.powered = False
                        self.last_t = p.get("t", 0)
                        if p.get("policy") not in ("held", None):
                            self.powered = True
                        self.state, self.state_at = p, time.time()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1.0)

    def _poll_health(self):
        while True:
            h, _ = rpc(self.sock, "robot.health")
            with self.lock:
                self.health = h
            time.sleep(5.0)

    def snapshot(self) -> dict:
        with self.lock:
            p, at, h, powered, message = self.state, self.state_at, self.health, self.powered, self.message
        out = {"connected": p is not None and time.time() - at < 2.0, "message": message,
               "lifed": unit_active(LIFED_UNIT),
               "battery": round(h["battery"]["percent"]) if h and h.get("battery") else None,
               "neck_limits": [NECK_MIN_DEG, NECK_MAX_DEG]}
        if not out["connected"]:
            out["status"] = "robotd is not running"
            return out
        g = p["safety"]["gravity"]
        temps = p.get("temps_c") or []
        hot = max(range(len(temps)), key=lambda i: temps[i]) if temps else None
        policy = p.get("policy") or "held"
        if p["safety"].get("fallen"):
            status = "Fallen"
        elif policy == "homing":
            status = "Standing up"
        elif policy in ("limp_fall", "limp_pose"):
            status = "Falling: going soft"
        elif policy != "held":
            status = f"Policy driving ({policy})"
        else:
            status = "Holding home" if powered else "Relaxed"
        out.update(
            status=status,
            policy=policy,
            # trunk-frame gravity: +x is the trunk leaning forward
            pitch=round(math.degrees(math.atan2(g[0], math.hypot(g[1], g[2]))), 1),
            side=round(abs(math.degrees(math.atan2(-g[1], -g[2]))), 1),
            hottest=None if hot is None else {"name": JOINTS[hot] if hot < len(JOINTS) else str(hot),
                                              "c": round(temps[hot])},
            neck_cmd=round(math.degrees(p["head"][0]), 1) if p.get("head") else 0.0,
        )
        return out

    def do(self, what: str, args: dict) -> str:
        if what == "stand":
            r, err = rpc(self.sock, "robot.init")
            msg = err or "standing up to the home pose"
            if not err:
                self.powered = True
        elif what == "policy_on":
            r, err = rpc(self.sock, "robot.enable", {"on": True, "toggle": False})
            msg = err or (r or {}).get("reason", "policy on")
            if not err:
                self.powered = True
        elif what == "policy_off":
            r, err = rpc(self.sock, "robot.enable", {"on": False, "toggle": False})
            msg = err or (r or {}).get("reason", "policy off")
        elif what == "relax":
            r, err = rpc(self.sock, "robot.relax")
            msg = err or "torque off: the robot is limp"
            if not err:
                self.powered = False
        elif what == "head":
            deg = max(NECK_MIN_DEG, min(NECK_MAX_DEG, float(args.get("neck_deg", 0.0))))
            # robot.head is a notification in the protocol; sent as a request it is answered too.
            # robotd applies it to the home pose it holds, and passes it to a driving policy
            r, err = rpc(self.sock, "robot.head", {"neck_pitch": math.radians(deg), "head_pitch": 0.0,
                                                   "head_yaw": 0.0, "head_roll": 0.0})
            msg = err or f"neck command {deg:+.0f}°"
        elif what in ("lifed_on", "lifed_off"):
            verb = "start" if what == "lifed_on" else "stop"
            r = subprocess.run(["systemctl", "--user", verb, LIFED_UNIT], capture_output=True, text=True)
            msg = r.stderr.strip() or f"lifed {'started' if verb == 'start' else 'stopped'}"
        else:
            msg = f"unknown action {what!r}"
        with self.lock:
            self.message = f"{time.strftime('%H:%M:%S')}  {msg}"
        return msg


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Robot Controls</title>
<style>
:root{--bg:#f4f2ee;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e2dfd8;--go:#1f7a4d;--stop:#b3261e;--warn:#a15c00;--btn:#ecebe7}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1f1f22;--ink:#f2f2f2;--mute:#9a9aa0;--line:#333338;--go:#3fb27f;--stop:#ff6b5e;--warn:#e7a54a;--btn:#2a2a2e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 system-ui,-apple-system,sans-serif}
main{max-width:480px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:14px}
#status{font-size:28px;font-weight:650;margin:0 0 6px}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;color:var(--mute);font-size:15px}
.facts b{color:var(--ink);font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
button{font:inherit;font-weight:600;font-size:18px;border:0;border-radius:12px;padding:18px 8px;background:var(--btn);color:var(--ink);cursor:pointer}
button:active{transform:scale(.98)}
.go{background:var(--go);color:#fff}.stop{background:var(--stop);color:#fff}
.small{font-size:14px;padding:8px 12px}
.row{display:flex;align-items:center;justify-content:space-between;gap:10px}
input[type=range]{width:100%;margin:14px 0 6px;accent-color:var(--go)}
.hint{color:var(--mute);font-size:14px;margin:8px 0 0}
#msg{color:var(--mute);font-size:14px;min-height:20px}
.warn{color:var(--warn)}
</style></head><body><main>
<div class="card">
  <p id="status">…</p>
  <div class="facts">
    <span>Lean <b id="pitch">–</b></span><span>Side <b id="side">–</b></span>
    <span>Hottest <b id="hot">–</b></span><span>Battery <b id="bat">–</b></span>
  </div>
</div>
<div class="card">
  <div class="grid">
    <button id="stand">Stand</button>
    <button class="go" id="policy_on">Policy on</button>
    <button id="policy_off">Policy off</button>
    <button class="stop" id="relax">Relax</button>
  </div>
  <p class="hint">Hold the robot before Stand, Policy on and Relax. Relax makes it limp.</p>
</div>
<div class="card">
  <div class="row"><span>Head <b id="neckv">0°</b></span><button class="small" id="center">Center</button></div>
  <input type="range" id="neck" step="1" value="0">
  <div class="row hint" style="margin:0"><span>forward</span><span>back</span></div>
  <p class="hint">Works while the robot stands at home and while the policy is on.</p>
</div>
<div class="card">
  <div class="row"><span>Life layer: <b id="lifed">–</b></span><button class="small" id="lifedbtn">–</button></div>
  <p class="hint" id="lifedhint"></p>
</div>
<p id="msg"></p>
</main>
<script>
const $ = id => document.getElementById(id);
let dragging = false, lifed = false;
async function send(what, args) {
  try {
    const r = await fetch("/cmd", {method: "POST", headers: {"Content-Type": "application/json"},
                                   body: JSON.stringify(Object.assign({do: what}, args || {}))});
    $("msg").textContent = (await r.json()).message;
  } catch (e) { $("msg").textContent = "the page lost the robot: " + e; }
  refresh();
}
for (const id of ["stand", "policy_on", "policy_off", "relax"]) $(id).onclick = () => send(id);
const neck = $("neck");
function showNeck() { $("neckv").textContent = (neck.value > 0 ? "+" : "") + neck.value + "°"; }
neck.oninput = () => { dragging = true; showNeck(); };
neck.onchange = () => { dragging = false; send("head", {neck_deg: Number(neck.value)}); };
$("center").onclick = () => { neck.value = 0; showNeck(); send("head", {neck_deg: 0}); };
$("lifedbtn").onclick = () => send(lifed ? "lifed_off" : "lifed_on");
async function refresh() {
  let s;
  try { s = await (await fetch("/state")).json(); } catch (e) { $("status").textContent = "No connection to the brain"; return; }
  $("status").textContent = s.status;
  if (s.connected) {
    const p = s.pitch;
    $("pitch").textContent = Math.abs(p) < 1 ? "level" : Math.abs(p) + "° " + (p > 0 ? "forward" : "back");
    $("side").textContent = s.side + "°";
    $("hot").textContent = s.hottest ? s.hottest.c + " °C" : "–";
    $("hot").className = s.hottest && s.hottest.c >= 60 ? "warn" : "";
    if (!dragging) {
      neck.min = s.neck_limits[0]; neck.max = s.neck_limits[1];
      neck.value = Math.round(s.neck_cmd); showNeck();
    }
  }
  $("bat").textContent = s.battery == null ? "–" : s.battery + "%";
  lifed = s.lifed;
  $("lifed").textContent = lifed ? "running" : "stopped";
  $("lifedbtn").textContent = lifed ? "Stop" : "Start";
  $("lifedhint").textContent = lifed ? "It can turn the head and make the robot rest by itself. Stop it while testing." : "";
  if (s.message && !$("msg").textContent) $("msg").textContent = s.message;
}
refresh(); setInterval(refresh, 500);
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--robot", default="/tmp/robotd.sock")
    a = ap.parse_args()
    robot = Robot(a.robot)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body: bytes, kind: str):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/state":
                self._send(200, json.dumps(robot.snapshot()).encode(), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/cmd":
                return self._send(404, b"not found", "text/plain")
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                msg = robot.do(str(body.get("do", "")), body)
            except Exception as e:  # noqa: BLE001
                msg = f"failed: {e}"
            self._send(200, json.dumps({"message": msg}).encode(), "application/json")

    print(f"robotpanel on :{a.port}, robotd at {a.robot}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
