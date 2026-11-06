# -*- coding: utf-8 -*-
"""DuckBuddy build / repair tool: a web page served from the computer for four jobs: servo setup, zero calibration, IMU firmware flashing and the whole-robot test.

    python tools/bringup/app.py --host orangepi@duck-1a2b.local             # open http://localhost:8780 in the browser
    python tools/bringup/app.py --host orangepi@192.168.1.50 --com COM11    # by IP, plus the Feetech USB board
    python tools/bringup/app.py --bench pi@192.168.1.166                    # Raspberry Pi test bench in place of the USB board

Layout: web page ⇄ this program (computer) ⇄ two "agents" (agent.py, one JSON per line):
- Robot agent: on each connection, agent.py is sent over ssh on stdin and runs on the robot (nothing to install there).
  It owns the /dev/ttyS7 servo bus (500k) and runs the mic / speaker / ToF / camera / IMU tests.
- USB agent: agent.py --usb runs on the computer, with the Feetech USB board (CH343). Factory servos run at 1M;
  the OPi's UART7 set to 1M really runs at 750k, so a new servo's ID / baud rate can only be changed here.
  Or a Raspberry Pi test bench (--bench): a Pi with a servo HAT (Robot HAT E1) whose UART does 1M
  exactly. agent.py --usb runs on it over ssh, the same way as on the robot, and takes the USB board's place.
Zero calibration reuses tools/joint_align as is (its Calib / Renderer / page): it starts on port+1 and is embedded in the page.
IMU firmware: cargo build + probe-rs download on the computer (ST-Link on PDB J2); after flashing, ID 200 is read over the robot bus to check it.
"""
import argparse
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
AGENT = os.path.join(HERE, "agent.py")
FIRMWARE = os.path.join(ROOT, "firmware", "imu-feetech")
ELF = os.path.join(FIRMWARE, "target", "thumbv6m-none-eabi", "release", "imu-feetech")
CHIP = "STM32G031F8Px"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Boot code on the robot: the first line is the size of agent.py in bytes, then the source, then stdin is the request stream
BOOT = "import sys;b=sys.stdin.buffer;n=int(b.readline());exec(b.read(n))"


class Agent:
    """One agent.py process: requests go out one at a time (one lock), replies are matched by id. Reconnects on the next call if it dropped."""

    def __init__(self, name, argv, send_source):
        self.name, self.argv, self.send_source = name, argv, send_source
        self.lock = threading.Lock()
        self.p = None
        self.next_id = 0
        self.replies = queue.Queue()
        self.err_tail = []
        self.hello = None

    def _start(self):
        self.err_tail = []
        self.replies = queue.Queue()
        self.p = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        if self.send_source:
            src = open(AGENT, "rb").read()
            try:
                self.p.stdin.write(b"%d\n" % len(src) + src)
                self.p.stdin.flush()
            except OSError:
                pass  # ssh already exited (cannot connect): no hello comes below, so ssh's error output is reported
        threading.Thread(target=self._read_out, args=(self.p, self.replies), daemon=True).start()
        threading.Thread(target=self._read_err, args=(self.p,), daemon=True).start()
        try:
            first = self.replies.get(timeout=25)
        except queue.Empty:
            first = None
        if not first or not first.get("hello"):
            time.sleep(0.2)  # let the stderr reader thread collect ssh's error
            self.close()
            tail = " / ".join(self.err_tail[-3:])
            raise RuntimeError(f"{self.name} agent did not start" + (f": {tail}" if tail else ""))
        self.hello = first

    @staticmethod
    def _read_out(p, q):
        for line in p.stdout:
            try:
                q.put(json.loads(line))
            except ValueError:
                pass
        q.put(None)

    def _read_err(self, p):
        for line in p.stderr:
            self.err_tail = (self.err_tail + [line.decode("utf-8", "replace").strip()])[-20:]

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def call(self, op, args=None, timeout=90):
        with self.lock:
            if not self.alive():
                self._start()
            self.next_id += 1
            rid = self.next_id
            try:
                self.p.stdin.write((json.dumps({"id": rid, "op": op, "args": args or {}}) + "\n").encode())
                self.p.stdin.flush()
            except OSError:
                self.close()
                raise RuntimeError(f"{self.name} agent disconnected; click again to reconnect")
            deadline = time.time() + timeout
            while True:
                try:
                    m = self.replies.get(timeout=max(0.1, deadline - time.time()))
                except queue.Empty:
                    self.close()  # replies no longer match the requests: start over
                    raise RuntimeError(f"{op} timed out ({timeout} s)")
                if m is None:
                    self.close()
                    tail = " / ".join(self.err_tail[-3:])
                    raise RuntimeError(f"{self.name} agent disconnected" + (f": {tail}" if tail else ""))
                if m.get("id") == rid:
                    if not m.get("ok"):
                        raise RuntimeError(m.get("error") or "failed")
                    return m["result"]

    def close(self):
        if self.p is not None:
            try:
                self.p.kill()
            except OSError:
                pass
        self.p = None


