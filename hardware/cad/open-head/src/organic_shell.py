# /// script
# dependencies = ["numpy", "scipy", "trimesh", "rtree", "manifold3d", "scikit-image", "networkx"]
# ///
"""Open head shell for DuckBuddy: an organic, branching frame.

Run from hardware/cad/open-head:

    uv run src/organic_shell.py            # full resolution (0.3 mm), about 2 minutes
    uv run src/organic_shell.py --res 0.5  # quick draft

It writes tmp/open_head_shell.stl (the part) and tmp/open_head_review.glb (the part with
the HAT, the speaker and the Pi, for review).

How it is made:
1. Branches (tapered tubes along smooth curves) grow from the three screw bosses to the
   four HAT standoffs, the speaker tray and the face-plate collar. They are joined with
   smooth blends, as a distance field on a voxel grid.
2. The field is carved away, with smooth edges, wherever it comes closer than the set
   clearance to the head parts: the neck parts swept over head roll and head yaw, the parts
   fixed in the head, the Pi with its cooling shield and Dupont plugs, and the parts under
   the HAT board.
3. The field is meshed (marching cubes) and smoothed.
4. The exact features are cut from the mesh: the contact plane on the bottom shell, the
   screw pilots, the HAT standoff tops, the speaker pocket and the face-plate slot.

Head frame: X forward, Y to the robot's left, Z up, in mm (head_params.py).
"""

import argparse
import json
import sys
import time
from pathlib import Path

import manifold3d as m3
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

sys.path.insert(0, str(Path(__file__).resolve().parent))
import head_meshes as hm  # noqa: E402
import head_params as p  # noqa: E402

BIG = np.float32(1e3)

# Grid bounds (head frame).
GRID_LO = np.array([-38.0, -48.0, -4.0])
GRID_HI = np.array([80.0, 49.0, 44.0])

BLEND = 2.5        # smooth-union radius between branches
CARVE_BLEND = 1.2  # smooth-subtraction radius of the clearance carving
# Carving clearances: the fit-check margins plus an allowance for the point sampling.
SAMPLE_ALLOWANCE = 0.3

# ---------------------------------------------------------------------------------------
# The frame. Each branch is a list of control points (x, y, z, radius); the centre line is
# a Catmull-Rom curve through them and the radius follows along it.

B = p.BOSS_BACK
FL, FR = p.BOSS_FRONT  # front-left (+Y), front-right (-Y)
S1, S3, S2, S4 = (p.hat_hole_xy(*h) for h in p.HAT_HOLES)  # rear-left, front-left, rear-right, front-right
EAR_X = (p.SPK_CENTER[0] - p.SPK_EAR_PITCH / 2, p.SPK_CENTER[0] + p.SPK_EAR_PITCH / 2)
EAR_Y = p.SPK_CENTER[1]
EAR_TOP_Z = p.SPK_SEAT_Z + p.SPK_EAR_TOP - p.SPK_EAR_T
DECK_Z = 19.3       # centre height of the deck branches
COLUMN_R = p.BOSS_D / 2
STANDOFF_TOP_R = 2.6
COLLAR_SIDE_Z = 13.0  # the collar runs down the plate sides to here and merges into the legs

