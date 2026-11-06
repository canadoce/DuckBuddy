# -*- coding: utf-8 -*-
"""Joint mapping check page: the MuJoCo training model shows the same pose as the real robot's joints, live.

robotd's `robot.state` gives 15 joint angles every tick (with joint_ids / signs / offsets applied, the same
angles the policy sees) and the IMU gravity direction. This tool applies them to the model that microduck_rl
trains on and renders it (`model/` comes from `robot/microduck_hl2915/` on the training server; its kinematics
match hardware/original). With torque off, move the robot by hand and check that the model turns the same way and by the same angle.

    python tools/joint_align/server.py                     # connect to the OPi, http://localhost:8770
    python tools/joint_align/server.py --demo              # no robot, only the model (sliders)

robotd must be running on the OPi; `--start-robotd` starts it on the OPi for you
(~/robot/robotd --params robotd-test.toml). On connect it sends robot.relax once to turn torque off, then only reads;
this tool never sends enable / move.

Calibration (2026-10-25, the HD-1910 robot): at start it reads joint_signs / joint_offsets from robotd's config (--config) on the OPi.
On the page each joint can be "Reverse"d (flip the sign), or the current pose can be "Set to zero" (recompute the offset); changes apply at once
to the display and the model (the robot.state angles are turned back into encoder readings with the values robotd uses now, then converted with the new values).
"Write config" makes a backup, then changes these two lines in the toml; with --restart-cmd it then restarts robotd so they take effect.

Fine-tuning: restarting robotd keeps the torque on, so you can fine-tune while standing in home. Each joint's −/+ makes it, for the same command angle,
actually turn 0.5° more in the negative/positive direction. "Write and go home" writes, restarts, then runs --init-cmd to move the robot smoothly to the new home:

    python tools/joint_align/server.py --host orangepi@duck-1a2b.local \\
        --restart-cmd "systemctl --user restart robotd-dev" \\
        --init-cmd "cd ~/robot && ./robotctl robot init --robot-socket /tmp/robotd.sock"
"""
import argparse
import io
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MODEL = os.path.join(HERE, "model", "robot_allcollisions.xml")
MESHDIR = os.path.join(ROOT, "hardware", "original", "mjcf", "assets")

# JOINT_NAMES and home pose from duck-control/src/model.rs (mouth is not in the training model)
JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]
JOINT_CN = {
    "left_hip_yaw": "Left hip yaw", "left_hip_roll": "Left hip roll", "left_hip_pitch": "Left hip pitch",
    "left_knee": "Left knee", "left_ankle": "Left ankle",
    "neck_pitch": "Neck pitch", "head_pitch": "Head pitch", "head_yaw": "Head yaw", "head_roll": "Head roll",
    "mouth": "Mouth",
    "right_hip_yaw": "Right hip yaw", "right_hip_roll": "Right hip roll", "right_hip_pitch": "Right hip pitch",
    "right_knee": "Right knee", "right_ankle": "Right ankle",
}
HOME = [0.0, -0.0873, -0.4579, -0.0049, 0.4530,
        0.3491, 0.3491, 0.0, 0.0, 0.0,
        0.0, 0.0873, 0.4579, 0.0049, -0.4530]

# Runs on the OPi: subscribe to robot.state and print one short JSON line per tick
REMOTE = r'''
import socket, json, sys
# Relax first: the HL-2915 torque can be on at power-up, but robotd assumes it is off at start and does not turn it off.
# Only on the first connect: later reconnects are most likely "Write and go home" restarting robotd, while the robot is being moved back to home.
if "relax" in sys.argv[1:]:
    r = socket.socket(socket.AF_UNIX); r.connect("/tmp/robotd.sock")
    r.sendall(b'{"jsonrpc":"2.0","id":2,"method":"robot.relax"}\n'); r.recv(4096); r.close()
s = socket.socket(socket.AF_UNIX); s.connect("/tmp/robotd.sock")
s.sendall(b'{"jsonrpc":"2.0","id":1,"method":"robot.subscribe","params":{"hz":20}}\n')
buf = b""
while True:
    d = s.recv(65536)
    if not d: break
    buf += d
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        try: m = json.loads(line)
        except Exception: continue
        if m.get("method") != "robot.state": continue
        p = m["params"]
        print(json.dumps({"t": p.get("t"), "joints": p.get("joints"), "targets": p.get("targets"),
                          "gravity": p.get("safety", {}).get("gravity"), "policy": p.get("policy")}), flush=True)
'''


