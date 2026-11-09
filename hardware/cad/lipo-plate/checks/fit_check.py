# /// script
# dependencies = ["mujoco", "numpy", "scipy", "trimesh", "rtree", "manifold3d"]
# ///
"""Fit check of the LiPo battery plate against the DuckBuddy trunk.

Run from hardware/cad/lipo-plate, after `uv run src/build_plate.py` and
`uv run tools/policy_poses.py` (both plates):

    uv run checks/fit_check.py [MJLAB_DIR]

MJLAB_DIR is the microduck-simulator folder app/public/robot/mjlab (default: the one next to
this repository). In the trunk frame (X forward, Y left, Z up, mm) it measures:

- the plate against the trunk parts: no more overlap than the old plate has (it sits in the
  shells' grooves); what the plate adds outside the old one's slab, top and servo brackets (the
  cup, the pad), the LiPo, the BNO055's mount and the BNO055 with its Qwiic plug against the trunk
  parts: no overlap, and at least STATIC_MARGIN (LARGEST_MARGIN for the largest pack the cup takes,
  3 mm over the nominal size every way; the mount and the BNO055 rest on the rear hip servos, whose
  passive horns are left off, so only no overlap there), the mount at least MOUNT_GAP from the
  plate and the BNO055 at least BOARD_STOP_GAP from the upper bracket's tabs behind it;
- the path of the plate when it slides up into the shells, as the old one does;
- the robot's policies in the simulation (tools/policy_poses.py: walking, getting up from lying,
  sitting down and up, the forward roll, under the stress conditions of the policy tests), with
  the old battery and with the LiPo plate's shape and masses: each skill must succeed at least as often with
  the LiPo plate; in every pose of the LiPo plate's runs the head and the neck must keep
  MOVING_MARGIN from the BNO055 and its mount, which only they can reach, through the shells' top
  opening (the legs' nearest approach to them, through the shell walls, and the legs' and the
  head's to the plate and the pack are reported: the simulation has them touch the body there, as
  it has them touch the old battery). Poses that put the head or the neck more than SHELL_DEPTH
  into the shells are left out: the simulation has no contact there, the real robot cannot go there;
- for information, the legs and the head over the model's full joint ranges, most of which the
  robot never uses: the poses that keep MOVING_MARGIN from the old plate and the NP-F970 and do
  not run into the shells, the trunk floor or the locker, and how near they come to the new
  parts;
- the floor in the sit pose of the robot model (the robot rests on its feet, shins and
  hips), at least FLOOR_MARGIN under the plate and the largest pack.
"""

import itertools
import sys
import tempfile
from pathlib import Path

import manifold3d as m3
import mujoco
import numpy as np
import trimesh
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import build_plate as bp  # noqa: E402
import plate_params as p  # noqa: E402

DEFAULT_MJLAB = ROOT.parents[3] / "microduck-simulator/app/public/robot/mjlab"
REV_A = ROOT.parents[1] / "rev-a/mjcf/robot_allcollisions.xml"

STATIC_MARGIN = 1.0
MOVING_MARGIN = 3.0
CONTACT = 0.5  # a moving part this close to the body is taken as running into it
# The simulation has no contact between the head and the shells: a pose that puts the head or the
# neck deeper than this inside a shell is one the real robot cannot reach, and is left out.
SHELL_DEPTH = 1.0
OLD = "old plate + NP-F970"
LARGEST_MARGIN = 0.5  # the largest pack (+3 mm every way) only has to touch nothing
FLOOR_MARGIN = 10.0
OVERLAP_LIMIT = 0.5  # mm3
MOUNT_GAP = 0.3  # the mount's arms beside the plate's upper bracket tabs (0.5 by design)
BOARD_STOP_GAP = 0.1  # the BNO055's back edge to the upper bracket's tabs (0.2 by design)
# The old plate's slab and the features at its top, as (x0, x1, y0, y1, z0, z1).
SLAB = (-23.1, -20.9, -28.0, 28.0, -39.9, 40.0)
TOP = (-31.5, -20.9, -28.0, 28.0, 31.0, 40.0)
BRACKETS = [(-21.0, -13.9, -12.7, 12.7, -5.4, -1.1), (-21.0, -13.9, -12.7, 12.7, 23.0, 27.3)]

