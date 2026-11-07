"""A fixed dummy of the HL-2915 servo, to print and mount in place of a faulty one.

The Feetech HL-2915 has the same outer shape, screw holes and output shaft as the Dynamixel
XL330 (hardware/print/README.md), so the dummy is the XL330 from the Microduck CAD
(vendor/xl330.step): the body with its corner holes and cable notch, and both horns (output
and idler) with their four screw holes each, as one solid. Nothing turns: mounted the way the
robot's CAD places the servo, it holds its joint at the zero pose.
"""
import os

import build123d as bd
from cad import model, read_xbf

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "..", "vendor", "xl330.xbf")

# XL330 / HL-2915: a 23 x 20 x 34 mm body, a horn 3 mm proud on each side (29 mm across them).
BODY_X, BODY_Y, BODY_Z = 29.0, 20.0, 34.0


@model
def servo_dummy():
    shape = read_xbf(VENDOR)
    solids = shape.solids()
    assert len(solids) == 1, f"expected one solid, got {len(solids)}"
    dummy = solids[0]
    assert dummy.is_valid, "the solid is not valid"
    size = dummy.bounding_box().size
    for got, want, axis in zip((size.X, size.Y, size.Z), (BODY_X, BODY_Y, BODY_Z), "XYZ"):
        assert abs(got - want) < 0.05, f"{axis}: {got:.2f} mm, expected {want} mm"
    assert dummy.volume > 15000, f"volume {dummy.volume:.0f} mm^3: not a closed solid?"
    dummy.label = "servo_dummy"
    dummy.color = "#e0a030"
    return dummy


if __name__ == "__main__":
    servo_dummy()
