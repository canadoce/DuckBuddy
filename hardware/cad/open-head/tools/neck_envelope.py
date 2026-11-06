# /// script
# dependencies = ["numpy", "trimesh"]
# ///
"""Height maps of the parts under the head shell, used to pick the deck heights.

Usage (from hardware/cad/open-head):
    uv run tools/neck_envelope.py reference/microduck reference/envelope.npz

Writes, on a 1 mm grid in head X and Y, the highest Z reached by
- "moving": the neck parts that move under the head, swept by head roll +-25 deg;
- "fixed": the servos and the motor support fixed in the head.
checks/fit_check.py does the full 3D sweep (roll and yaw); this map is for planning.
"""

import sys
from pathlib import Path

import numpy as np
import trimesh

RES = 1.0
XS = np.arange(-45, 85, RES)
YS = np.arange(-55, 55, RES)


def points(f):
    m = trimesh.load(f)
    return m.subdivide_to_size(1.0).vertices if len(m.faces) < 400000 else m.vertices


def height_map(P):
    H = np.full((len(YS), len(XS)), -np.inf)
    i = np.floor((P[:, 0] - XS[0]) / RES).astype(int)
    j = np.floor((P[:, 1] - YS[0]) / RES).astype(int)
    ok = (i >= 0) & (i < len(XS)) & (j >= 0) & (j < len(YS))
    np.maximum.at(H, (j[ok], i[ok]), P[ok, 2])
    return H


def main(microduck, out):
    files = sorted(Path(microduck).glob("*.stl"))
    moving = [f for f in files if f.name.split("__")[0] in ("yaw_roll_motion", "neck_pitch", "neck")]
    fixed = [f for f in files if any(k in f.name for k in ("jaw_soft__xl330", "motor_support", "configuration_default"))]
    Pm = np.vstack([points(f) for f in moving])
    Pf = np.vstack([points(f) for f in fixed])
    Hm = np.full((len(YS), len(XS)), -np.inf)
    for a in np.radians(np.arange(-25, 25.01, 0.5)):
        c, s = np.cos(a), np.sin(a)
        R = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
        Hm = np.maximum(Hm, height_map(Pm @ R.T))
    Hf = height_map(Pf)
    np.savez(out, xs=XS, ys=YS, moving=Hm, fixed=Hf)
    for y0 in range(-30, 40, 10):
        sel = (YS >= y0) & (YS < y0 + 10)
        print(f"y {y0}..{y0 + 10}: moving max {np.max(Hm[sel]):.1f}, fixed max {np.max(Hf[sel]):.1f}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
