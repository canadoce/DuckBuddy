"""The LiPo battery plate, and stand-ins for the LiPo and the BNO055, in the trunk frame
(see plate_params.py).

The plate replaces the old battery plate (power_support). Its outline and the features at its
top that meet the shells and the locker (shelf, hinge knuckles, blocks) are the old plate's,
measured from the print part; the rest is new: a pad on the back that the LiPo rests on, with a
channel for the strap through it, a cup under the pack, a rib near the top, and four standoffs on
the front face for the BNO055, just under the hip servos.
"""

import build123d as bd
from cad import model

import plate_params as p


def box(x0, x1, y0, y1, z0, z1):
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * bd.Box(x1 - x0, y1 - y0, z1 - z0)


def yz_prism(face, x0, x1):
    """A face drawn in (Y, Z) extruded along X from x0 to x1."""
    return bd.extrude(bd.Plane.YZ.offset(x0) * face, amount=x1 - x0)


def outline():
    """The plate's outline in (Y, Z), corners rounded. Every corner radius is above the 0.5 mm
    rounding of the face edges, so that rounding runs cleanly around the corners."""
    ey, zb = p.PLATE_EDGE_Y, p.PLATE_BOTTOM_Z

    def top_r(y):  # the old top edge, right part
        return 38.2 + (25.4 - y) * 1.2 / 22.0

    def top_l(y):  # left part
        return 38.2 + (y + 25.6) * 0.7 / 14.1

    pts = [  # (y, z, corner radius)
        (-ey, zb, 3.0), (ey, zb, 3.0),
        (ey, 22.8, 1.0), (27.2, 22.8, 2.0), (27.2, top_r(27.2), 2.0), (1.9, top_r(1.9), 1.0),
        (1.9, 34.6, 1.2), (-10.0, 34.6, 1.2), (-10.0, top_l(-10.0), 1.0), (-27.3, top_l(-27.3), 2.0),
        (-27.3, 22.8, 2.0), (-ey, 22.8, 1.0),
    ]
    face = bd.make_face(bd.Polyline(*[(y, z) for y, z, _ in pts], close=True))
    for r in sorted({c for _, _, c in pts}, reverse=True):
        at = [(y, z) for y, z, c in pts if c == r]
        corners = [v for v in face.vertices() if any(abs(v.X - y) < 1e-4 and abs(v.Y - z) < 1e-4 for y, z in at)]
        face = bd.fillet(corners, r)
    return face


def knuckle(s):
    """A hinge knuckle at the plate's top corner (s = +1 left, -1 right), with its pin hole."""
    cy, cz = s * 25.0, 36.03
    head = bd.Pos(cy, cz) * bd.Circle(1.9)
    stem = bd.Pos(cy, 33.15) * bd.Rectangle(1.4, 2.3)
    tab = bd.Pos(s * (21.05 + 23.6) / 2, 36.02) * bd.Rectangle(2.6, 1.36)
    face = head + stem + tab - bd.Pos(cy, cz) * bd.Circle(0.8)
    return yz_prism(face, p.TOP_BACK_X, p.PLATE_BACK_X + 0.2)


def top_features():
    """The shelf, the knuckles and the blocks behind the plate's top, as on the old plate."""
    x0, x1 = p.TOP_BACK_X, p.PLATE_BACK_X + 0.2
    shelf = box(x0, x1, -23.0, 23.0, 31.47, 33.38)
    shelf = bd.fillet(shelf.edges().filter_by(bd.Axis.Z).group_by(bd.Axis.X)[0], 1.8)
    for s in (-1, 1):  # two slots from the back edge, round-ended at X -27.2
        shelf -= bd.Pos(-29.6, s * 16.85, 32.4) * bd.Box(4.8, 2.9, 3.0)
        shelf -= bd.Pos(-27.2, s * 16.85, 32.4) * bd.Cylinder(1.45, 3.0)
    out = shelf + knuckle(1) + knuckle(-1)
    for s in (-1, 1):
        out += box(x0, x1, s * 11.05, s * 12.92, 35.28, 38.1)
    return out


def cup():
    """The floor and 8 mm lips under the pack, with an opening at the back for its leads."""
    yo = p.PAD_Y
    z0, zf = p.PLATE_BOTTOM_Z, p.FLOOR_TOP_Z
    zt = zf + p.LIP_H
    xb = p.CUP_IN_X - p.LIP_T
    outer = box(xb, p.PLATE_BACK_X + 0.5, -yo, yo, z0, zt)
    outer = bd.fillet(outer.edges().filter_by(bd.Axis.Z).group_by(bd.Axis.X)[0], 3.0)
    inner = box(p.CUP_IN_X, p.REST_X, -p.CUP_IN_Y, p.CUP_IN_Y, zf, zt + 1)
    inner = bd.fillet(inner.edges().filter_by(bd.Axis.Z).group_by(bd.Axis.X)[0], 1.5)
    body = outer - inner
    w = p.LEAD_EXIT_W
    xe = p.CUP_IN_X + p.LEAD_EXIT_DEPTH - w / 2
    body -= box(xb - 1, xe, -w / 2, w / 2, z0 - 1, zt + 1)
    body -= bd.Pos(xe, 0, (z0 + zt) / 2) * bd.Cylinder(w / 2, zt - z0 + 2)
    # Round the lips' top edges and the cup's bottom edges (not where it meets the plate).
    top = [e for e in body.edges() if abs(e.center().Z - zt) < 1e-3 and e.center().X < p.REST_X - 0.1]
    body = bd.fillet(top, 0.6)
    bottom = [e for e in body.edges() if abs(e.center().Z - z0) < 1e-3 and e.center().X < p.PLATE_BACK_X - 1]
    return bd.fillet(bottom, 1.0)


