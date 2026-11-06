# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["mujoco", "onnxruntime", "numpy", "pillow", "imageio", "imageio-ffmpeg", "trimesh",
#                 "better-actuator-models @ git+https://github.com/Rhoban/bam@62bd8ce12154340be97e06f7f41a0ca8f116d967"]
# ///
"""Run the HL-2915 policies with the old battery and with the LiPo plate, and record their poses.

Run from hardware/cad/lipo-plate:

    uv run tools/policy_poses.py [--plate stock|lipo|both] [MJLAB_DIR]

It runs the walk, stand-up, sit/stand and roulade policies of training/policies in the BAM
simulation (training/bam/sim_hl2915.py), each under the five stress conditions of
training/bam/stress_hl2915.py, with robotd's target low-pass and 0.35 deg of gear play, as
training/policies/README.md tests them. The stand-up starts from every lying pose. It prints
each skill's score (as training/bam/eval_skills_hl2915.py scores it; for the walk, falls and
distance) and writes every control tick's 14 joint angles (rad, in POLICY_JOINTS order), trunk
height and gravity to tmp/policy_poses_<plate>.npz.

The scene is hardware/rev-a/mjcf/scene.xml with the Microduck meshes of MJLAB_DIR (the
microduck-simulator folder app/public/robot/mjlab, default: the one next to this repository).
`stock` is the model as the policies were trained: the NP-F970 on the old plate. `lipo` takes the
NP-F970 out of the collision model and puts in boxes for the largest LiPo, the cup, the pad, the
rib, the plate's lower part and the BNO055 with its plug, so the legs and the floor meet the new
shape. It also changes the trunk's mass (`lipo_trunk_inertial`) and shows the plate, the pack and
the board in place of the old plate and the NP-F970 (for videos, tools/policy_videos.py).
"""

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parents[2]
BAM = REPO / "training/bam"
sys.path.insert(0, str(BAM))

POLICIES = REPO / "training/policies"
WALK = POLICIES / "hl2915_walk_v6lp_slip_3999.onnx"
SKILL_POLICIES = {"standup": POLICIES / "hl2915_standup_v4bl_5999.onnx",
                  "sitstand": POLICIES / "hl2915_sitstand_v4bl_3999.onnx",
                  "roulade": POLICIES / "hl2915_roulade_v4bl_6999.onnx"}
WALK_SPEEDS = (0.2, 0.3)
WALK_S = 8.0
BACKLASH = "0.35"
DEFAULT_MJLAB = REPO.parent / "microduck-simulator/app/public/robot/mjlab"
NP_F970_VISUAL = '<geom type="mesh" class="visual" pos="-0.0359693 0 -0.00385049" ' \
                 'quat="0.00617059 0.70708 -0.70708 -0.00617059" mesh="np_f970" material="np_f970_material"/>'
PLATE_VISUAL = '<geom type="mesh" class="visual" pos="0.004 -0 -0.0175215" quat="0.707107 -0 0 0.707107" ' \
               'mesh="power_support" material="power_support_material"/>'
TRUNK_INERTIAL = '<inertial pos="-0.01945772 -2.407926e-05 0.003765416" mass="0.206214" ' \
                 'fullinertia="0.000125285 0.000155157 0.00013248 5.01721e-08 -2.4107e-05 1.17083e-07"/>'
# The trunk's mass in the model (hardware/rev-a/mjcf/mjcf_mass.py) holds the battery the robot was
# weighed with, a 3S 1500 mAh LiPo of 119.6 g, in the NP-F970's place (its box, mm), and the old
# plate. The LiPo plate's trunk takes them out and puts in the OVONIC pack (nominal size, on the
# pad), the new plate and the BNO055 with its plug and the end of its cable.
OLD_BATTERY = (0.1196, (-46.8, -25.1, -19.3, 19.3, -39.4, 31.7))
NEW_BATTERY_KG = 0.139
PETG_KG_M3 = 1270.0  # the plates are 1.2 to 3.6 mm thick: walls all through, taken as solid
BNO055_KG = 0.003
NP_F970_COLLISION = '<geom type="mesh" class="collision" pos="-0.0359693 0 -0.00385049" ' \
                    'quat="0.00617059 0.70708 -0.70708 -0.00617059" mesh="np_f970" material="np_f970_material"/>'


