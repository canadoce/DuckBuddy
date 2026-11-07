# -*- coding: utf-8 -*-
"""Robot-side agent for bringup: one JSON request per line in, one JSON reply per line out (stdin/stdout).

On each connection app.py sends this file over ssh on stdin and runs it (nothing to install on the robot),
or it runs directly on the computer with the Feetech USB board (new servos at the factory 1M can only get a new ID/baud rate this way:
the OPi's UART set to 1M really runs at 750k).

    {"id": 1, "op": "scan", "args": {"lo": 0, "hi": 30}}
    -> {"id": 1, "ok": true, "result": {...}}

Needs only the standard library + pyserial. Bus operations check for robotd first and refuse while it runs (it holds the servo bus, /dev/ttyS0).
Each bus operation opens and closes the serial port itself and does not keep it open. Operations that move a servo (center / wiggle / torque)
are sent by the page only after the user confirms "held"; this side only does the hard safety limits (current limit, torque off on deviation/overcurrent, refuse multi-turn readings).

Manual debugging:  python3 agent.py --config ~/robot/active.toml   then type requests on stdin.
"""
import argparse
import array
import base64
import io
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import wave

# ---- Feetech HLS memory table (same on HD-1910), see tools/servo/fts_bus.py / probe_regs.py ------
LOCK, ID_ADDR, BAUD_ADDR, MODE, TORQUE, GOAL_POS, PRES_POS = 55, 5, 6, 33, 40, 42, 56
BAUDS = [1000000, 500000, 250000, 128000, 115200, 76800, 57600, 38400]  # register 6 values 0..7
BROADCAST = 0xFE
IMU_ID = 200
IMU_MODEL = 0x16D6
DEG_PER_COUNT = 360.0 / 4096

# (address, bytes, name, kind, signed) kind: ro read-only / ee EEPROM (unlocked and locked again on write) / ram
REGS = [
    (0, 1, "Firmware major version", "ro", False), (1, 1, "Firmware minor version", "ro", False), (3, 2, "Model", "ro", False),
    (5, 1, "ID", "ee", False), (6, 1, "Baud rate index 0=1M 1=500k 2=250k", "ee", False),
    (7, 1, "Return delay", "ee", False), (8, 1, "Reply level", "ee", False),
    (9, 2, "Min angle limit", "ee", False), (11, 2, "Max angle limit", "ee", False),
    (13, 1, "Max temperature °C", "ee", False), (14, 1, "Max voltage ×0.1V", "ee", False),
    (15, 1, "Min voltage ×0.1V", "ee", False), (16, 2, "Max torque ×0.1%", "ee", False),
    (18, 1, "Phase", "ee", False), (19, 1, "Unload conditions b0 voltage b2 temperature b3 current", "ee", False),
    (20, 1, "LED alarm conditions", "ee", False),
    (21, 1, "P gain", "ee", False), (22, 1, "D gain", "ee", False), (23, 1, "I gain", "ee", False),
    (28, 2, "Protection current (9 bits, same unit as current)", "ee", False),
    (31, 2, "Position correction (reading = raw − this, BIT15 sign bit)", "ee", True),
    (33, 1, "Mode 0 position 1 constant speed 2 constant current 3 PWM 4 PD", "ee", False),
    (38, 1, "Overcurrent protection time ×10ms", "ee", False),
    (40, 1, "Torque switch 0 off 1 on 2 damping", "ram", False), (41, 1, "Acceleration", "ram", False),
    (42, 2, "Goal position", "ram", True), (44, 2, "Goal current (=0 no force)", "ram", True),
    (46, 2, "Running speed ×0.732RPM (=0 stop)", "ram", True), (48, 2, "Torque limit", "ram", False),
    (55, 1, "Lock flag 0 unlocked 1 locked", "ram", False),
    (56, 2, "Present position", "ro", True), (58, 2, "Present speed", "ro", True), (60, 2, "Present load", "ro", False),
    (62, 1, "Present voltage ×0.1V", "ro", False), (63, 1, "Present temperature °C", "ro", False),
    (65, 1, "Status bits", "ro", False), (66, 1, "Moving flag", "ro", False), (69, 2, "Present current", "ro", True),
]
REG_BY_ADDR = {r[0]: r for r in REGS}


def smag(v):
    """Sign bit + magnitude -> signed. Feetech uses BIT15 as the direction bit, not two's complement."""
    return -(v & 0x7FFF) if v & 0x8000 else v


def enc(v):
    v = int(v)
    return (0x8000 | -v) if v < 0 else v


class BusError(Exception):
    pass


class Bus:
    """Minimal host side of the Feetech protocol 1.0. Does not handle echo (neither the OPi's HAT nor the CH343 board echoes)."""

    def __init__(self, port, baud, timeout=0.012):
        import serial  # only needed when a bus is really opened
        self.port, self.baud = port, baud
        self.s = serial.Serial(port, baud, timeout=timeout, write_timeout=0.5)

    def close(self):
        self.s.close()

    def _send(self, sid, inst, params=()):
        body = [sid, len(params) + 2, inst] + list(params)
        self.s.reset_input_buffer()
        self.s.write(bytes([0xFF, 0xFF] + body + [(~sum(body)) & 0xFF]))
        self.s.flush()

    def _status(self, sid):
        hdr = self.s.read(4)
        if len(hdr) < 4 or hdr[0] != 0xFF or hdr[1] != 0xFF or hdr[2] != sid or hdr[3] < 2:
            return None
        n = hdr[3]
        rest = self.s.read(n)
        if len(rest) < n or (~(sid + n + sum(rest[:-1]))) & 0xFF != rest[-1]:
            return None
        return rest[0], bytes(rest[1:-1])

    def ping(self, sid):
        self._send(sid, 0x01)
        r = self._status(sid)
        return None if r is None else r[0]

    def read(self, sid, addr, n, tries=2):
        for _ in range(tries):
            self._send(sid, 0x02, (addr, n))
            r = self._status(sid)
            if r is not None and len(r[1]) == n:
                return r[1]
        return None

    def write(self, sid, addr, data, tries=2):
        """Write and wait for the reply; a broadcast does not wait. Returns the error byte (0 = OK) or None (no reply)."""
        for _ in range(tries):
            self._send(sid, 0x03, [addr] + list(data))
            if sid == BROADCAST:
                time.sleep(0.005)
                return 0
            r = self._status(sid)
            if r is not None:
                return r[0]
        return None

    def r8(self, sid, addr):
        d = self.read(sid, addr, 1)
        return None if d is None else d[0]

    def r16(self, sid, addr):
        d = self.read(sid, addr, 2)
        return None if d is None else d[0] | (d[1] << 8)

    def w8(self, sid, addr, v):
        return self.write(sid, addr, [int(v) & 0xFF])

    def w16(self, sid, addr, v):
        v = int(v) & 0xFFFF
        return self.write(sid, addr, [v & 0xFF, v >> 8])

    def must(self, err, what):
        if err is None:
            raise BusError(f"{what}: no reply")

    def pos(self, sid):
        v = self.r16(sid, PRES_POS)
        return None if v is None else smag(v)

    def sync_read(self, ids, addr, n):
        """SYNC_READ: one status packet back per ID, in ids order. Returns {id: bytes}; missing or bad ones are left out."""
        self._send(BROADCAST, 0x82, [addr, n] + list(ids))
        want = len(ids) * (6 + n)
        buf = self.s.read(want)
        out, i = {}, 0
        while i + 6 <= len(buf):
            if buf[i] != 0xFF or buf[i + 1] != 0xFF:
                i += 1
                continue
            sid, ln = buf[i + 2], buf[i + 3]
            end = i + 4 + ln
            if ln < 2 or end > len(buf):
                i += 1
                continue
            body = buf[i + 2:end - 1]
            if (~sum(body)) & 0xFF == buf[end - 1] and ln == n + 2 and sid in ids:
                out[sid] = bytes(buf[i + 5:end - 1])
                i = end
            else:
                i += 1
        return out


# ---- Runtime context -----------------------------------------------------------------------------

class Ctx:
    port = "/dev/ttyS0"
    baud = 500000
    usb = False
    config = None
    cfg_path = None


