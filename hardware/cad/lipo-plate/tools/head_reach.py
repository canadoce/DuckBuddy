# /// script
# dependencies = ["mujoco", "numpy", "scipy", "trimesh", "rtree", "manifold3d"]
# ///
"""Map how low the head and the neck reach inside the trunk, for placing parts on the hip servos.

Run from hardware/cad/lipo-plate, after tools/policy_poses.py:

    uv run tools/head_reach.py [MJLAB_DIR]

Over every pose of the LiPo plate's policy runs it takes the head's and the neck's surface points
in the trunk frame and prints, on a 2 mm grid over X -24 to 14 and Y -16 to 16, the lowest Z they
reach above Z 20 (blank: never below Z 45). The simulation has no contact between the neck and
the shells, so some poses put the neck into them; a pose where a point of the head or the neck is
more than fit_check.SHELL_DEPTH (1 mm) deep inside a shell is one the real robot cannot reach.
The map is printed for all poses and for the reachable ones, and saved as tmp/head_reach.npz.
"""

import sys
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "checks"))
import fit_check as fc  # noqa: E402

X = np.arange(-24, 15, 2.0)
Y = np.arange(-16, 17, 2.0)


def lowest(P, low):
    P = P[(P[:, 2] > 20) & (P[:, 2] < 45) & (P[:, 0] > X[0] - 1) & (P[:, 0] < X[-1] + 1) & (np.abs(P[:, 1]) < Y[-1] + 1)]
    i = np.clip(np.round((P[:, 0] - X[0]) / 2).astype(int), 0, len(X) - 1)
    j = np.clip(np.round((P[:, 1] - Y[0]) / 2).astype(int), 0, len(Y) - 1)
    np.minimum.at(low, (i, j), P[:, 2])


def main():
    mjlab = Path(sys.argv[1]) if len(sys.argv) > 1 else fc.DEFAULT_MJLAB
    m = fc.load_model(mjlab)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    tb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    clouds = fc.body_clouds(m, d, fc.subtree(m, fc.HEAD), 1.0)
    rec = np.load(fc.bp.TMP / "policy_poses_lipo.npz")
    adr = [fc.joint(m, str(n))[0] for n in rec["joints"]]
    shells = fc.ShellDepth()
    low = {"all": np.full((len(X), len(Y)), np.inf), "reachable": np.full((len(X), len(Y)), np.inf)}
    through = total = 0
    for skill in dict.fromkeys(rec["scores"][:, 0]):
        for row in rec[skill][::2]:
            d.qpos[:] = m.qpos0
            d.qpos[adr] = row
            mujoco.mj_kinematics(m, d)
            Rt, pt = d.xmat[tb].reshape(3, 3), d.xpos[tb]
            P = np.vstack([(c @ d.xmat[b].reshape(3, 3).T + d.xpos[b] - pt) @ Rt for b, c in clouds.items()]) * 1000
            hit = shells.deep(P)
            total += 1
            through += bool(hit)
            lowest(P, low["all"])
            if not hit:
                lowest(P, low["reachable"])
    print(f"{through} of {total} poses put the head or the neck more than {fc.SHELL_DEPTH:.0f} mm into the shells")
    for k in low:
        print(f"\nlowest Z of the head and neck, {k} poses (rows X, columns Y)")
        print("   X\\Y " + "".join(f"{y:5.0f}" for y in Y))
        for i, x in enumerate(X):
            print(f"{x:6.0f} " + "".join("     " if not np.isfinite(v) else f"{v:5.1f}" for v in low[k][i]))
    np.savez(fc.bp.TMP / "head_reach.npz", x=X, y=Y, **low)


if __name__ == "__main__":
    main()