class Live:
    """The latest robot state, updated by the SSH reader thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.joints = list(HOME)
        self.gravity = [0.0, 0.0, -1.0]
        self.stamp = 0.0
        self.status = "Not connected"
        self.policy = None

    def set(self, joints, gravity, policy):
        with self.lock:
            if joints and len(joints) == 15:
                self.joints = list(joints)
            if gravity and len(gravity) == 3:
                self.gravity = list(gravity)
            self.policy = policy
            self.stamp = time.time()
            self.status = "Connected"

    def get(self):
        with self.lock:
            return list(self.joints), list(self.gravity), self.stamp, self.status, self.policy


def reader(live, host, start_robotd):
    first = True
    while True:
        if start_robotd:
            # Wrap the whole start in nohup sh -c and close all fds, or ssh keeps waiting for the background process output
            start = ("cd ~/robot && ORT_DYLIB_PATH=$HOME/robot/onnxruntime-linux-aarch64-1.28.3/lib/libonnxruntime.so "
                     "exec ./robotd --params robotd-test.toml --socket /tmp/robotd.sock > /tmp/robotd.log 2>&1")
            try:
                subprocess.run(["ssh", "-o", "BatchMode=yes", host,
                                "pgrep -x robotd >/dev/null || { nohup sh -c '" + start + "' "
                                "> /dev/null 2>&1 < /dev/null & sleep 5; }"],
                               capture_output=True, timeout=30)
            except subprocess.TimeoutExpired:
                live.status = "Starting robotd timed out"
        live.status = "Connecting…"
        try:
            # The script goes through stdin (python3 -), so the remote shell does not parse its quotes
            p = subprocess.Popen(["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=3", host,
                                  "python3", "-u", "-"] + (["relax"] if first else []),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace")
            p.stdin.write(REMOTE)
            p.stdin.close()
            for line in p.stdout:
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                first = False
                live.set(m.get("joints"), m.get("gravity"), m.get("policy"))
            err = p.stderr.read().strip().splitlines()
            live.status = "Disconnected: " + (err[-1] if err else "is robotd running?")
        except Exception as e:  # noqa: BLE001
            live.status = f"Disconnected: {e}"
        time.sleep(2)


RAD_PER_COUNT = 2 * math.pi / 4096

# Runs on the OPi: read signs / offsets from robotd's config (tomllib, Python 3.11+)
READ_CONFIG = r'''
import json, os, sys, tomllib
path = os.path.realpath(os.path.expanduser(sys.argv[1]))
bus = tomllib.load(open(path, "rb")).get("bus", {})
print(json.dumps({"path": path, "signs": bus.get("joint_signs") or [1] * 15,
                  "offsets": bus.get("joint_offsets") or [0] * 15}))
'''

# Runs on the OPi: make a backup, then change only the joint_signs / joint_offsets lines (each a one-line array) and add a comment line above them
WRITE_CONFIG = r'''
import json, re, shutil, sys, time
path, signs, offsets = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
text = open(path, encoding="utf-8").read()
fmt = lambda v: "[" + ", ".join("%4d" % x for x in v).lstrip() + "]"
for key, vals in (("joint_signs", signs), ("joint_offsets", offsets)):
    pat = re.compile(r"^(%s\s*=\s*)\[[^\]\n]*\]" % key, re.M)
    if not pat.search(text):
        sys.exit("no single-line %s in %s" % (key, path))
    text = pat.sub(lambda m: m.group(1) + fmt(vals), text, count=1)
stamp = time.strftime("%Y%m%d-%H%M%S")
note = "# %s joint_align: joint_signs / joint_offsets set on the robot by hand\n" % time.strftime("%Y-%m-%d")
text = re.sub(r"^# [0-9-]+ joint_align: joint_signs / joint_offsets set on the robot by hand\n", "", text, flags=re.M)
text = re.sub(r"^(joint_signs\s*=)", lambda m: note + m.group(1), text, count=1, flags=re.M)
shutil.copy2(path, path + ".bak-" + stamp)
open(path, "w", encoding="utf-8").write(text)
print(path + ".bak-" + stamp)
'''


class Calib:
    """The signs / offsets robotd uses now (read from the OPi) and the set being tried on the page.

    The robot.state angles use the current values: a = s0·(raw − 2048 − o0)·k. First get back raw − 2048 = s0·a/k + o0,
    then convert with the trial values: a' = s1·(raw − 2048 − o1)·k."""

    def __init__(self, host, config, restart_cmd, init_cmd):
        self.host, self.config, self.restart_cmd, self.init_cmd = host, config, restart_cmd, init_cmd
        self.lock = threading.Lock()
        self.loaded = None          # (signs, offsets) that robotd uses now
        self.signs = self.offsets = None
        self.path = None
        self.msg = "Reading config…"

    def load(self):
        try:
            out = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, "python3", "-", self.config],
                                 input=READ_CONFIG, capture_output=True, text=True, timeout=20)
            cfg = json.loads(out.stdout)
        except Exception as e:  # noqa: BLE001
            self.msg = f"Cannot read config: {e}"
            return
        with self.lock:
            self.loaded = ([int(s) for s in cfg["signs"]], [int(o) for o in cfg["offsets"]])
            self.signs, self.offsets = list(self.loaded[0]), list(self.loaded[1])
            self.path = cfg["path"]
            self.msg = f"Config loaded from {self.path}"

    def _counts(self, i, a):
        return self.loaded[0][i] * a / RAD_PER_COUNT + self.loaded[1][i]

    def apply(self, joints):
        with self.lock:
            if not self.loaded:
                return joints
            return [self.signs[i] * (self._counts(i, a) - self.offsets[i]) * RAD_PER_COUNT
                    for i, a in enumerate(joints)]

    def flip(self, i):
        with self.lock:
            if self.loaded:
                self.signs[i] = -self.signs[i]

    def zero(self, idx, joints, target=None):
        """Save the current pose of these joints as 0°; if target is given (for example the standing HOME), save it as target[i].
        a' = s·(raw − 2048 − o)·k = t  →  o = (raw − 2048) − s·t/k, where s is the direction being tried."""
        with self.lock:
            if self.loaded:
                for i in idx:
                    t = target[i] if target else 0.0
                    self.offsets[i] = int(round(self._counts(i, joints[i]) - self.signs[i] * t / RAD_PER_COUNT))

    def nudge(self, i, deg):
        """For the same command angle, make this joint actually turn deg degrees more in the positive direction (the reading drops by deg)."""
        with self.lock:
            if self.loaded:
                self.offsets[i] += self.signs[i] * int(round(math.radians(deg) / RAD_PER_COUNT))

    def reset(self):
        with self.lock:
            if self.loaded:
                self.signs, self.offsets = list(self.loaded[0]), list(self.loaded[1])

    def save(self, home=False):
        with self.lock:
            if not self.loaded:
                return False, "Config not read yet"
            signs, offsets = list(self.signs), list(self.offsets)
        try:
            out = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, "python3", "-", self.path,
                                  "'" + json.dumps(signs) + "'", "'" + json.dumps(offsets) + "'"],
                                 input=WRITE_CONFIG, capture_output=True, text=True, timeout=20)
        except Exception as e:  # noqa: BLE001
            return False, f"Write failed: {e}"
        if out.returncode != 0:
            return False, "Write failed: " + (out.stderr.strip().splitlines() or ["?"])[-1]
        msg = f"Wrote {self.path} (backup {out.stdout.strip()})"
        if self.restart_cmd:
            r = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, self.restart_cmd],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return False, msg + "; restarting robotd failed: " + r.stderr.strip()
            with self.lock:
                self.loaded = (signs, offsets)
            msg += "; robotd restarted"
            if home and self.init_cmd:
                # Restarting robotd keeps the torque on; robotd must read the bus once before it accepts init, so on failure wait a bit and retry
                for _ in range(5):
                    time.sleep(1.5)
                    r = subprocess.run(["ssh", "-o", "BatchMode=yes", self.host, self.init_cmd],
                                       capture_output=True, text=True, timeout=30)
                    if r.returncode == 0:
                        return True, msg + "; going to home"
                return False, msg + "; going to home failed: " + (r.stderr.strip() or r.stdout.strip())
        else:
            msg += "; takes effect after robotd restarts (until then the display still uses the trial values)"
        return True, msg

    def snapshot(self):
        with self.lock:
            if not self.loaded:
                return dict(ready=False, msg=self.msg)
            return dict(ready=True, msg=self.msg, path=self.path, signs=self.signs, offsets=self.offsets,
                        can_home=bool(self.restart_cmd and self.init_cmd),
                        loaded_signs=self.loaded[0], loaded_offsets=self.loaded[1])