BRANCHES = {
    # screw bosses: columns from below the contact plane up into the deck
    "boss_back": [(*B, -3.0, COLUMN_R), (*B, 8.0, COLUMN_R + 0.2), (*B, 17.0, COLUMN_R)],
    "boss_front_left": [(*FL, -3.0, COLUMN_R), (*FL, 8.0, COLUMN_R + 0.3), (*FL, 16.0, COLUMN_R)],
    "boss_front_right": [(*FR, -3.0, COLUMN_R), (*FR, 8.0, COLUMN_R + 0.3), (*FR, 16.0, COLUMN_R)],
    # HAT standoffs: tapered columns up to the board (cut flat at HAT_BOTTOM_Z)
    "standoff_rear_left": [(*S1, 18.0, 3.4), (*S1, 22.0, 3.0), (*S1, p.HAT_BOTTOM_Z + 1.0, STANDOFF_TOP_R)],
    "standoff_rear_right": [(*S2, 18.0, 3.4), (*S2, 22.0, 3.0), (*S2, p.HAT_BOTTOM_Z + 1.0, STANDOFF_TOP_R)],
    "standoff_front_left": [(*S3, 19.5, 3.4), (*S3, 22.5, 3.0), (*S3, p.HAT_BOTTOM_Z + 1.0, STANDOFF_TOP_R)],
    "standoff_front_right": [(*S4, 19.5, 3.4), (*S4, 22.5, 3.0), (*S4, p.HAT_BOTTOM_Z + 1.0, STANDOFF_TOP_R)],
    # rear fork: back boss to the two rear standoffs, and a bow between them
    "fork_left": [(B[0], B[1], 15.5, 3.4), (-27.5, 1.5, 18.8, 2.9), (S1[0], S1[1], 20.5, 2.7)],
    "fork_right": [(B[0], B[1], 15.5, 3.4), (-29.0, -10.0, 18.8, 2.8), (S2[0], S2[1], 20.0, 2.7)],
    "rear_bow": [(S1[0], S1[1], 20.5, 2.3), (-21.0, -9.5, 19.5, 2.0), (S2[0], S2[1], 20.0, 2.3)],
    # right rail, outside the swept neck parts, rear-right to front-right standoff
    "right_rail": [(S2[0], S2[1], 20.0, 2.7), (-12.0, -30.0, DECK_Z, 2.5), (8.0, -31.5, DECK_Z, 2.4),
                   (25.0, -30.5, DECK_Z, 2.5), (S4[0], S4[1], 22.0, 2.7)],
    # front right: front-right boss to the front-right standoff, beside the Pi
    "front_right": [(FR[0], FR[1], 14.0, COLUMN_R), (60.0, -38.5, 18.0, 3.1), (47.0, -36.0, DECK_Z, 2.8),
                    (39.0, -28.0, 21.0, 2.7), (S4[0], S4[1], 22.0, 2.7)],
    # front left: front-left boss to the front speaker ear, beside the Pi
    "front_left": [(FL[0], FL[1], 14.0, COLUMN_R), (60.0, 38.5, 18.0, 3.1), (47.0, 36.5, DECK_Z, 2.8),
                   (EAR_X[1] + 1.0, EAR_Y + 1.0, 19.5, 2.8)],
    # front bow between the front standoffs, ahead of the swept neck parts
    "front_bow": [(S3[0], S3[1], 22.0, 2.4), (37.5, -9.5, 21.0, 2.2), (S4[0], S4[1], 22.0, 2.4)],
    # front-left standoff to the front ear of the tray
    "front_tray_link": [(S3[0], S3[1], 22.0, 2.4), (36.5, 15.0, 20.0, 2.3), (EAR_X[1], EAR_Y - 2.0, 19.5, 2.5)],
    # rear-left standoff to the rear ear and the rear-right corner of the tray
    "rear_tray_link": [(S1[0], S1[1], 20.5, 2.5), (-14.0, 15.0, 18.5, 2.3), (EAR_X[0], EAR_Y, 18.5, 2.6)],
    "rear_tray_brace": [(S1[0], S1[1], 20.5, 2.2), (-10.0, 9.0, 18.0, 2.0), (1.0, 12.5, 18.0, 2.2)],
    # speaker ear bosses (cut flat under the ear flange)
    "ear_rear": [(EAR_X[0], EAR_Y, 16.5, 3.4), (EAR_X[0], EAR_Y, EAR_TOP_Z + 1.0, 3.0)],
    "ear_front": [(EAR_X[1], EAR_Y, 16.5, 3.4), (EAR_X[1], EAR_Y, EAR_TOP_Z + 1.0, 3.0)],
    # legs from the front bosses up into the collar ends
    "collar_leg_left": [(FL[0], FL[1], 11.0, COLUMN_R), (70.0, 43.5, 14.5, 3.0), (72.8, 45.2, 17.0, 2.6)],
    "collar_leg_right": [(FR[0], FR[1], 11.0, COLUMN_R), (70.0, -43.5, 14.5, 3.0), (72.8, -45.2, 17.0, 2.6)],
}

# Speaker tray: a tube ring around the speaker's bottom edge. The pocket cut leaves a
# ledge under the speaker edge and a low rim around it.
SPK_IN = (p.SPK_CENTER[0] - p.SPK_BODY[0] / 2 - p.SPK_CLEAR, p.SPK_CENTER[0] + p.SPK_BODY[0] / 2 + p.SPK_CLEAR,
          p.SPK_CENTER[1] - p.SPK_BODY[1] / 2 - p.SPK_CLEAR, p.SPK_CENTER[1] + p.SPK_BODY[1] / 2 + p.SPK_CLEAR)
