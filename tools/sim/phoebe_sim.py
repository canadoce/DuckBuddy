# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "aiohttp>=3.12",
#     "numpy>=2.2",
#     "opencv-python-headless>=4.12",
#     "sherpa-onnx>=2.0.1",
#     "soundfile>=0.13",
#     "fastapi>=0.118",
#     "uvicorn>=0.37",
# ]
# ///
"""phoebe-sim: the whole duck on a Mac, with a web page for its body.

    uv run tools/sim/phoebe_sim.py [--port 8090] [--no-build] [--open]

Starts the brain's services as they run on the Orange Pi (robotd --fake, lifed, voiced, visiond,
duckweb, duckbrain, duckjev), with the hardware replaced:

- the microphone is the browser's (voiced reads it through an `arecord` stand-in, tools/sim/shim.py);
- every sound (robotd's voice, lifed's clips) plays in the browser (an `aplay` stand-in);
- the camera is the browser's (a `duckcam` stand-in): faces, motion, QR codes and Jev's photos work;
- the ToF in the face is a slider (a stand-in tofd on its socket);
- the robot's tilt is a set of buttons (robotd --fake-tilt): lean it, lay it down, see it fall;
- the speaker volume (`amixer`) and the Wi-Fi (`nmcli`, for the QR code join) are pretend.

Open http://127.0.0.1:8090 (the page needs a click to turn on the sound, the mic and the camera).
Use headphones: the mic hears the speaker otherwise. Settings, as on the brain:
~/.config/duck/persona.json (or $DUCK_PERSONA), ~/.config/duckbrain/jev.env and duckbrain.env.
Its own files: ~/.local/state/phoebe-sim (logs, voice prints, the sound bank), /tmp/phoebe-sim
(the sockets), ~/.cache/duckbuddy (the hearing models and voice clips, shared with deploy.sh).
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import itertools
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import webbrowser

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TOOLS = os.path.join(REPO, "tools")
RUN = "/tmp/phoebe-sim"
STATE = os.path.expanduser("~/.local/state/phoebe-sim")
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "duckbuddy")
MODELS = os.path.join(CACHE, "hearing")
VOICE = "en-US-JennyNeural"
CLIPS = os.path.join(CACHE, f"voice-{VOICE}")
BIN = os.path.join(STATE, "bin")
SOCK = os.path.join(RUN, "sim.sock")
TILT = os.path.join(STATE, "tilt")
ROBOT_CONFIG = os.path.join(REPO, "deploy", "robots", "opi-hl2915-robothat-e1.toml")
PORTS = {"duckweb": 18088, "duckbrain": 18210, "duckjev": 18211}
SHIMS = ("aplay", "arecord", "duckcam", "amixer", "nmcli", "timedatectl", "ip")
MIC_RATE = 48000                 # what the page sends: mono 16-bit at 48 kHz
CAM_W, CAM_H = 1920, 1080        # duckcam's frame (the IMX219 at 1080p)
TOF_HZ = 15
PLAY_LEAD_S = 0.15               # how far a sound may run ahead of real time on its way to the page
LOG_LINES = 400
ANSI = re.compile(r"\x1b\[[0-9;]*m")

ORT = "onnxruntime-osx-arm64-1.28.3"          # the brain's version (deploy.sh), for robotd's policies
ORT_URL = f"https://github.com/microsoft/onnxruntime/releases/download/v1.28.3/{ORT}.tgz"
POLICIES = os.path.join(REPO, "policies")
REL = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
MOON = "sherpa-onnx-moonshine-base-en-quantized-2026-02-27"
MODEL_FILES = {                  # the same files deploy/brain/deploy.sh puts in ~/models/hearing
    "silero_vad.onnx": f"{REL}/asr-models/silero_vad.onnx",
    "dpdfnet_baseline.onnx": f"{REL}/speech-enhancement-models/dpdfnet_baseline.onnx",
    "gtcrn_simple.onnx": f"{REL}/speech-enhancement-models/gtcrn_simple.onnx",
    "nemo_en_titanet_small.onnx": f"{REL}/speaker-recongition-models/nemo_en_titanet_small.onnx",
}
TILTS = {                        # gravity in the trunk frame (x forward, y left, z up): upright is 0 0 -1
    "upright": (0.0, 0.0, -1.0),
    "lean forward": (0.5, 0.0, -0.866),
    "lean back": (-0.5, 0.0, -0.866),
    "on its front": (1.0, 0.0, 0.0),
    "on its back": (-1.0, 0.0, 0.0),
    "on its side": (0.0, 1.0, 0.0),
    "upside down": (0.0, 0.0, 1.0),
}


def say(msg):
    print(f"phoebe-sim: {msg}", flush=True)


# ── setup ────────────────────────────────────────────────────────────────────────────────────────

def persona_path() -> str:
    for p in (os.environ.get("DUCK_PERSONA"), os.path.expanduser("~/.config/duck/persona.json")):
        if p and os.path.exists(os.path.expanduser(p)):
            return os.path.expanduser(p)
    return os.path.join(TOOLS, "persona", "example.json")


def read_env(path) -> dict:
    """NAME=value lines, as systemd's EnvironmentFile reads them."""
    out = {}
    try:
        with open(os.path.expanduser(path)) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def write_shims():
    os.makedirs(BIN, exist_ok=True)
    shim = os.path.join(HERE, "shim.py")
    for name in SHIMS:
        p = os.path.join(BIN, name)
        with open(p, "w") as f:
            f.write(f'#!/bin/sh\nexec "{sys.executable}" "{shim}" {name} "$@"\n')
        os.chmod(p, 0o755)


