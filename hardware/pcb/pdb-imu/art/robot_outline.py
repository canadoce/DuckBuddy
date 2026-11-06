# /// script
# dependencies = ["mujoco", "numpy", "pillow"]
# ///
"""Render the microduck robot from its MuJoCo model for the board art.

The meshes are not in this repository; they come with microduck_rl
(src/mjlab_microduck/robot/microduck/assets). The robot is drawn in the SIT
keyframe with the head lifted, in isometric view (orthographic, seen from the
front left and 35.26 degrees above), by MuJoCo's own renderer, so hidden
surfaces are handled exactly.

Run (from hardware/pcb/pdb-imu):
  uv run art/robot_outline.py <path to microduck assets folder>
Writes art/src/microduck_iso_parts.png: one gray level per part, 0 = background.
The levels are listed in PARTS below; make_art.py reads them.

NECK_PITCH, HEAD_PITCH (rad) and AZIMUTH (deg) override the pose and view.
"""
import os, pathlib, shutil, sys, tempfile
import numpy as np
import mujoco
from PIL import Image

HERE = pathlib.Path(__file__).parent
MJCF = HERE.parent.parent.parent / "rev-a" / "mjcf"
assets = pathlib.Path(sys.argv[1]).resolve()

# Gray level of each part in the output image.
PARTS = {"shell": 10, "face": 20, "eye": 30, "jaw": 40, "neck": 50, "trunk": 60, "left_leg": 70, "right_leg": 80}
FACE_MESHES = {
    "top_head_shell": "shell", "bottom_head_shell": "shell",
    "face_part": "face", "lens": "eye", "m12_lens_holder": "eye", "noenoeil": "eye",
    "jaw": "jaw", "jaw_soft": "jaw", "soft_mouth_top": "jaw",
}
SIZE = 2400  # px, square

with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    for f in MJCF.glob("*.xml"):
        shutil.copy(f, tmp / f.name)
    (tmp / "assets").symlink_to(assets)
    m = mujoco.MjModel.from_xml_path(str(tmp / "scene.xml"))

m.vis.global_.offwidth = m.vis.global_.offheight = SIZE
m.vis.global_.orthographic = 1
d = mujoco.MjData(m)
mujoco.mj_resetDataKeyframe(m, d, mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_KEY, "SIT"))
# SIT keeps the head pitched down (head_pitch 1.6 rad); lift it so the robot looks ahead.
for joint, angle in {"neck_pitch": float(os.environ.get("NECK_PITCH", 0.5)),
                     "head_pitch": float(os.environ.get("HEAD_PITCH", 0.0))}.items():
    d.qpos[m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, joint)]] = angle
mujoco.mj_forward(m, d)

# Part of each geom: head parts by mesh name, the rest by which branch of the body tree it is on.
trunk = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
head_body = m.jnt_bodyid[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "head_pitch")]
def joint_names(b):
    return [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) or "" for j in range(m.njnt) if m.jnt_bodyid[j] == b]
def branch(b):
    chain = [b]
    while chain[-1] not in (trunk, 0):
        chain.append(m.body_parentid[chain[-1]])
    if head_body in chain:
        return "head"
    names = " ".join(n for c in chain for n in joint_names(c))
    if "left_" in names:
        return "left_leg"
    if "right_" in names:
        return "right_leg"
    return "neck" if "neck" in names else "trunk"


geom_level = np.zeros(m.ngeom, np.uint8)
for g in range(m.ngeom):
    if m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or m.geom_group[g] == 3:
        m.geom_rgba[g][3] = 0  # floor, collision shapes: not drawn
        continue
    part = branch(m.geom_bodyid[g])
    if part == "head":
        part = FACE_MESHES.get(mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, m.geom_dataid[g]), "shell")
    geom_level[g] = PARTS[part]

# Isometric camera, looking at the middle of the robot.
drawn = [g for g in range(m.ngeom) if geom_level[g]]
lo = np.min([d.geom_xpos[g] for g in drawn], axis=0)
hi = np.max([d.geom_xpos[g] for g in drawn], axis=0)
cam = mujoco.MjvCamera()
cam.type = mujoco.mjtCamera.mjCAMERA_FREE
cam.lookat[:] = (lo + hi) / 2
cam.azimuth = 180 + float(os.environ.get("AZIMUTH", 45))  # camera sits in front (+x) and to the left (+y)
cam.elevation = -35.264
cam.distance = 2.0
m.vis.global_.fovy = 0.32  # orthographic: height of the view, in metres

r = mujoco.Renderer(m, SIZE, SIZE)
opt = mujoco.MjvOption()
for i in range(len(opt.geomgroup)):
    opt.geomgroup[i] = 1
r.update_scene(d, camera=cam, scene_option=opt)
r.enable_segmentation_rendering()
seg = r.render()
ids, types = seg[..., 0], seg[..., 1]
img = np.where((types == mujoco.mjtObj.mjOBJ_GEOM) & (ids >= 0), geom_level[np.clip(ids, 0, m.ngeom - 1)], 0).astype(np.uint8)

# Crop to the robot.
ys, xs = np.nonzero(img)
img = img[max(ys.min() - 10, 0):ys.max() + 11, max(xs.min() - 10, 0):xs.max() + 11]
(HERE / "src").mkdir(exist_ok=True)
Image.fromarray(img).save(HERE / "src" / "microduck_iso_parts.png")
print("image", img.shape[1], "x", img.shape[0], "px; parts:", sorted({k for k, v in PARTS.items() if (img == v).any()}))