LEGS = ("yaw2roll", "bearing_roll")
HEAD = ("neck",)
SIT = {"left_hip_pitch": -np.pi / 6, "left_knee": np.pi / 3, "right_hip_pitch": np.pi / 6, "right_knee": -np.pi / 3,
       "neck_pitch": 0.4992, "head_pitch": 1.6005}


class ShellDepth:
    """Tells whether points are inside a shell deeper than SHELL_DEPTH: farther than that from the
    nearest of many surface samples, on the inner side of its face, and inside the closed mesh."""

    def __init__(self):
        shells = trimesh.util.concatenate([trimesh.load(bp.REF / f"{s}_shell_duckbuddy.stl") for s in ("left", "right")])
        S, face = trimesh.sample.sample_surface_even(shells, 400000, radius=0.15, seed=1)
        self.S, self.N, self.tree = S, shells.face_normals[face], cKDTree(S)
        self.mesh = shells
        self.lo, self.hi = shells.bounds

    def deep(self, P):
        P = P[np.all((P > self.lo) & (P < self.hi), axis=1)]
        if not len(P):
            return False
        dist, j = self.tree.query(P, workers=-1)
        far = dist > SHELL_DEPTH
        cand = P[far][np.einsum("ij,ij->i", P[far] - self.S[j[far]], self.N[j[far]]) < 0]
        # the normal side is only a quick filter (it misreads points near the shells' open edges):
        # the few candidates are tested against the closed shell meshes
        return bool(len(cand)) and bool(self.mesh.contains(cand).any())


def pts(m, spacing):
    n = int(max(2000, m.area / spacing ** 2))
    return np.vstack([m.sample(n), m.vertices])


def overlap(a, b):
    """Overlap volume (mm3), or None when one of the meshes is not a closed solid."""
    try:
        return (bp.to_manifold(a) ^ bp.to_manifold(b)).volume()
    except AssertionError:
        return None


def load_model(mjlab):
    """The rev-a model (the one the policies train on) with the Microduck meshes, on a floor."""
    xml = REV_A.read_text().replace('meshdir="assets"', f'meshdir="{Path(mjlab).resolve() / "meshes"}"')
    xml = xml.replace("<worldbody>", '<worldbody><geom name="floor" type="plane" size="1 1 0.1"/>', 1)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "robot.xml"
        path.write_text(xml)
        return mujoco.MjModel.from_xml_path(str(path))


def subtree(m, roots):
    ids = {mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, r) for r in roots}
    changed = True
    while changed:
        changed = False
        for b in range(m.nbody):
            if b not in ids and m.body_parentid[b] in ids:
                ids.add(b)
                changed = True
    return ids


def body_clouds(m, d, bodies, spacing):
    """Surface points of each body's visual meshes, in the body frame (m)."""
    out = {}
    for g in range(m.ngeom):
        b = m.geom_bodyid[g]
        if b not in bodies or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or m.geom_group[g] != 2:
            continue
        mid = m.geom_dataid[g]
        va, vn = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
        fa, fn = m.mesh_faceadr[mid], m.mesh_facenum[mid]
        tm = trimesh.Trimesh(m.mesh_vert[va:va + vn] * 1000, m.mesh_face[fa:fa + fn], process=False)
        P = pts(tm, spacing) / 1000
        w = P @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g]
        Rb, pb = d.xmat[b].reshape(3, 3), d.xpos[b]
        out.setdefault(b, []).append((w - pb) @ Rb)
    return {b: np.vstack(v) for b, v in out.items()}


def joint(m, name):
    j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, name)
    return m.jnt_qposadr[j], m.jnt_range[j]