def build(skip: bool):
    if not skip:
        say("building robotd and sounds (cargo build)")
        subprocess.run(["cargo", "build", "-q", "-p", "robotd", "-p", "sounds"], cwd=REPO, check=True)
    for b in ("robotd", "sounds"):
        if not os.access(os.path.join(REPO, "target", "debug", b), os.X_OK):
            sys.exit(f"no target/debug/{b}: run without --no-build")


def sound_bank(seed: int) -> str:
    bank = os.path.join(STATE, "sounds")
    subprocess.run([os.path.join(REPO, "target", "debug", "sounds"), "ensure-bank", "--dir", bank,
                    "--seed", str(seed)], check=True, stdout=subprocess.DEVNULL)
    return bank


def onnxruntime() -> str:
    """libonnxruntime for robotd's policies (it loads the library at run time, ORT_DYLIB_PATH)."""
    lib = os.path.join(CACHE, ORT, "lib", "libonnxruntime.dylib")
    if not os.path.exists(lib):
        with tempfile.TemporaryDirectory() as tmp:
            tgz = os.path.join(tmp, "ort.tgz")
            fetch(ORT_URL, tgz)
            with tarfile.open(tgz) as t:
                t.extractall(CACHE, filter="data")
    return lib


def robot_config(bank: str, policies: bool) -> str:
    """The brain's robot config, with the sound going to the page, the ToF to the slider and the
    policies from the repo (on the robot they come with the release)."""
    text = open(ROBOT_CONFIG).read()
    if policies:
        if "[policy]" in text:
            sys.exit(f"{ROBOT_CONFIG} has a [policy] section: phoebe_sim.py sets the policy paths itself")
        text += "\n[policy]\n" + "".join(
            f'{k} = "{POLICIES}/{f}"\n' for k, f in (
                ("walk", "alpha_walking.onnx"), ("stand", "alpha_stand.onnx"), ("sitstand", "alpha_sitstand.onnx"),
                ("ground_pick", "alpha_ground_pick.onnx"), ("kick_left", "ball_kick_left.onnx"),
                ("kick_right", "ball_kick_right.onnx"), ("roulade", "roulade.onnx")))
    for old, new in (('device = "duck_out"', f'device = "sim"\nbank = "{bank}"'),
                     ('socket = "/tmp/tofd.sock"', f'socket = "{RUN}/tofd.sock"')):
        if text.count(old) != 1:
            sys.exit(f"{ROBOT_CONFIG}: expected one {old!r}")
        text = text.replace(old, new)
    path = os.path.join(STATE, "robotd.toml")
    with open(path, "w") as f:
        f.write(text)
    return path


def fetch(url, dest):
    say(f"downloading {os.path.basename(dest)}")
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    os.replace(tmp, dest)