RING_OFFSET = 1.0   # ring centre line outside the pocket edge
RING_R = 2.8        # tube radius: 1.8 mm ledge under the speaker, rim up to Z 21.6
RING_Z = 18.8
RING_CORNER = 3.0
WIRE_EXIT_W = 8.0   # opening in the rim towards the HAT for the speaker wire


# ---------------------------------------------------------------------------------------
# distance field helpers

class Grid:
    def __init__(self, h):
        self.h = h
        self.n = np.ceil((GRID_HI - GRID_LO) / h).astype(int) + 1
        self.axes = [GRID_LO[i] + h * np.arange(self.n[i]) for i in range(3)]
        self.d = np.full(self.n, BIG, dtype=np.float32)

    def block(self, lo, hi):
        i0 = np.clip(np.floor((np.asarray(lo) - GRID_LO) / self.h).astype(int), 0, self.n - 1)
        i1 = np.clip(np.ceil((np.asarray(hi) - GRID_LO) / self.h).astype(int) + 1, 0, self.n)
        sl = tuple(slice(a, b) for a, b in zip(i0, i1))
        X = self.axes[0][sl[0]][:, None, None].astype(np.float32)
        Y = self.axes[1][sl[1]][None, :, None].astype(np.float32)
        Z = self.axes[2][sl[2]][None, None, :].astype(np.float32)
        return sl, X, Y, Z


def smin(a, b, k):
    h = np.clip(k - np.abs(a - b), 0, None) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


def catmull_rom(points, step=0.7):
    P = np.asarray(points, float)
    E = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = E[i:i + 4]
        n = max(2, int(np.ceil(np.linalg.norm(p2[:3] - p1[:3]) / step)))
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1:])
    return np.vstack(out)


def branch_field(grid, points):
    """Distance to a tapered tube along a Catmull-Rom curve (union of tapered segments)."""
    C = catmull_rom(points)
    pad = C[:, 3].max() + BLEND + 2 * grid.h
    sl, X, Y, Z = grid.block(C[:, :3].min(0) - pad, C[:, :3].max(0) + pad)
    d = np.full((X.shape[0], Y.shape[1], Z.shape[2]), BIG, dtype=np.float32)
    off = np.array([s.start for s in sl])
    for a, b in zip(C[:-1], C[1:]):
        r = max(a[3], b[3]) + BLEND + 2 * grid.h
        lo = np.floor((np.minimum(a[:3], b[:3]) - r - GRID_LO) / grid.h).astype(int) - off
        hi = np.ceil((np.maximum(a[:3], b[:3]) + r - GRID_LO) / grid.h).astype(int) + 1 - off
        lo = np.clip(lo, 0, d.shape)
        hi = np.clip(hi, 0, d.shape)
        s = tuple(slice(x0, x1) for x0, x1 in zip(lo, hi))
        x, y, z = X[s[0]], Y[:, s[1]], Z[:, :, s[2]]
        ba = (b[:3] - a[:3]).astype(np.float32)
        px, py, pz = x - a[0], y - a[1], z - a[2]
        t = np.clip((px * ba[0] + py * ba[1] + pz * ba[2]) / max(float(ba @ ba), 1e-9), 0, 1)
        dist = np.sqrt((px - t * ba[0]) ** 2 + (py - t * ba[1]) ** 2 + (pz - t * ba[2]) ** 2) - (a[3] + (b[3] - a[3]) * t)
        d[s] = np.minimum(d[s], dist)
    return sl, d


def tray_ring_field(grid):
    x0, x1, y0, y1 = SPK_IN
    o = RING_OFFSET
    lo = np.array([x0 - o, y0 - o])
    hi = np.array([x1 + o, y1 + o])
    pad = RING_R + BLEND + 1
    sl, X, Y, Z = grid.block((lo[0] - pad, lo[1] - pad, RING_Z - pad), (hi[0] + pad, hi[1] + pad, RING_Z + pad))
    c, half = (lo + hi) / 2, (hi - lo) / 2 - RING_CORNER
    qx, qy = np.abs(X - c[0]) - half[0], np.abs(Y - c[1]) - half[1]
    rect = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - RING_CORNER
    return sl, (np.sqrt(rect ** 2 + (Z - RING_Z) ** 2) - RING_R).astype(np.float32)


