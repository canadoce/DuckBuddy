# /// script
# dependencies = ["numpy", "scipy", "trimesh", "rtree", "manifold3d", "networkx", "lxml"]
# ///
"""The head's face plate for the Radxa Camera 8M 219, the SparkFun Qwiic Mini ToF Imager and a 1 W LED.

Run from hardware/cad/face-plate:

    uv run src/face_plate.py

It starts from the DuckBuddy face plate (../open-head/reference/face_part_duckbuddy.stl, in
the head frame) and changes only the two sensor mounts:
- camera: cuts off the four standoffs of the old IMX219 board (21 x 13.5 mm hole pattern),
  widens the lens hole to 15 mm and adds four 5 mm standoffs with M2 pilots on the Radxa
  board's 28 x 28 mm holes;
- ToF: cuts off the old ToF frame (a 3 mm frame for a board with 19.8 mm hole pitch) and fills
  its two blind holes, then adds two pins on the SparkFun Mini's 20.32 mm holes and four 0.3 mm
  pads: the board lies on the plate's back with its sensor in the ToF window.
- LED: a 6.4 mm hole on the robot's right of the camera, mirroring the ToF window, with a cup
  on the back that seats a 1 W LED emitter (collar on the plate, dome through the hole) and
  slots for its two leads.
The outline, the Pi standoffs, the ToF window and the three slots for the eye piece stay as
they are. Dimensions: ../open-head/src/head_params.py.

Writes tmp/face_plate.stl (head frame), tmp/face_plate_review.glb (with the camera, the ToF, the LED, the Pi,
the bottom shell and the eye piece) and the print files STL/face_plate.stl and
3MF/face_plate.3mf (front face down on the bed).
"""

import sys
from pathlib import Path

import manifold3d as m3
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "open-head" / "src"))
import head_meshes as hm  # noqa: E402
import head_params as p  # noqa: E402

TMP = ROOT / "tmp"
SEGMENTS = 64


def manifold(m):
    man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                              tri_verts=np.asarray(m.faces, np.uint32)))
    assert man.status() == m3.Error.NoError, f"not a solid: {man.status()}"
    return man


def to_trimesh(man):
    mesh = man.to_mesh()
    return trimesh.Trimesh(mesh.vert_properties[:, :3], mesh.tri_verts, process=False)


def xbox(x0, x1, y0, y1, z0, z1):
    return m3.Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def xcyl(x0, x1, y, z, r0, r1=None):
    """A cylinder (or cone) along +X from x0 to x1, radius r0 at x0 and r1 at x1."""
    c = m3.Manifold.cylinder(x1 - x0, r0, r0 if r1 is None else r1, SEGMENTS)
    return c.rotate((0.0, 90.0, 0.0)).translate((x0, y, z))


def reference_plate():
    """The DuckBuddy plate as one solid: its five mesh bodies (the plate and four glued-on
    camera bosses) joined."""
    bodies = hm.ref("face_part_duckbuddy").split(only_watertight=True)
    solid = manifold(bodies[0])
    for b in bodies[1:]:
        solid = solid + manifold(b)
    return solid


def old_boss_cutter():
    """The old camera standoffs, from their tops to the plate's back face, sparing the ToF
    frame where a standoff was joined to its edge."""
    f = p.PLATE_TOF_FRAME
    s = 0.05
    frame = xbox(f["x"][0] + s, f["x"][1], f["y"][0] + s, f["y"][1] - s, f["z"][0] + s, f["z"][1] - s)
    w = p.PLATE_OLD_BOSS_W / 2 + 0.25
    cut = None
    for yc, zc in p.PLATE_OLD_BOSSES:
        b = xbox(62.0, p.PLATE_BACK_X + 0.01, yc - w, yc + w, zc - w, zc + w) - frame
        cut = b if cut is None else cut + b
    return cut


def old_tof_cutter():
    """The old ToF frame and the raised ring around the window, down to the plate's back face."""
    o = p.PLATE_OLD_TOF
    x_back = p.PLATE_BACK_X + 0.01
    cut = None
    for (x0, y0, z0), (y1, z1) in (o["frame"], o["ring"]):
        b = xbox(x0, x_back, y0, y1, z0, z1)
        cut = b if cut is None else cut + b
    return cut


def old_tof_hole_fill():
    """Plugs for the old frame's two blind screw holes (they end 0.15 mm behind the front face)."""
    o = p.PLATE_OLD_TOF
    fill = None
    for y, z in o["holes"]:
        c = xcyl(p.PLATE_BACK_X - 0.2, o["hole_end_x"], y, z, o["hole_d"] / 2 + 0.1)
        fill = c if fill is None else fill + c
    return fill


def tof_mount():
    """Two pins through the ToF board's holes, with pads under them, and two pads under the board's
    lower corners: the board's front face rests at tof_board_front_x()."""
    x_pad = p.tof_board_front_x()
    x_root = p.PLATE_BACK_X + 0.3
    x_tip = x_pad - p.TOF_BOARD[2] - p.TOF_PIN_PROUD
    chamfer = 0.4
    out = None
    for hy, hz in p.tof_holes():
        pad = xcyl(x_pad, x_root, hy, hz, p.TOF_PAD_D / 2)
        pin = xcyl(x_tip + chamfer, x_pad, hy, hz, p.TOF_PIN_D / 2) + \
            xcyl(x_tip, x_tip + chamfer, hy, hz, p.TOF_PIN_D / 2 - chamfer, p.TOF_PIN_D / 2)
        part = pad + pin
        out = part if out is None else out + part
    c = p.TOF_CORNER_PAD
    for bx in (0.2, p.TOF_BOARD[0] - 0.2 - c):
        (ya, za), (yb, zb) = p.tof_to_head(bx, p.TOF_BOARD[1] - 0.2 - c), p.tof_to_head(bx + c, p.TOF_BOARD[1] - 0.2)
        out = out + xbox(x_pad, x_root, ya, yb, zb, za)
    return out