def procs():
    """[(pid, comm, cmdline)]. Reads /proc only, no fork, so it never matches its own command line."""
    out = []
    if not os.path.isdir("/proc"):
        return out
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            comm = open(f"/proc/{d}/comm").read().strip()
            cmd = open(f"/proc/{d}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        out.append((int(d), comm, cmd))
    return out


def robotd_pids():
    return [p for p, c, _ in procs() if c == "robotd"]


def user_unit(unit, action):
    return subprocess.run(["systemctl", "--user", action, unit], capture_output=True, text=True, timeout=20)


def load_config(path):
    path = os.path.realpath(os.path.expanduser(path))
    if not os.path.exists(path):
        return None, path
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        return None, path
    with open(path, "rb") as f:
        return tomllib.load(f), path


def bus_cfg():
    return (Ctx.config or {}).get("bus", {})


def ma_per_count(args):
    v = args.get("ma_per_count")
    return float(v) if v else float(bus_cfg().get("current_ma_per_count", 6.5))


def open_bus(baud=None):
    if not Ctx.usb:
        pids = robotd_pids()
        if pids:
            raise BusError(f"robotd is running (PID {pids}) and holds the servo bus; stop it on the overview page first")
    try:
        return Bus(Ctx.port, int(baud or Ctx.baud))
    except Exception as e:  # noqa: BLE001
        raise BusError(f"cannot open {Ctx.port}: {e}")


class bus_session:
    """One bus operation, closed right after: on the robot robotd may want this port at any time, and on the computer the FD software may want it."""

    def __init__(self, baud=None):
        self.baud = baud

    def __enter__(self):
        self.bus = open_bus(self.baud)
        return self.bus

    def __exit__(self, *exc):
        self.bus.close()


# ---- Overview ------------------------------------------------------------------------------------

def op_hello(args):
    bus = bus_cfg()
    unit = args.get("unit", "robotd-dev")
    info = dict(hostname=socket.gethostname(), python=sys.version.split()[0], usb=Ctx.usb,
                port=Ctx.port, baud=Ctx.baud, port_exists=os.path.exists(Ctx.port) or Ctx.usb,
                config_path=Ctx.cfg_path, config_found=Ctx.config is not None)
    if Ctx.config is not None:
        info["bus"] = {k: bus.get(k) for k in ("servo", "joint_ids", "joint_signs", "joint_offsets", "imu",
                                                "imu_axes", "current_ma_per_count", "port")}
        info["battery"] = Ctx.config.get("battery")
    if not Ctx.usb:
        info["robotd_pids"] = robotd_pids()
        info["robotd_unit"] = unit
        r = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True, text=True)
        info["robotd_unit_state"] = r.stdout.strip()
        info["robotd_socket"] = os.path.exists("/tmp/robotd.sock")
        busy = {"visiond": "visiond", "tofd": "tofd", "voiced": "voiced", "lifed": "lifed", "duckcam": "duckcam",
                "padd": "padd"}
        info["services"] = sorted({name for p, c, cmd in procs() for key, name in busy.items()
                                   if c == key or (key + ".py") in cmd})
    return info


def op_robotd_stop(args):
    unit = args.get("unit", "robotd-dev")
    if user_unit(unit, "is-active").stdout.strip() == "active":
        r = user_unit(unit, "stop")
        if r.returncode != 0:
            raise RuntimeError(f"systemctl --user stop {unit} failed: {r.stderr.strip()}")
        how = f"ran systemctl --user stop {unit}"
    else:
        pid = int(args.get("pid") or 0)
        if not pid or pid not in robotd_pids():
            raise RuntimeError(f"robotd was not started by {unit}; it can only be stopped by the PID shown on the page, now {robotd_pids()}")
        os.kill(pid, 15)
        how = f"sent SIGTERM to PID {pid}"
    for _ in range(30):
        if not robotd_pids():
            break
        time.sleep(0.2)
    left = robotd_pids()
    return dict(msg=how + ("; robotd has exited" if not left else f"; still running: {left}") + ". Note: stopping robotd does not relax the servos, torque is still on.",
                robotd_pids=left)


def op_robotd_start(args):
    unit = args.get("unit", "robotd-dev")
    if robotd_pids():
        return dict(msg="robotd is already running", robotd_pids=robotd_pids())
    r = user_unit(unit, "start")
    if r.returncode != 0:
        raise RuntimeError(f"systemctl --user start {unit} failed: {r.stderr.strip()}")
    for _ in range(25):
        if os.path.exists("/tmp/robotd.sock") and robotd_pids():
            break
        time.sleep(0.2)
    return dict(msg=f"started {unit}", robotd_pids=robotd_pids())


def robotd_rpc(method, params=None, timeout=3.0):
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    s.connect("/tmp/robotd.sock")
    req = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        req["params"] = params
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    return json.loads(buf.split(b"\n")[0] or b"{}")


def op_relax_all(args):
    """Emergency relax: if robotd is running, ask it to relax; otherwise broadcast torque 0."""
    if not Ctx.usb and robotd_pids():
        r = robotd_rpc("robot.relax")
        return dict(msg="sent robot.relax to robotd", reply=r)
    with bus_session(args.get("baud")) as bus:
        bus.w8(BROADCAST, TORQUE, 0)
        bus.w8(BROADCAST, TORQUE, 0)
    return dict(msg="broadcast torque switch=0 (all servos relaxed)")


# ---- Servos --------------------------------------------------------------------------------------

def read_all(bus, sid):
    """Read 0..70 and decode it by REGS. Two blocks; a failed block is read again in 10-byte pieces."""
    raw = {}
    for start, n in ((0, 40), (40, 31)):
        d = bus.read(sid, start, n)
        if d is None:
            for s in range(start, start + n, 10):
                k = min(10, start + n - s)
                d2 = bus.read(sid, s, k)
                if d2 is not None:
                    raw.update({s + i: b for i, b in enumerate(d2)})
        else:
            raw.update({start + i: b for i, b in enumerate(d)})
    regs = {}
    for addr, n, _name, _kind, signed in REGS:
        if any(a not in raw for a in range(addr, addr + n)):
            continue
        v = raw[addr] if n == 1 else raw[addr] | (raw[addr + 1] << 8)
        regs[addr] = smag(v) if signed else v
    return regs


def summary(regs, mpc):
    g = regs.get
    pos = g(56)
    return dict(fw=f"{g(0)}.{g(1)}" if g(0) is not None else None, model=g(3), baud_idx=g(6),
                mode=g(33), unload=g(19), limits=[g(9), g(11)], p=g(21), d=g(22), lock=g(55),
                torque=g(40), pos=pos, multi_turn=pos is not None and not 0 <= pos <= 4095,
                volt=None if g(62) is None else g(62) / 10, temp=g(63), status=g(65),
                goal_curr_ma=None if g(44) is None else round(g(44) * mpc), speed=g(46),
                curr_ma=None if g(69) is None else round(g(69) * mpc))


def op_scan(args):
    lo, hi = int(args.get("lo", 0)), int(args.get("hi", 253))
    bauds = args.get("bauds") or [args.get("baud") or Ctx.baud]
    mpc = ma_per_count(args)
    found = []
    for b in bauds:
        with bus_session(b) as bus:
            bus.s.timeout = 0.006
            ids = [sid for sid in range(lo, hi + 1) if sid != BROADCAST and
                   (bus.ping(sid) is not None or bus.ping(sid) is not None)]
            bus.s.timeout = 0.02
            for sid in ids:
                if sid == IMU_ID:
                    d = bus.read(sid, 0, 8)
                    found.append(dict(id=sid, baud=int(b), imu=True,
                                      model=None if d is None else d[3] | (d[4] << 8),
                                      fw=None if d is None else f"{d[0]}.{d[1]}"))
                    continue
                found.append(dict(id=sid, baud=int(b), **summary(read_all(bus, sid), mpc)))
    return dict(found=found, bauds=[int(b) for b in bauds], range=[lo, hi])


def op_read_regs(args):
    sid = int(args["id"])
    with bus_session(args.get("baud")) as bus:
        regs = read_all(bus, sid)
    if not regs:
        raise BusError(f"ID {sid} does not answer")
    return dict(id=sid, regs=[dict(addr=a, size=n, name=name, kind=k, signed=s, value=regs.get(a))
                              for a, n, name, k, s in REGS], summary=summary(regs, ma_per_count(args)))


def op_read_raw(args):
    """Raw bytes (not decoded by the table), for checking a register's format."""
    sid, addr, n = int(args["id"]), int(args["addr"]), int(args.get("n", 2))
    with bus_session(args.get("baud")) as bus:
        d = bus.read(sid, addr, n)
    if d is None:
        raise BusError(f"ID {sid} does not answer")
    return dict(id=sid, addr=addr, bytes=list(d), hex=d.hex(" "))


def write_reg(bus, sid, addr, value):
    if addr not in REG_BY_ADDR:
        raise BusError(f"address {addr} is not in the register table")
    _, n, name, kind, signed = REG_BY_ADDR[addr]
    if kind == "ro":
        raise BusError(f"{addr} {name} is read-only")
    v = enc(value) if signed else int(value)
    if kind == "ee":
        bus.must(bus.w8(sid, LOCK, 0), "unlock EEPROM")
        time.sleep(0.02)
    err = bus.w8(sid, addr, v) if n == 1 else bus.w16(sid, addr, v)
    bus.must(err, f"write {addr}")
    if kind == "ee":
        time.sleep(0.03)
        target = int(value) if addr == ID_ADDR else sid
        if addr != BAUD_ADDR:
            bus.w8(target, LOCK, 1)
    return err