def sweep(m, clouds, grid, trees, roi, shells=None):
    """For each pose of the grid, the nearest distance from the moving points to each tree. A pose
    "runs into the body" when a point comes within CONTACT of it or, with `shells`, more than
    SHELL_DEPTH into the shells (for the head, whose neck passes close to the shells' opening)."""
    d = mujoco.MjData(m)
    tb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    names = list(grid)
    worst = {k: (np.inf, None) for k in trees if k not in ("body", OLD)}
    hits = near_old = 0
    for values in itertools.product(*grid.values()):
        d.qpos[:] = m.qpos0
        for n, v in zip(names, values):
            d.qpos[joint(m, n)[0]] = v
        mujoco.mj_kinematics(m, d)
        Rt, pt = d.xmat[tb].reshape(3, 3), d.xpos[tb]
        P = np.vstack([(c @ d.xmat[b].reshape(3, 3).T + d.xpos[b] - pt) @ Rt for b, c in clouds.items()]) * 1000
        P = P[np.all((P > roi[0]) & (P < roi[1]), axis=1)]
        if not len(P):
            continue
        if shells.deep(P) if shells else trees["body"].query(P, distance_upper_bound=CONTACT, workers=-1)[0].min() < CONTACT:
            hits += 1
            continue
        if trees[OLD].query(P, distance_upper_bound=MOVING_MARGIN, workers=-1)[0].min() < MOVING_MARGIN:
            near_old += 1
            continue
        for k, t in trees.items():
            if k in ("body", OLD):
                continue
            dist, _ = t.query(P, distance_upper_bound=min(worst[k][0], 30.0), workers=-1)
            i = np.argmin(dist)
            if dist[i] < worst[k][0]:
                worst[k] = (dist[i], (dict(zip(names, np.round(np.degrees(values)).astype(int).tolist())),
                                      np.round(P[i], 1).tolist()))
    return worst, hits, near_old


