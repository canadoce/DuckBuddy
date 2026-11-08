"""Meshes of the head in the head frame, shared by the shell generator and the fit check.

Head frame: X forward, Y to the robot's left, Z up, in mm (see head_params.py).
Plain Python (numpy, trimesh); no CAD kernel.
"""

import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh

import head_params as p

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"
REF = ROOT / "reference"
PARTS_GLB = TMP / "parts.glb"

# glTF is in metres with Y up; the head frame is in mm with Z up.
GLTF_TO_HEAD = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]) @ np.diag([1000.0, 1000.0, 1000.0, 1.0])
HEAD_TO_GLTF = np.linalg.inv(GLTF_TO_HEAD)

# Reference meshes by role.
FIXED_PARTS = {
    "jaw_servo": "jaw_soft__xl330__44",
    "motor_support": "motor_support",
    "side_bearing": "seeed_bearing__configuration_default",
    "jaw": "jaw_soft__jaw__54",
    "soft_mouth_top": "soft_mouth_top",
}
ROLL_SERVO = "jaw_soft__xl330__49"
ABOVE_YAW = "yaw_roll_motion__"           # moves with head roll
BELOW_YAW = ("neck_pitch__", "neck__")   # moves with head roll and head yaw
YAW_AXIS_X = 17.9                         # head-yaw axis: vertical through X 17.9, Y 0 (zero roll)
ROLL_RANGE_DEG = 25.0
YAW_RANGE_DEG = 170.0


def build_parts():
    """Build the parts assembly (HAT, speaker, Pi) with the CAD server and export it to tmp/parts.glb."""
    TMP.mkdir(exist_ok=True)
    out = subprocess.run(["cad", "run", "src/assembly.py"], cwd=ROOT, capture_output=True, text=True)
    ids = re.findall(r"id: ([0-9a-f-]{36})", out.stdout + out.stderr)
    if out.returncode or not ids:
        sys.exit(out.stdout + out.stderr)
    subprocess.run(["cad", "export", ids[-1], str(PARTS_GLB)], cwd=ROOT, check=True, capture_output=True)


def load_parts(path=PARTS_GLB):
    """The parts GLB as head-frame meshes, grouped: hat_board, hat_parts, speaker, pi, pi_zone, camera, tof, led."""
    scene = trimesh.load(path)
    groups = {"hat_board": [], "hat_parts": [], "speaker": [], "pi": [], "pi_zone": [], "camera": [], "tof": [], "led": []}
    for node in scene.graph.nodes_geometry:
        T, gname = scene.graph[node]
        m = scene.geometry[gname].copy()
        m.apply_transform(GLTF_TO_HEAD @ T)
        name = node.lower()
        if "camera" in name:
            groups["camera"].append(m)
        elif "tof_" in name:
            groups["tof"].append(m)
        elif "led_1w" in name:
            groups["led"].append(m)
        elif "speaker" in name:
            groups["speaker"].append(m)
        elif "dupont" in name:
            groups["pi_zone"].append(m)
        elif "pi_board" in name or "cooling_shield" in name:
            groups["pi"].append(m)
        elif "robot_hat_pcb" in name:
            groups["hat_board"].append(m)
        else:
            groups["hat_parts"].append(m)
    parts = {k: trimesh.util.concatenate(v) for k, v in groups.items() if v}
    sb = parts["speaker"].bounds
    assert abs(sb[0][2] - 18.5) < 0.05 and sb[0][1] > 0, f"unexpected speaker placement {sb}"
    return parts


def ref(name):
    """A reference mesh: a Microduck part by (part of) its name, or a DuckBuddy part."""
    files = sorted((REF / "microduck").glob(f"*{name}*.stl")) or [REF / f"{name}.stl"]
    return trimesh.util.concatenate([trimesh.load(f) for f in files])


FACE_PLATE_STL = ROOT.parent / "face-plate" / "STL" / "face_plate.stl"  # print frame


def plate_print_matrix():
    """4x4 transform from the head frame to the face plate's print frame (head_params)."""
    M = np.eye(4)
    M[:3, :3] = np.array(p.PLATE_PRINT_R)
    M[:3, 3] = np.array(p.PLATE_PRINT_T)
    return M


def face_plate(path=FACE_PLATE_STL):
    """The face plate in the head frame: the plate for the Radxa camera (../face-plate), or the
    DuckBuddy reference plate when it has not been made."""
    if not path.exists():
        return ref("face_part_duckbuddy")
    m = trimesh.load(path)
    m.apply_transform(np.linalg.inv(plate_print_matrix()))
    return m


def moving_meshes():
    above = [trimesh.load(f) for f in sorted((REF / "microduck").glob(f"{ABOVE_YAW}*.stl"))]
    below = [trimesh.load(f) for p in BELOW_YAW for f in sorted((REF / "microduck").glob(f"{p}*.stl"))]
    return trimesh.util.concatenate(above), trimesh.util.concatenate(below)


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_z(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def sweep(above_pts, below_pts, roll_step=1.0, yaw_step=15.0, keep=None):
    """Yield (roll_deg, points) of the moving parts over the head-roll and head-yaw ranges.

    keep(points) -> mask, applied to each pose's points before they are yielded.
    """
    c0 = np.array([YAW_AXIS_X, 0.0, 0.0])
    yaws = np.radians(np.arange(-YAW_RANGE_DEG, YAW_RANGE_DEG + 0.01, yaw_step))
    for roll in np.arange(-ROLL_RANGE_DEG, ROLL_RANGE_DEG + 0.01, roll_step):
        Rr = rot_x(np.radians(roll))
        clouds = [above_pts @ Rr.T] + [((below_pts - c0) @ rot_z(y).T + c0) @ Rr.T for y in yaws]
        P = np.vstack(clouds)
        if keep is not None:
            P = P[keep(P)]
        yield roll, P


def plain_material(rgba):
    """A one-colour material for a review GLB (the viewer and snapshots ignore vertex colours).

    rgba is sRGB 0-255, as a colour is picked; glTF wants the base colour in linear light, so it
    is converted (passing sRGB as it is washes every colour out)."""
    c = np.asarray(rgba[:3], float) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    factor = [*lin.tolist(), (rgba[3] if len(rgba) > 3 else 255) / 255.0]
    mat = trimesh.visual.material.PBRMaterial(baseColorFactor=factor, metallicFactor=0.0, roughnessFactor=0.7)
    return trimesh.visual.TextureVisuals(material=mat)


# Review colours (sRGB): the open head shell lilac, the face plate grey, the bottom head shell
# (the mouth part) orange.
REVIEW_SKELETON = (176, 132, 222, 255)
REVIEW_FACE = (128, 134, 144, 255)
REVIEW_MOUTH = (232, 106, 23, 255)
REVIEW_EYE = (200, 204, 210, 255)


def surface_points(m, spacing=0.25, cap=400000):
    """Points on a mesh surface about `spacing` apart, plus its vertices."""
    n = int(min(cap, max(2000, m.area / spacing ** 2)))
    return np.vstack([m.sample(n), m.vertices])
