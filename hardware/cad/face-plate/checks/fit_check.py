# /// script
# dependencies = ["numpy", "scipy", "trimesh", "rtree", "manifold3d"]
# ///
"""Fit check of the face plate for the Radxa camera, the SparkFun Mini ToF and the LED.

Run from hardware/cad/face-plate, after `uv run src/face_plate.py`:

    uv run checks/fit_check.py [tmp/face_plate.stl]

In the head frame (X forward, Y left, Z up, mm) it checks:
- the plate is one closed solid, and away from the camera mount it is the DuckBuddy plate
  unchanged (every point of the reference surface outside the changed areas lies on it);
- the camera board rests on the four standoffs, each pilot hole is on a board hole, and
  the board, the lens and the FPC connector overlap nothing of the plate;
- the lens clears the plate's hole, the camera clears the Pi (the FPC connector on the
  board's back) and the bottom shell;
- the ToF board rests on its pads, each pin passes through a board hole, the sensor clears
  the plate's ToF window and ends behind the front face, the ToF parts overlap nothing of the
  plate, and its connectors clear the camera and the Pi;
- the LED's collar rests on the plate's back, its dome clears the hole, the LED overlaps nothing
  of the plate and clears the camera and the Pi;
- how close the lens barrel comes to the eye piece's hole (reported only: the eye piece
  is the original Microduck part and optional).
"""

import sys
from pathlib import Path

import manifold3d as m3
import numpy as np
import trimesh
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "open-head" / "src"))
import head_meshes as hm  # noqa: E402
import head_params as p  # noqa: E402

OVERLAP_LIMIT = 0.5     # mm3: meshing noise at a contact face
UNCHANGED_TOL = 0.02    # mm: the reference surface must lie on the new plate this closely
LENS_CLEAR = 0.4        # mm: lens to the plate's hole
CAM_PI_CLEAR = 0.5      # mm: the FPC connector to the Pi
CAM_SHELL_CLEAR = 1.0   # mm: the camera to the bottom shell
TOF_WINDOW_CLEAR = 0.4  # mm: the ToF sensor to the plate's window
LED_DOME_CLEAR = 0.3    # mm: the LED dome to the plate's hole (radial)


def manifold(m):
    m = m.copy()
    m.merge_vertices()  # GLB meshes come with split vertices
    man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                              tri_verts=np.asarray(m.faces, np.uint32)))
    return man if man.status() == m3.Error.NoError else None


def overlap(a, b):
    ma, mb = manifold(a), manifold(b)
    return None if ma is None or mb is None else (ma ^ mb).volume()