def face_outline():
    pts = json.loads((hm.REF / "face_outline.json").read_text())
    return np.array(pts[:-1] if pts[0] == pts[-1] else pts)


def polygon_sdf(poly, U, V):
    """Signed distance in 2D to a closed polygon (positive outside), on broadcast grids U, V."""
    d = np.full(np.broadcast(U, V).shape, np.inf)
    inside = np.zeros(d.shape, bool)
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        e = b - a
        t = np.clip(((U - a[0]) * e[0] + (V - a[1]) * e[1]) / (e @ e), 0, 1)
        d = np.minimum(d, np.hypot(U - a[0] - t * e[0], V - a[1] - t * e[1]))
        cross = ((a[1] > V) != (b[1] > V)) & (U < (b[0] - a[0]) * (V - a[1]) / (b[1] - a[1] + 1e-12) + a[0])
        inside ^= cross
    return np.where(inside, -d, d)


def collar_field(grid):
    """A rounded band over the top edge of the face plate, lips on both faces."""
    sl, X, Y, Z = grid.block((p.COLLAR_X[0] - 2, -50, COLLAR_SIDE_Z - 4), (p.COLLAR_X[1] + 2, 50, GRID_HI[2]))
    s = polygon_sdf(face_outline(), Y, Z).astype(np.float32)  # (1, ny, nz)
    uc = (p.COLLAR_OUT - p.COLLAR_LIP) / 2
    hu = (p.COLLAR_OUT + p.COLLAR_LIP) / 2
    vc = (p.COLLAR_X[0] + p.COLLAR_X[1]) / 2
    hv = (p.COLLAR_X[1] - p.COLLAR_X[0]) / 2
    rr = 1.6
    qu = np.abs(s - uc) - (hu - rr)
    qv = np.abs(X - vc) - (hv - rr)
    d = np.sqrt(np.maximum(qu, 0) ** 2 + np.maximum(qv, 0) ** 2) + np.minimum(np.maximum(qu, qv), 0) - rr
    d = smax(d, (COLLAR_SIDE_Z - Z) + 0 * d, 1.5)
    return sl, d.astype(np.float32)


def add(grid, field, k=BLEND):
    sl, d = field
    grid.d[sl] = smin(grid.d[sl], d, k)


# ---------------------------------------------------------------------------------------
# clearance carving

def keepout_sets(parts):
    """(name, points, clearance) for every set of parts the shell must keep away from."""
    in_grid = lambda P: np.all((P > GRID_LO - 5) & (P < GRID_HI + 5), axis=1)  # noqa: E731
    sets = []
    fixed = np.vstack([hm.surface_points(hm.ref(n)) for n in hm.FIXED_PARTS.values()])
    sets.append(("fixed parts", fixed, p.STATIC_MARGIN))
    sets.append(("roll servo", hm.surface_points(hm.ref(hm.ROLL_SERVO)), p.ROLL_SERVO_MARGIN))
    sets.append(("face plate", hm.surface_points(hm.ref("face_part_duckbuddy"), 0.2), 0.4))
    pi = np.vstack([hm.surface_points(parts[k]) for k in ("pi", "pi_zone")])
    sets.append(("pi", pi, p.PI_MARGIN))
    sets.append(("hat parts", hm.surface_points(parts["hat_parts"], 0.2, cap=1500000), p.HAT_PARTS_MARGIN))
    bottom = hm.surface_points(hm.ref("bottom_head_shell_duckbuddy"))
    near_boss = np.zeros(len(bottom), bool)
    for x, y in (p.BOSS_BACK, *p.BOSS_FRONT):
        near_boss |= np.hypot(bottom[:, 0] - x, bottom[:, 1] - y) < p.BOSS_D / 2 + 1.5
    sets.append(("bottom shell", bottom[~near_boss], 0.3))
    # the moving neck parts over the whole head-roll and head-yaw range
    above, below = hm.moving_meshes()
    A, Bp = hm.surface_points(above, 0.35), hm.surface_points(below, 0.35)
    region = lambda P: in_grid(P) & (P[:, 2] > 5.0)  # noqa: E731
    cells = set()
    chunks = []
    for _, P in hm.sweep(A, Bp, roll_step=1.0, yaw_step=10.0, keep=region):
        key = np.round(P / 0.2).astype(np.int32)
        _, idx = np.unique(key, axis=0, return_index=True)
        chunks.append(P[idx])
    moving = np.vstack(chunks)
    _, idx = np.unique(np.round(moving / 0.2).astype(np.int32), axis=0, return_index=True)
    sets.append(("moving neck parts", moving[idx], p.MOVING_MARGIN))
    del cells
    return [(n, P[in_grid(P)], c) for n, P, c in sets]


