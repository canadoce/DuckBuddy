# /// script
# dependencies = ["mujoco", "numpy", "trimesh"]
# ///
"""Write the Microduck trunk meshes in the trunk frame (X forward, Y left, Z up, mm).

Usage (from hardware/cad/lipo-plate):
    uv run tools/trunk_meshes.py MJLAB_DIR reference

MJLAB_DIR is the microduck-simulator folder app/public/robot/mjlab, which holds
robot_allcollisions.xml and meshes/. The trunk frame is the MuJoCo trunk_base body frame,
scaled to mm. Only the parts fixed to the trunk are written, as <mesh>__<geom id>.stl.
The IMU site of the model is printed.
"""

import sys
import tempfile
from pathlib import Path

import mujoco
import numpy as np
import trimesh


def load(src):
    xml = (Path(src) / "robot_allcollisions.xml").read_text()
    xml = xml.replace('meshdir="assets"', f'meshdir="{Path(src).resolve() / "meshes"}"')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "robot.xml"
        path.write_text(xml)
        return mujoco.MjModel.from_xml_path(str(path))


def main(src, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    m = load(src)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    tb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    Rb, pb = d.xmat[tb].reshape(3, 3), d.xpos[tb]
    for g in range(m.ngeom):
        if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or m.geom_group[g] != 2 or m.geom_bodyid[g] != tb:
            continue
        mid = m.geom_dataid[g]
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mid)
        va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
        fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
        world = m.mesh_vert[va:va + vn] @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g]
        tm = trimesh.Trimesh((world - pb) @ Rb * 1000.0, m.mesh_face[fa:fa + fn], process=False)
        tm.export(out / f"{name}__{g}.stl")
        print(f"{name}__{g}", np.round(tm.bounds, 1).tolist())
    s = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "imu")
    print("imu site", np.round((d.site_xpos[s] - pb) @ Rb * 1000.0, 2).tolist())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