def changed_area(P):
    """Points of the plate's surface in the areas the generator changes."""
    cy, cz = p.CAM_AXIS
    m = (np.hypot(P[:, 1] - cy, P[:, 2] - cz) < p.PLATE_LENS_HOLE_D / 2 + 0.3) & (P[:, 0] > p.PLATE_BACK_X - 1.0)
    w = p.PLATE_OLD_BOSS_W / 2 + 0.3
    for yc, zc in p.PLATE_OLD_BOSSES:
        m |= (np.abs(P[:, 1] - yc) < w) & (np.abs(P[:, 2] - zc) < w) & (P[:, 0] < p.PLATE_BACK_X + 0.1)
    for hy, hz in p.cam_holes():
        m |= (np.hypot(P[:, 1] - hy, P[:, 2] - hz) < p.CAM_BOSS_D / 2 + 0.3) & (P[:, 0] < p.PLATE_BACK_X + 0.5)
    o = p.PLATE_OLD_TOF
    for (x0, y0, z0), (y1, z1) in (o["frame"], o["ring"]):  # the old frame and its board area
        m |= (P[:, 1] > y0 - 0.3) & (P[:, 1] < y1 + 0.3) & (P[:, 2] > z0 - 0.3) & (P[:, 2] < z1 + 0.3) \
            & (P[:, 0] < p.PLATE_BACK_X + 0.1)
    (ya, za), (yb, zb) = p.tof_to_head(0, 0), p.tof_to_head(*p.TOF_BOARD[:2])
    m |= (P[:, 1] > ya - 0.3) & (P[:, 1] < yb + 0.3) & (P[:, 2] > zb - 0.3) & (P[:, 2] < za + 0.3) \
        & (P[:, 0] < p.PLATE_BACK_X + 0.4)
    for y, z in o["holes"]:
        m |= np.hypot(P[:, 1] - y, P[:, 2] - z) < o["hole_d"] / 2 + 0.3
    ly, lz = p.LED_AT
    m |= np.hypot(P[:, 1] - ly, P[:, 2] - lz) < p.LED_CUP_ID / 2 + p.LED_CUP_WALL + 0.3
    return m


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tmp" / "face_plate.stl"
    plate = trimesh.load(path)
    if not hm.PARTS_GLB.exists():
        hm.build_parts()
    parts = hm.load_parts()
    cam = parts["camera"]
    fails = []
    pieces = len(plate.split(only_watertight=False))
    print(f"plate {path.name}: watertight {plate.is_watertight}, pieces {pieces}, volume {plate.volume / 1000:.2f} cm3, "
          f"bounds {np.round(plate.bounds, 2).tolist()}")
    if not plate.is_watertight or pieces != 1:
        fails.append("plate is not one closed solid")
    S = hm.surface_points(plate, 0.12, cap=1500000)
    tree = cKDTree(S)

    print("\n-- unchanged away from the camera, ToF and LED mounts")
    R = hm.surface_points(hm.ref("face_part_duckbuddy"), 0.2, cap=800000)
    R = R[~changed_area(R)]
    d, _ = tree.query(R, workers=-1)
    far = d > UNCHANGED_TOL  # the samples are 0.12 mm apart: measure these exactly
    if far.any():
        d[far] = np.abs(trimesh.proximity.signed_distance(plate, R[far]))
    k = np.argmax(d)
    bad = d[k] > UNCHANGED_TOL
    print(f"  reference surface to the new plate: max {d[k]:.3f} mm at {np.round(R[k], 2).tolist()} "
          f"({len(R)} points)" + ("  <-- FAIL" if bad else ""))
    if bad:
        fails.append(f"plate changed away from the camera mount ({d[k]:.3f} mm)")

    print("\n-- camera on the plate")
    v = overlap(plate, cam)
    bad = v is None or v > OVERLAP_LIMIT
    print(f"  overlap with the camera {v if v is None else round(v, 3)} mm3" + ("  <-- FAIL" if bad else ""))
    if bad:
        fails.append("the camera overlaps the plate")
    cy, cz = p.CAM_AXIS
    h = p.CAM_BOARD / 2
    C = hm.surface_points(cam, 0.15, cap=600000)
    board = C[(np.abs(C[:, 0] - p.CAM_FRONT_X) < 0.01) & (np.abs(C[:, 1] - cy) < h) & (np.abs(C[:, 2] - cz) < h)]
    d, _ = tree.query(board, workers=-1)
    print(f"  board front face to the standoffs: gap {d.min():.3f} mm")
    if d.min() > 0.02:
        fails.append(f"the board does not rest on the standoffs ({d.min():.3f} mm)")
    xs = p.CAM_FRONT_X + 2.0
    for hy, hz in p.cam_holes():
        axis, wall = plate.contains([[xs, hy, hz], [xs, hy + p.M2_PILOT_D / 2 + 0.6, hz]])
        ok = (not axis) and wall
        print(f"  standoff at ({hy:.2f}, {hz:.2f}): pilot open {not axis}, wall solid {wall}" + ("" if ok else "  <-- FAIL"))
        if not ok:
            fails.append(f"standoff at ({hy:.2f}, {hz:.2f}) has no pilot on the board hole")
    lens = C[(C[:, 0] > p.CAM_FRONT_X + 0.05) & (np.abs(C[:, 1] - cy) < 8) & (np.abs(C[:, 2] - cz) < 8)]
    d, i = tree.query(lens, workers=-1)
    k = np.argmin(d)
    bad = d[k] < LENS_CLEAR
    print(f"  lens to the plate: {d[k]:.2f} mm (need {LENS_CLEAR}) at {np.round(lens[k], 2).tolist()}" + ("  <-- FAIL" if bad else ""))
    if bad:
        fails.append(f"lens to the plate {d[k]:.2f} mm")

    print("\n-- ToF on the plate")
    tof = parts["tof"]
    v = overlap(plate, tof)
    bad = v is None or v > OVERLAP_LIMIT
    print(f"  overlap with the ToF parts {v if v is None else round(v, 3)} mm3" + ("  <-- FAIL" if bad else ""))
    if bad:
        fails.append("the ToF parts overlap the plate")
    T = hm.surface_points(tof, 0.12, cap=600000)
    xf = p.tof_board_front_x()
    (ya, za), (yb, zb) = p.tof_to_head(0, 0), p.tof_to_head(*p.TOF_BOARD[:2])
    front = T[(np.abs(T[:, 0] - xf) < 0.01) & (T[:, 1] > ya) & (T[:, 1] < yb) & (T[:, 2] > zb) & (T[:, 2] < za)]
    d, _ = tree.query(front, workers=-1)
    print(f"  board front face to the pads: gap {d.min():.3f} mm")
    if d.min() > 0.02:
        fails.append(f"the ToF board does not rest on its pads ({d.min():.3f} mm)")
    xs = xf - p.TOF_BOARD[2] / 2
    for hy, hz in p.tof_holes():
        pin, = plate.contains([[xs, hy, hz]])
        ring = np.array([[xs, hy + p.TOF_HOLE_D / 2 * np.cos(a), hz + p.TOF_HOLE_D / 2 * np.sin(a)] for a in np.linspace(0, 2 * np.pi, 24)])
        gap = tree.query(ring)[0].min()
        ok = pin and gap > 0.05
        print(f"  pin at ({hy:.2f}, {hz:.2f}): in the hole {pin}, {gap:.2f} mm to the hole wall" + ("" if ok else "  <-- FAIL"))
        if not ok:
            fails.append(f"no pin through the ToF hole at ({hy:.2f}, {hz:.2f})")
    sy, sz = p.TOF_SENSOR_AT
    sensor = T[(T[:, 0] > xf + 0.05) & (np.abs(T[:, 1] - sy) < 4) & (np.abs(T[:, 2] - sz) < 2)]
    d, _ = tree.query(sensor, workers=-1)
    k = np.argmin(d)
    behind = p.PLATE_FRONT_X - sensor[:, 0].max()
    bad = d[k] < TOF_WINDOW_CLEAR or behind < 0
    print(f"  sensor to the window: {d[k]:.2f} mm (need {TOF_WINDOW_CLEAR}); its face {behind:.2f} mm behind the "
          f"plate's front" + ("  <-- FAIL" if bad else ""))
    if bad:
        fails.append("the ToF sensor does not fit the window")
    for name, m in (("camera", cam), ("pi", parts["pi"])):
        d, _ = cKDTree(hm.surface_points(m, 0.15, cap=800000)).query(T, workers=-1)
        k = np.argmin(d)
        bad = d[k] < p.TOF_MARGIN
        print(f"  ToF to the {name:6s} {d[k]:5.2f} mm (need {p.TOF_MARGIN}) at {np.round(T[k], 2).tolist()}" + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"ToF to the {name}: {d[k]:.2f} mm")

    print("\n-- LED on the plate")
    led = parts["led"]
    v = overlap(plate, led)
    bad = v is None or v > OVERLAP_LIMIT
    print(f"  overlap with the LED {v if v is None else round(v, 3)} mm3" + ("  <-- FAIL" if bad else ""))
    if bad:
        fails.append("the LED overlaps the plate")
    L = hm.surface_points(led, 0.1, cap=400000)
    ly, lz = p.LED_AT
    r = np.hypot(L[:, 1] - ly, L[:, 2] - lz)
    seat = L[(np.abs(L[:, 0] - p.PLATE_BACK_X) < 0.01) & (r > p.LED_HOLE_D / 2 + 0.05) & (r < p.LED_COLLAR[0] / 2 - 0.05)]
    d, _ = tree.query(seat, workers=-1)
    print(f"  collar to the plate's back face: gap {d.min():.3f} mm, seat {(p.LED_COLLAR[0] - p.LED_HOLE_D) / 2:.2f} mm wide")
    if d.min() > 0.03:
        fails.append(f"the LED collar does not rest on the plate ({d.min():.3f} mm)")
    dome = L[L[:, 0] > p.PLATE_BACK_X + 0.01]
    d, _ = tree.query(dome, workers=-1)
    k = np.argmin(d)
    print(f"  dome to the hole: {d[k]:.2f} mm (need {LED_DOME_CLEAR}); dome out {dome[:, 0].max() - p.PLATE_FRONT_X:.2f} mm in front of the plate")
    if d[k] < LED_DOME_CLEAR:
        fails.append(f"LED dome to the hole {d[k]:.2f} mm")
    body = L[(L[:, 0] < p.PLATE_BACK_X - p.LED_COLLAR[1] - 0.05) & (r > p.LED_BODY[0] / 2 - 0.05)]
    d, _ = tree.query(body, workers=-1)
    print(f"  body to the cup: {d.min():.2f} mm")
    for name, m in (("camera", cam), ("pi", parts["pi"])):
        d, _ = cKDTree(hm.surface_points(m, 0.15, cap=800000)).query(L, workers=-1)
        k = np.argmin(d)
        bad = d[k] < p.LED_MARGIN
        print(f"  LED to the {name:6s} {d[k]:5.2f} mm (need {p.LED_MARGIN}) at {np.round(L[k], 2).tolist()}" + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"LED to the {name}: {d[k]:.2f} mm")

    print("\n-- camera to the other parts")
    for name, m, need in (("pi", parts["pi"], CAM_PI_CLEAR), ("bottom_head_shell", hm.ref("bottom_head_shell_duckbuddy"), CAM_SHELL_CLEAR)):
        d, _ = cKDTree(hm.surface_points(m, 0.2, cap=800000)).query(C, workers=-1)
        k = np.argmin(d)
        bad = d[k] < need
        print(f"  {name:18s} {d[k]:5.2f} mm (need {need:.1f}) at {np.round(C[k], 2).tolist()}" + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"camera to {name}: {d[k]:.2f} mm")
    eye = hm.ref("noenoeil")
    d, _ = cKDTree(hm.surface_points(eye, 0.15)).query(C, workers=-1)
    v = overlap(eye, cam)
    print(f"  eye piece (info)   {d.min():5.2f} mm, overlap {round(v, 3) if v is not None else None} mm3: "
          f"its hole is 14.3 mm, the lens barrel 14 mm at most")

    print("\nRESULT:", "PASS" if not fails else "FAIL\n  " + "\n  ".join(fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
