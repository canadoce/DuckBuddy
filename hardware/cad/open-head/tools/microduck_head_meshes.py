# /// script
# dependencies = ["mujoco", "numpy", "trimesh"]
# ///
"""Write the Microduck head and neck meshes in the head frame (X forward, Y left, Z up, mm).

Usage (from hardware/cad/open-head):
    uv run tools/microduck_head_meshes.py MJLAB_DIR reference/microduck

MJLAB_DIR is the microduck-simulator folder app/public/robot/mjlab, which holds
robot_allcollisions.xml and meshes/. The head frame is the MuJoCo jaw_soft body frame
remapped as forward = -z, left = y, up = x; its origin is on the head-roll servo axis.
Files are named <body>__<mesh>__<geom id>.stl.
"""

import sys
import tempfile
from pathlib import Path

import mujoco
import numpy as np
import trimesh

BODIES = {"jaw_soft", "yaw_roll_motion", "neck_pitch", "neck"}
# jaw_soft body axes -> head frame: forward = -z, left = y, up = x
TO_HEAD = np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=float)


def main(src, out):
    src, out = Path(src).resolve(), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    xml = (src / "robot_allcollisions.xml").read_text()
    xml = xml.replace('meshdir="assets"', f'meshdir="{src / "meshes"}"')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "robot.xml"
        path.write_text(xml)
        m = mujoco.MjModel.from_xml_path(str(path))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    hb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "jaw_soft")
    Rb, pb = d.xmat[hb].reshape(3, 3), d.xpos[hb]
    for g in range(m.ngeom):
        if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or m.geom_group[g] != 2:
            continue
        body = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, m.geom_bodyid[g])
        if body not in BODIES:
            continue
        mid = m.geom_dataid[g]
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mid)
        va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
        fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
        V, F = m.mesh_vert[va:va + vn], m.mesh_face[fa:fa + fn]
        world = V @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g]
        local = (world - pb) @ Rb  # jaw_soft body frame, metres
        tm = trimesh.Trimesh(local @ TO_HEAD.T * 1000.0, F, process=False)
        key = f"{body}__{name}__{g}"
        tm.export(out / f"{key}.stl")
        print(key, np.round(tm.bounds, 1).tolist())
    for j in ["head_roll", "head_yaw", "head_pitch", "neck_pitch"]:
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j)
        anchor = (d.xanchor[jid] - pb) @ Rb @ TO_HEAD.T * 1000.0
        axis = d.xaxis[jid] @ Rb @ TO_HEAD.T
        print(j, "anchor", np.round(anchor, 1), "axis", np.round(axis, 3))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