def carve(grid, sets):
    band = grid.d < CARVE_BLEND + 2 * grid.h
    idx = np.nonzero(band)
    pts = np.stack([grid.axes[i][idx[i]] for i in range(3)], axis=1)
    d = grid.d[idx]
    for name, P, clear in sets:
        clear = clear + SAMPLE_ALLOWANCE
        t0 = time.time()
        dist, _ = cKDTree(P).query(pts, distance_upper_bound=clear + CARVE_BLEND + grid.h, workers=-1)
        dist = np.where(np.isfinite(dist), dist, clear + CARVE_BLEND + grid.h).astype(np.float32)
        before = (d < 0).sum()
        d = smax(d, clear - dist, CARVE_BLEND)
        print(f"  carve {name:18s} {len(P):8d} pts, clearance {clear:.1f} mm: "
              f"{before - (d < 0).sum():7d} voxels removed ({time.time() - t0:.1f} s)")
    grid.d[idx] = d


# ---------------------------------------------------------------------------------------
# exact features (manifold booleans on the mesh)

def m_box(x0, x1, y0, y1, z0, z1):
    return m3.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def m_cyl(x, y, z0, z1, r, r_top=None):
    return m3.Manifold.cylinder(z1 - z0, r, r if r_top is None else r_top, 96).translate([x, y, z0])


def m_cyl_x(x0, x1, y, z, r):
    """Cylinder along X."""
    return m3.Manifold.cylinder(x1 - x0, r, r, 96).rotate([0, 90, 0]).translate([x0, y, z])


def to_manifold(mesh):
    man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                              tri_verts=np.asarray(mesh.faces, np.uint32)))
    assert man.status() == m3.Error.NoError, man.status()
    return man


def to_trimesh(man):
    out = man.to_mesh()
    return trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts), process=False)


def exact_features(body):
    cut = []
    # contact plane on the bottom shell's bosses
    body = body ^ m_box(-100, 100, -100, 100, p.BOSS_Z0, 100)
    # back boss flattened in front of the roll servo
    cut.append(m_box(p.ROLL_SERVO_BACK_X - p.ROLL_SERVO_GAP, -15, -12, 12, -10, p.ROLL_SERVO_TOP_Z + 1.0))
    # M3 pilots with an entry chamfer, from below
    for x, y in (p.BOSS_BACK, *p.BOSS_FRONT):
        cut.append(m_cyl(x, y, p.BOSS_Z0 - 0.1, p.BOSS_Z0 + p.M3_PILOT_DEPTH, p.M3_PILOT_D / 2))
        cut.append(m_cyl(x, y, p.BOSS_Z0 - 0.01, p.BOSS_Z0 + p.M3_CHAMFER, p.M3_PILOT_D / 2 + p.M3_CHAMFER, p.M3_PILOT_D / 2))
    # the HAT board: nothing above its underside within its outline (flat standoff tops)
    bx = (p.HAT_X0 + p.HAT_BOARD_X[0] - 1.0, p.HAT_X0 + p.HAT_BOARD_X[1] + 1.0)
    by = (p.HAT_Y0 + p.HAT_BOARD_Y[0] - 1.0, p.HAT_Y0 + p.HAT_BOARD_Y[1] + 1.0)
    cut.append(m_box(*bx, *by, p.HAT_BOTTOM_Z, 100))
    for hx, hy in p.HAT_HOLES:
        x, y = p.hat_hole_xy(hx, hy)
        cut.append(m_cyl(x, y, p.HAT_BOTTOM_Z - p.M25_PILOT_DEPTH, p.HAT_BOTTOM_Z + 0.1, p.M25_PILOT_D / 2))
    # speaker: pocket, ear flanges, floor window, wire exit towards the HAT
    x0, x1, y0, y1 = SPK_IN
    cut.append(m_box(x0, x1, y0, y1, p.SPK_SEAT_Z, 100))
    half = p.SPK_EAR_PITCH / 2 + p.SPK_EAR_END + p.SPK_CLEAR
    cx, cy = p.SPK_CENTER
    w = p.SPK_EAR_W / 2 + p.SPK_CLEAR
    cut.append(m_box(cx - half, cx + half, cy - w, cy + w, EAR_TOP_Z, 100))
    cut.append(m_box(cx - WIRE_EXIT_W / 2, cx + WIRE_EXIT_W / 2, y0 - 8.0, y0 + 0.1, p.SPK_SEAT_Z, 100))
    for x in EAR_X:
        cut.append(m_cyl(x, EAR_Y, EAR_TOP_Z - p.M2_PILOT_DEPTH, EAR_TOP_Z + 0.1, p.M2_PILOT_D / 2))
    # face plate slot in the collar, clear of the Pi's upper standoffs
    cs = m3.CrossSection([face_outline().tolist()], m3.FillRule.NonZero).offset(p.COLLAR_GAP, m3.JoinType.Round)
    slot = m3.Manifold.extrude(cs, p.FACE_SLOT_X[1] - p.FACE_SLOT_X[0])
    # extrusion frame (a, b, c) = (Y, Z, X) -> head frame
    cut.append(slot.transform([[0, 0, 1, p.FACE_SLOT_X[0]], [1, 0, 0, 0], [0, 1, 0, 0]]))
    for y, z in p.FACE_STANDOFFS:
        cut.append(m_cyl_x(55.0, p.FACE_SLOT_X[0] + 0.01, y, z, p.FACE_STANDOFF_CLEAR_R))
    return body - m3.Manifold.batch_boolean(cut, m3.OpType.Add)