def write_id(bus, old, new):
    """Change the ID. The reply comes from the new ID (or not at all), so it is not awaited: PING the new ID after the write to check, then lock on the new ID."""
    bus.must(bus.w8(old, LOCK, 0), "unlock EEPROM")
    time.sleep(0.03)
    bus.write(old, ID_ADDR, [new], tries=1)
    time.sleep(0.08)
    if bus.ping(new) is None and bus.ping(new) is None:
        return False
    bus.w8(new, LOCK, 1)
    return True


def op_write_reg(args):
    sid, addr, value = int(args["id"]), int(args["addr"]), int(args["value"])
    if addr in (ID_ADDR, BAUD_ADDR):
        raise BusError("use the matching buttons to change the ID / baud rate (they check for conflicts and reconnect at the new baud rate)")
    with bus_session(args.get("baud")) as bus:
        write_reg(bus, sid, addr, value)
        time.sleep(0.02)
        regs = read_all(bus, sid)
    return dict(id=sid, addr=addr, readback=regs.get(addr))


def op_set_id(args):
    old, new = int(args["id"]), int(args["new_id"])
    if not 0 <= new <= 252 or new == IMU_ID:
        raise BusError("the new ID must be in 0..252 and cannot be the IMU's 200")
    with bus_session(args.get("baud")) as bus:
        if bus.ping(old) is None:
            raise BusError(f"ID {old} does not answer")
        if bus.ping(new) is not None or bus.ping(new) is not None:
            raise BusError(f"ID {new} is already used by a device")
        ok = write_id(bus, old, new)
        lock = bus.r8(new, LOCK) if ok else None
    if not ok:
        raise BusError(f"ID {new} does not answer after the write: power the servo off and on, then scan again")
    return dict(msg=f"ID {old} → {new}, lock={lock}", id=new)


def op_set_baud(args):
    sid, to = int(args["id"]), int(args["to"])
    if to not in BAUDS:
        raise BusError(f"unsupported baud rate {to}")
    with bus_session(args.get("baud")) as bus:
        if bus.ping(sid) is None:
            raise BusError(f"ID {sid} does not answer at {bus.baud}")
        if bus.baud == to:
            return dict(msg="already at this baud rate")
        write_reg(bus, sid, BAUD_ADDR, BAUDS.index(to))
        time.sleep(0.1)
    note = ""
    if not Ctx.usb and to == 1000000:
        note = " (the OPi's UART set to 1M really runs at 750k, so the robot bus will not find it)"
    with bus_session(to) as bus:
        ok = bus.ping(sid) is not None
        if ok:
            bus.w8(sid, LOCK, 1)
            reg = bus.r8(sid, BAUD_ADDR)
    if not ok:
        return dict(msg=f"written; no reply at {to}{note}. Power the servo off and on, then scan at {to} (the lock is set the next time something else is changed)",
                    ok=False)
    return dict(msg=f"ID {sid} set to {to} bps, register 6={reg}, locked", ok=True)


def prepare_motion(bus, sid, mpc, current_ma, speed):
    """Checks and setup before torque on: returns the present position. Refuses an out-of-range (multi-turn) reading; sets the goal to the present position first."""
    mode = bus.r8(sid, MODE)
    if mode not in (0, 4):
        raise BusError(f"ID {sid} is in mode {mode}; it is only moved in position mode 0 / 4")
    p = bus.pos(sid)
    if p is None:
        raise BusError(f"cannot read the position of ID {sid}")
    goal_curr = max(1, min(2047, round(current_ma / mpc)))
    # write the goal + 44 + 46 together (42..47): the HD-1910 sticks at zero current if 46 is not rewritten; writing 42 turns torque on
    blk = b"".join(struct.pack("<H", enc(v)) for v in (p, goal_curr, speed))
    bus.must(bus.write(sid, GOAL_POS, list(blk)), "write goal")
    return p, goal_curr


def goal(bus, sid, target, goal_curr, speed):
    blk = b"".join(struct.pack("<H", enc(v)) for v in (target, goal_curr, speed))
    return bus.write(sid, GOAL_POS, list(blk))


def watch_move(bus, sid, start, target, mpc, seconds, max_ma, max_dev, trace, t_ref, done_tol=None):
    """Watch the move to target: returns the reason on overcurrent (3 times in a row) or on leaving [start, target] ± max_dev counts, else None.
    Appends [seconds (since t_ref), position, current mA] to trace."""
    lo, hi = min(start, target) - max_dev, max(start, target) + max_dev
    over = 0
    t0 = time.time()
    p = start
    while time.time() - t0 < seconds:
        time.sleep(0.04)
        d = bus.read(sid, 56, 15)
        if d is None:
            continue
        p = smag(d[0] | d[1] << 8)
        ma = abs(smag(d[13] | d[14] << 8)) * mpc
        trace.append([round(time.time() - t_ref, 2), p, round(ma)])
        if not lo <= p <= hi:
            return f"position {p} left the range [{lo}, {hi}]"
        over = over + 1 if ma > max_ma else 0
        if over >= 3:
            return f"current {ma:.0f} mA stayed above {max_ma} mA"
        if done_tol is not None and abs(p - target) <= done_tol:
            return None
    return None


def op_wiggle(args):
    """Swing ±amp° around the present position and come back, then release torque. A side that crosses 0/4095 is skipped."""
    sid = int(args["id"])
    amp = float(args.get("amp_deg", 6))
    mpc = ma_per_count(args)
    current_ma = float(args.get("current_ma", 400))
    max_ma = float(args.get("max_ma", 1500))
    speed = int(args.get("speed", 100))
    max_dev = round(float(args.get("max_dev_deg", 15)) / DEG_PER_COUNT)
    a = round(amp / DEG_PER_COUNT)
    with bus_session(args.get("baud")) as bus:
        p0 = bus.pos(sid)
        if p0 is None:
            raise BusError(f"cannot read the position of ID {sid}")
        if not 0 <= p0 <= 4095:
            raise BusError(f"ID {sid} reads {p0}, outside 0..4095 (multi-turn count): power the servo off and on, then try again")
        targets = [t for t in (p0 + a, p0 - a) if 0 <= t <= 4095] + [p0]
        skipped = 2 - (len(targets) - 1)
        p0, gc = prepare_motion(bus, sid, mpc, current_ma, speed)
        t_ref, trace = time.time(), []
        result, reached = None, []
        try:
            bus.must(bus.w8(sid, TORQUE, 1), "torque on")
            start = p0
            for t in targets:
                goal(bus, sid, t, gc, speed)
                result = watch_move(bus, sid, start, t, mpc, 0.9, max_ma, max_dev, trace, t_ref)
                p = bus.pos(sid)
                reached.append(dict(target=t, pos=p, err_deg=None if p is None else round((p - t) * DEG_PER_COUNT, 2)))
                if result:
                    break
                start = p if p is not None else t
        finally:
            bus.w8(sid, TORQUE, 0)
            bus.w8(sid, TORQUE, 0)
    ok = result is None and all(r["err_deg"] is not None and abs(r["err_deg"]) <= 2.5 for r in reached)
    return dict(ok=ok, aborted=result, reached=reached, skipped_sides=skipped, trace=trace,
                peak_ma=max([t[2] for t in trace] or [0]),
                msg=("aborted: " + result if result else ("reached" if ok else "one step did not reach its target (error > 2.5°)")) + "; torque released")


def op_center(args):
    """Move to the nearest center 2048+4096k in the same turn and hold torque (for fitting the horn). Watched: torque off on overcurrent / moving away."""
    sid = int(args["id"])
    mpc = ma_per_count(args)
    current_ma = float(args.get("current_ma", 400))
    max_ma = float(args.get("max_ma", 1500))
    speed = int(args.get("speed", 80))
    with bus_session(args.get("baud")) as bus:
        p0, gc = prepare_motion(bus, sid, mpc, current_ma, speed)
        target = 2048 + 4096 * round((p0 - 2048) / 4096)
        bus.must(bus.w8(sid, TORQUE, 1), "torque on")
        goal(bus, sid, target, gc, speed)
        why = watch_move(bus, sid, p0, target, mpc, 8.0, max_ma, 300, [], time.time(), done_tol=3)
        p = bus.pos(sid)
        if why or p is None or abs(p - target) > 8:
            bus.w8(sid, TORQUE, 0)
            bus.w8(sid, TORQUE, 0)
            return dict(ok=False, pos=p, target=target,
                        msg=f"did not reach center ({why or f'stopped at {p}'}), torque released")
    return dict(ok=True, pos=p, target=target, msg=f"at center {p} (goal {target}), torque held: fit the horn, then release torque")