def led_cup():
    """The LED's seat on the plate's back: a ring around the body with slots for the leads."""
    ly, lz = p.LED_AT
    x0, x1 = p.PLATE_BACK_X - p.LED_CUP_DEPTH, p.PLATE_BACK_X + 0.3
    r_in = p.LED_CUP_ID / 2
    ring = xcyl(x0, x1, ly, lz, r_in + p.LED_CUP_WALL) - xcyl(x0 - 0.1, x1 + 0.1, ly, lz, r_in)
    w = p.LED_SLOT_W / 2
    slots = xbox(x0 - 0.1, p.PLATE_BACK_X, ly - w, ly + w, lz - r_in - p.LED_CUP_WALL - 1, lz + r_in + p.LED_CUP_WALL + 1)
    return ring - slots


def new_standoffs():
    """Round standoffs with M2 pilots on the Radxa board's holes, rooted in the plate."""
    x0, x1 = p.CAM_FRONT_X, p.PLATE_BACK_X + p.CAM_BOSS_ROOT
    chamfer = 0.4
    out = None
    for hy, hz in p.cam_holes():
        boss = xcyl(x0, x1, hy, hz, p.CAM_BOSS_D / 2)
        pilot = xcyl(x0 - 0.1, x0 + p.M2_PILOT_DEPTH, hy, hz, p.M2_PILOT_D / 2)
        mouth = xcyl(x0 - 0.1, x0 + chamfer, hy, hz, p.M2_PILOT_D / 2 + chamfer + 0.1, p.M2_PILOT_D / 2)
        boss = boss - pilot - mouth
        out = boss if out is None else out + boss
    return out


def build():
    cy, cz = p.CAM_AXIS
    plate = reference_plate()
    plate = plate - old_boss_cutter()
    plate = plate - xcyl(p.PLATE_BACK_X - 1.0, p.PLATE_FRONT_X + 1.0, cy, cz, p.PLATE_LENS_HOLE_D / 2)
    plate = plate + new_standoffs()
    plate = (plate + old_tof_hole_fill()) - old_tof_cutter()
    plate = plate + tof_mount()
    ly, lz = p.LED_AT
    plate = (plate + led_cup()) - xcyl(p.PLATE_BACK_X - 1.0, p.PLATE_FRONT_X + 1.0, ly, lz, p.LED_HOLE_D / 2)
    pieces = sorted(plate.decompose(), key=lambda q: -q.volume())
    if len(pieces) > 1:
        print(f"WARNING: {len(pieces)} pieces; extra volumes {[round(q.volume(), 2) for q in pieces[1:]]} mm3")
    mesh = to_trimesh(pieces[0])
    print(f"plate: {len(mesh.faces)} faces, watertight {mesh.is_watertight}, volume {mesh.volume / 1000:.2f} cm3, "
          f"bounds {np.round(mesh.bounds, 2).tolist()}")
    return mesh


def write_review(plate, path):
    if not hm.PARTS_GLB.exists():
        hm.build_parts()
    scene = trimesh.load(hm.PARTS_GLB)
    keep = set()
    for node in scene.graph.nodes_geometry:
        _, gname = scene.graph[node]
        if gname and ("camera" in node.lower() or "pi_" in node.lower() or "tof_" in node.lower() or "led_1w" in node.lower()):
            keep.add(gname)
    scene.delete_geometry(set(scene.geometry) - keep)
    for name, m, color in (("face_plate", plate, hm.REVIEW_FACE),
                           ("bottom_head_shell", hm.ref("bottom_head_shell_duckbuddy"), hm.REVIEW_MOUTH),
                           ("eye_piece", hm.ref("noenoeil"), hm.REVIEW_EYE)):
        m = m.copy()
        m.apply_transform(hm.HEAD_TO_GLTF)
        m.visual = hm.plain_material(color)
        scene.add_geometry(m, node_name=name, geom_name=name)
    scene.export(path)


def main():
    TMP.mkdir(exist_ok=True)
    plate = build()
    plate.export(TMP / "face_plate.stl")
    write_review(plate, TMP / "face_plate_review.glb")
    printed = plate.copy()
    printed.apply_transform(hm.plate_print_matrix())
    assert abs(printed.bounds[0][2]) < 0.05, "the front face is not on the bed"
    for d in ("STL", "3MF"):
        (ROOT / d).mkdir(exist_ok=True)
    printed.export(ROOT / "STL" / "face_plate.stl")
    printed.export(ROOT / "3MF" / "face_plate.3mf")
    print(f"wrote {TMP / 'face_plate.stl'}, {TMP / 'face_plate_review.glb'}, STL/face_plate.stl, 3MF/face_plate.3mf "
          f"(print size {np.round(printed.extents, 1).tolist()} mm)")
    return 0 if plate.is_watertight else 1


if __name__ == "__main__":
    sys.exit(main())