class Renderer:
    """Renders on one thread (a GL context cannot be shared across threads); requests wait in a queue."""

    def __init__(self):
        self.q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def render(self, joints, gravity, view, bump=None, deg=0.0):
        done = queue.Queue(1)
        self.q.put((joints, gravity, view, bump, deg, done))
        return done.get(timeout=10)

    def _run(self):
        import mujoco
        from PIL import Image
        try:
            spec = mujoco.MjSpec.from_file(MODEL)
            spec.meshdir = MESHDIR
            floor = spec.worldbody.add_geom()
            floor.type = mujoco.mjtGeom.mjGEOM_PLANE
            floor.size = [1, 1, 0.01]
            floor.rgba = [0.55, 0.6, 0.66, 1]
            for pos in ([0.6, 0.6, 1.2], [-0.6, -0.4, 1.0]):
                light = spec.worldbody.add_light()
                light.pos = pos
                light.dir = -np.asarray(pos) / np.linalg.norm(pos)
                light.diffuse = [0.6, 0.6, 0.6]
            spec.visual.headlight.ambient = [0.35, 0.35, 0.35]
            model = spec.compile()
        except Exception as e:  # noqa: BLE001
            print("model load failed:", e, file=sys.stderr, flush=True)
            while True:
                *_, done = self.q.get()
                done.put(b"")
        data = mujoco.MjData(model)
        r = mujoco.Renderer(model, height=420, width=420)
        adr = {n: model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n)]
               for n in JOINT_NAMES if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, n) >= 0}
        cam = mujoco.MjvCamera()
        while True:
            joints, gravity, view, bump, deg, done = self.q.get()
            try:
                mujoco.mj_resetData(model, data)
                for i, n in enumerate(JOINT_NAMES):
                    if n in adr:
                        data.qpos[adr[n]] = joints[i] + (math.radians(deg) if n == bump else 0.0)
                # Body attitude: rotate the gravity direction in the body frame to world -z (yaw set to 0)
                g = np.asarray(gravity, float)
                g = g / (np.linalg.norm(g) or 1.0)
                down = np.array([0.0, 0.0, -1.0])
                axis = np.cross(g, down)
                s, c = np.linalg.norm(axis), float(np.dot(g, down))
                quat = np.array([1.0, 0, 0, 0]) if s < 1e-9 else np.r_[
                    math.cos(math.atan2(s, c) / 2), axis / s * math.sin(math.atan2(s, c) / 2)]
                data.qpos[0:3] = [0, 0, 0.3]
                data.qpos[3:7] = quat
                mujoco.mj_kinematics(model, data)
                # Put the lowest point of the body on the floor (also works lying on the back or front): geom center minus its bounding radius
                zmin = float(np.min(data.geom_xpos[1:, 2] - model.geom_rbound[1:] * 0.6))
                data.qpos[2] -= zmin
                mujoco.mj_kinematics(model, data)
                cam.lookat[:] = [0.0, 0.0, 0.11]
                cam.distance = 0.55
                cam.elevation = -8.0
                # The robot faces +x: front = seen from +x (the robot's left leg is on the right of the image), side = seen from the left, +y (the robot faces the left of the image), iso = front-left
                cam.azimuth = {"front": 180.0, "side": 270.0, "iso": 215.0}.get(view, 180.0)
                r.update_scene(data, camera=cam)
                img = Image.fromarray(r.render())
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=82)
                done.put(buf.getvalue())
            except Exception as e:  # noqa: BLE001
                print("render error:", e, file=sys.stderr)
                done.put(b"")


