# /// script
# dependencies = ["mujoco", "numpy", "scipy", "trimesh", "rtree", "manifold3d"]
# ///
"""Quick check of the BNO055 and its mount against the head and the neck only.

Run from hardware/cad/lipo-plate, after `uv run src/build_plate.py`:

    uv run checks/neck_check.py [MJLAB_DIR]

The BNO055 and its mount are closed in by the shells, the servos and the plate, so after a change
to them only the head and the neck can come near. This runs that part of checks/fit_check.py
alone: the head and the neck in every 2nd pose of the LiPo plate's policy runs (poses that put them
more than 1 mm into the shells left out, as there), against the BNO055 and its mount, with the
same 3 mm margin. It does not replace the full check: run that before printing a bigger change.
"""

import sys
from pathlib import Path

import mujoco
import numpy as np
import trimesh
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_check as fc  # noqa: E402


def main():
    mjlab = Path(sys.argv[1]) if len(sys.argv) > 1 else fc.DEFAULT_MJLAB
    m = fc.load_model(mjlab)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    parts = fc.bp.load_parts()
    target = trimesh.util.concatenate([trimesh.load(fc.bp.TMP / "imu_mount.stl"), parts["bno055_pcb"],
                                       parts["bno055_parts"], parts["qwiic_plug"]])
    tree = cKDTree(fc.pts(target, 0.3))
    rec = np.load(fc.bp.TMP / "policy_poses_lipo.npz")
    names = [str(n) for n in rec["joints"]]
    adr = [fc.joint(m, n)[0] for n in names]
    tb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    clouds = fc.body_clouds(m, d, fc.subtree(m, fc.HEAD), 1.2)
    shells = fc.ShellDepth()
    fails = []
    for skill in dict.fromkeys(rec["scores"][:, 0]):
        best, at, unreal, q = np.inf, None, 0, rec[skill][::2]
        for row in q:
            d.qpos[:] = m.qpos0
            d.qpos[adr] = row
            mujoco.mj_kinematics(m, d)
            Rt, pt = d.xmat[tb].reshape(3, 3), d.xpos[tb]
            H = np.vstack([(c @ d.xmat[b].reshape(3, 3).T + d.xpos[b] - pt) @ Rt * 1000 for b, c in clouds.items()])
            dist, j = tree.query(H, distance_upper_bound=min(best, 30.0), workers=-1)
            k = np.argmin(dist)
            if dist[k] < best:
                if shells.deep(H):
                    unreal += 1
                    continue
                best, at = dist[k], np.round(H[k], 1).tolist()
        bad = best < fc.MOVING_MARGIN
        print(f"  {skill:9s} head/neck to BNO055 + mount {best:5.2f} mm (need {fc.MOVING_MARGIN}) at {at}"
              + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"{skill}: {best:.2f} mm")
    print("RESULT:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