def main():
    mjlab = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MJLAB
    plate = trimesh.load(bp.TMP / "lipo_plate.stl")
    old_plate = trimesh.load(bp.REF / "power_support_duckbuddy.stl")
    # What the new plate adds to the old one (the cup, the skirt, the standoffs): what lies
    # outside the old plate's slab and top features. The old plate sits in the shells' grooves and
    # against the locker by design, so only this is held to the clearances; the recreated slab and
    # top are held to the old plate's overlaps.
    old_region = bp.box(*SLAB) + bp.box(*TOP)
    for b in BRACKETS:
        old_region += bp.box(*b)
    pieces = bp.to_trimesh(bp.to_manifold(plate) - bp.to_manifold(old_plate) - old_region).split(only_watertight=False)
    adds = trimesh.util.concatenate([q for q in pieces if q.volume > 0.5])
    parts = bp.load_parts()
    lipo = parts["lipo"]
    big = trimesh.creation.box(bounds=np.array(p.lipo_box(p.LIPO_TOL)).reshape(3, 2).T)
    bno = trimesh.util.concatenate([parts["bno055_pcb"], parts["bno055_parts"], parts["qwiic_plug"]])
    mount = trimesh.load(bp.TMP / "imu_mount.stl")
    old = trimesh.util.concatenate([old_plate,
                                    trimesh.load(next(bp.REF.glob("np_f970__*.stl")))])
    fixed = {f.stem.removesuffix("_duckbuddy"): bp.load_fixed(f) for f in bp.fixed_parts()}
    fails = []
    print(f"lipo_plate: bounds {np.round(plate.bounds, 1).tolist()}, watertight {plate.is_watertight}, "
          f"volume {plate.volume / 1000:.1f} cm3")

    print(f"imu_mount: bounds {np.round(mount.bounds, 1).tolist()}, watertight {mount.is_watertight}, "
          f"volume {mount.volume / 1000:.2f} cm3")

    print("\n-- new parts, LiPo, BNO055 and its mount against the trunk parts (overlap must be 0)")
    old_v = {k: overlap(old_plate, f) for k, f in fixed.items()}
    print("  the whole plate against the trunk parts, overlap new / old (the old plate's contact faces):")
    for k, f in fixed.items():
        v = overlap(plate, f)
        if v is not None and (v > 0.01 or (old_v[k] or 0) > 0.01):
            bad = v > (old_v[k] or 0) + OVERLAP_LIMIT
            print(f"    {k:40s} {v:6.2f} / {old_v[k]:6.2f} mm3" + ("  <-- FAIL" if bad else ""))
            if bad:
                fails.append(f"plate overlaps {k} by {v:.2f} mm3 (old plate {old_v[k]:.2f})")
    held = {"new parts": adds, "lipo": lipo, "lipo, largest": big, "imu mount": mount, "bno055 + plug": bno}
    for name, a in held.items():
        A = pts(a, 0.2)
        for fname, f in fixed.items():
            dmin = cKDTree(pts(f, 0.2)).query(A, workers=-1)[0].min()
            v = overlap(a, f)
            if dmin < 5 or (v or 0) > 0:
                need = LARGEST_MARGIN if a is big else 0.0 if (a is mount or a is bno) and fname.startswith("xl330") else STATIC_MARGIN
                bad = (v or 0) > OVERLAP_LIMIT or dmin < need
                note = "not a closed mesh, distance only" if v is None else f"overlap {v:.2f} mm3"
                print(f"  {name:15s} vs {fname:40s} {dmin:5.2f} mm, {note}" + ("  <-- FAIL" if bad else ""))
                if bad:
                    fails.append(f"{name} vs {fname}: {dmin:.2f} mm, {note}")
    # the servo meshes are open, so the overlap with them is not measured: the hubs left on the rear
    # hip servos' tops (closed cylinders) are checked on their own
    for side, hname in ((1, "left"), (-1, "right")):
        h = bp.hub(side)
        side_wall = h.copy()
        side_wall.apply_translation([0, 0, -0.1])  # below its top face, which the cap rests on
        vm = overlap(mount, h)
        dm_h = cKDTree(pts(side_wall, 0.1)).query(pts(mount, 0.1), workers=-1)[0].min()
        db_h = cKDTree(pts(h, 0.1)).query(pts(bno, 0.1), workers=-1)[0].min()
        bad = vm is None or vm > OVERLAP_LIMIT or db_h < BOARD_STOP_GAP
        print(f"  {hname} servo hub: overlap with the mount {vm:.2f} mm3 (its cap rests on it, "
              f"{dm_h:.2f} mm around its side), the BNO055 {db_h:.2f} mm from it (need {BOARD_STOP_GAP})"
              + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"{hname} hub: mount overlap {vm} mm3, BNO055 at {db_h:.2f} mm")
    dl = cKDTree(pts(big, 0.3)).query(pts(plate, 0.3), workers=-1)[0].min()
    db = cKDTree(pts(bno, 0.2)).query(pts(mount, 0.2), workers=-1)[0].min()
    dm = cKDTree(pts(plate, 0.1)).query(pts(mount, 0.1), workers=-1)[0].min()
    dbp = cKDTree(pts(plate, 0.2)).query(pts(bno, 0.2), workers=-1)[0].min()
    print(f"  largest LiPo to the plate {dl:.2f} mm, BNO055 to its mount {db:.2f} mm (both rest on them)")
    bad = dm < MOUNT_GAP or dbp < BOARD_STOP_GAP
    print(f"  mount to the plate {dm:.2f} mm (need {MOUNT_GAP}), BNO055 to the plate {dbp:.2f} mm (need {BOARD_STOP_GAP}: "
          "the upper bracket's tabs keep it from sliding back)" + ("  <-- FAIL" if bad else ""))
    if bad:
        fails.append(f"mount {dm:.2f} mm / BNO055 {dbp:.2f} mm from the plate")

    print("\n-- sliding the plate up into the shells (as the old one goes in), new parts against the shells")
    shells = trimesh.util.concatenate([fixed["left_shell"], fixed["right_shell"]])
    S = cKDTree(pts(shells, 0.3))
    A = pts(adds, 0.3)
    worst_new = min(S.query(A - [0, 0, s], workers=-1)[0].min() for s in np.arange(0, 70.1, 1.0))
    print(f"  new parts: nearest {worst_new:.2f} mm to the shells over a 70 mm slide")
    if worst_new < 0.5:
        fails.append(f"slide-in: new parts {worst_new:.2f} mm from the shells")

    m = load_model(mjlab)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    tb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    # The legs' first links sit on the hip servos and bearings by design: "running into the
    # body" means reaching the shells, the trunk floor or the locker.
    body = trimesh.util.concatenate([f for k, f in fixed.items() if not k.startswith(("xl330", "seeed"))])
    trees = {"body": cKDTree(pts(body, 0.5)), "new parts": cKDTree(pts(adds, 0.5)),
             "lipo": cKDTree(pts(big, 0.5)),
             "bno055 + mount": cKDTree(pts(trimesh.util.concatenate([bno, mount]), 0.3)), OLD: cKDTree(pts(old, 0.5))}

    policy_motion(m, d, trees, fails)

    print("\n-- for information: legs over their full joint ranges (poses that run into the body are left out)")
    legs = subtree(m, LEGS)
    clouds = body_clouds(m, d, legs, 1.2)
    grid = {}
    for side in ("left", "right"):
        for j, n in (("hip_yaw", 3), ("hip_roll", 3), ("hip_pitch", 13), ("knee", 13), ("ankle", 5)):
            lo, hi = joint(m, f"{side}_{j}")[1]
            grid[f"{side}_{j}"] = np.linspace(lo, hi, n)
    for side in ("left", "right"):
        g = {k: v for k, v in grid.items() if k.startswith(side)}
        c = {b: v for b, v in clouds.items() if (side == "left") == (b in subtree(m, ("yaw2roll",)))}
        worst, hits, near = sweep(m, c, g, trees, (np.array([-90, -60, -120]), np.array([0, 60, 60])))
        print(f"  {side} leg ({hits} poses run into the body, {near} come within {MOVING_MARGIN:.0f} mm of the old parts; left out):")
        report(worst, None, f"{side} leg")

    print("\n-- for information: head over its full joint ranges (poses that put it over 1 mm into the shells are left out)")
    head = subtree(m, HEAD)
    clouds = body_clouds(m, d, head, 1.5)
    g = {}
    for j, n in (("neck_pitch", 11), ("head_pitch", 13), ("head_yaw", 7), ("head_roll", 3)):
        lo, hi = joint(m, j)[1]
        g[j] = np.linspace(lo, hi, n)
    worst, hits, near = sweep(m, clouds, g, trees, (np.array([-90, -60, -70]), np.array([40, 60, 200])), ShellDepth())
    print(f"  head ({hits} poses go into the shells, {near} come within {MOVING_MARGIN:.0f} mm of the old parts; left out):")
    report(worst, None, "head")

    print("\n-- floor (the robot model settled in its sit pose, and standing upright at home)")
    d = mujoco.MjData(m)
    for n, v in SIT.items():
        d.qpos[joint(m, n)[0]] = v
    for a in range(m.nu):
        jn = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[a, 0])
        d.ctrl[a] = SIT.get(jn, 0.0)
    d.qpos[2] = 0.25
    for _ in range(int(3.0 / m.opt.timestep)):
        mujoco.mj_step(m, d)
    R, p0 = d.xmat[tb].reshape(3, 3), d.xpos[tb] * 1000
    for name, a in (("plate", plate), ("lipo", big), ("old NP-F970", old)):
        z = (a.vertices @ R.T + p0)[:, 2].min()
        bad = name != "old NP-F970" and z < FLOOR_MARGIN
        print(f"  sit: {name:12s} lowest point {z:5.1f} mm above the floor" + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"sit: {name} {z:.1f} mm above the floor")

    print("\nRESULT:", "PASS" if not fails else "FAIL\n  " + "\n  ".join(fails))
    return 0 if not fails else 1


