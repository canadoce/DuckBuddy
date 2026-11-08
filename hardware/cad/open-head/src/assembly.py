"""The boards and the speaker placed in the head frame, for the shell generator, the fit
check and the review.

The Robot HAT is the board's own STEP (vendor/robot_hat_e1.xbf). The speaker, the
Orange Pi Zero 3W with its cooling shield and Dupont plugs, and the Radxa camera and the
SparkFun ToF board and the LED behind the face plate are stand-ins with their outer sizes. The shell itself is a mesh (src/organic_shell.py), which a CAD document
cannot hold, so it is joined to these parts in the review file the generator writes.
"""

from pathlib import Path

import build123d as bd
from cad import model, read_xbf

import head_params as p

VENDOR = Path(__file__).resolve().parent.parent / "vendor"

# The HAT STEP puts the board top at z 0.59 and bottom-side parts from z -0.4 down,
# so z -0.4 is taken as the board underside.
HAT_STEP_UNDERSIDE_Z = -0.4


def box(x0, x1, y0, y1, z0, z1):
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * bd.Box(x1 - x0, y1 - y0, z1 - z0)


def leaves(node, word, loc, path=""):
    """The leaf parts under node in world placement, leaving out sub-trees whose label has word."""
    loc = loc * node.location
    path = f"{path}/{node.label}"
    if node.children:
        for c in node.children:
            if word not in (c.label or ""):
                yield from leaves(c, word, loc, path)
    else:
        part = node.located(loc)
        part.label = path.rsplit("/", 2)[-2] + "/" + str(node.label)  # reference designator / model
        yield part


def hat():
    """The HAT STEP, flattened to its leaf parts, without the Pi Zero the STEP carries under it.

    A compound keeps the shape it was made with, and making one from children resets their
    locations, so the parts are placed in world coordinates and their locations put back.
    """
    place = bd.Location((p.HAT_X0, p.HAT_Y0, p.HAT_BOTTOM_Z - HAT_STEP_UNDERSIDE_Z))
    parts = list(leaves(read_xbf(VENDOR / "robot_hat_e1.xbf"), "rasp_pi_zero", place))
    locations = [q.location for q in parts]
    tree = bd.Compound(children=parts)
    for q, loc in zip(parts, locations):
        q.location = loc
    tree.label = "robot_hat_e1"
    return tree


def speaker():
    cx, cy = p.SPK_CENTER
    bx, by, bz = p.SPK_BODY
    z0 = p.SPK_SEAT_Z
    body = box(cx - bx / 2, cx + bx / 2, cy - by / 2, cy + by / 2, z0, z0 + bz)
    half = p.SPK_EAR_PITCH / 2 + p.SPK_EAR_END
    ears = box(cx - half, cx + half, cy - p.SPK_EAR_W / 2, cy + p.SPK_EAR_W / 2,
               z0 + p.SPK_EAR_TOP - p.SPK_EAR_T, z0 + p.SPK_EAR_TOP)
    spk = body + ears
    spk.label = "speaker"
    spk.color = "#222222"
    return spk


def orange_pi():
    board = box(*p.PI_BOARD_X, -p.PI_Y, p.PI_Y, *p.PI_Z)
    board.label = "pi_board"
    board.color = "#1f6f43"
    x0 = p.PI_BOARD_X[0]
    shield = box(x0 - p.PI_SHIELD_T, x0, -p.PI_SHIELD_Y, p.PI_SHIELD_Y, p.PI_Z[0] + 2.0, p.PI_Z[1] - 6.0)
    shield.label = "pi_cooling_shield"
    shield.color = "#333333"
    hx0 = x0 - p.PI_HEADER["length"] - p.DUPONT_LENGTH + 6.0
    plugs = box(hx0, x0, *p.PI_HEADER["y"], *p.PI_HEADER["z"])
    plugs.label = "pi_header_dupont_zone"
    plugs.color = "#c9a227"
    pi = bd.Compound(children=[board, shield, plugs])
    pi.label = "orange_pi_zero_3w"
    return pi