def op_set_center_here(args):
    """Make the servo's present position read 2048: changes EEPROM 31 (position correction, BIT15 sign bit).

    Bench test on 2026-10-31, HL-2915 (firmware 3.45): reading = (raw − 31) mod 4096; the 0/4095 wrap point and the goal position
    shift with it, and it is kept over power off. Writing 40=128 (the STS one-step center calibration) does nothing on it. HD-1910 not tested yet."""
    sid = int(args["id"])
    with bus_session(args.get("baud")) as bus:
        bus.must(bus.w8(sid, TORQUE, 0), "torque off")  # changing the offset with torque on makes the servo rush to the old goal in the new coordinates
        v31, p = bus.r16(sid, 31), bus.pos(sid)
        if v31 is None or p is None:
            raise BusError(f"cannot read 31 / the position of ID {sid}")
        if not 0 <= p <= 4095:
            raise BusError(f"reading {p} is outside 0..4095 (multi-turn count): power the servo off and on, then set it again")
        old = smag(v31)
        new = old + (p - 2048)
        new = (new + 2048) % 4096 - 2048  # take the equal offset in −2048..2047
        write_reg(bus, sid, 31, new)
        time.sleep(0.05)
        after = bus.pos(sid)
        back = bus.r16(sid, 31)
    ok = after is not None and abs(after - 2048) <= 3 and back is not None and smag(back) == new
    return dict(ok=ok, old_offset=old, new_offset=new, pos_before=p, pos_after=after,
                msg=(f"position correction {old} → {new}, reading now {after}" if ok
                     else f"failed: 31 reads back {None if back is None else smag(back)}, reading {after}") + "; torque released")


def op_torque(args):
    sid, on = int(args["id"]), int(args.get("on", 0))
    with bus_session(args.get("baud")) as bus:
        if on:
            p0, gc = prepare_motion(bus, sid, ma_per_count(args), float(args.get("current_ma", 400)),
                                    int(args.get("speed", 100)))
            if not 0 <= p0 <= 4095:
                bus.w8(sid, TORQUE, 0)
                raise BusError(f"reading {p0} is outside 0..4095 (multi-turn count), torque stays off")
        bus.must(bus.w8(sid, TORQUE, on), "write torque switch")
        return dict(msg=f"ID {sid} torque {'on (holding the present position)' if on else 'off'}", torque=bus.r8(sid, TORQUE))


# ---- Joint mapping (after assembly): wiggle each servo, pick its joint, then renumber or write joint_ids

TEMP_BASE = 160  # temporary ID during a renumber = 160 + final ID; a scan after an interruption that finds 16x / 17x shows where it goes


def op_remap_ids(args):
    """Change IDs by moves=[[old, new], ...] all together. All move to temporary IDs first, then to the final IDs, so swaps and rotations work."""
    moves = [(int(a), int(b)) for a, b in args.get("moves") or [] if int(a) != int(b)]
    if not moves:
        return dict(ok=True, log=[], msg="nothing to change: every servo already has its target ID")
    olds, news = [m[0] for m in moves], [m[1] for m in moves]
    if len(set(olds)) != len(olds) or len(set(news)) != len(news):
        raise BusError("an old ID or a new ID is repeated")
    if any(not 0 <= n <= 39 for n in news):
        raise BusError("new IDs must be in 0..39 (the temporary ID is 160 + new ID)")
    log = []
    with bus_session(args.get("baud")) as bus:
        missing = [o for o in olds if bus.ping(o) is None and bus.ping(o) is None]
        if missing:
            raise BusError(f"these IDs do not answer: {missing}; scan again first")
        for n in news:
            if n not in olds and (bus.ping(n) is not None or bus.ping(n) is not None):
                raise BusError(f"ID {n} is already used by a device that is not in the mapping")
            if bus.ping(TEMP_BASE + n) is not None:
                raise BusError(f"temporary ID {TEMP_BASE + n} is already used (left by an interrupted renumber? change it back to {n} first)")
        for phase, pairs in (("temporary", [(o, TEMP_BASE + n) for o, n in moves]),
                             ("final", [(TEMP_BASE + n, n) for o, n in moves])):
            for a, b in pairs:
                ok = write_id(bus, a, b)
                log.append(f"{phase}: {a} → {b}" + ("" if ok else " (no reply)"))
                if not ok:
                    raise BusError("; ".join(log) + f". ID {b} does not answer after the write, stopping here: power the servos off and on, then scan again"
                                   f" ({TEMP_BASE}+x is a temporary ID, x is the ID it should get)")
        locks = {n: bus.r8(n, LOCK) for n in news}
    return dict(ok=True, log=log, locks=locks, msg=f"changed {len(moves)} servos, all answer and are locked")


def op_write_joint_ids(args):
    """Change the [bus] joint_ids line in the robot config: back it up first, read it back after the write, restore it if wrong."""
    import re
    ids = [int(i) for i in args.get("ids") or []]
    servos = [i for i in ids if i != 0]   # 0: no servo on that joint (a printed dummy), robotd leaves it off the bus
    if len(ids) != 15 or not servos or len(set(servos)) != len(servos):
        raise BusError("joint_ids needs 15 entries, the servos' IDs all different (0 for a joint with no servo)")
    path = Ctx.cfg_path
    if Ctx.usb or not path or not os.path.exists(path):
        raise BusError(f"no config file to write ({path})")
    text = open(path, encoding="utf-8").read()
    line = "joint_ids = [" + ", ".join(str(i) for i in ids) + "]"
    note = time.strftime("# %Y-%m-%d") + " bringup: joint_ids mapped by wiggling each servo\n"
    text = re.sub(r"^# [0-9-]+ bringup: joint_ids mapped by wiggling each servo\n", "", text, flags=re.M)
    new, n = re.subn(r"^joint_ids\s*=\s*\[[^\]]*\]", lambda m: note + line, text, count=1, flags=re.M)
    if not n:
        new, n = re.subn(r"^\[bus\][ \t]*\n", lambda m: m.group(0) + note + line + "\n", text, count=1, flags=re.M)
    if not n:
        raise BusError(f"{path} has no [bus] section")
    backup = path + time.strftime(".bak-%Y%m%d-%H%M%S")
    while os.path.exists(backup):
        backup += "x"
    shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    m = re.search(r"^joint_ids\s*=\s*\[([^\]]*)\]", open(path, encoding="utf-8").read(), flags=re.M)
    cfg, _ = load_config(path)  # Python < 3.11 has no tomllib: then only this line is checked
    if cfg is not None:
        got = [int(i) for i in cfg.get("bus", {}).get("joint_ids") or []]
    else:
        got = [int(x) for x in m.group(1).split(",") if x.strip()] if m else None
    if got != ids:
        shutil.copy2(backup, path)
        raise BusError(f"read-back after the write is wrong, restored from {backup}")
    if cfg is not None:
        Ctx.config = cfg
    return dict(ok=True, path=path, backup=backup, line=line,
                msg=f"wrote {path} (backup {os.path.basename(backup)}); restart robotd for it to take effect")


# ---- New-servo setup wizard (USB board, same chain method as tools/servo/setup_ids.py) -----------
#
# Factory servos are all ID 1 / 1M. Chain mode: at any time only the servo just plugged in has ID 1, so IDs are given in reverse (15→1)
# and the servos already set up stay on the chain. Each one moves to the final baud rate (500k) right away, so it is no longer on 1M.
# The page calls them step by step: wiz_probe (who is online) → wiz_configure (ID + EEPROM + baud rate) → (first servo)
# power off and on, wiz_verify → center / torque to fit the horn.

FRESH_ID = 1
UNLOAD, MIN_ANGLE, MAX_ANGLE = 19, 9, 11


def clean_ping(bus, sid, tries=6):
    """Counts only if tries valid replies come in a row: when servos share an ID, a valid packet can still come out now and then."""
    return all(bus.ping(sid) is not None for _ in range(tries))


def raw_activity(bus, sid):
    """Whether any bytes come back on the line (broken pieces from a collision count too)."""
    for _ in range(3):
        bus._send(sid, 0x01)
        time.sleep(0.01)
        if bus.s.read(32):
            return True
    return False


