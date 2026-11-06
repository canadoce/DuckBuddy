# -*- coding: utf-8 -*-
"""HL-2915 pendulum rig recording -- writes logs that BAM (Better Actuator Models) can fit directly.

The actuator model in the training repo microduck_rl is identified with BAM. BAM's own Feetech recording script is for the STS3215
(a different memory table, 1M, Linux serial port). This is a rewrite with the same trajectories and log format for the HLS memory table + debug board.

Rig: the servo is fixed at the edge of a table with the output shaft level; a stiff pendulum arm is fitted on the horn, with a weight at its end.
The arm **hanging down freely is position 0**. It must swing freely past ±110° to both sides (not hitting the table, not catching cables).
Measure: the arm's own mass --arm-mass, the end weight --mass (kg), and the distance from the shaft to the center of the weight --length (m).

Usage (debug board COM11, only this one servo connected, 12V power; close the FD desktop app first):
    python tools/servo/bam_record.py --check                       # read only: show position 0, voltage, temperature
    python tools/servo/bam_record.py --mass 0.1 --arm-mass 0.02 --length 0.1 --logdir training/data/bam-hl2915/m100
    python tools/servo/bam_record.py ... --kps 16 --trajectories sin_sin   # record only one set

Each set (Kp x trajectory) is 6 seconds and is saved as one JSON. Ctrl-C during recording turns torque off at once.
Registers match the robot: goal current 44 (default 1300 mA), running speed 46 = 250, acceleration 41 = 0,
live Kp 50 / Kd 51 (Kd default 8, same as deploy/robots/opi-hl2915-rev-a.toml).
"""
import argparse
import datetime
import json
import math
import os
import sys
import time

import serial

from fts_bus import (ACCEL, GOAL_CURR, GOAL_SPEED, MAX_ANGLE, MIN_ANGLE, MODE, PRES_POS,
                     TORQUE, smag)

KP, KD = 50, 51
COUNTS_PER_RAD = 4096 / (2 * math.pi)
RAD_S_PER_SPEED = 0.732 * 2 * math.pi / 60       # address 58: 0.732 rpm/count
MA_PER_COUNT = 6.5
RUNNING_SPEED = 250
MAX_TEMP = 65


# ---- BAM trajectories (ported as is from bam/trajectory.py, 6 s, 0 = hanging down) ----
def cubic(keyframes, t):
    if t <= keyframes[0][0]:
        return keyframes[0][1]
    if t >= keyframes[-1][0]:
        return keyframes[-1][1]
    for (t0, x0, v0), (t1, x1, v1) in zip(keyframes, keyframes[1:]):
        if t0 <= t <= t1:
            h, s = t1 - t0, (t - t0) / (t1 - t0)
            h00, h10 = 2*s**3 - 3*s**2 + 1, s**3 - 2*s**2 + s
            h01, h11 = -2*s**3 + 3*s**2, s**3 - s**2
            return h00*x0 + h10*h*v0 + h01*x1 + h11*h*v1


TRAJECTORIES = {
    # lift to -90° in 2 s, then cut torque and let it fall freely: back-drive / low speed friction
    "lift_and_drop": lambda t: (cubic([[0, 0, 0], [2, -math.pi/2, 0]], t), t < 2.0),
    # sin(t²) swings faster and faster: the main trajectory, covers the whole speed range (the last part hits the servo's speed limit)
    "sin_time_square": lambda t: (math.sin(t*t), True),
    # slow 0 -> 90° -> 72°: static friction and load
    "up_and_down": lambda t: (cubic([[0, 0, 0], [3, math.pi/2, 0], [6, 0.8*math.pi/2, 0]], t), True),
    # several frequencies added, at most about ±101° within 6 s
    "sin_sin": lambda t: (math.sin(t)*math.pi/2 + math.sin(5*t)*0.5*math.sin(2*t), True),
    # no torque the whole time
    "nothing": lambda t: (0.0, False),
}
DURATION = 6.0
MAX_EXCURSION = 1.8        # rad, sin_sin peaks at 1.76 within 6 s