def policy_motion(m, d, trees, fails):
    """The policies' scores with the old battery and with the LiPo plate, and the legs and the head
    in every pose of the LiPo plate's runs against the BNO055 and its mount (and, reported, the
    plate and pack)."""
    runs = {k: np.load(bp.TMP / f"policy_poses_{k}.npz") for k in ("stock", "lipo")}
    print("\n-- the policies in the simulation: successes with the old battery / with the LiPo plate")
    for skill in dict.fromkeys(runs["stock"]["scores"][:, 0]):
        n = {k: sum(r[3] == "True" for r in rec["scores"] if r[0] == skill) for k, rec in runs.items()}
        total = sum(1 for r in runs["stock"]["scores"] if r[0] == skill)
        bad = n["lipo"] < n["stock"]
        print(f"  {skill:9s} {n['stock']:2d}/{total} / {n['lipo']:2d}/{total}" + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"{skill}: {n['lipo']}/{total} with the LiPo plate, {n['stock']}/{total} with the old battery")
    rec = runs["lipo"]
    names = [str(n) for n in rec["joints"]]
    adr = [joint(m, n)[0] for n in names]
    tb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    clouds = body_clouds(m, d, subtree(m, LEGS + HEAD), 1.2)
    head = subtree(m, HEAD)
    roi = (np.array([-90, -60, -120]), np.array([40, 60, 200]))
    print("\n-- legs and head in the poses of the LiPo plate's runs (every 2nd control tick)")
    keys = {k: t for k, t in trees.items() if k not in ("body", OLD)}
    shells = ShellDepth()
    for skill in dict.fromkeys(rec["scores"][:, 0]):
        worst = {k: (np.inf, None) for k in keys}
        q = rec[skill][::2]
        unreal = 0
        legs_mount = np.inf
        for row in q:
            d.qpos[:] = m.qpos0
            d.qpos[adr] = row
            mujoco.mj_kinematics(m, d)
            Rt, pt = d.xmat[tb].reshape(3, 3), d.xpos[tb]
            by = {b: (c @ d.xmat[b].reshape(3, 3).T + d.xpos[b] - pt) @ Rt * 1000 for b, c in clouds.items()}
            P = np.vstack(list(by.values()))
            P = P[np.all((P > roi[0]) & (P < roi[1]), axis=1)]
            H = np.vstack([v for b, v in by.items() if b in head])
            if shells.deep(H):
                unreal += 1
                continue
            for k, t in keys.items():
                # the BNO055 and its mount are closed in by the shells, the servos and the plate; only
                # the head and the neck come in, through the shells' top opening (the legs' nearest
                # approach, through the shell walls, is reported apart)
                Q = H if k == "bno055 + mount" else P
                dist, j = t.query(Q, distance_upper_bound=min(worst[k][0], 30.0), workers=-1)
                j = np.argmin(dist)
                if dist[j] < worst[k][0]:
                    worst[k] = (dist[j], (dict(zip(names, np.round(np.degrees(row)).astype(int).tolist())),
                                          np.round(Q[j], 1).tolist()))
            L = np.vstack([v for b, v in by.items() if b not in head])
            legs_mount = min(legs_mount, keys["bno055 + mount"].query(L, workers=-1)[0].min())
        print(f"  {skill} ({len(q)} poses, {unreal} left out: the head or the neck over {SHELL_DEPTH:.0f} mm into the shells):")
        report(worst, fails, f"{skill}", info=("new parts", "lipo"))
        print(f"    (legs to the BNO055 and its mount, through the shell walls: {legs_mount:.2f} mm)")


def report(worst, fails, what, info=()):
    """Print the nearest distances; with `fails`, the ones under MOVING_MARGIN fail (except `info`)."""
    for k, (dist, at) in worst.items():
        bad = fails is not None and k not in info and dist < MOVING_MARGIN
        need = "" if fails is None or k in info else f" (need {MOVING_MARGIN:.0f})"
        print(f"    {k:20s} {dist:5.2f} mm{need}" + (f" at {at}" if at and dist < 10 and k not in info else "")
              + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"{what} vs {k}: {dist:.2f} mm")


if __name__ == "__main__":
    sys.exit(main())
