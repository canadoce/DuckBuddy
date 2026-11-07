"""Stand-ins for the brain's hardware programs, for the Mac simulator (phoebe_sim.py).

phoebe_sim.py puts small wrappers named aplay, arecord, duckcam, amixer, nmcli, timedatectl and ip
first on the services' PATH; each runs this file with its own name first:

    shim.py aplay [-q] [-D dev] [-t raw|wav] [-f S16_LE] [-c N] [-r RATE] [file | -]
    shim.py arecord [-D dev] [-f S16_LE] [-r RATE] [-c N] [-t raw] ...    (raw PCM on stdout)
    shim.py duckcam [--every N] [--half | --nv12] ...                      (duckcam's frames on stdout)
    shim.py amixer -c card -M -q sset PCM N%                               (the speaker volume)
    shim.py nmcli ...                                                      (a pretend Wi-Fi)
    shim.py timedatectl ... / shim.py ip ...                               (the clock is set; an address)

Each one talks to the simulator on $PHOEBE_SIM_SOCK: one JSON line saying what it is, then the
data. Sound to play goes up in frames (u32 length, then bytes; length 0 is the normal end), so a
player killed mid-sound (robotd hushing a one-shot) is told apart from one that finished. The
simulator reads the sound only as fast as it plays, so a writer into aplay's stdin waits the way it
does on the robot, and aplay exits when the sound has finished playing.

Standard library only.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
import wave

SOCK = os.environ.get("PHOEBE_SIM_SOCK", "/tmp/phoebe-sim/sim.sock")
CHUNK = 4096


def connect(header: dict) -> socket.socket:
    s = socket.socket(socket.AF_UNIX)
    s.connect(SOCK)
    s.sendall((json.dumps(header) + "\n").encode())
    return s


def opts(argv, with_value):
    """Flags and the positional arguments, for the few flags each program is called with."""
    flags, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a in with_value and i + 1 < len(argv):
            flags[a] = argv[i + 1]
            i += 2
            continue
        if a.startswith("-") and a != "-":
            flags[a] = True
        else:
            rest.append(a)
        i += 1
    return flags, rest


def aplay(argv):
    f, rest = opts(argv, {"-D", "-t", "-f", "-c", "-r", "--device"})
    path = rest[0] if rest else "-"
    if path != "-" and f.get("-t", "wav") != "raw":
        w = wave.open(path, "rb")
        if w.getsampwidth() != 2:
            sys.exit(f"aplay (sim): {path}: only 16-bit wavs")
        rate, ch, name = w.getframerate(), w.getnchannels(), os.path.basename(path)
        read = lambda n: w.readframes(n // (2 * ch))  # noqa: E731
    else:
        if f.get("-f", "S16_LE") != "S16_LE":
            sys.exit("aplay (sim): only S16_LE")
        rate, ch = int(f.get("-r", 8000)), int(f.get("-c", 1))
        src = sys.stdin.buffer if path == "-" else open(path, "rb")
        name = "stream" if path == "-" else os.path.basename(path)
        read = lambda n: src.read1(n) if hasattr(src, "read1") else src.read(n)  # noqa: E731
    try:
        s = connect({"op": "play", "rate": rate, "channels": ch, "name": name, "device": f.get("-D", "")})
    except OSError as e:
        sys.exit(f"aplay (sim): simulator not reachable: {e}")
    try:
        while data := read(CHUNK):
            s.sendall(struct.pack("<I", len(data)) + data)
        s.sendall(struct.pack("<I", 0))
        s.recv(16)                     # the simulator answers when the sound has finished playing
    except (OSError, KeyboardInterrupt):
        pass


def pump_out(header):
    """Copy what the simulator sends to stdout until either side stops."""
    try:
        s = connect(header)
    except OSError as e:
        sys.exit(f"{header['op']} (sim): simulator not reachable: {e}")
    out = sys.stdout.buffer
    try:
        while data := s.recv(1 << 16):
            out.write(data)
            out.flush()
    except (OSError, KeyboardInterrupt):
        pass


def arecord(argv):
    f, _ = opts(argv, {"-D", "-f", "-r", "-c", "-t", "-B", "-d"})
    if f.get("-f", "S16_LE") != "S16_LE":
        sys.exit("arecord (sim): only S16_LE")
    pump_out({"op": "rec", "rate": int(f.get("-r", 8000)), "channels": int(f.get("-c", 1)),
              "seconds": float(f.get("-d", 0))})


def duckcam(argv):
    f, _ = opts(argv, {"--every", "--frames", "--dev"})
    pump_out({"op": "cam", "every": max(1, int(f.get("--every", 1))), "half": bool(f.get("--half")),
              "nv12": bool(f.get("--nv12")), "frames": int(f.get("--frames", 0))})


def tell(header):
    try:
        s = connect(header)
        reply = s.recv(1 << 16).decode(errors="replace")
        s.close()
        return reply
    except OSError:
        return ""


def amixer(argv):
    if "sset" in argv:
        i = argv.index("sset")
        if argv[i + 1:i + 2] == ["PCM"] and i + 2 < len(argv):
            try:
                pct = float(argv[i + 2].rstrip("%"))
            except ValueError:
                return
            tell({"op": "volume", "pct": pct})


def nmcli(argv):
    shown = []
    for i, a in enumerate(argv):
        shown.append("***" if i > 0 and argv[i - 1] == "password" else a)
    try:
        reply = json.loads(tell({"op": "nmcli", "args": argv, "shown": shown}) or "{}")
    except ValueError:
        reply = {}
    sys.stdout.write(reply.get("out", ""))
    sys.stderr.write(reply.get("err", ""))
    sys.exit(int(reply.get("code", 0 if reply else 8)))


def timedatectl(argv):
    """The Mac keeps its clock set: lifed's time of day works."""
    if "NTPSynchronized" in argv:
        print("yes")


def ip(argv):
    """`ip -4 -o addr show wlan0`: the address the duck says when asked."""
    if "addr" in argv:
        print("3: wlan0    inet 127.0.0.1/8 brd 127.255.255.255 scope global wlan0")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    prog, argv = sys.argv[1], sys.argv[2:]
    {"aplay": aplay, "arecord": arecord, "duckcam": duckcam, "amixer": amixer, "nmcli": nmcli,
     "timedatectl": timedatectl, "ip": ip}[prog](argv)


if __name__ == "__main__":
    main()
