# -*- coding: utf-8 -*-
"""Change the servo mass in the MJCF from XL330 (18g) to HL-2915-C001 (measured 28g), recompute each link's
mass / center of mass / inertia tensor; then scale all the non-servo mass so the whole robot equals the measured total.

Measured (2026-10-05, with the 3S 1500mAh battery, 119.6g): whole robot 850g, one servo 28g.
There is only the total, no per-part weights, so the non-servo parts (printed parts, boards, battery, wiring) are scaled
by one factor: the non-servo center of mass of each link stays, the inertia scales with the mass. Once per-part weights are known, set each link on its own.

Mass and center of mass are exact; the servo's own inertia uses an equivalent isotropic approximation (the mean of the three principal
inertias of a 34x20x23mm uniform box), because the geoms all point different ways and the final values must come from measurement anyway. The parallel-axis terms are exact.
"""
import re, os

# the original Microduck model (hardware/original/mjcf, from Pollen's repository) in, this directory out
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(OUT_DIR, "..", "..", "original", "mjcf")
FILES = ["robot_walk.xml", "robot_allcollisions.xml", "robot_allcollisions_rollers.xml"]

M_OLD = 0.018           # XL330, kg
M_NEW = 0.028           # HL-2915-C001, measured, kg
MEASURED_TOTAL = 0.850  # whole robot, measured (with battery), kg
# 34 x 20 x 23 mm uniform box, the mean of the three principal inertias for unit mass
A, B, C = 0.034, 0.020, 0.023
I_UNIT = ((B*B+C*C) + (A*A+C*C) + (A*A+B*B)) / 3 / 12

INERTIAL = re.compile(r'<inertial pos="([^"]+)" mass="([^"]+)" fullinertia="([^"]+)"\s*/>')


def nums(s):
    return [float(x) for x in s.split()]


def pa(m, r):
    """Inertia tensor part of a point mass m at offset r from the reference point, returns (ixx,iyy,izz,ixy,ixz,iyz)."""
    x, y, z = r
    return (m*(y*y+z*z), m*(x*x+z*z), m*(x*x+y*y), -m*x*y, -m*x*z, -m*y*z)


def servo_positions(blk):
    """Positions of the xl330 geoms directly in this body (nested bodies are already cut into other blocks)."""
    out = []
    for m in re.finditer(r'<!-- Part xl330[_0-9]* -->(.*?)(?=<!-- Part |\Z)', blk, re.S):
        g = re.search(r'<geom[^>]*pos="([^"]+)"', m.group(1))
        out.append(nums(g.group(1)) if g else [0.0, 0.0, 0.0])
    return out


def blocks(t):
    """Cut into blocks at <body boundaries: from each <body ...> to the next <body, with its inertial and Part comments."""
    return re.split(r'(?=<body )', t)


def rest_scale(t, total=MEASURED_TOTAL):
    """The scale factor for the non-servo parts, plus the servo count and the original non-servo total mass."""
    rest, n = 0.0, 0
    for blk in blocks(t):
        mi = INERTIAL.search(blk) if blk.startswith("<body ") else None
        if mi:
            k = len(servo_positions(blk))
            rest += float(mi.group(2)) - k*M_OLD
            n += k
    return (total - n*M_NEW) / rest, n, rest


def total_mass(t):
    return sum(float(INERTIAL.search(b).group(2))
               for b in blocks(t) if b.startswith("<body ") and INERTIAL.search(b))


def process(path, out, total=MEASURED_TOTAL):
    """Replace the XL330s in path with HL-2915s, scale the rest to total, write to out, return a per-link report."""
    t = open(path, encoding="utf-8").read()
    S, _, _ = rest_scale(t, total)
    report = []
    new_parts = []
    for blk in blocks(t):
        mb = re.match(r'<body name="([a-z_0-9]+)"', blk)
        mi = INERTIAL.search(blk) if mb else None
        if not mi:
            new_parts.append(blk)
            continue
        name = mb.group(1)
        servos = servo_positions(blk)
        n = len(servos)

        c0 = nums(mi.group(1))
        m0 = float(mi.group(2))
        I0 = nums(mi.group(3))          # ixx iyy izz ixy ixz iyz, about c0

        # 1) remove the XL330s, get the mass / center of mass / inertia of "the rest" (about cr)
        mr = m0 - n*M_OLD
        cr = [(m0*c0[k] - M_OLD*sum(p[k] for p in servos)) / mr for k in range(3)]
        Ir = list(I0)
        for p in servos:
            a = pa(M_OLD, [p[k]-c0[k] for k in range(3)])
            for k in range(6):
                Ir[k] -= a[k] + (M_OLD*I_UNIT if k < 3 else 0.0)
        a = pa(mr, [cr[k]-c0[k] for k in range(3)])
        Ir = [Ir[k] - a[k] for k in range(6)]

        # 2) scale the rest to the measured total
        mr, Ir = mr*S, [x*S for x in Ir]

        # 3) add the HL-2915s, combine about the new center of mass c1
        m1 = mr + n*M_NEW
        c1 = [(mr*cr[k] + M_NEW*sum(p[k] for p in servos)) / m1 for k in range(3)]
        a = pa(mr, [cr[k]-c1[k] for k in range(3)])
        I1 = [Ir[k] + a[k] for k in range(6)]
        for p in servos:
            a = pa(M_NEW, [p[k]-c1[k] for k in range(3)])
            for k in range(6):
                I1[k] += a[k] + (M_NEW*I_UNIT if k < 3 else 0.0)

        new = ('<inertial pos="{:.7g} {:.7g} {:.7g}" mass="{:.6g}" '
               'fullinertia="{:.6g} {:.6g} {:.6g} {:.6g} {:.6g} {:.6g}"/>').format(
            c1[0], c1[1], c1[2], m1, *I1)
        blk = blk.replace(mi.group(0), new, 1)
        report.append((name, n, m0*1000, m1*1000, sum((c0[k]-c1[k])**2 for k in range(3))**0.5*1000))
        new_parts.append(blk)

    open(out, "w", encoding="utf-8").write("".join(new_parts))
    return report


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for f in FILES:
        rep = process(os.path.join(SRC_DIR, f), os.path.join(OUT_DIR, f))
        if f == FILES[0]:
            print(f"{'link':<20}{'servo':>5}{'old g':>10}{'new g':>10}{'CoM move mm':>12}")
            for n, k, a, b, d in rep:
                print(f"{n:<20}{k:>5}{a:>10.1f}{b:>10.1f}{d:>12.2f}")
            print()
        print(f"{f}: updated {len(rep)} links")

    t = open(os.path.join(SRC_DIR, FILES[0]), encoding="utf-8").read()
    S, n, rest = rest_scale(t)
    new_total = total_mass(open(os.path.join(OUT_DIR, FILES[0]), encoding="utf-8").read())
    print(f"\nservos {n} x {M_NEW*1000:.1f} g; non-servo parts {rest*1000:.1f} g x {S:.3f} = {rest*S*1000:.1f} g")
    print(f"whole robot mass: {total_mass(t)*1000:.1f} g -> {new_total*1000:.1f} g (measured {MEASURED_TOTAL*1000:.0f} g)")