def pad():
    """The pad the pack rests on, from the cup up past the strap channel, and the rib near the top."""
    zt = p.CHANNEL_Z1 + p.CHANNEL_WALL
    body = box(p.REST_X, p.PLATE_BACK_X + 0.5, -p.PAD_Y, p.PAD_Y, p.FLOOR_TOP_Z + p.LIP_H - 1, zt)
    # The skin is 1.2 mm thick: its back corners rounded 0.6, its mouth edges (cut_channel) 0.3.
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z).group_by(bd.Axis.X)[0], 0.6)
    back_top = [e for e in body.edges() if abs(e.center().Z - zt) < 1e-3 and e.center().X < p.PLATE_BACK_X - 1]
    body = bd.fillet(back_top, 0.45)
    rib = box(p.REST_X, p.PLATE_BACK_X + 0.5, -p.RIB_Y, p.RIB_Y, *p.RIB_Z)
    rib = bd.fillet(rib.edges().group_by(bd.Axis.X)[0], 1.0)
    return body + rib


def cut_channel(body):
    """The strap channel, from the pad's skin 1 mm into the plate, out through the sides; its
    mouths at the pad's sides rounded, where the strap bends round the pack."""
    body -= box(p.REST_X + p.SKIN_T, p.PLATE_BACK_X + p.CHANNEL_IN_PLATE, -p.PLATE_EDGE_Y - 1, p.PLATE_EDGE_Y + 1,
                p.CHANNEL_Z0, p.CHANNEL_Z1)
    mouths = [e for e in body.edges().filter_by(bd.Axis.Z)
              if abs(abs(e.center().Y) - p.PAD_Y) < 1e-3 and abs(e.center().X - (p.REST_X + p.SKIN_T)) < 1e-3]
    assert len(mouths) == 2, mouths
    return bd.fillet(mouths, 0.3)


def standoffs():
    out = None
    for y, z in p.bno_holes():
        c = bd.Pos(p.PLATE_FRONT_X - 0.3 + (p.STANDOFF_H + 0.3) / 2, y, z) * bd.Rot(0, 90, 0) * bd.Cylinder(
            p.STANDOFF_D / 2, p.STANDOFF_H + 0.3)
        c = bd.chamfer(c.edges().sort_by(bd.Axis.X)[-1], 0.4)
        out = c if out is None else out + c
    return out


@model
def lipo_plate():
    plate = yz_prism(outline(), p.PLATE_BACK_X, p.PLATE_FRONT_X)
    faces = plate.faces().sort_by(bd.Axis.X)
    plate = bd.fillet(faces[-1].edges(), 0.5)  # front face outline
    plate = bd.fillet(plate.faces().sort_by(bd.Axis.X)[0].edges(), 0.3)  # back face outline
    body = cut_channel(plate + top_features() + cup() + pad() + standoffs())
    for y, z in p.bno_holes():  # blind: the face the pack rests on stays whole
        x0, x1 = p.PLATE_BACK_X + p.PILOT_SKIN, p.PLATE_FRONT_X + p.STANDOFF_H + 1
        body -= bd.Pos((x0 + x1) / 2, y, z) * bd.Rot(0, 90, 0) * bd.Cylinder(p.M25_PILOT_D / 2, x1 - x0)
    body.label = "lipo_plate"
    body.color = "#2b2b2b"
    bb = body.bounding_box()
    assert abs(bb.min.Z - p.PLATE_BOTTOM_Z) < 0.01 and abs(bb.max.X - (p.PLATE_FRONT_X + p.STANDOFF_H)) < 0.01, bb
    assert p.CHANNEL_Z1 + p.CHANNEL_WALL < 0, "the channel's mouths below the shells"
    assert len(body.solids()) == 1
    return body


def bno055_board_shape():
    y0, z0 = p.BNO_CENTER
    w, h = p.BNO_BOARD
    x0 = p.PLATE_FRONT_X + p.STANDOFF_H
    pcb = box(x0, x0 + p.PCB_T, y0 - w / 2, y0 + w / 2, z0 - h / 2, z0 + h / 2)
    pcb.label, pcb.color = "bno055_pcb", "#1a1a40"
    xp = x0 + p.PCB_T
    parts = box(xp, xp + p.BNO_PARTS_H, y0 - w / 2 + 1, y0 + w / 2 - 1, z0 - h / 2 + 1, z0 + h / 2 - 1)
    parts.label, parts.color = "bno055_parts", "#555555"
    # The Qwiic plug in the STEMMA QT socket at the board's bottom edge.
    plugs = [box(xp, xp + p.QWIIC_H, y0 - p.QWIIC_W / 2, y0 + p.QWIIC_W / 2, z0 - h / 2 - p.QWIIC_OUT, z0 - h / 2)]
    for q in plugs:
        q.label, q.color = "qwiic_plug", "#dddddd"
    return [pcb, parts] + plugs


@model
def parts_review():
    """The LiPo and the BNO055 with its Qwiic plugs, placed."""
    lipo = box(*p.lipo_box())
    lipo.label, lipo.color = "lipo", "#3060c0"
    return bd.Compound(children=[lipo] + bno055_board_shape(), label="parts")


if __name__ == "__main__":
    lipo_plate()
    parts_review()