class Servo:
    """Fast reads and writes for one servo: one read covers 56..70, 15 bytes; goal position uses SYNC_WRITE (no reply)."""

    def __init__(self, port, baud, sid):
        self.s = serial.Serial(port, baud, timeout=0.02, write_timeout=0.2)
        self.id = sid

    def _send(self, sid, inst, params):
        body = [sid, len(params) + 2, inst] + list(params)
        self.s.write(bytes([0xFF, 0xFF] + body + [(~sum(body)) & 0xFF]))

    def _reply(self):
        hdr = self.s.read(4)
        if len(hdr) < 4 or hdr[:2] != b"\xff\xff" or hdr[2] != self.id:
            return None
        rest = self.s.read(hdr[3])
        if len(rest) < hdr[3] or (~(sum(hdr[2:]) + sum(rest[:-1]))) & 0xFF != rest[-1]:
            return None
        return rest[1:-1]

    def read(self, addr, n):
        self.s.reset_input_buffer()
        self._send(self.id, 0x02, (addr, n))
        return self._reply()

    def write(self, addr, data):
        self.s.reset_input_buffer()
        self._send(self.id, 0x03, [addr] + list(data))
        return self._reply() is not None

    def w8(self, addr, v):
        return self.write(addr, [v & 0xFF])

    def w16(self, addr, v):
        return self.write(addr, [v & 0xFF, (v >> 8) & 0xFF])

    def goal(self, counts):
        counts = max(0, min(4095, int(round(counts))))
        self._send(0xFE, 0x83, [42, 2, self.id, counts & 0xFF, counts >> 8])

    def state(self):
        d = self.read(PRES_POS, 15)
        if d is None or len(d) < 15:
            return None
        return dict(pos=smag(d[0] | d[1] << 8), speed=smag(d[2] | d[3] << 8),
                    volts=d[6] * 0.1, temp=d[7], status=d[9],
                    current=smag(d[13] | d[14] << 8) * MA_PER_COUNT)

    def torque(self, on):
        for _ in range(3):
            if self.w8(TORQUE, 1 if on else 0):
                return
        raise IOError("writing the torque switch failed")


def state_or_die(servo):
    for _ in range(3):
        st = servo.state()
        if st is not None:
            return st
    raise IOError(f"ID {servo.id} does not reply")


def find_zero(servo):
    """Position with torque off and the arm hanging down freely (1 s average). Refuses if it swings too much."""
    servo.torque(False)
    samples = []
    t0 = time.time()
    while time.time() - t0 < 1.0:
        samples.append(state_or_die(servo)["pos"])
    mean = sum(samples) / len(samples)
    spread = max(samples) - min(samples)
    return mean, spread


