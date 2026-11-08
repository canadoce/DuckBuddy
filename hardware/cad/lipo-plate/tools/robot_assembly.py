# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["mujoco", "numpy", "trimesh", "scipy"]
# ///
"""Write the whole robot, standing, with this fork's parts, as one GLB for the CAD viewer.

Run from hardware/cad/lipo-plate, after src/build_plate.py, ../open-head's and ../face-plate's
builds:

    uv run tools/robot_assembly.py [MJLAB_DIR]

It poses the `lipo` scene of tools/policy_poses.py (the robot model the policies train on, with
the LiPo plate, the pack, the BNO055 and its mount in place of the old plate and the NP-F970) in
its STAND keyframe, and swaps the model's head parts for this fork's: the open head shell and the
speaker (../open-head/tmp/open_head_review.glb), the face plate, the Robot HAT E1, the Orange Pi
Zero 3W, the camera, the ToF board and the LED (../face-plate/tmp/face_plate_review.glb), placed
by the head frame (the jaw_soft body, see ../open-head/tools/microduck_head_meshes.py). It writes
tmp/duckbuddy_assembly.glb, one node per part.
"""

import sys
from pathlib import Path

import mujoco
import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy_poses as pp  # noqa: E402

CAD = pp.ROOT.parent
OUT = pp.ROOT / "tmp/duckbuddy_assembly.glb"
# The model's head parts this fork replaces.
HEAD_REPLACED = {"top_head_shell", "face_part", "elec_rpi_robot_hat_pcb", "pcb__raspberry_pi_zero_2_w", "speaker",
                 "lens", "m12_lens_holder"}
HEAD_PARTS = [  # (review file, its top-level nodes to take)
    (CAD / "open-head/tmp/open_head_review.glb", {"open_head_shell", "speaker", "robot_hat_e1", "orange_pi_zero_3w",
                                                   "radxa_camera_8m_219", "sparkfun_mini_tof_vl53l5cx"}),
    (CAD / "face-plate/tmp/face_plate_review.glb", {"face_plate", "led_1w"}),
]
GLTF_TO_MM = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]) @ np.diag([1000.0, 1000.0, 1000.0, 1.0])
HEAD_TO_BODY = np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=float).T  # head frame axes -> jaw_soft body
COLOURS = {"open_head_shell": (235, 235, 230), "face_plate": (40, 40, 40), "speaker": (60, 60, 60)}


def pose(mat, pos):
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = mat.reshape(3, 3), pos
    return T


def main():
    mjlab = sys.argv[1] if len(sys.argv) > 1 else str(pp.DEFAULT_MJLAB)
    scene_xml = pp.ROOT / "tmp/mjcf_lipo/scene.xml"
    if not scene_xml.exists():  # written by tools/policy_poses.py; not rewritten here while it may be running
        scene_xml = pp.scene_with_meshes(mjlab, "lipo")
    m = mujoco.MjModel.from_xml_path(str(scene_xml))
    d = mujoco.MjData(m)
    mujoco.mj_resetDataKeyframe(m, d, mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, "STAND"))
    mujoco.mj_kinematics(m, d)
    d.qpos[2] -= min(d.geom_xpos[:, 2])  # roughly on the floor: only for the view
    mujoco.mj_kinematics(m, d)
    scene = trimesh.Scene()
    to_gltf = np.linalg.inv(GLTF_TO_MM)

    def add(mesh, name, rgba):
        mat = trimesh.visual.material.PBRMaterial(baseColorFactor=[int(c) for c in rgba], metallicFactor=0.0,
                                                  roughnessFactor=0.8)
        mesh.visual = trimesh.visual.TextureVisuals(material=mat)
        mesh.apply_transform(to_gltf)
        scene.add_geometry(mesh, node_name=name, geom_name=name)

    head = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "jaw_soft")
    count = {}
    for g in range(m.ngeom):
        if m.geom_group[g] != 2:  # visual geoms only
            continue
        body = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, m.geom_bodyid[g])
        if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH:
            mid = m.geom_dataid[g]
            name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, mid)
            if m.geom_bodyid[g] == head and name in HEAD_REPLACED:
                continue
            va, vn, fa, fn = m.mesh_vertadr[mid], m.mesh_vertnum[mid], m.mesh_faceadr[mid], m.mesh_facenum[mid]
            mesh = trimesh.Trimesh(m.mesh_vert[va:va + vn].copy(), m.mesh_face[fa:fa + fn].copy(), process=False)
        elif m.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX:
            name = "box"
            mesh = trimesh.creation.box(extents=2 * m.geom_size[g])
        else:
            continue
        mesh.apply_transform(pose(d.geom_xmat[g], d.geom_xpos[g]))
        mesh.apply_scale(1000.0)
        rgba = m.mat_rgba[m.geom_matid[g]] if m.geom_matid[g] >= 0 else m.geom_rgba[g]
        count[name] = count.get(name, 0) + 1
        add(mesh, f"{body}/{name}.{count[name]}", (np.clip(rgba, 0, 1) * 255).astype(np.uint8))
    # This fork's head parts, from the head frame (mm) to the world (mm).
    H = pose(d.xmat[head], d.xpos[head] * 1000) @ np.block([[HEAD_TO_BODY, np.zeros((3, 1))], [np.zeros((1, 3)), 1]])
    for path, keep in HEAD_PARTS:
        review = trimesh.load(path)
        for node in review.graph.nodes_geometry:
            top = node.split("/")[0]
            if top not in keep:
                continue
            T, gname = review.graph[node]
            mesh = review.geometry[gname].copy()
            mesh.apply_transform(H @ GLTF_TO_MM @ T)
            rgba = COLOURS.get(top)
            if rgba is None:
                mat = getattr(mesh.visual, "material", None)
                base = getattr(mat, "baseColorFactor", None)
                if base is not None:
                    rgba = tuple(int(c) for c in base[:3])
                else:
                    c = mesh.visual.face_colors if mesh.visual.kind == "face" else None
                    rgba = tuple(c[0][:3]) if c is not None else (120, 120, 120)
            add(mesh, f"head/{node}", (*rgba, 255))
    scene.export(OUT)
    print(f"wrote {OUT}: {len(scene.geometry)} parts")


if __name__ == "__main__":
    main()