def hearing_models():
    """voiced's models, in the layout of the brain's ~/models/hearing."""
    moon = os.path.join(MODELS, "moonshine")
    os.makedirs(moon, exist_ok=True)
    if not os.path.exists(os.path.join(moon, f".{MOON}")):
        with tempfile.TemporaryDirectory() as tmp:
            tb = os.path.join(tmp, "m.tar.bz2")
            fetch(f"{REL}/asr-models/{MOON}.tar.bz2", tb)
            with tarfile.open(tb) as t:
                t.extractall(tmp, filter="data")
            for f in ("encoder_model.ort", "decoder_model_merged.ort", "tokens.txt"):
                os.replace(os.path.join(tmp, MOON, f), os.path.join(moon, f))
        open(os.path.join(moon, f".{MOON}"), "w").close()
    for name, url in MODEL_FILES.items():
        if not os.path.exists(os.path.join(MODELS, name)):
            fetch(url, os.path.join(MODELS, name))


def voice_clips():
    """lifed's person's-voice clips, rendered once with edge-tts, as deploy.sh does."""
    prompts = os.path.join(TOOLS, "lifed", "prompts.py")
    done = os.path.join(CLIPS, ".done")
    if os.path.exists(done) and os.path.getmtime(done) >= os.path.getmtime(prompts):
        return
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg is needed to render the voice clips (brew install ffmpeg)")
    say(f"rendering the voice clips ({VOICE})")
    shutil.rmtree(CLIPS, ignore_errors=True)
    os.makedirs(CLIPS)
    subprocess.run(["uv", "run", "--no-project", "--with", "edge-tts>=7.2.8", "--with", "numpy", "--with", "scipy",
                    "--with", "soundfile", "python", os.path.join(TOOLS, "lifed", "render_prompts.py"), CLIPS,
                    "--voice", VOICE], check=True)
    open(done, "w").close()


# ── the services ─────────────────────────────────────────────────────────────────────────────────

class Service:
    def __init__(self, sim, name, cmd, env=None):
        self.sim, self.name, self.cmd, self.env = sim, name, cmd, env or {}
        self.proc: asyncio.subprocess.Process | None = None
        self.lines = collections.deque(maxlen=LOG_LINES)
        self.status, self.started = "stopped", 0.0
        self.log = open(os.path.join(STATE, "logs", f"{name}.log"), "a", buffering=1)

    def info(self):
        return {"name": self.name, "status": self.status, "since": self.started,
                "pid": self.proc.pid if self.proc and self.proc.returncode is None else None}

    async def start(self):
        env = {**os.environ, **self.sim.env, **self.env}
        self.proc = await asyncio.create_subprocess_exec(*self.cmd, env=env, cwd=REPO, stdin=subprocess.DEVNULL,
                                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                         start_new_session=True, limit=1 << 20)
        self.status, self.started = "running", time.time()
        self.log.write(f"--- {time.strftime('%F %T')} started: {' '.join(self.cmd)}\n")
        self.sim.send({"t": "service", **self.info()})
        asyncio.create_task(self.read(self.proc))

    async def read(self, proc):
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError:            # a line longer than the limit: skip it
                continue
            if not raw:
                break
            line = ANSI.sub("", raw.decode(errors="replace")).rstrip()
            self.lines.append(line)
            self.log.write(line + "\n")
            self.sim.send({"t": "log", "name": self.name, "line": line})
        code = await proc.wait()
        if proc is self.proc:
            self.status = "stopped" if self.sim.stopping or code in (-signal.SIGTERM, -signal.SIGKILL) \
                else f"exited ({code})"
            self.lines.append(f"--- {self.status}")
            self.log.write(f"--- {time.strftime('%F %T')} {self.status}\n")
            self.sim.send({"t": "service", **self.info()})
            self.sim.send({"t": "log", "name": self.name, "line": f"--- {self.status}"})

    async def stop(self):
        p = self.proc
        if p is None or p.returncode is not None:
            return
        try:
            os.killpg(p.pid, signal.SIGTERM)
            await asyncio.wait_for(p.wait(), 5)
        except (ProcessLookupError, PermissionError):
            pass
        except asyncio.TimeoutError:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await p.wait()

    async def restart(self):
        await self.stop()
        await self.start()


# ── the simulator ────────────────────────────────────────────────────────────────────────────────