def lipo_boxes():
    """Collision boxes of the LiPo plate's new shape, in the trunk frame (mm): (x0, x1, y0, y1, z0, z1)."""
    sys.path.insert(0, str(ROOT / "src"))
    import plate_params as p

    y0, z0 = p.BNO_CENTER
    w, h = p.BNO_BOARD
    xb = p.CUP_IN_X - p.LIP_T
    x_pcb = p.PLATE_FRONT_X + p.STANDOFF_H
    return {
        "lipo": p.lipo_box(p.LIPO_TOL),
        "cup": (xb, p.PLATE_BACK_X, -p.PAD_Y, p.PAD_Y, p.PLATE_BOTTOM_Z, p.FLOOR_TOP_Z + p.LIP_H),
        "pad": (p.REST_X, p.PLATE_BACK_X, -p.PAD_Y, p.PAD_Y, p.PLATE_BOTTOM_Z, p.CHANNEL_Z1 + p.CHANNEL_WALL),
        "rib": (p.REST_X, p.PLATE_BACK_X, -p.RIB_Y, p.RIB_Y, *p.RIB_Z),
        "plate_lower": (p.PLATE_BACK_X, p.PLATE_FRONT_X, -p.PLATE_EDGE_Y, p.PLATE_EDGE_Y, p.PLATE_BOTTOM_Z, -40.0),
        "bno055": (p.PLATE_FRONT_X, x_pcb + p.BNO_PARTS_H, y0 - w / 2, y0 + w / 2, z0 - h / 2, z0 + h / 2),
        "qwiic": (x_pcb + p.PCB_T, x_pcb + p.PCB_T + p.QWIIC_H, y0 - p.QWIIC_W / 2, y0 + p.QWIIC_W / 2,
                  z0 - h / 2 - p.QWIIC_OUT, z0 - h / 2),
    }


def inertia_about_origin(m, c, I):
    """3x3 inertia (kg m2) of mass m with centre c (m) and inertia I about c, taken about the origin."""
    c = np.asarray(c, float)
    return np.asarray(I, float) + m * (c @ c * np.eye(3) - np.outer(c, c))


def box_part(m, b):
    """Mass, centre (m) and inertia about the centre of a uniform box b (mm: x0, x1, y0, y1, z0, z1)."""
    b = np.asarray(b, float).reshape(3, 2) / 1000
    d = b[:, 1] - b[:, 0]
    return m, b.mean(1), np.diag([d[1] ** 2 + d[2] ** 2, d[0] ** 2 + d[2] ** 2, d[0] ** 2 + d[1] ** 2]) * m / 12


def mesh_part(path):
    """Mass, centre (m) and inertia about the centre of a printed part's mesh (mm), in PETG."""
    import trimesh

    mesh = trimesh.load(path)
    assert mesh.is_watertight, path
    mesh.apply_scale(0.001)
    mesh.density = PETG_KG_M3
    return mesh.mass, mesh.center_mass, mesh.moment_inertia