class Job:
    """A command run on the computer (cargo / probe-rs). Its output is collected line by line for the page to poll."""
    jobs = {}
    seq = 0

    def __init__(self, title, cmds, cwd):
        Job.seq += 1
        self.id, self.title, self.lines, self.rc, self.done = Job.seq, title, [], None, False
        Job.jobs[self.id] = self
        threading.Thread(target=self._run, args=(cmds, cwd), daemon=True).start()

    def _run(self, cmds, cwd):
        for cmd in cmds:
            exe = shutil.which(cmd[0])
            if not exe:
                self.lines.append(f"cannot find {cmd[0]} (not in PATH)")
                self.rc = -1
                break
            self.lines.append("$ " + " ".join(cmd))
            try:
                p = subprocess.Popen([exe] + cmd[1:], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     creationflags=NO_WINDOW)
                for raw in iter(p.stdout.readline, b""):
                    for part in raw.decode("utf-8", "replace").replace("\r", "\n").split("\n"):
                        if part.strip():
                            self.lines.append(part.rstrip())
                self.rc = p.wait()
            except OSError as e:
                self.lines.append(str(e))
                self.rc = -1
            if self.rc != 0:
                break
        self.lines.append("done" if self.rc == 0 else f"failed (exit code {self.rc})")
        self.done = True

    def snapshot(self, since=0):
        return dict(id=self.id, title=self.title, lines=self.lines[since:], n=len(self.lines), done=self.done,
                    rc=self.rc)


def firmware_info():
    def newest(d):
        t = 0
        for base, _, files in os.walk(d):
            for f in files:
                t = max(t, os.path.getmtime(os.path.join(base, f)))
        return t
    src = max(newest(os.path.join(FIRMWARE, "src")), os.path.getmtime(os.path.join(FIRMWARE, "Cargo.toml")))
    elf = os.path.getmtime(ELF) if os.path.exists(ELF) else None
    git = subprocess.run(["git", "log", "-1", "--format=%h %cs %s", "--", "."], cwd=FIRMWARE, capture_output=True,
                         text=True, encoding="utf-8", creationflags=NO_WINDOW).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=FIRMWARE, capture_output=True, text=True,
                           encoding="utf-8", creationflags=NO_WINDOW).stdout.strip()
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t))  # noqa: E731
    return dict(dir=FIRMWARE, elf=ELF if elf else None, elf_time=fmt(elf) if elf else None, src_time=fmt(src),
                stale=elf is None or elf < src, git=git, dirty=[l for l in dirty.splitlines() if "target/" not in l],
                cargo=shutil.which("cargo"), probe_rs=shutil.which("probe-rs"), chip=CHIP)


class Calibration:
    """Zero calibration: starts the tools/joint_align server on port+1 (same code, same page)."""

    def __init__(self, a):
        self.a = a
        self.url = None  # the port number once started
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.url:
                return self.url
            if not self.a.host:
                raise RuntimeError("zero calibration needs the robot: start app.py with --host")
            spec = importlib.util.spec_from_file_location("joint_align_server",
                                                          os.path.join(ROOT, "tools", "joint_align", "server.py"))
            ja = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ja)
            live = ja.Live()
            # on the first connection joint_align sends robot.relax (the page has already confirmed the robot is lying down / held)
            threading.Thread(target=ja.reader, args=(live, self.a.host, False), daemon=True).start()
            calib = ja.Calib(self.a.host, self.a.config, self.a.restart_cmd, self.a.init_cmd)
            threading.Thread(target=calib.load, daemon=True).start()
            srv = ThreadingHTTPServer((self.a.listen, self.a.port + 1), ja.make_handler(live, ja.Renderer(), False, calib))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.url = self.a.port + 1
            return self.url