def camera():
    """The Radxa Camera 8M 219 behind the face plate: board, lens module, FPC connector."""
    cy, cz = p.CAM_AXIS
    h = p.CAM_BOARD / 2
    x1 = p.CAM_FRONT_X
    x0 = x1 - p.CAM_BOARD_T
    board = box(x0, x1, cy - h, cy + h, cz - h, cz + h)
    for hy, hz in p.cam_holes():
        board -= bd.Pos((x0 + x1) / 2, hy, hz) * bd.Rot(0, 90, 0) * bd.Cylinder(p.CAM_HOLE_D / 2, p.CAM_BOARD_T + 1)
    board.label = "camera_board"
    board.color = "#1f6f43"
    (base_w, base_l), (neck_d, neck_l), (barrel_d, barrel_l) = p.CAM_LENS
    x = x1
    base = box(x, x + base_l, cy - base_w / 2, cy + base_w / 2, cz - base_w / 2, cz + base_w / 2)
    x += base_l
    neck = bd.Pos(x + neck_l / 2, cy, cz) * bd.Rot(0, 90, 0) * bd.Cylinder(neck_d / 2, neck_l)
    x += neck_l
    barrel = bd.Pos(x + barrel_l / 2, cy, cz) * bd.Rot(0, 90, 0) * bd.Cylinder(barrel_d / 2, barrel_l)
    lens = base + neck + barrel
    lens.label = "camera_lens"
    lens.color = "#202020"
    fw, fu, fh = p.CAM_FPC
    fpc = box(x0 - fh, x0, cy - fw / 2, cy + fw / 2, cz - h, cz - h + fu)
    fpc.label = "camera_fpc_connector"
    fpc.color = "#d8c9a3"
    cam = bd.Compound(children=[board, lens, fpc])
    cam.label = "radxa_camera_8m_219"
    return cam


def tof():
    """The SparkFun Qwiic Mini ToF Imager (VL53L5CX) on the back of the face plate: board, sensor
    on its front, the two vertical Qwiic connectors on its back, and the cable plug on the far one."""
    bw, bh, bt = p.TOF_BOARD
    x1 = p.tof_board_front_x()
    x0 = x1 - bt
    (y0, z1), (y1, z0) = p.tof_to_head(0, 0), p.tof_to_head(bw, bh)
    board = box(x0, x1, y0, y1, z0, z1)
    for hy, hz in p.tof_holes():
        board -= bd.Pos((x0 + x1) / 2, hy, hz) * bd.Rot(0, 90, 0) * bd.Cylinder(p.TOF_HOLE_D / 2, bt + 1)
    board.label = "tof_board"
    board.color = "#c4161c"
    sy, sz = p.TOF_SENSOR_AT
    sw, sh, st = p.TOF_SENSOR
    sensor = box(x1, x1 + st, sy - sw / 2, sy + sw / 2, sz - sh / 2, sz + sh / 2)
    sensor.label = "tof_sensor"
    sensor.color = "#202020"
    parts = [board, sensor]
    for i, (cx0, cx1) in enumerate(p.TOF_CONNECTORS_X):
        (ya, za), (yb, zb) = p.tof_to_head(cx0, p.TOF_CONNECTOR_Y[0]), p.tof_to_head(cx1, p.TOF_CONNECTOR_Y[1])
        c = box(x0 - p.TOF_CONNECTOR_H, x0, ya, yb, zb, za)
        c.label = f"tof_qwiic_{i + 1}"
        c.color = "#e8e8e8"
        parts.append(c)
        if i == 1:
            plug = box(x0 - p.TOF_CONNECTOR_H - p.TOF_PLUG, x0 - p.TOF_CONNECTOR_H, ya + 0.6, yb - 0.6, zb + 0.6, za - 0.6)
            plug.label = "tof_qwiic_plug"
            plug.color = "#202020"
            parts.append(plug)
    t = bd.Compound(children=parts)
    t.label = "sparkfun_mini_tof_vl53l5cx"
    return t


def led():
    """The 1 W LED emitter behind the face plate, dome forward (sizes partly assumed: head_params)."""
    ly, lz = p.LED_AT
    x = p.PLATE_BACK_X
    cd, cl = p.LED_COLLAR
    bd_, bl = p.LED_BODY
    dd, dh = p.LED_DOME
    collar = bd.Pos(x - cl / 2, ly, lz) * bd.Rot(0, 90, 0) * bd.Cylinder(cd / 2, cl)
    body = bd.Pos(x - cl - bl / 2, ly, lz) * bd.Rot(0, 90, 0) * bd.Cylinder(bd_ / 2, bl)
    dome = bd.Pos(x, ly, lz) * bd.Rot(0, 90, 0) * bd.scale(bd.Sphere(dd / 2), (1, 1, 2 * dh / dd))
    dome = dome & box(x, x + dh + 0.1, ly - dd, ly + dd, lz - dd, lz + dd)
    span, w, t = p.LED_LEADS
    x0 = x - cl - bl
    leads = box(x0, x0 + t, ly - w / 2, ly + w / 2, lz - span / 2, lz + span / 2)
    lamp = collar + body + leads
    lamp.label = "led_body"
    lamp.color = "#e6e6e6"
    dome.label = "led_dome"
    dome.color = "#f2e26b"
    t = bd.Compound(children=[lamp, dome])
    t.label = "led_1w"
    return t


@model
def open_head_parts():
    kit = bd.Compound(children=[hat(), speaker(), orange_pi(), camera(), tof(), led()])
    kit.label = "open_head_parts"
    return kit


if __name__ == "__main__":
    open_head_parts()