def lipo_trunk_inertial():
    """The trunk's <inertial> with the LiPo plate, the pack and the BNO055 in place of the old ones."""
    sys.path.insert(0, str(ROOT / "src"))
    import plate_params as p

    m0, c0 = 0.206214, np.array([-0.01945772, -2.407926e-05, 0.003765416])
    ixx, iyy, izz, ixy, ixz, iyz = 0.000125285, 0.000155157, 0.00013248, 5.01721e-08, -2.4107e-05, 1.17083e-07
    total = inertia_about_origin(m0, c0, [[ixx, ixy, ixz], [ixy, iyy, iyz], [ixz, iyz, izz]])
    mass, moment = m0, m0 * c0
    x0 = p.PLATE_FRONT_X + p.STANDOFF_H
    y0, z0 = p.BNO_CENTER
    parts = [(-1, box_part(*OLD_BATTERY)), (+1, box_part(NEW_BATTERY_KG, p.lipo_box(0.0))),
             (-1, mesh_part(ROOT / "reference/power_support_duckbuddy.stl")), (+1, mesh_part(ROOT / "tmp/lipo_plate.stl")),
             (+1, box_part(BNO055_KG, (x0, x0 + p.PCB_T + p.BNO_PARTS_H, y0 - p.BNO_BOARD[0] / 2,
                                       y0 + p.BNO_BOARD[0] / 2, z0 - p.BNO_BOARD[1] / 2, z0 + p.BNO_BOARD[1] / 2)))]
    for sign, (m, c, I) in parts:
        total += sign * inertia_about_origin(m, c, I)
        mass += sign * m
        moment += sign * m * np.asarray(c)
    c = moment / mass
    I = total - mass * (c @ c * np.eye(3) - np.outer(c, c))
    return (f'<inertial pos="{c[0]:.7g} {c[1]:.7g} {c[2]:.7g}" mass="{mass:.6g}" fullinertia="{I[0, 0]:.6g} '
            f'{I[1, 1]:.6g} {I[2, 2]:.6g} {I[0, 1]:.6g} {I[0, 2]:.6g} {I[1, 2]:.6g}"/>'), mass, c


def lipo_visuals():
    """Visual geoms of the plate (its mesh), the pack (nominal size) and the BNO055 with its plug."""
    sys.path.insert(0, str(ROOT / "src"))
    import plate_params as p

    colours = {"lipo": "0.19 0.38 0.75 1", "bno055": "0.10 0.10 0.30 1", "qwiic": "0.86 0.86 0.86 1"}
    boxes = dict(lipo_boxes(), lipo=p.lipo_box(0.0))
    out = ['<geom type="mesh" class="visual" mesh="lipo_plate" rgba="0.16 0.16 0.16 1"/>']
    for name, colour in colours.items():
        x0, x1, y0, y1, z0, z1 = boxes[name]
        pos = " ".join(f"{v / 2000:.5f}" for v in (x0 + x1, y0 + y1, z0 + z1))
        size = " ".join(f"{abs(v) / 2000:.5f}" for v in (x1 - x0, y1 - y0, z1 - z0))
        out.append(f'<geom type="box" class="visual" pos="{pos}" size="{size}" rgba="{colour}"/>')
    return out


def scene_with_meshes(mjlab, plate):
    """A copy of the rev-a MJCF folder in tmp/, its meshdir pointing at the Microduck meshes; for
    plate "lipo", with the NP-F970's collision mesh swapped for the LiPo plate's boxes, the trunk's
    mass changed and the new parts shown."""
    src, dst = REPO / "hardware/rev-a/mjcf", ROOT / f"tmp/mjcf_{plate}"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.xml"):
        text = f.read_text().replace('meshdir="assets"', f'meshdir="{Path(mjlab).resolve() / "meshes"}"')
        if plate == "lipo" and f.name == "robot_allcollisions.xml":
            assert text.count(NP_F970_COLLISION) == 1
            boxes = []
            for name, (x0, x1, y0, y1, z0, z1) in lipo_boxes().items():
                pos = " ".join(f"{v / 2000:.5f}" for v in (x0 + x1, y0 + y1, z0 + z1))
                size = " ".join(f"{abs(v) / 2000:.5f}" for v in (x1 - x0, y1 - y0, z1 - z0))
                boxes.append(f'<geom name="lipo_plate_{name}" type="box" class="collision" pos="{pos}" size="{size}"/>')
            text = text.replace(NP_F970_COLLISION, "\n      ".join(boxes))
            for old in (NP_F970_VISUAL, PLATE_VISUAL, TRUNK_INERTIAL):
                assert text.count(old) == 1, old
            text = text.replace(NP_F970_VISUAL, "").replace(PLATE_VISUAL, "\n      ".join(lipo_visuals()))
            text = text.replace(TRUNK_INERTIAL, lipo_trunk_inertial()[0])
            text = text.replace("</asset>", f'  <mesh name="lipo_plate" file="{ROOT / "tmp/lipo_plate.stl"}" '
                                            'scale="0.001 0.001 0.001"/>\n  </asset>', 1)
        (dst / f.name).write_text(text)
    return dst / "scene.xml"


