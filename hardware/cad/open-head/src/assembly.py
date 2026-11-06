"""The boards and the speaker placed in the head frame, for the shell generator, the fit
check and the review.

The Robot HAT is the board's own STEP (vendor/robot_hat_e1.xbf). The speaker and the
Orange Pi Zero 3W with its cooling shield and Dupont plugs are stand-ins with their
outer sizes. The shell itself is a mesh (src/organic_shell.py), which a CAD document
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


@model
def open_head_parts():
    kit = bd.Compound(children=[hat(), speaker(), orange_pi()])
    kit.label = "open_head_parts"
    return kit


if __name__ == "__main__":
    open_head_parts()