# ---------------------------------------------------------------------------------------

def build(res):
    t0 = time.time()
    hm.build_parts()
    parts = hm.load_parts()
    grid = Grid(res)
    print(f"grid {grid.n.tolist()} at {res} mm")
    for name, pts in BRANCHES.items():
        add(grid, branch_field(grid, pts))
    add(grid, tray_ring_field(grid))
    add(grid, collar_field(grid), 3.0)
    print(f"frame field {time.time() - t0:.1f} s")
    sets = keepout_sets(parts)
    print(f"clearance sets {time.time() - t0:.1f} s")
    carve(grid, sets)
    grid.d[[0, -1], :, :] = BIG
    grid.d[:, [0, -1], :] = BIG
    grid.d[:, :, [0, -1]] = BIG
    verts, faces, _, _ = marching_cubes(grid.d, level=0.0, spacing=(res, res, res))
    mesh = trimesh.Trimesh(verts + GRID_LO, faces, process=False)  # watertight as it comes; merging would break it
    if mesh.volume < 0:
        mesh.invert()
    trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53, iterations=10)
    print(f"meshed {len(mesh.faces)} faces, watertight {mesh.is_watertight} ({time.time() - t0:.1f} s)")
    body = exact_features(to_manifold(mesh))
    # keep the main body; crumbs under 1 mm3 (left where the carving grazes a branch) are dropped
    pieces = sorted(body.decompose(), key=lambda q: -q.volume())
    lost = [q.volume() for q in pieces[1:] if q.volume() > 1.0]
    if lost:
        print(f"WARNING: the frame is in {1 + len(lost)} pieces; extra pieces {np.round(lost, 1).tolist()} mm3")
    body = pieces[0]
    shell = to_trimesh(body)
    print(f"shell {len(shell.faces)} faces, volume {shell.volume / 1000:.1f} cm3, "
          f"bounds {np.round(shell.bounds, 1).tolist()}, watertight {shell.is_watertight} ({time.time() - t0:.1f} s)")
    return shell, 1 + len(lost)


def write_review(shell, path):
    scene = trimesh.load(hm.PARTS_GLB)
    s = shell.copy()
    s.apply_transform(hm.HEAD_TO_GLTF)
    s.visual.face_colors = [232, 116, 44, 255]
    scene.add_geometry(s, node_name="open_head_shell", geom_name="open_head_shell")
    scene.export(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--res", type=float, default=0.3, help="voxel size in mm (default 0.3)")
    ap.add_argument("--out", type=Path, default=hm.TMP / "open_head_shell.stl")
    a = ap.parse_args()
    shell, n = build(a.res)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    shell.export(a.out)
    write_review(shell, hm.TMP / "open_head_review.glb")
    print(f"wrote {a.out} and {hm.TMP / 'open_head_review.glb'}")
    return 0 if n == 1 and shell.is_watertight else 1


if __name__ == "__main__":
    sys.exit(main())