def op_wiz_probe(args):
    """target already there (set up again in place) / one factory ID 1 (fresh) / collision / none. Also checks that the servos already set up are still there."""
    target = int(args["target"])
    final = int(args.get("final_baud", 500000))
    factory = [int(b) for b in args.get("factory_bauds") or [1000000, final]]
    assigned = [int(i) for i in args.get("assigned") or []]
    with bus_session(final) as bus:
        gone = [i for i in assigned if not clean_ping(bus, i, tries=3)]
    if gone:
        return dict(state="lost", gone=gone, msg=f"IDs {gone} set up before no longer answer: something in the chain is loose, check the cables first")
    for b in dict.fromkeys([final] + factory):
        with bus_session(b) as bus:
            if target != FRESH_ID and clean_ping(bus, target, tries=4):
                return dict(state="target", baud=b, msg=f"ID {target} already has a servo at {b} bps: this is the renumbered one, setting it up again in place")
    collide = None
    for b in factory:
        with bus_session(b) as bus:
            if clean_ping(bus, FRESH_ID):
                model = bus.r16(FRESH_ID, 3)
                mode = bus.r8(FRESH_ID, MODE)
                return dict(state="fresh", baud=b, model=model, mode=mode,
                            msg=f"found a servo with ID {FRESH_ID} ({b} bps, model {model}, mode {mode})")
            if raw_activity(bus, FRESH_ID):
                collide = b
    if collide:
        return dict(state="collision", baud=collide,
                    msg=f"more than one servo answers on ID {FRESH_ID} (the replies at {collide} bps are broken): plug in only one new servo at a time")
    return dict(state="none", msg="no new servo found: check the power, the direction of the 3-wire cable and that it is fully plugged in")


def op_wiz_configure(args):
    """cur_id@baud → new_id: set the ID, single-turn limits 0/4095, mode 0, unload conditions, lock; then set the final baud rate and check."""
    cur, new = int(args["cur_id"]), int(args["new_id"])
    baud, final = int(args["baud"]), int(args.get("final_baud", 500000))
    unload = args.get("unload")
    steps = []
    with bus_session(baud) as bus:
        if not clean_ping(bus, cur, tries=3):
            raise BusError(f"ID {cur} does not answer at {baud} bps")
        if cur != new:
            if clean_ping(bus, new, tries=2):
                raise BusError(f"ID {new} is already in use")
            bus.must(bus.w8(cur, LOCK, 0), "unlock")
            time.sleep(0.05)
            bus.w8(cur, ID_ADDR, new)
            time.sleep(0.08)
            if not clean_ping(bus, new, tries=4):
                raise BusError(f"no ping reply from ID {new} after the change")
            if cur == FRESH_ID and clean_ping(bus, FRESH_ID, tries=4):
                raise BusError(f"a servo still answers on ID {FRESH_ID}: more than one was plugged in, so this change may have gone to another servo")
            steps.append(f"ID {cur} → {new}")
        bus.must(bus.w8(new, LOCK, 0), "unlock")
        time.sleep(0.05)
        bus.w16(new, MIN_ANGLE, 0)
        time.sleep(0.03)
        bus.w16(new, MAX_ANGLE, 4095)
        time.sleep(0.03)
        bus.w8(new, MODE, 0)
        time.sleep(0.03)
        steps.append("limits 0/4095, mode 0")
        if unload is not None and unload != "":
            bus.w8(new, UNLOAD, int(unload))
            time.sleep(0.03)
            steps.append(f"unload conditions {int(unload)} (0x{int(unload):02x})")
        if baud != final:
            bus.w8(new, BAUD_ADDR, BAUDS.index(final))
            time.sleep(0.1)
            steps.append(f"baud rate {baud} → {final}")
        else:
            bus.w8(new, LOCK, 1)
            time.sleep(0.05)
    with bus_session(final) as bus:
        if not clean_ping(bus, new, tries=4):
            raise BusError(f"after the baud rate change ID {new} does not answer at {final} bps: power off and on, then detect again; it will be found as an already renumbered servo")
        bus.w8(new, LOCK, 1)
        time.sleep(0.05)
        regs = read_all(bus, new)
    s = summary(regs, ma_per_count(args))
    bad = []
    if s["mode"] != 0:
        bad.append(f"mode reads back {s['mode']}")
    if s["limits"] != [0, 4095]:
        bad.append(f"limits read back {s['limits']}")
    if unload not in (None, "") and s["unload"] != int(unload):
        bad.append(f"unload conditions read back {s['unload']}")
    if s["lock"] != 1:
        bad.append("not locked")
    if s["status"]:
        bad.append(f"status bits {s['status']}")
    return dict(ok=not bad, problems=bad, id=new, baud=final, steps=steps, summary=s)


def op_wiz_verify(args):
    """After power off and on: ID / baud rate / mode / limits / unload conditions all still there = the EEPROM really saved them."""
    sid, final = int(args["id"]), int(args.get("final_baud", 500000))
    unload = args.get("unload")
    with bus_session(final) as bus:
        if not clean_ping(bus, sid, tries=4):
            raise BusError(f"after power off ID {sid} does not answer at {final} bps: the EEPROM did not save, do not do the rest yet")
        s = summary(read_all(bus, sid), ma_per_count(args))
    bad = []
    if s["mode"] != 0 or s["limits"] != [0, 4095]:
        bad.append(f"mode {s['mode']}, limits {s['limits']}")
    if unload not in (None, "") and s["unload"] != int(unload):
        bad.append(f"unload conditions {s['unload']}")
    return dict(ok=not bad, problems=bad, summary=s,
                msg="all settings survived power off, the EEPROM saves correctly" if not bad else "some settings were lost at power off: " + "; ".join(bad))


# ---- Whole-robot test ----------------------------------------------------------------------------

def imu_on_i2c():
    """[bus] imu_source = "bno055": the IMU is a BNO055 on I2C, not ID 200 on the servo bus."""
    return bus_cfg().get("imu_source", "bus") == "bno055"


def joint_list():
    """The servo IDs in the config's joint_ids (a 0, a joint with a printed dummy, has none), and whether
    the IMU is on the servo bus (it is not with the BNO055)."""
    bus = bus_cfg()
    ids = [int(i) for i in bus.get("joint_ids") or [] if int(i) != 0]
    return ids, bool(bus.get("imu", False)) and not imu_on_i2c()


def op_test_bus(args):
    """Every ID must answer + the error rate of N rounds of robotd-style SYNC_READ (15 bytes from 56, IMU last)."""
    ids = [int(i) for i in args.get("ids") or []]
    imu = bool(args.get("imu", True))
    if not ids:
        ids, imu_cfg = joint_list()
        imu = imu and imu_cfg
    if not ids:
        raise BusError("no joint_ids in the config: scan on the servo page first")
    rounds = int(args.get("rounds", 500))
    mpc = ma_per_count(args)
    order = ids + ([IMU_ID] if imu else [])
    with bus_session(args.get("baud")) as bus:
        bus.s.timeout = 0.02
        missing = [sid for sid in order if all(bus.ping(sid) is None for _ in range(3))]
        servos = []
        for sid in ids:
            d = bus.read(sid, 56, 15)
            if d is None:
                servos.append(dict(id=sid, ok=False))
                continue
            pos = smag(d[0] | d[1] << 8)
            servos.append(dict(id=sid, ok=True, pos=pos, multi_turn=not 0 <= pos <= 4095, volt=d[6] / 10,
                               temp=d[7], status=d[9], curr_ma=round(abs(smag(d[13] | d[14] << 8)) * mpc)))
        bus.s.timeout = 0.03
        fails = {sid: 0 for sid in order}
        bad_rounds = 0
        t0 = time.time()
        for _ in range(rounds):
            got = bus.sync_read(order, 56, 15)
            miss = [sid for sid in order if sid not in got]
            for sid in miss:
                fails[sid] += 1
            bad_rounds += bool(miss)
        dt = time.time() - t0
    total = rounds * len(order)
    err_rate = sum(fails.values()) / total if total else 0
    volts = [s["volt"] for s in servos if s.get("ok")]
    problems = []
    if missing:
        problems.append(f"no reply: {missing}")
    if err_rate > float(args.get("max_err", 0.005)):
        problems.append(f"SYNC_READ error rate {err_rate:.2%}")
    hot = [s["id"] for s in servos if s.get("ok") and s["status"]]
    if hot:
        problems.append(f"status bits not 0: {hot}")
    mt = [s["id"] for s in servos if s.get("multi_turn")]
    if mt:
        problems.append(f"multi-turn readings (power the servos off to clear): {mt}")
    return dict(ok=not problems, problems=problems, order=order, missing=missing, servos=servos,
                rounds=rounds, err_rate=err_rate, bad_rounds=bad_rounds,
                fails={str(k): v for k, v in fails.items() if v}, ms_per_round=round(dt / max(1, rounds) * 1000, 2),
                volt_min=min(volts) if volts else None, volt_max=max(volts) if volts else None)


def half(bits):
    s = -1.0 if bits & 0x8000 else 1.0
    e, f = (bits >> 10) & 0x1F, bits & 0x3FF
    if e == 0:
        return s * f * 2.0 ** -24
    if e == 0x1F:
        return float("nan") if f else s * float("inf")
    return s * (1 + f / 1024) * 2.0 ** (e - 15)


