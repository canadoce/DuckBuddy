# -*- coding: utf-8 -*-
"""Change the Feetech HLS servos on the bus to a new baud rate (written to EEPROM, kept after power off).

The Orange Pi A733 UART can only output 500k accurately (1M is really 750k), so the servo bus always uses 500k.

Usage (close the FD desktop app first, it holds the serial port):
    python tools/servo/set_baud.py                 # default COM11, only 1 servo allowed on the bus
    python tools/servo/set_baud.py --all           # change all servos on the bus together (whole chain)
    python tools/servo/set_baud.py --to 1000000    # change back to 1M
    python tools/servo/set_baud.py --scan          # scan only, no change

Only writes two addresses, 55 (lock flag) and 6 (baud rate). Torque/position are not touched, so the servos do not move.
"""
import argparse
import sys
import time

from fts_bus import Bus, LOCK, BAUD_ADDR

BAUDS = [1000000, 500000, 250000, 128000, 115200, 76800, 57600, 38400]  # register 6 values 0..7


def scan_all(port, bauds):
    """Scan once at each baud rate, return {baud: [ids]} (only rates with servos are listed)."""
    found = {}
    for b in bauds:
        bus = Bus(port, b)
        try:
            ids = bus.scan(0, 253, tries=1)
        finally:
            bus.close()
        if ids:
            found[b] = ids
        print(f"  {b:>7} bps: {ids if ids else '-'}")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM11")
    ap.add_argument("--to", type=int, default=500000, choices=BAUDS)
    ap.add_argument("--all", action="store_true", help="allow changing several servos at once")
    ap.add_argument("--scan", action="store_true", help="scan only")
    a = ap.parse_args()

    print(f"Scanning {a.port} ...")
    found = scan_all(a.port, BAUDS)
    if a.scan:
        return 0
    if not found:
        print("No servos found: check power, wire order, and whether the FD desktop app is still open.")
        return 1

    old = {(b, i) for b, ids in found.items() for i in ids}
    ids = sorted({i for _, i in old})
    if len(ids) != len(old):
        print("The same ID shows up at several baud rates, please change them one at a time.")
        return 1
    if len(ids) > 1 and not a.all:
        print(f"There are {len(ids)} servos on the bus {ids}; to change the whole chain add --all.")
        return 1

    idx = BAUDS.index(a.to)
    todo = [(b, i) for b, i in sorted(old) if b != a.to]
    for b, i in todo:
        bus = Bus(a.port, b)
        try:
            bus.w8(i, LOCK, 0)          # unlock EEPROM
            time.sleep(0.02)
            bus.w8(i, BAUD_ADDR, idx)   # write the baud rate value
            time.sleep(0.05)
        finally:
            bus.close()
        print(f"  ID {i}: {b} -> {a.to} written")

    # At the new baud rate check and lock each servo (including ones already at the target rate that were not locked last time);
    # some models only switch after a power cycle, so print a hint
    time.sleep(0.2)
    bus = Bus(a.port, a.to)
    bad = []
    try:
        for i in ids:
            if bus.ping(i) is None:
                bad.append(i)
                continue
            if bus.r8(i, LOCK) != 1:
                bus.w8(i, LOCK, 1)
                time.sleep(0.02)
            v = bus.r8(i, BAUD_ADDR)
            print(f"  ID {i}: {a.to} bps replies OK, register6={v}, lock={bus.r8(i, LOCK)}")
    finally:
        bus.close()

    if bad:
        print(f"ID {bad} did not reply at {a.to} bps: power cycle the servos and run this script again (it will lock them).")
        return 2
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
