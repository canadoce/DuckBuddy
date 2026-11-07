# /// script
# requires-python = ">=3.10"
# dependencies = ["mujoco>=3.1", "numpy", "trimesh"]
# ///
"""The whole robot at its zero pose, with the servo dummies in their own colour: a build guide.

The robot's model (hardware/rev-a/mjcf/robot_allcollisions.xml) names its meshes but this repository
does not hold them; pass the folder that does (the Microduck `assets` folder):

    uv run hardware/cad/servo-dummy/layout/robot_layout.py <mesh folder> [out.glb]

It writes a GLB (default: robot_layout.glb beside this script), in mm, one node per part:
  - printed and bought parts: light grey;
  - servos: dark grey, named "servo <joint>";
  - dummies (DUMMY_JOINTS): magenta, named "DUMMY <joint>".
Open it with `cad viewer FILE` (text-to-cad) or any glTF viewer.

A servo drives the joint whose axis is its output shaft: seen along the axis it is 29 mm long, horn to
horn, and the middle of each horn face is on the axis; the nearest such servo along the axis wins (the
left and right legs' axes line up at the zero pose). Every joint must get its own servo. The model
has no mouth joint (the jaw is fixed in it), so the mouth gets the one servo left over.
"""
import os
import sys

import mujoco
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
XML = os.path.join(REPO, "hardware", "rev-a", "mjcf", "robot_allcollisions.xml")
OUT = os.path.join(HERE, "robot_layout.glb")
SERVO_MESH = "xl330"
# The joints that get a printed dummy while their servos are replaced: both hip yaws and hip rolls.
DUMMY_JOINTS = {"left_hip_yaw", "left_hip_roll", "right_hip_yaw", "right_hip_roll"}
PART = [0.80, 0.80, 0.80, 1.0]     # light grey
SERVO = [0.18, 0.18, 0.20, 1.0]    # dark grey
DUMMY = [1.00, 0.00, 0.80, 1.0]    # magenta
VISUAL_GROUP = 2
HORN_TO_HORN = 29.0   # mm, the servo along its shaft

# JOINT_NAMES order (duck-control): left leg, neck and head, right leg.
JOINTS = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]


def geom_mesh(m, d, g):
    """The mesh of visual geom g, placed in the world frame, in mm."""
    mid = m.geom_dataid[g]
    v0, nv = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
    f0, nf = m.mesh_faceadr[mid], m.mesh_facenum[mid]
    verts = m.mesh_vert[v0:v0 + nv] @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g]
    faces = m.mesh_face[f0:f0 + nf]
    return trimesh.Trimesh(verts * 1000.0, faces, process=False)


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    spec = mujoco.MjSpec.from_file(XML)
    spec.meshdir = os.path.abspath(sys.argv[1])
    out = os.path.abspath(sys.argv[2]) if len(sys.argv) == 3 else OUT
    m = spec.compile()
    d = mujoco.MjData(m)
    mujoco.mj_kinematics(m, d)

    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) for j in range(m.njnt)]
    missing = [j for j in JOINTS if j != "mouth" and j not in names]
    assert not missing, f"joints not in the model: {missing}"

    servo_mesh = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_MESH, SERVO_MESH)
    visual = [g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH
              and m.geom_group[g] == VISUAL_GROUP]
    servos = [g for g in visual if m.geom_dataid[g] == servo_mesh]
    assert len(servos) == len(JOINTS), f"{len(servos)} servo meshes, expected {len(JOINTS)}"

    # servo -> joint: the servo's output shaft is the joint axis. Seen along the axis, the servo is
    # 29 mm long (horn to horn), and the middle of each horn face lies on the axis.
    verts = {g: geom_mesh(m, d, g).vertices / 1000.0 for g in servos}

    def cost(g, a, u):
        r = verts[g] - a
        t = r @ u
        if abs((t.max() - t.min()) * 1000.0 - HORN_TO_HORN) > 0.5:
            return np.inf      # not turned this way
        off = 0.0
        for face in (t <= t.min() + 0.0005, t >= t.max() - 0.0005):
            c = r[face].mean(axis=0)
            off = max(off, np.linalg.norm(c - (c @ u) * u))
        return off * 1000.0

    def gap(g, a, u):
        """How far along the axis the servo is from the joint (0 when the joint is inside it):
        the left and right legs' axes line up at the zero pose, the near servo is the one."""
        t = (verts[g] - a) @ u
        return max(t.min(), -t.max(), 0.0) * 1000.0

    pick = {}
    for name in JOINTS:
        if name == "mouth":
            continue
        j = names.index(name)
        a, u = d.xanchor[j], d.xaxis[j] / np.linalg.norm(d.xaxis[j])
        g = min(servos, key=lambda g: (round(cost(g, a, u), 1), gap(g, a, u)))
        pick[name] = (g, cost(g, a, u))
        assert gap(g, a, u) < 10.0, f"{name}: nearest servo is {gap(g, a, u):.1f} mm along the axis"
    used = [g for g, _ in pick.values()]
    assert len(set(used)) == len(JOINTS) - 1, "two joints matched the same servo: " + str(pick)
    (left,) = [g for g in servos if g not in used]
    pick["mouth"] = (left, 0.0)
    used.append(left)
    for name, (g, c) in pick.items():
        assert c < 1.0, f"{name}: nearest servo horn is {c:.1f} mm off its axis"

    scene = trimesh.Scene()

    def add(mesh, name, rgba):
        # glTF is +Y up, the robot's model +Z up: (x, y, z) -> (x, z, -y)
        mesh.vertices = mesh.vertices[:, [0, 2, 1]] * [1.0, 1.0, -1.0]
        mesh.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            name=name, baseColorFactor=rgba, metallicFactor=0.0, roughnessFactor=0.6))
        scene.add_geometry(mesh, node_name=name, geom_name=name)

    for name in JOINTS:
        g = pick[name][0]
        dummy = name in DUMMY_JOINTS
        add(geom_mesh(m, d, g), ("DUMMY " if dummy else "servo ") + name, DUMMY if dummy else SERVO)
    by_body = {}
    for g in visual:
        if g not in used:
            by_body.setdefault(m.geom_bodyid[g], []).append(geom_mesh(m, d, g))
    for b, meshes in by_body.items():
        add(trimesh.util.concatenate(meshes), mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b), PART)
    scene.export(out)
    for name in JOINTS:
        print(f"{name:16s} {'DUMMY' if name in DUMMY_JOINTS else 'servo'}")
    print(f"{out}: {len(by_body)} bodies of parts, {len(JOINTS)} servo places")


if __name__ == "__main__":
    main()