def gravity_sensor(x, y, z):
    """For the SFLP quaternion (x,y,z, w=√(1−…)), the direction of world −z in the sensor frame (same as duck-control imu.rs)."""
    w = math.sqrt(max(0.0, 1 - x * x - y * y - z * z))
    v = (0.0, 0.0, -1.0)
    t = ((y * v[2] - z * v[1]) * 2, (z * v[0] - x * v[2]) * 2, (x * v[1] - y * v[0]) * 2)
    c = (y * t[2] - z * t[1], z * t[0] - x * t[2], x * t[1] - y * t[0])
    return [v[i] - w * t[i] + c[i] for i in range(3)]


def to_trunk(g, axes):
    """[bus] imu_axes (e.g. "y,x,-z": trunk x = sensor y …) maps a sensor-frame vector to the trunk frame."""
    out = []
    for tok in axes.split(","):
        tok = tok.strip()
        sgn = -1.0 if tok.startswith("-") else 1.0
        out.append(sgn * g["xyz".index(tok.lstrip("+-"))])
    return out


def op_test_imu(args):
    seconds = float(args.get("seconds", 2.0))
    axes = args.get("axes") or bus_cfg().get("imu_axes") or "z,y,-x"
    if imu_on_i2c():
        return test_imu_bno055(args, seconds, axes)
    with bus_session(args.get("baud")) as bus:
        bus.s.timeout = 0.02
        head = bus.read(IMU_ID, 0, 8)
        if head is None:
            raise BusError("ID 200 (IMU board) does not answer")
        diag0 = bus.read(IMU_ID, 90, 8)
        samples = []
        t0 = time.time()
        reads = fails = 0
        while time.time() - t0 < seconds:
            reads += 1
            d = bus.read(IMU_ID, 56, 15, tries=1)
            if d is None:
                fails += 1
                continue
            samples.append((time.time() - t0, d))
            time.sleep(0.008)
        diag1 = bus.read(IMU_ID, 90, 8)
    if len(samples) < 5:
        raise BusError(f"too few IMU readings ({len(samples)}/{reads})")
    model = head[3] | head[4] << 8
    # sample counter (byte 12, +1 per fusion output, wraps at 8 bits)
    cnt = 0
    for (_, a), (_, b) in zip(samples, samples[1:]):
        cnt += (b[12] - a[12]) % 256
    rate = cnt / (samples[-1][0] - samples[0][0])
    gyro = [[struct.unpack_from("<h", d, 2 * k)[0] * 0.0175 for k in range(3)] for _, d in samples]
    gmean = [sum(g[k] for g in gyro) / len(gyro) for k in range(3)]
    gstd = [math.sqrt(sum((g[k] - gmean[k]) ** 2 for g in gyro) / len(gyro)) for k in range(3)]
    last = samples[-1][1]
    q = [half(struct.unpack_from("<H", last, 6 + 2 * k)[0]) for k in range(3)]
    qn = math.sqrt(sum(v * v for v in q))
    flags = last[13]
    gs = gravity_sensor(*q) if qn <= 1.02 else [0, 0, 0]
    gt = to_trunk(gs, axes)
    pitch = math.degrees(math.atan2(gt[0], math.hypot(gt[1], gt[2])))
    roll = math.degrees(math.atan2(-gt[1], -gt[2]))
    dg = lambda d, k: None if d is None else d[2 * k] | d[2 * k + 1] << 8  # noqa: E731
    diag = None
    if diag0 and diag1:
        diag = dict(rx_err=(dg(diag1, 0) - dg(diag0, 0)) % 65536, expired=(dg(diag1, 1) - dg(diag0, 1)) % 65536,
                    replies=(dg(diag1, 2) - dg(diag0, 2)) % 65536, rx_err_total=dg(diag1, 0),
                    expired_total=dg(diag1, 1))
    problems = []
    if model != IMU_MODEL:
        problems.append(f"model 0x{model:04X} is not 0x{IMU_MODEL:04X}")
    if flags & 3 != 3:
        problems.append(f"flags {flags:#04x}: sensor not set up or attitude not valid")
    if not 90 <= rate <= 150:
        problems.append(f"fusion output {rate:.0f} Hz (should be about 120)")
    if not 0.98 <= qn <= 1.02 and qn > 0:
        problems.append(f"|q| = {qn:.3f}")
    if qn == 0:
        problems.append("quaternion is all 0 (no SFLP output yet)")
    if max(gstd) > float(args.get("max_gyro_std", 1.0)):
        problems.append(f"gyro noise while still {max(gstd):.2f} dps (set it down steady and test again)")
    if max(abs(v) for v in gmean) > 5:
        problems.append(f"gyro bias {max(abs(v) for v in gmean):.1f} dps")
    if diag and diag["rx_err"]:
        problems.append(f"IMU board serial receive errors: {diag['rx_err']}")
    if fails > reads * 0.01:
        problems.append(f"read failures {fails}/{reads}")
    return dict(ok=not problems, problems=problems, fw=f"{head[0]}.{head[1]}", model=f"0x{model:04X}",
                rate_hz=round(rate, 1), flags=flags, quat=[round(v, 4) for v in q], quat_norm=round(qn, 4),
                gyro_mean_dps=[round(v, 2) for v in gmean], gyro_std_dps=[round(v, 3) for v in gstd],
                gravity_sensor=[round(v, 3) for v in gs], axes=axes, pitch_deg=round(pitch, 1),
                roll_deg=round(roll, 1), reads=reads, read_fails=fails, diag=diag)


# ---- BNO055 on I2C ([bus] imu_source = "bno055", the Robot HAT E1 build) -----------------------

BNO_CHIP_ID, BNO_MODE_IMU = 0xA0, 0x08


class I2cDev:
    """i2c-dev, standard library only: I2C_SLAVE, then write the register and read."""

    def __init__(self, path, addr):
        import fcntl
        self.fd = os.open(path, os.O_RDWR)
        fcntl.ioctl(self.fd, 0x0703, addr)

    def read(self, reg, n):
        os.write(self.fd, bytes([reg]))
        return os.read(self.fd, n)

    def write(self, reg, val):
        os.write(self.fd, bytes([reg, val]))

    def close(self):
        os.close(self.fd)


def test_imu_bno055(args, seconds, axes):
    """Same checks as the bus board where they apply: chip ID, fusion mode, sample rate, |q|,
    gyro noise and bias while still, gyro calibration, and pitch / roll in the trunk frame.
    Sets the chip to IMU fusion mode first if robotd is not running (robotd does it itself)."""
    bus = bus_cfg()
    path = args.get("i2c") or bus.get("imu_i2c") or "/dev/i2c-0"
    addr = int(args.get("address") or bus.get("imu_i2c_address") or 0x28)
    try:
        dev = I2cDev(path, addr)
    except OSError as e:
        raise BusError(f"cannot open {path}: {e}")
    try:
        try:
            chip = dev.read(0x00, 1)[0]
        except OSError as e:
            raise BusError(f"BNO055 at 0x{addr:02x} on {path} does not answer ({e}): check the Qwiic cable (J5)")
        if chip != BNO_CHIP_ID:
            raise BusError(f"0x{addr:02x} on {path} has chip ID 0x{chip:02x}, not a BNO055 (0xA0)")
        sw = dev.read(0x04, 2)
        mode = dev.read(0x3D, 1)[0] & 0x0F
        set_up = False
        if mode != BNO_MODE_IMU and not robotd_pids():
            dev.write(0x3D, 0x00); time.sleep(0.03)
            dev.write(0x07, 0x00); dev.write(0x3E, 0x00); time.sleep(0.01)
            dev.write(0x3B, 0x00); dev.write(0x3D, BNO_MODE_IMU); time.sleep(0.05)
            mode = dev.read(0x3D, 1)[0] & 0x0F
            set_up = True
        samples, reads, fails = [], 0, 0
        t0 = time.time()
        while time.time() - t0 < seconds:
            reads += 1
            try:
                samples.append((time.time() - t0, dev.read(0x14, 20)))
            except OSError:
                fails += 1
            time.sleep(0.005)
        calib = dev.read(0x35, 1)[0]
        sys_status, sys_err = dev.read(0x39, 1)[0], dev.read(0x3A, 1)[0]
    finally:
        dev.close()
    if len(samples) < 5:
        raise BusError(f"too few BNO055 readings ({len(samples)}/{reads})")
    # Changes of the whole sample per second. The quaternion alone does not change while the
    # chip lies perfectly still, but the gyro's last bit does; a frozen chip changes neither.
    changes = sum(1 for (_, a), (_, b) in zip(samples, samples[1:]) if a != b)
    rate = changes / max(1e-6, samples[-1][0] - samples[0][0])
    gyro = [[struct.unpack_from("<h", d, 2 * k)[0] / 16.0 for k in range(3)] for _, d in samples]
    gmean = [sum(g[k] for g in gyro) / len(gyro) for k in range(3)]
    gstd = [math.sqrt(sum((g[k] - gmean[k]) ** 2 for g in gyro) / len(gyro)) for k in range(3)]
    w, x, y, z = [v / 16384.0 for v in struct.unpack_from("<4h", samples[-1][1], 12)]
    qn = math.sqrt(w * w + x * x + y * y + z * z)
    gs = gravity_sensor(x / qn, y / qn, z / qn) if qn > 0.5 else [0, 0, 0]
    gt = to_trunk(gs, axes)
    pitch = math.degrees(math.atan2(gt[0], math.hypot(gt[1], gt[2])))
    roll = math.degrees(math.atan2(-gt[1], -gt[2]))
    gyro_cal = (calib >> 4) & 3
    problems = []
    if mode != BNO_MODE_IMU:
        problems.append(f"mode 0x{mode:x}, not IMU fusion (0x8)" + ("" if set_up else "; robotd should have set it"))
    if rate < 20:
        problems.append(f"samples change only {rate:.0f} times a second: the chip looks frozen")
    if qn == 0:
        problems.append("quaternion is all 0 (no fusion output yet)")
    elif not 0.98 <= qn <= 1.02:
        problems.append(f"|q| = {qn:.3f}")
    if max(gstd) > float(args.get("max_gyro_std", 1.0)):
        problems.append(f"gyro noise while still {max(gstd):.2f} dps (set it down steady and test again)")
    if max(abs(v) for v in gmean) > 5:
        problems.append(f"gyro bias {max(abs(v) for v in gmean):.1f} dps")
    if gyro_cal != 3:
        problems.append(f"gyro calibration {gyro_cal}/3: keep the robot still for a few seconds and test again")
    if fails > reads * 0.01:
        problems.append(f"read failures {fails}/{reads}")
    return dict(ok=not problems, problems=problems, fw=f"BNO055 {sw[1]:x}.{sw[0]:02x}", model="BNO055",
                rate_hz=round(rate, 1), flags=calib, calib=dict(sys=calib >> 6, gyro=gyro_cal, accel=(calib >> 2) & 3),
                sys_status=sys_status, sys_err=sys_err, quat=[round(v, 4) for v in (w, x, y, z)], quat_norm=round(qn, 4),
                gyro_mean_dps=[round(v, 2) for v in gmean], gyro_std_dps=[round(v, 3) for v in gstd],
                gravity_sensor=[round(v, 3) for v in gs], axes=axes, pitch_deg=round(pitch, 1),
                roll_deg=round(roll, 1), reads=reads, read_fails=fails, diag=None, i2c=path, address=addr)