def job(scene, skill, policy, cond, init, vx=0.0, seed=0):
    os.chdir(REPO)
    import eval_skills_hl2915 as ev
    import sim_hl2915 as sh

    label, extra, delay = cond
    if skill == "walk":
        a = ev.args_for(str(policy), extra, delay, "stand", WALK_S, None, ev.ROBOTD_LOWPASS, BACKLASH)
        cmd = dict(ev.ZERO, twist=[vx, 0.0, 0.0])
    else:
        _, duration, cmd_fn, _ = ev.SKILLS[skill]
        a = ev.args_for(str(policy), extra, delay, init, duration, cmd_fn, ev.ROBOTD_LOWPASS, BACKLASH)
        cmd = ev.ZERO
    a.scene = str(scene)
    a.backlash_seed = seed
    log = sh.run(a, str(scene), str(policy), cmd)
    if skill == "walk":
        ok = log["fell"] is None
        score = ("ok" if ok else f"fell {log['fell']:.1f}s") + f" dx {log['x'][-1] - log['x'][0]:+.2f} m"
    else:
        ok, score = ev.SKILLS[skill][3](log)
    return skill, label, init if skill != "walk" else f"{vx} m/s", bool(ok), score, \
        np.asarray(log["q"]), np.asarray(log["z"]), np.asarray(log["gz"])


def main():
    sys.path.insert(0, str(BAM))
    import eval_skills_hl2915 as ev
    import sim_walk as sw

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plate", choices=("stock", "lipo", "both"), default="both")
    ap.add_argument("mjlab", nargs="?", default=str(DEFAULT_MJLAB))
    a = ap.parse_args()
    for plate in ("stock", "lipo") if a.plate == "both" else (a.plate,):
        scene = scene_with_meshes(a.mjlab, plate)
        jobs = [(scene, "walk", WALK, c, "stand", vx) for c in ev.CONDITIONS for vx in WALK_SPEEDS]
        jobs += [(scene, s, p, c, i, 0.0) for s, p in SKILL_POLICIES.items() for c in ev.CONDITIONS
                 for i in ev.SKILLS[s][0]]
        with ProcessPoolExecutor(os.cpu_count()) as ex:
            results = list(ex.map(job, *zip(*jobs)))
        print(f"\n==== {plate}")
        out = {}
        for skill in ["walk"] + list(SKILL_POLICIES):
            rows = [r for r in results if r[0] == skill]
            print(f"  {skill}: {sum(r[3] for r in rows)}/{len(rows)}")
            for label, *_ in ev.CONDITIONS:
                cells = [r for r in rows if r[1] == label]
                print(f"    {label:<30} " + "  ".join(f"{r[2]}:{r[4]}" for r in cells))
            out[skill] = np.vstack([r[5] for r in rows])
            out[skill + "_z"] = np.concatenate([r[6] for r in rows])
            out[skill + "_gz"] = np.concatenate([r[7] for r in rows])
        scores = np.array([(r[0], r[1], r[2], str(r[3])) for r in results])
        np.savez(ROOT / f"tmp/policy_poses_{plate}.npz", joints=np.array(sw.POLICY_JOINTS), scores=scores, **out)


if __name__ == "__main__":
    main()
