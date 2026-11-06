# -*- coding: utf-8 -*-
"""HL-2915 command latency: how long from writing a goal position (SYNC_WRITE, same as robotd) until the servo responds.

Done on the pendulum rig (pendulum hanging down = position 0): hold at 0, send steps of ±step in turn, poll
position and current at about 1 kHz, and record for each step
  - current rise: |current - mean before the step| > 60 mA (the motor starts to push)
  - motion start: position leaves the start by >= 3 counts (0.26°)
  - halfway: 50% of the move done
Times count from the moment of the write, minus half a read cycle (a read returns the state between request and reply).

Usage (debug board COM11, pendulum rig; close the FD desktop app first):
    python tools/servo/latency_test.py --kps 16,32 --out training/data/bam-hl2915/latency.json
"""
import argparse
import json
import statistics
import sys
import time

from bam_record import (ACCEL, COUNTS_PER_RAD, GOAL_CURR, GOAL_SPEED, KD, KP, MA_PER_COUNT,
                        RUNNING_SPEED, Servo, find_zero, state_or_die)


def step_once(servo, start, target, window):
    """Send one step, return [(t, pos, current)], t relative to the write."""
    base = []
    for _ in range(20):
        st = servo.state()
        if st:
            base.append(st["current"])
    t_write = time.perf_counter()
    servo.goal(target)
    trace = []
    while True:
        t0 = time.perf_counter()
        st = servo.state()
        t1 = time.perf_counter()
        if st:
            trace.append(((t0 + t1) / 2 - t_write, st["pos"], st["current"], t1 - t0))
        if t1 - t_write > window:
            break
    return statistics.mean(base) if base else 0.0, trace


def analyse(start, target, i_base, trace):
    sign = 1 if target > start else -1
    half = start + (target - start) / 2
    t_cur = t_move = t_half = None
    for t, pos, cur, _ in trace:
        if t_cur is None and abs(cur - i_base) > 60:
            t_cur = t
        if t_move is None and (pos - start) * sign >= 3:
            t_move = t
        if t_half is None and (pos - half) * sign >= 0:
            t_half = t
    rtt = statistics.median(r for *_, r in trace) if trace else 0.0
    return t_cur, t_move, t_half, rtt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM11")
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--id", type=int, default=1)
    ap.add_argument("--kps", default="16,32")
    ap.add_argument("--kd", type=int, default=8)
    ap.add_argument("--current-ma", type=float, default=1300.0)
    ap.add_argument("--step-deg", type=float, default=10.0)
    ap.add_argument("--reps", type=int, default=12, help="number of steps per Kp (alternating positive and negative)")
    ap.add_argument("--out")
    a = ap.parse_args()

    servo = Servo(a.port, a.baud, a.id)
    state_or_die(servo)
    zero, spread = find_zero(servo)
    if spread > 10:
        sys.exit("The pendulum is still swinging, wait until it is still")
    zero = round(zero)
    step = round(a.step_deg / 180 * 3.14159265 * COUNTS_PER_RAD)

    assert servo.w16(GOAL_CURR, int(round(a.current_ma / MA_PER_COUNT)))
    assert servo.w16(GOAL_SPEED, RUNNING_SPEED)
    assert servo.w8(ACCEL, 0)
    assert servo.w8(KD, a.kd)

    results = {}
    try:
        servo.goal(zero)
        servo.torque(True)
        for kp in [int(k) for k in a.kps.split(",")]:
            servo.w8(KP, kp)
            time.sleep(0.8)
            rows = []
            for r in range(a.reps):
                target = zero + (step if r % 2 == 0 else -step)
                st = state_or_die(servo)
                start = st["pos"]
                i_base, trace = step_once(servo, start, target, 0.25)
                t_cur, t_move, t_half, rtt = analyse(start, target, i_base, trace)
                rows.append(dict(start=start, target=target, t_current=t_cur, t_move=t_move,
                                 t_half=t_half, rtt=rtt,
                                 trace=[(round(t, 5), p, round(c, 1)) for t, p, c, _ in trace]))
                f = lambda x: f"{x * 1000:5.1f}" if x is not None else "  -  "
                print(f"Kp {kp:2d} #{r:2d} {start}->{target}: current rise {f(t_cur)} ms, motion start {f(t_move)} ms, "
                      f"halfway {f(t_half)} ms (one read {rtt * 1000:.2f} ms)")
                # back to 0 and wait until still
                servo.goal(zero)
                time.sleep(0.6)
            results[kp] = rows
            for key, name in (("t_current", "current rise"), ("t_move", "motion start"), ("t_half", "halfway")):
                v = [x[key] for x in rows if x[key] is not None]
                if v:
                    print(f"  Kp {kp} {name}: median {statistics.median(v) * 1000:.1f} ms, "
                          f"range {min(v) * 1000:.1f}..{max(v) * 1000:.1f} ms ({len(v)}/{len(rows)})")
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        servo.torque(False)
        print("Torque off")

    if a.out and results:
        json.dump(dict(zero=zero, step_counts=step, kd=a.kd, current_limit_ma=a.current_ma,
                       baud=a.baud, results=results), open(a.out, "w"))
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