# ---- Audio --------------------------------------------------------------------------------------

RATE = 48000


def alsa_devs():
    txt = ""
    for rc in ("/etc/asound.conf", os.path.expanduser("~/.asoundrc")):
        if os.path.exists(rc):
            txt += open(rc).read()
    if "pcm.duck_out" in txt and "pcm.duck_in" in txt:
        return "duck_out", "duck_in"
    return "plughw:CARD=aic3104,DEV=0", "plughw:CARD=aic3104,DEV=0"


def write_wav(path, segments):
    """segments: [(seconds, frequency Hz or 0, dBFS)], the same on both channels (the amplifier uses only the left channel)."""
    frames = array.array("h")
    for secs, freq, dbfs in segments:
        n = int(secs * RATE)
        amp = 32767 * 10 ** (dbfs / 20) if freq else 0
        fade = int(0.01 * RATE)
        for i in range(n):
            g = min(1.0, i / fade, (n - 1 - i) / fade) if freq else 0
            v = int(amp * g * math.sin(2 * math.pi * freq * i / RATE))
            frames.append(v)
            frames.append(v)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames.tobytes())


def play_and_record(wav_path, record_s):
    """Start playback first (it starts with silence), then recording: if recording starts first, the whole recording sticks at ±32767 (seen on 10-25)."""
    out_dev, in_dev = alsa_devs()
    if "aic3104" not in open("/proc/asound/cards").read():
        raise RuntimeError("sound card aic3104 is not registered (check the brain overlay and brain-audio.service, deploy/brain)")
    player = subprocess.Popen(["aplay", "-q", "-D", out_dev, wav_path], stderr=subprocess.PIPE)
    time.sleep(0.25)
    try:
        r = subprocess.run(["arecord", "-q", "-D", in_dev, "-f", "S16_LE", "-r", str(RATE), "-c", "2",
                            "-t", "raw", "-s", str(int(record_s * RATE))],
                           capture_output=True, timeout=record_s + 10)
    finally:
        try:
            player.wait(timeout=record_s + 5)
        except subprocess.TimeoutExpired:
            player.kill()
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError("arecord failed: " + r.stderr.decode(errors="replace").strip())
    a = array.array("h")
    a.frombytes(r.stdout[: len(r.stdout) // 4 * 4])
    skip = int(0.15 * RATE) * 2  # the power-up transient at the start
    return list(a[skip::2]), list(a[skip + 1::2]), (out_dev, in_dev), player.returncode


def windows(x, n=2400):
    return [x[i:i + n] for i in range(0, len(x) - n + 1, n)]


def chan_stats(x):
    if not x:
        return dict(dc=0, rms=0, floor=0, peak=0, clip=0)
    dc = sum(x) / len(x)
    w = sorted(math.sqrt(sum((v - dc) ** 2 for v in seg) / len(seg)) for seg in windows(x)) or [0]
    rms = math.sqrt(sum((v - dc) ** 2 for v in x) / len(x))
    clip = sum(1 for v in x if abs(v) >= 32700) / len(x)
    return dict(dc=round(dc), rms=round(rms, 1), floor=round(w[len(w) // 10], 1), peak=round(w[-1], 1),
                clip=round(clip, 4))


def op_test_mic(args):
    secs = float(args.get("seconds", 4))
    wav = "/tmp/bringup-silence.wav"
    write_wav(wav, [(secs + 1.0, 0, 0)])
    left, right, devs, _ = play_and_record(wav, secs)
    chans = dict(left=chan_stats(left), right=chan_stats(right))
    problems = []
    for name, s in chans.items():
        cn = "Left" if name == "left" else "Right"
        if s["rms"] < 2:
            problems.append(f"{cn} channel is almost all 0 (codec not up / i2c-2)")
        if abs(s["dc"]) > float(args.get("max_dc", 3000)):
            problems.append(f"{cn} channel DC offset {s['dc']}")
        if s["clip"] > 0.02:
            problems.append(f"{cn} channel {s['clip']:.1%} clipped")
        if s["peak"] < float(args.get("min_ratio", 4)) * max(s["floor"], 1):
            problems.append(f"{cn} channel heard no sound (peak {s['peak']} / noise floor {s['floor']}): clap or talk while it records")
    return dict(ok=not problems, problems=problems, devices=devs, seconds=secs, **chans)


def goertzel(seg, freq):
    k = 2 * math.cos(2 * math.pi * freq / RATE)
    s1 = s2 = 0.0
    for v in seg:
        s1, s2 = v + k * s1 - s2, s1
    return (s1 * s1 + s2 * s2 - k * s1 * s2) / (len(seg) ** 2)


def op_test_speaker(args):
    """Play 1 kHz on the speaker and record with the mic at the same time: how many dB the 1 kHz energy in the loud windows is above the quiet windows. Needs no time alignment."""
    freq = float(args.get("freq", 1000))
    dbfs = float(args.get("dbfs", -12))
    tone = float(args.get("seconds", 1.5))
    wav = "/tmp/bringup-tone.wav"
    write_wav(wav, [(0.5, 0, 0), (tone, freq, dbfs), (0.8, 0, 0)])
    left, right, devs, rc = play_and_record(wav, tone + 1.0)
    res = {}
    for name, x in (("left", left), ("right", right)):
        p = sorted(goertzel(seg, freq) for seg in windows(x))
        if not p:
            continue
        loud = sum(p[len(p) // 2:]) / max(1, len(p) - len(p) // 2)
        quiet = sum(p[: max(1, len(p) // 4)]) / max(1, len(p) // 4)
        res[name] = dict(tone_db=round(10 * math.log10(max(loud, 1e-9) / max(quiet, 1e-9)), 1),
                         tone_amp=round(math.sqrt(max(loud, 0)) * 2, 1))
    best = max((v["tone_db"] for v in res.values()), default=0)
    need = float(args.get("min_db", 15))
    problems = [] if best >= need else [f"the mic recorded 1 kHz only {best} dB above quiet (needs ≥ {need}): check speaker / amplifier / U6 DIN"]
    if rc not in (0, None):
        problems.append(f"aplay exit code {rc}")
    return dict(ok=not problems, problems=problems, freq=freq, dbfs=dbfs, devices=devs, best_db=best, **res)


# ---- ToF ---------------------------------------------------------------------------------------

def tofd_bus_default():
    unit = os.path.expanduser("~/.config/systemd/user/tofd-dev.service")
    if os.path.exists(unit):
        txt = open(unit).read()
        i = txt.find("--bus ")
        if i >= 0:
            return txt[i + 6:].split()[0]
    return "/dev/i2c-2"


def read_tof(sock_path, seconds):
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(3.0)
    s.connect(sock_path)
    s.sendall(b'{"jsonrpc":"2.0","id":1,"method":"tof.stream"}\n')
    frames, buf, status = [], b"", None
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            d = s.recv(65536)
        except socket.timeout:
            break
        if not d:
            break
        buf += d
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("method") == "tof.frame":
                frames.append((time.time(), m["params"]))
            elif "result" in m:
                status = m["result"]
            elif "error" in m:
                raise RuntimeError(f"tofd: {m['error']}")
    s.close()
    return frames, status


def op_test_tof(args):
    seconds = float(args.get("seconds", 2.5))
    sock = "/tmp/tofd.sock"
    child, started = None, False
    if not os.path.exists(sock) or not any(c == "tofd" for _, c, _ in procs()):
        exe = os.path.expanduser(args.get("tofd") or "~/robot/tofd")
        if not os.path.exists(exe):
            raise RuntimeError(f"tofd is not running and there is no {exe}")
        sock = "/tmp/bringup-tofd.sock"
        if os.path.exists(sock):
            os.unlink(sock)
        bus = args.get("bus") or tofd_bus_default()
        child = subprocess.Popen([exe, "--bus", bus, "--socket", sock], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE)
        started = True
        for _ in range(60):
            if os.path.exists(sock) or child.poll() is not None:
                break
            time.sleep(0.1)
    try:
        if child is not None and child.poll() is not None:
            raise RuntimeError("tofd does not start: " + child.stderr.read().decode(errors="replace").strip()[-400:])
        # a tofd started here must first set up the sensor (the firmware upload takes a few seconds), so wait longer
        frames, status = read_tof(sock, seconds + (6.0 if started else 0.0))
    finally:
        if child is not None:
            child.terminate()  # stop only the one started here (the exact PID held by Popen)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
    if started:
        frames = [f for f in frames if f[0] >= frames[-1][0] - seconds] if frames else []
    if len(frames) < 3:
        return dict(ok=False, problems=[f"only {len(frames)} frames received"], status=status, started_tofd=started)
    hz = (len(frames) - 1) / (frames[-1][0] - frames[0][0])
    valid_counts, centre = [], []
    for _, p in frames:
        st, dist = p.get("status") or [], p.get("distance_mm") or []
        valid = [i for i, v in enumerate(st) if v in (5, 9)]
        valid_counts.append(len(valid))
        mid = sorted(dist[r * 8 + c] for r in range(2, 6) for c in range(2, 6) if r * 8 + c in valid)
        if mid:
            centre.append(mid[len(mid) // 2])
    last = frames[-1][1]
    vmed = sorted(valid_counts)[len(valid_counts) // 2]
    problems = []
    if hz < 10:
        problems.append(f"frame rate {hz:.1f} Hz (should be about 15)")
    if vmed < int(args.get("min_valid", 32)):
        problems.append(f"only {vmed}/64 valid zones")
    return dict(ok=not problems, problems=problems, hz=round(hz, 1), frames=len(frames), valid_median=vmed,
                centre_mm=sorted(centre)[len(centre) // 2] if centre else None,
                grid=last.get("distance_mm"), grid_status=last.get("status"), started_tofd=started,
                sensor=(status or {}).get("sensor") if isinstance(status, dict) else None)


# ---- Camera ------------------------------------------------------------------------------------

def bmp_grey(w, h, pix):
    row = (w + 3) & ~3
    pal = b"".join(bytes((i, i, i, 0)) for i in range(256))
    data = b"".join(bytes(pix[y * w:(y + 1) * w]) + b"\0" * (row - w) for y in range(h - 1, -1, -1))
    off = 14 + 40 + len(pal)
    return (b"BM" + struct.pack("<IHHI", off + len(data), 0, 0, off)
            + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 8, 0, len(data), 2835, 2835, 256, 0) + pal + data)


def find_duckcam():
    for p in ("~/robot/duckcam", "~/duckcam", "~/visiond/duckcam", "~/robot/visiond/duckcam"):
        p = os.path.expanduser(p)
        if os.path.exists(p):
            return p
    return shutil.which("duckcam")


def op_test_camera(args):
    names = {}
    base = "/sys/class/video4linux"
    if os.path.isdir(base):
        for d in os.listdir(base):
            try:
                names[d] = open(os.path.join(base, d, "name")).read().strip()
            except OSError:
                pass
    vin = sorted((n for n, v in names.items() if v.startswith("vin_video")), key=lambda n: int(n[5:]))
    mods = open("/proc/modules").read() if os.path.exists("/proc/modules") else ""
    if not vin:
        hint = "" if "vin_v4l2" in mods else ": the vin driver is not loaded, run sudo modprobe -a vin_io imx219 vin_v4l2"
        return dict(ok=False, problems=["no vin_video device" + hint], nodes=names)
    busy = [f"{c}({p})" for p, c, cmd in procs() if c == "duckcam" or "visiond.py" in cmd]
    if busy:
        return dict(ok=False, problems=[f"the camera is in use: {busy}; stop visiond, then test"], device="/dev/" + vin[0])
    exe = find_duckcam()
    if not exe:
        return dict(ok=False, problems=["cannot find duckcam (build tools/visiond/duckcam.c on the OPi)"], device="/dev/" + vin[0])
    n = int(args.get("frames", 45))
    r = subprocess.run([exe, "--half", "--frames", str(n), "--dev", "/dev/" + vin[0]], capture_output=True,
                       timeout=30)
    data, frames, i = r.stdout, [], 0
    while i + 32 <= len(data) and data[i:i + 4] == b"DCAM":
        w, h, seq, ts, exp, gain = struct.unpack_from("<IIIqII", data, i + 4)
        frames.append((w, h, seq, ts, exp, gain, i + 32))
        i += 32 + w * h
    if not frames:
        err = r.stderr.decode(errors="replace").strip().splitlines()
        return dict(ok=False, problems=["duckcam gave no frames: " + (err[-1] if err else f"exit code {r.returncode}")],
                    device="/dev/" + vin[0])
    w, h, seq, ts, exp, gain, off = frames[-1]
    pix = data[off:off + w * h]
    step = 4
    tw, th = w // step, h // step
    thumb = bytes(pix[(y * step) * w + x * step] for y in range(th) for x in range(tw))
    sample = pix[::97]
    mean = sum(sample) / len(sample)
    std = math.sqrt(sum((v - mean) ** 2 for v in sample) / len(sample))
    tail = frames[len(frames) // 3:]
    fps = (len(tail) - 1) / ((tail[-1][3] - tail[0][3]) / 1e9) if len(tail) > 1 and tail[-1][3] > tail[0][3] else None
    problems = []
    if fps is not None and fps < 10:
        problems.append(f"frame rate {fps:.1f}")
    if not 8 <= mean <= 245:
        problems.append(f"mean brightness {mean:.0f} (all black / all white)")
    if std < 3:
        problems.append(f"the image has almost no texture (std dev {std:.1f})")
    return dict(ok=not problems, problems=problems, device="/dev/" + vin[0], frames=len(frames), size=[w, h],
                fps=None if fps is None else round(fps, 1), exposure_us=exp, gain=gain, mean=round(mean, 1),
                std=round(std, 1), thumb_bmp=base64.b64encode(bmp_grey(tw, th, thumb)).decode())


OPS = {name[3:]: fn for name, fn in globals().items() if name.startswith("op_")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="~/robot/active.toml")
    ap.add_argument("--port", default=None)
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--usb", action="store_true", help="USB board on the computer: no robotd check, no peripheral tests")
    a = ap.parse_args()
    Ctx.usb = a.usb
    Ctx.baud = a.baud
    if not a.usb:
        Ctx.config, Ctx.cfg_path = load_config(a.config)
    Ctx.port = a.port or bus_cfg().get("port") or "/dev/ttyS0"
    out = sys.stdout
    out.write(json.dumps({"hello": True, "ops": sorted(OPS)}) + "\n")
    out.flush()
    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        rid = req.get("id")
        fn = OPS.get(req.get("op"))
        try:
            if fn is None:
                raise RuntimeError(f"no such op: {req.get('op')}")
            resp = {"id": rid, "ok": True, "result": fn(req.get("args") or {})}
        except Exception as e:  # noqa: BLE001
            resp = {"id": rid, "ok": False, "error": f"{e}" if isinstance(e, (BusError, RuntimeError))
                    else f"{type(e).__name__}: {e}"}
        out.write(json.dumps(resp) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