class Sim:
    def __init__(self, a):
        self.a = a
        self.pages: set = set()
        self.recs: list = []                  # (queue, rate, channels) per arecord
        self.last_mic = 0.0
        self.jpeg: bytes | None = None
        self.jpeg_seq = 0
        self.cam_cache: dict = {}
        self.tof_mm: int | None = None
        self.tilt = "upright"
        self.volume: float | None = None
        self.networks = ["SimHome", "DuckTest"]
        self.wifi_active = "SimHome"
        self.plays: dict = {}
        self.ids = itertools.count(1)
        self.life: dict | None = None
        self.robot: dict | None = None
        self.health: dict | None = None
        self.stopping = False
        self.services: dict[str, Service] = {}
        self.env: dict = {}
        self.persona = persona_path()
        self.typed = None

    # page traffic
    def send(self, msg: dict):
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.pages):
            if not ws.closed:
                asyncio.create_task(self._send(ws, data))

    @staticmethod
    async def _send(ws, data):
        try:
            if isinstance(data, bytes):
                await ws.send_bytes(data)
            else:
                await ws.send_str(data)
        except (ConnectionError, RuntimeError):
            pass

    def send_audio(self, sid, rate, ch, pcm: bytes):
        data = struct.pack("<BBHII", 1, ch, 0, sid, rate) + pcm
        for ws in list(self.pages):
            if not ws.closed:
                asyncio.create_task(self._send(ws, data))

    def hello(self):
        bank = os.path.join(STATE, "sounds")
        tags = sorted(d for d in os.listdir(bank) if os.path.isdir(os.path.join(bank, d))) \
            if os.path.isdir(bank) else []
        from persona import load as load_persona
        return {"t": "hello", "persona": load_persona(self.persona).name, "persona_path": self.persona,
                "services": [s.info() for s in self.services.values()],
                "logs": {n: list(s.lines)[-200:] for n, s in self.services.items()},
                "tof_mm": self.tof_mm, "tilt": self.tilt, "tilts": list(TILTS), "volume": self.volume,
                "networks": self.networks, "wifi": self.wifi_active, "tags": tags,
                "duckweb": f"http://127.0.0.1:{PORTS['duckweb']}/", "life": self.life, "robot": self.robot,
                "health": self.health, "jev": self.env.get("DUCKBRAIN_SYSTEMONE_URL", ""),
                "llm": self.env.get("DUCKBRAIN_LLM", "")}

    async def on_page(self, request):
        from aiohttp import WSMsgType, web
        ws = web.WebSocketResponse(max_msg_size=8 << 20, heartbeat=20)
        await ws.prepare(request)
        self.pages.add(ws)
        await ws.send_str(json.dumps(self.hello(), ensure_ascii=False))
        try:
            async for m in ws:
                if m.type == WSMsgType.BINARY:
                    self.from_page_bytes(m.data)
                elif m.type == WSMsgType.TEXT:
                    try:
                        await self.from_page(json.loads(m.data))
                    except Exception as e:  # noqa: BLE001 - one bad message must not drop the page
                        say(f"page message {m.data[:80]!r}: {e!r}")
        finally:
            self.pages.discard(ws)
        return ws

    def from_page_bytes(self, data: bytes):
        kind, body = data[0], data[1:]
        if kind == 1:                                    # mic: int16 mono at 48 kHz
            self.last_mic = time.monotonic()
            self.feed_mic(np.frombuffer(body[: len(body) // 2 * 2], np.int16))
        elif kind == 2:                                  # camera: a JPEG
            self.jpeg, self.jpeg_seq = bytes(body), self.jpeg_seq + 1
            self.cam_cache.clear()

    async def from_page(self, m: dict):
        t = m.get("t")
        if t == "event":
            r = await self.rpc(os.path.join(RUN, "lifed.sock"), "life.event", m["ev"])
            self.send({"t": "note", "text": f"life.event {m['ev'].get('type')}: {r.get('result') or r.get('error')}"})
        elif t == "say":
            text, who = m.get("text", ""), m.get("speaker") or None
            await asyncio.get_running_loop().run_in_executor(None, self.say_typed, text, who)
            self.send({"t": "note", "text": f"typed: {text!r}" + (f" as {who}" if who else "")})
        elif t == "tof":
            self.tof_mm = None if m.get("mm") is None else int(m["mm"])
            self.send({"t": "tof", "mm": self.tof_mm})
        elif t == "tilt" and m.get("name") in TILTS:
            self.set_tilt(m["name"])
        elif t == "sound":
            r = await self.rpc(os.path.join(RUN, "robotd.sock"), "robot.sound", {"tag": m["tag"]})
            self.send({"t": "note", "text": f"robot.sound {m['tag']}: {r.get('result') or r.get('error')}"})
        elif t == "enable":                              # the gamepad's Start
            await self.enable(bool(m.get("on")))
        elif t == "networks":
            self.networks = [n.strip() for n in m.get("networks", []) if n.strip()]
            self.send({"t": "wifi", "networks": self.networks, "active": self.wifi_active})
        elif t == "restart" and m.get("name") in self.services:
            await self.services[m["name"]].restart()

    async def enable(self, on: bool):
        r = await self.rpc(os.path.join(RUN, "robotd.sock"), "robot.enable", {"on": on})
        self.send({"t": "note", "text": f"robot.enable {on}: {r.get('result') or r.get('error')}"})
        return r

    async def start_robot(self):
        """Press Start once robotd answers, as someone does with the gamepad after switching on."""
        for _ in range(60):
            if ((await self.enable(True)).get("result") or {}).get("accepted"):
                return
            await asyncio.sleep(1.0)

    def set_tilt(self, name):
        self.tilt = name
        with open(TILT + ".new", "w") as f:
            f.write(" ".join(str(v) for v in TILTS[name]) + "\n")
        os.replace(TILT + ".new", TILT)
        self.send({"t": "tilt", "name": name})

    def say_typed(self, text, speaker):
        """Typed words, handed to lifed exactly as voiced hands what it hears (hearing.Ears.heard)."""
        import hearing
        if self.typed is None:
            hearing.LIFED = os.path.join(RUN, "lifed.sock")
            self.typed = type("Typed", (), {"addressed_until": 0.0, "heard": hearing.Ears.heard})()
        who = {"speaker": speaker, "score": 1.0} if speaker else None
        self.typed.heard(text, None, who)

    # the hardware stand-ins (shim.py) on sim.sock
    async def on_shim(self, r, w):
        try:
            h = json.loads(await r.readline())
            op = h.get("op")
            if op == "play":
                await self.play(r, w, h)
            elif op == "rec":
                await self.rec(w, h)
            elif op == "cam":
                await self.cam(w, h)
            elif op == "volume":
                self.volume = float(h["pct"])
                self.send({"t": "volume", "pct": self.volume})
                w.write(b"ok\n")
            elif op == "nmcli":
                w.write((json.dumps(self.nmcli(h["args"], h.get("shown") or h["args"])) + "\n").encode())
            await w.drain()
        except (ConnectionError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            w.close()

    async def play(self, r, w, h):
        loop = asyncio.get_running_loop()
        sid, rate, ch = next(self.ids), int(h["rate"]), int(h["channels"])
        frame, bps = 2 * ch, 2 * ch * rate
        self.plays[sid] = h.get("name", "")
        self.send({"t": "play", "id": sid, "name": h.get("name", ""), "rate": rate, "ch": ch})
        t0, sent, carry, normal = loop.time(), 0, b"", False
        try:
            while True:
                n = struct.unpack("<I", await r.readexactly(4))[0]
                if n == 0:
                    normal = True
                    break
                data = carry + await r.readexactly(n)
                cut = len(data) // frame * frame
                data, carry = data[:cut], data[cut:]
                if not data:
                    continue
                now = loop.time()
                if now > t0 + sent / bps + 0.05:          # the writer fell behind: start the clock again
                    t0 = now - sent / bps
                ahead = t0 + sent / bps - now - PLAY_LEAD_S
                if ahead > 0:
                    await asyncio.sleep(ahead)
                self.send_audio(sid, rate, ch, data)
                sent += len(data)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        if normal:
            rest = t0 + sent / bps - loop.time()
            if rest > 0:
                await asyncio.sleep(rest)
            w.write(b"done\n")
        else:
            self.send({"t": "stop", "id": sid})
        self.plays.pop(sid, None)
        self.send({"t": "played", "id": sid, "s": round(sent / bps, 2), "cut": not normal})

    async def rec(self, w, h):
        q: asyncio.Queue = asyncio.Queue(maxsize=400)
        rate, ch = int(h["rate"]), int(h["channels"])
        limit = int(float(h.get("seconds") or 0) * rate * ch * 2) or None
        client = (q, rate, ch)
        self.recs.append(client)
        try:
            n = 0
            while limit is None or n < limit:
                data = await q.get()
                if limit is not None:
                    data = data[: limit - n]
                w.write(data)
                await w.drain()
                n += len(data)
        finally:
            self.recs.remove(client)

    def feed_mic(self, mono: np.ndarray):
        for q, rate, ch in self.recs:
            x = mono
            if rate != MIC_RATE and len(x):
                n = max(1, round(len(x) * rate / MIC_RATE))
                x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x.astype(np.float32)).astype(np.int16)
            if ch > 1:
                x = np.repeat(x[:, None], ch, axis=1).reshape(-1)
            try:
                q.put_nowait(x.astype("<i2").tobytes())
            except asyncio.QueueFull:
                pass

    async def mic_silence(self):
        """Silence while the page sends no mic, so the ears keep running as on the robot."""
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.02)
            now = time.monotonic()
            n, last = int(round((now - last) * MIC_RATE)), now
            if now - self.last_mic > 0.25 and self.recs:
                self.feed_mic(np.zeros(n, np.int16))

    def frame(self, half: bool, nv12: bool) -> bytes:
        key = (self.jpeg_seq, half, nv12)
        if key in self.cam_cache:
            return self.cam_cache[key]
        import cv2
        img = None
        if self.jpeg is not None:
            img = cv2.imdecode(np.frombuffer(self.jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            img = np.full((CAM_H, CAM_W, 3), 40, np.uint8)        # no camera: a dark room
        img = cv2.resize(img, (CAM_W, CAM_H), interpolation=cv2.INTER_LINEAR)
        if nv12:
            i420 = cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420).reshape(-1)
            y, u, v = i420[: CAM_W * CAM_H], i420[CAM_W * CAM_H: CAM_W * CAM_H * 5 // 4], i420[CAM_W * CAM_H * 5 // 4:]
            uv = np.empty(u.size * 2, np.uint8)
            uv[0::2], uv[1::2] = u, v
            out = y.tobytes() + uv.tobytes()
        else:
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if half:
                g = cv2.resize(g, (CAM_W // 2, CAM_H // 2), interpolation=cv2.INTER_AREA)
            out = g.tobytes()
        self.cam_cache[key] = out
        return out

    async def cam(self, w, h):
        loop = asyncio.get_running_loop()
        every, half, nv12 = int(h["every"]), bool(h["half"]) and not h["nv12"], bool(h["nv12"])
        fw, fh = (CAM_W // 2, CAM_H // 2) if half else (CAM_W, CAM_H)
        period, seq, sent, t_next = every / 30.0, 0, 0, loop.time()
        while not h.get("frames") or sent < h["frames"]:
            data = await loop.run_in_executor(None, self.frame, half, nv12)
            hdr = struct.pack("<4sIIIqII", b"DCNV" if nv12 else b"DCAM", fw, fh, seq, time.monotonic_ns(), 10000, 256)
            w.write(hdr + data)
            await w.drain()
            seq, sent = seq + every, sent + 1
            t_next += period
            await asyncio.sleep(max(0.0, t_next - loop.time()))

    def nmcli(self, args, shown):
        """A pretend NetworkManager: the page's list of networks on the air, one of them joined."""
        self.send({"t": "note", "text": "nmcli " + " ".join(shown)})
        esc = lambda s: s.replace("\\", "\\\\").replace(":", "\\:")  # noqa: E731
        bssid = lambda i: esc(f"02:00:00:00:00:{i:02X}")             # noqa: E731
        if args[:3] == ["-t", "-f", "SSID-HEX,BSSID"]:
            return {"out": "".join(f"{n.encode().hex().upper()}:{bssid(i)}\n" for i, n in enumerate(self.networks))}
        if args[:3] == ["-t", "-f", "ACTIVE,SSID"]:
            return {"out": "".join(f"{'yes' if n == self.wifi_active else 'no'}:{esc(n)}\n" for n in self.networks)}
        if args[:3] == ["-t", "-f", "NAME,TYPE"]:
            return {"out": f"{esc(self.wifi_active)}:802-11-wireless\n" if self.wifi_active else ""}
        if args[:3] == ["device", "wifi", "connect"]:
            target = args[3]
            names = {f"02:00:00:00:00:{i:02X}": n for i, n in enumerate(self.networks)}
            ssid = names.get(target, target if target in self.networks else None)
            if ssid is None:
                return {"code": 10, "err": f"Error: No network with SSID '{target}' found.\n"}
            self.wifi_active = ssid
            self.send({"t": "wifi", "networks": self.networks, "active": ssid})
            return {"out": f"Device 'wlan0' successfully activated with '{ssid}'.\n"}
        if args[:2] == ["connection", "up"]:
            self.wifi_active = args[-1].removeprefix("duck-")
            self.send({"t": "wifi", "networks": self.networks, "active": self.wifi_active})
        return {"out": ""}

    # the stand-in tofd
    async def on_tof(self, r, w):
        try:
            while line := await r.readline():
                m = json.loads(line)
                if m.get("method") != "tof.stream":
                    w.write((json.dumps({"jsonrpc": "2.0", "id": m.get("id"),
                                         "error": {"code": -32601, "message": "unknown method"}}) + "\n").encode())
                    continue
                w.write((json.dumps({"jsonrpc": "2.0", "id": m.get("id"), "result": {
                    "accepted": True, "sensor": "sim", "rows": 8, "cols": 8, "hz": TOF_HZ}}) + "\n").encode())
                t0, seq = time.monotonic(), 0
                while True:
                    mm = self.tof_mm
                    frame = {"seq": seq, "at_us": int((time.monotonic() - t0) * 1e6), "rows": 8, "cols": 8,
                             "distance_mm": [mm or 0] * 64, "status": [5 if mm else 255] * 64}
                    w.write((json.dumps({"jsonrpc": "2.0", "method": "tof.frame", "params": frame}) + "\n").encode())
                    await w.drain()
                    seq += 1
                    await asyncio.sleep(1.0 / TOF_HZ)
        except (ConnectionError, ValueError, asyncio.IncompleteReadError):
            pass
        finally:
            w.close()

    # what the page shows of the duck
    @staticmethod
    async def rpc(path, method, params=None, timeout=3.0):
        try:
            r, w = await asyncio.wait_for(asyncio.open_unix_connection(path, limit=1 << 22), timeout)
            req = {"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params is not None else {})}
            w.write((json.dumps(req) + "\n").encode())
            await w.drain()
            line = await asyncio.wait_for(r.readline(), timeout)
            w.close()
            return json.loads(line)
        except (OSError, ValueError, asyncio.TimeoutError) as e:
            return {"error": {"message": str(e) or type(e).__name__}}

    async def watch_life(self):
        while True:
            r = await self.rpc(os.path.join(RUN, "lifed.sock"), "life.state")
            self.life = r.get("result")
            if self.life is not None:
                self.send({"t": "life", "s": self.life})
            await asyncio.sleep(0.5)

    async def watch_robot(self):
        path = os.path.join(RUN, "robotd.sock")
        while True:
            try:
                r, w = await asyncio.open_unix_connection(path, limit=1 << 22)
                w.write(b'{"jsonrpc":"2.0","id":1,"method":"robot.subscribe","params":{"hz":5}}\n')
                await w.drain()
                while line := await r.readline():
                    m = json.loads(line)
                    if m.get("method") == "robot.state":
                        self.robot = m["params"]
                        self.send({"t": "robot", "s": self.robot})
            except (OSError, ValueError):
                pass
            self.robot = None
            await asyncio.sleep(1.0)

    async def watch_health(self):
        while True:
            r = await self.rpc(os.path.join(RUN, "robotd.sock"), "robot.health")
            self.health = r.get("result")
            self.send({"t": "health", "s": self.health})
            await asyncio.sleep(3.0)

    # running it all
    def make_services(self, params: str, ort: str | None):
        py, sock = sys.executable, lambda n: os.path.join(RUN, f"{n}.sock")  # noqa: E731
        brain = f"http://127.0.0.1:{PORTS['duckbrain']}"
        jev = read_env("~/.config/duckbrain/jev.env")
        llm = read_env("~/.config/duckbrain/duckbrain.env")
        self.env = {"PATH": BIN + os.pathsep + os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1",
                    "PHOEBE_SIM_SOCK": SOCK, "DUCK_PERSONA": self.persona,
                    "DUCK_VOICES": os.path.join(STATE, "voices.json"), **jev, **llm}
        specs = [
            ("duckjev", [py, f"{TOOLS}/duckbrain/judge.py", str(PORTS["duckjev"])],
             {**jev, "DUCKBRAIN_JUDGE_LOG": os.path.join(STATE, "logs", "judge-log.jsonl")}),
            ("duckbrain", [py, f"{TOOLS}/duckbrain/server.py"],
             {**llm, "DUCKBRAIN_PORT": str(PORTS["duckbrain"]), "DUCKBRAIN_JEV_URL": f"http://127.0.0.1:{PORTS['duckjev']}"}),
            ("robotd", [os.path.join(REPO, "target", "debug", "robotd"), "--params", params, "--socket", sock("robotd"),
                        "--fake", "--fake-tilt", TILT] + ([] if ort else ["--no-policy"]),
             {"ORT_DYLIB_PATH": ort} if ort else {}),
            ("visiond", [py, f"{TOOLS}/visiond/visiond.py", "--sock", sock("visiond"), "--duckcam",
                         os.path.join(BIN, "duckcam"), "--lifed", sock("lifed"), "--tof", sock("tofd"),
                         "--brain", brain], {}),
            ("duckweb", [py, f"{TOOLS}/duckweb/duckweb.py", "--port", str(PORTS["duckweb"]), "--bind", "127.0.0.1",
                         "--lifed", sock("lifed"), "--vision", sock("visiond")], {}),
            ("lifed", [py, f"{TOOLS}/lifed/lifed.py", "--robotd", sock("robotd"), "--tap", sock("tap"),
                       "--sock", sock("lifed"), "--trace", os.path.join(STATE, "logs", "lifed-trace.jsonl"),
                       "--brain", brain, "--vision", sock("visiond"), "--voice-dir", CLIPS, "--audio-device", "sim",
                       "--state", os.path.join(STATE, "lifed-state.json"), "--tof", sock("tofd"), "--card", "sim",
                       "--jev-timeout", str(self.a.jev_timeout)], {}),
            ("voiced", [py, f"{TOOLS}/voiced/hearing.py", "--mic", "sim", "--keep-alive", "", "--models", MODELS,
                        "--pga", "-1", "--lifed", sock("lifed")], {}),
        ]
        self.services = {n: Service(self, n, c, e) for n, c, e in specs}

    async def run(self, params: str, ort: str | None):
        from aiohttp import web
        self.make_services(params, ort)
        os.makedirs(RUN, exist_ok=True)
        for p in (SOCK, os.path.join(RUN, "tofd.sock")):
            if os.path.exists(p):
                os.unlink(p)
        await asyncio.start_unix_server(self.on_shim, SOCK, limit=1 << 20)
        await asyncio.start_unix_server(self.on_tof, os.path.join(RUN, "tofd.sock"))
        app = web.Application(client_max_size=8 << 20)
        app.router.add_get("/", lambda _: web.FileResponse(os.path.join(HERE, "index.html")))
        app.router.add_get("/ws", self.on_page)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", self.a.port).start()
        for t in (self.mic_silence(), self.watch_life(), self.watch_robot(), self.watch_health()):
            asyncio.create_task(t)
        self.set_tilt("upright")
        for s in self.services.values():
            await s.start()
        if not self.a.no_policy and not self.a.no_start:
            asyncio.create_task(self.start_robot())
        url = f"http://127.0.0.1:{self.a.port}/"
        say(f"up: {url}  (duckweb {self.hello()['duckweb']}; logs {STATE}/logs; Ctrl-C stops it all)")
        if self.a.open:
            webbrowser.open(url)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()
        say("stopping")
        self.stopping = True
        await asyncio.gather(*(s.stop() for s in self.services.values()))
        await runner.cleanup()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8090, help="the simulator's page")
    ap.add_argument("--no-build", action="store_true", help="use target/debug/robotd and sounds as they are")
    ap.add_argument("--open", action="store_true", help="open the page in the browser")
    ap.add_argument("--seed", type=int, default=1, help="the voice seed for robotd's sound bank")
    ap.add_argument("--no-policy", action="store_true", help="robotd holds its pose (lifed then stays OFF)")
    ap.add_argument("--no-start", action="store_true", help="do not press Start (robot.enable) at launch")
    ap.add_argument("--jev-timeout", type=float, default=2.5, help="lifed's wait for Jev (a local Jev needs ~2 s)")
    a = ap.parse_args()
    for d in (STATE, os.path.join(STATE, "logs"), RUN, CACHE):
        os.makedirs(d, exist_ok=True)
    sys.path[:0] = [os.path.join(TOOLS, "persona"), os.path.join(TOOLS, "voiced")]
    os.environ["DUCK_PERSONA"] = persona_path()
    say(f"persona {os.environ['DUCK_PERSONA']}")
    write_shims()
    build(a.no_build)
    bank = sound_bank(a.seed)
    params = robot_config(bank, not a.no_policy)
    ort = None if a.no_policy else onnxruntime()
    hearing_models()
    voice_clips()
    import hearing  # noqa: F401 - typed words use voiced's own code; loaded now, not on the first one
    asyncio.run(Sim(a).run(params, ort))


if __name__ == "__main__":
    main()