def make_handler(a, robot, usb_box, calibration):
    page_path = os.path.join(HERE, "index.html")

    def usb():
        if usb_box["agent"] is None:
            raise RuntimeError("no serial port picked for the USB board yet")
        return usb_box["agent"]

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body, ctype="application/json", code=200):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            if u.path == "/":
                return self._send(open(page_path, "rb").read(), "text/html; charset=utf-8")
            if u.path == "/api/info":
                return self._send(dict(host=a.host, config=a.config, com=usb_box["port"], unit=a.unit,
                                       calib_port=calibration.url, restart_cmd=a.restart_cmd, init_cmd=a.init_cmd))
            if u.path == "/api/usb/ports":
                try:
                    from serial.tools import list_ports
                    ports = [dict(device=p.device, desc=p.description, vid=p.vid, pid=p.pid)
                             for p in list_ports.comports()]
                except ImportError:
                    ports = []
                if a.bench:
                    ports.insert(0, dict(device=bench_device(a), desc="Raspberry Pi test bench", vid=None, pid=None))
                return self._send(dict(ports=ports, current=usb_box["port"]))
            if u.path == "/api/flash/info":
                return self._send(firmware_info())
            if u.path == "/api/job":
                job = Job.jobs.get(int(qs.get("id", ["0"])[0]))
                if not job:
                    return self._send(dict(error="no such job"), code=404)
                return self._send(job.snapshot(int(qs.get("since", ["0"])[0])))
            self._send(b"not found", "text/plain", 404)

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length", "0"))
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                body = {}
            try:
                if u.path == "/api/call":
                    target = robot if body.get("target", "robot") == "robot" else usb()
                    args = dict(body.get("args") or {})
                    if target is robot:
                        args.setdefault("unit", a.unit)
                    return self._send(dict(ok=True, result=target.call(body["op"], args,
                                                                       timeout=float(body.get("timeout", 90)))))
                if u.path == "/api/agent/restart":
                    (robot if body.get("target", "robot") == "robot" else usb()).close()
                    return self._send(dict(ok=True))
                if u.path == "/api/usb/open":
                    port = body.get("port")
                    if usb_box["agent"]:
                        usb_box["agent"].close()
                    usb_box["port"] = port or None
                    usb_box["agent"] = usb_agent(port, a) if port else None
                    return self._send(dict(ok=True, port=usb_box["port"]))
                if u.path == "/api/calib/start":
                    return self._send(dict(ok=True, port=calibration.start()))
                if u.path == "/api/flash/run":
                    what = body.get("what")
                    probe = ["--chip", CHIP, "--non-interactive"]
                    if what == "build":
                        job = Job("Build firmware", [["cargo", "build", "--release"]], FIRMWARE)
                    elif what == "probe":
                        job = Job("Find ST-Link", [["probe-rs", "list"]], FIRMWARE)
                    elif what == "flash":
                        if not os.path.exists(ELF):
                            raise RuntimeError("not built yet (target/…/release/imu-feetech does not exist)")
                        job = Job("Flash", [["probe-rs", "download", *probe, "--disable-progressbars", "--verify", ELF],
                                         ["probe-rs", "reset", *probe]], FIRMWARE)
                    else:
                        raise RuntimeError(f"unknown action {what}")
                    return self._send(dict(ok=True, job=job.id))
            except Exception as e:  # noqa: BLE001
                return self._send(dict(ok=False, error=str(e)))
            self._send(dict(ok=False, error="not found"), code=404)

    return H


def bench_device(a):
    """The bench's entry in the port list: picking it uses the Pi's UART instead of a local port."""
    return f"ssh:{a.bench}:{a.bench_port}"


def usb_agent(port, a):
    if a.bench and port == bench_device(a):
        return Agent("Test bench", ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
                                    a.bench, f"python3 -u -c '{BOOT}' --usb --port {a.bench_port} --baud 1000000"],
                     send_source=True)
    return Agent("USB board", [sys.executable, "-u", AGENT, "--usb", "--port", port, "--baud", "1000000"],
                 send_source=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=None,
                    help="ssh address of the robot (no password), e.g. orangepi@duck-1a2b.local. Can be left out with --bench")
    ap.add_argument("--port", type=int, default=8780, help="web page port; zero calibration uses port+1")
    ap.add_argument("--listen", default="127.0.0.1", help="0.0.0.0 = other devices on the LAN can open it too")
    ap.add_argument("--com", default=None, help="serial port of the Feetech USB board (e.g. COM11); can also be picked in the page")
    ap.add_argument("--bench", default=None,
                    help="ssh address (no password) of a Raspberry Pi test bench with a servo HAT, e.g. pi@192.168.1.166; "
                         "used in place of the USB board")
    ap.add_argument("--bench-port", default="/dev/serial0", help="the bench's servo UART (default /dev/serial0)")
    ap.add_argument("--config", default="~/robot/active.toml", help="robotd's config file on the robot")
    ap.add_argument("--unit", default="robotd-dev", help="robotd's systemd --user unit")
    ap.add_argument("--restart-cmd", default="systemctl --user restart robotd-dev",
                    help="run on the robot after the zero offsets are written, so robotd reloads its config")
    ap.add_argument("--init-cmd", default="cd ~/robot && ./robotctl robot init --robot-socket /tmp/robotd.sock",
                    help="run by \"Write and go home\" after the restart")
    a = ap.parse_args()
    if not a.host and not a.bench:
        ap.error("give --host (the robot), --bench (a test bench), or both")

    if a.host:
        robot = Agent("Robot", ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
                              a.host, f"python3 -u -c '{BOOT}' --config {a.config}"], send_source=True)
    else:
        robot = Agent("Robot", [sys.executable, "-c", "import sys; sys.exit('no --host given: the robot is not connected')"],
                      send_source=False)
    usb_box = {"port": a.com, "agent": None}
    handler = make_handler(a, robot, usb_box, Calibration(a))
    if a.bench and not a.com:
        usb_box["port"] = bench_device(a)
    if usb_box["port"]:
        usb_box["agent"] = usb_agent(usb_box["port"], a)
    srv = ThreadingHTTPServer((a.listen, a.port), handler)
    print(f"http://localhost:{a.port}  (robot {a.host or '-'}" + (f", test bench {a.bench}" if a.bench else "") + ")",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        robot.close()
        if usb_box["agent"]:
            usb_box["agent"].close()


if __name__ == "__main__":
    main()