def record_one(servo, zero, kp, name, meta, logdir):
    traj = TRAJECTORIES[name]
    to_counts = lambda q: zero + q * COUNTS_PER_RAD
    servo.w8(KP, kp)

    # 1 s to get ready: like BAM, first hold at the start of the trajectory
    q0, en = traj(0.0)
    servo.goal(to_counts(q0))
    servo.torque(en)
    torque_on = en
    time.sleep(1.0)

    entries = []
    start = time.time()
    while True:
        t = time.time() - start
        if t >= DURATION:
            break
        q, en = traj(t)
        if en != torque_on:
            if en:
                servo.goal(to_counts(q))
            servo.torque(en)
            torque_on = en
        if en:
            servo.goal(to_counts(q))
        t0 = time.time() - start
        st = servo.state()
        t1 = time.time() - start
        if st is None:
            continue
        if st["temp"] >= MAX_TEMP:
            raise RuntimeError(f"temperature {st['temp']}°C, stopping")
        entries.append(dict(
            timestamp=(t0 + t1) / 2,
            position=(st["pos"] - zero) / COUNTS_PER_RAD,
            speed=st["speed"] * RAD_S_PER_SPEED,
            load=st["current"] / 1000.0,          # BAM does not use it; current (A) is stored here for reference
            input_volts=st["volts"],
            temp=float(st["temp"]),
            goal_position=q,
            torque_enable=en,
            current=st["current"] / 1000.0,
        ))

    # slowly back to 0 (1 rad/s), then cut torque
    st = state_or_die(servo)
    q = (st["pos"] - zero) / COUNTS_PER_RAD
    servo.goal(to_counts(q))
    servo.torque(True)
    while abs(q) > 1e-3:
        q = max(0.0, q - 0.01) if q > 0 else min(0.0, q + 0.01)
        servo.goal(to_counts(q))
        time.sleep(0.01)
    time.sleep(0.5)
    servo.torque(False)

    dt = [b["timestamp"] - a["timestamp"] for a, b in zip(entries, entries[1:])]
    rate = 1.0 / (sum(dt) / len(dt)) if dt else 0.0
    vin = sum(e["input_volts"] for e in entries) / max(1, len(entries))
    log = dict(meta, kp=kp, vin=round(vin, 2), trajectory=name, entries=entries)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%Hh%Mm%S")
    path = os.path.join(logdir, f"{stamp}_kp{kp}_{name}.json")
    json.dump(log, open(path, "w"))
    peak = max((abs(e["current"]) for e in entries), default=0)
    print(f"  {len(entries)} points / {rate:.0f} Hz, {vin:.1f} V, peak current {peak:.2f} A -> {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM11")
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--id", type=int, default=1)
    ap.add_argument("--check", action="store_true", help="read only, no torque")
    ap.add_argument("--mass", type=float, help="end weight kg")
    ap.add_argument("--arm-mass", type=float, help="arm's own mass kg (everything between the horn and the weight)")
    ap.add_argument("--length", type=float, help="shaft to center of weight m")
    ap.add_argument("--logdir")
    ap.add_argument("--kps", default="8,16,24,32")
    ap.add_argument("--kd", type=int, default=8)
    ap.add_argument("--current-ma", type=float, default=1300.0)
    ap.add_argument("--trajectories", default="sin_time_square,sin_sin,up_and_down,lift_and_drop")
    a = ap.parse_args()

    servo = Servo(a.port, a.baud, a.id)
    st = servo.state()
    if st is None:
        sys.exit(f"ID {a.id} does not reply on {a.port} @ {a.baud} (wrong baud rate/ID? check with set_baud.py --scan)")

    mode = servo.read(MODE, 1)
    lim = servo.read(MIN_ANGLE, 4)
    print(f"ID {a.id}: position {st['pos']}, {st['volts']:.1f} V, {st['temp']}°C, status 0x{st['status']:02x}, "
          f"mode {mode[0] if mode else '?'}, limits {lim[0] | lim[1] << 8 if lim else '?'}"
          f"..{lim[2] | lim[3] << 8 if lim else '?'}")

    zero, spread = find_zero(servo)
    margin = MAX_EXCURSION * COUNTS_PER_RAD
    print(f"hanging position 0 = {zero:.0f} (jitter {spread} counts within 1 s); {zero - margin:.0f}..{zero + margin:.0f} must be inside 0..4095")
    ok_range = zero - margin >= 0 and zero + margin <= 4095
    if not ok_range:
        print("!! Position 0 is too far from the midpoint, large trajectories will cross 0/4095. Refit the horn at a different angle on the servo so the hanging reading is near 2048.")
    if spread > 10:
        print("!! The arm is still swinging, wait until it is still and measure again.")
    if a.check:
        return
    if not ok_range or spread > 10:
        sys.exit(1)
    if mode is None or mode[0] != 0:
        sys.exit("The servo is not in position mode (33 != 0)")
    if None in (a.mass, a.arm_mass, a.length, a.logdir):
        sys.exit("Recording needs --mass --arm-mass --length --logdir")

    os.makedirs(a.logdir, exist_ok=True)
    kps = [int(k) for k in a.kps.split(",")]
    names = a.trajectories.split(",")
    for n in names:
        if n not in TRAJECTORIES:
            sys.exit(f"Unknown trajectory {n}; choices: {', '.join(TRAJECTORIES)}")

    # Same RAM settings as the robot (lost at power off, written every time)
    assert servo.w16(GOAL_CURR, int(round(a.current_ma / MA_PER_COUNT)))
    assert servo.w16(GOAL_SPEED, RUNNING_SPEED)
    assert servo.w8(ACCEL, 0)
    assert servo.w8(KD, a.kd)

    meta = dict(mass=a.mass, arm_mass=a.arm_mass, length=a.length, motor="hl2915",
                kd=a.kd, current_limit_ma=a.current_ma, zero_counts=zero, servo_id=a.id)
    try:
        for kp in kps:
            for n in names:
                print(f"Kp {kp}, {n}")
                record_one(servo, zero, kp, n, meta, a.logdir)
                time.sleep(3.0 if n == "lift_and_drop" else 1.0)
                # Between sets check again that position 0 has not drifted (a slipping horn would spoil all later data)
                z, sp = find_zero(servo)
                if sp <= 10 and abs(z - zero) > 30:
                    raise RuntimeError(f"position 0 moved from {zero:.0f} to {z:.0f}, is the horn or arm loose?")
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        servo.torque(False)
        print("Torque off")


if __name__ == "__main__":
    main()