def make_handler(live, renderer, demo, calib):
    page = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    slider = {"joints": list(HOME)}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _pose(self):
            if demo:
                return list(slider["joints"]), [0.0, 0.0, -1.0], time.time(), "Demo (no robot)", None
            joints, *rest = live.get()
            return (calib.apply(joints), *rest)

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            if u.path == "/":
                return self._send(page.encode(), "text/html; charset=utf-8")
            if u.path == "/state":
                joints, gravity, stamp, status, policy = self._pose()
                g = np.asarray(gravity, float)
                pitch = math.degrees(math.atan2(g[0], math.hypot(g[1], g[2])))
                roll = math.degrees(math.atan2(-g[1], -g[2]))
                body = dict(names=JOINT_NAMES, cn=[JOINT_CN[n] for n in JOINT_NAMES], joints=joints,
                            home=HOME, gravity=gravity, pitch=pitch, roll=roll, demo=demo,
                            age=time.time() - stamp if stamp else None, status=status, policy=policy,
                            calib=calib.snapshot() if calib else dict(ready=False, msg="Demo mode"))
                return self._send(json.dumps(body).encode(), "application/json")
            if u.path == "/frame":
                joints, gravity, *_ = self._pose()
                ref = qs.get("pose", [None])[0]
                if ref in ("zero", "home"):  # reference pose: the model with the body level, to pose the real robot after
                    joints, gravity = ([0.0] * len(HOME) if ref == "zero" else list(HOME)), [0.0, 0.0, -1.0]
                bump = qs.get("bump", [None])[0]
                deg = float(qs.get("deg", ["0"])[0])
                jpg = renderer.render(joints, gravity, qs.get("view", ["front"])[0], bump, deg)
                return self._send(jpg, "image/jpeg")
            self._send(b"not found", "text/plain", 404)

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/demo_pose" and demo:
                j = body.get("joints")
                if isinstance(j, list) and len(j) == 15:
                    slider["joints"] = [float(x) for x in j]
                return self._send(b"{}", "application/json")
            if calib and u.path in ("/flip", "/nudge", "/zero", "/reset", "/save"):
                ok, msg = True, ""
                if u.path == "/flip":
                    calib.flip(int(body["i"]))
                elif u.path == "/nudge":
                    calib.nudge(int(body["i"]), float(body["deg"]))
                elif u.path == "/zero":
                    joints, _, stamp, *_ = live.get()
                    if not stamp or time.time() - stamp > 1.0:
                        ok, msg = False, "The robot reading is not fresh; nothing was saved"
                    else:
                        idx = [int(body["i"])] if body.get("i") is not None else range(len(JOINT_NAMES))
                        calib.zero(idx, joints, HOME if body.get("ref") == "home" else None)
                elif u.path == "/reset":
                    calib.reset()
                else:
                    ok, msg = calib.save(home=bool(body.get("home")))
                calib.msg = msg or calib.msg
                return self._send(json.dumps(dict(ok=ok, msg=msg)).encode(), "application/json")
            self._send(b"{}", "application/json", 404)

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="orangepi@<robot-ip>")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--start-robotd", action="store_true")
    ap.add_argument("--config", default="~/robot/active.toml", help="config that robotd reads on the OPi (calibration is written back here)")
    ap.add_argument("--restart-cmd", default="", help="run on the OPi after writing the config, so robotd reads the config again")
    ap.add_argument("--init-cmd", default="", help="run by \"Write and go home\" after the restart, so the robot turns torque on and goes to home")
    a = ap.parse_args()

    live = Live()
    calib = None
    if not a.demo:
        threading.Thread(target=reader, args=(live, a.host, a.start_robotd), daemon=True).start()
        calib = Calib(a.host, a.config, a.restart_cmd, a.init_cmd)
        threading.Thread(target=calib.load, daemon=True).start()
    renderer = Renderer()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(live, renderer, a.demo, calib))
    print(f"http://localhost:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
