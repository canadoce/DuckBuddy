"""Dimensions of the LiPo battery plate, in the trunk frame.

Trunk frame: X forward, Y to the robot's left, Z up, in mm, the MuJoCo trunk_base body
frame of the Microduck model (tools/trunk_meshes.py). The old battery plate
(power_support) stands upright at the back of the trunk, its flat back face at X -23 and
its front face at X -21. The shells' back opening is free for |Y| < 20 below their lip;
the lowest part above the battery space (the shell's tube) is at Z 31.24.
"""

# The old plate's faces, and the back of the features at its top (shelf, hinge knuckles,
# blocks) that meet the shells and the locker. They are copied from the print part.
PLATE_BACK_X = -23.0
PLATE_FRONT_X = -21.0
TOP_BACK_X = -30.8
PLATE_EDGE_Y = 21.4  # half-width of the plate's lower part

# The LiPo: OVONIC 3S 2200 mAh 35C, 75 x 33 x 26 mm (+-3 mm), 139 g, standing up, flat on the
# plate's back, its 33 mm side across the robot. The cup takes the largest size, 78 x 36 x 29.
LIPO = (75.0, 33.0, 26.0)  # length (Z), width (Y), thickness (X)
LIPO_TOL = 3.0
LIPO_TOP_MAX = 30.5  # the top of the longest pack: 0.74 mm under the shell's tube

# The cup under the pack, below the plate's old bottom edge (Z -40). The plate ends at the cup's
# bottom, as high as the pack allows: in the simulation the forward roll (roulade) fails when the
# body's bottom reaches further down (it did with a rim down to Z -55).
# The lips stay inside the shells' back opening (|Y| < 20), which the plate passes through when
# it slides up into the shells: inside half-width 18 (the widest pack), outside 19.5.
CUP_IN_Y = (LIPO[1] + LIPO_TOL) / 2
FLOOR_TOP_Z = LIPO_TOP_MAX - (LIPO[0] + LIPO_TOL)  # -47.5
FLOOR_T = 2.0
PLATE_BOTTOM_Z = FLOOR_TOP_Z - FLOOR_T  # -49.5
LIP_T = 1.5
LIP_H = 8.0  # lips 8 mm above the floor

# One velcro strap, 27 mm wide, around the pack and through a flat channel in a pad on the plate's
# back, behind the BNO055. The pack rests on the pad's back (REST_X), the strap pulls it on.
# The channel takes a strap up to STRAP_T thick.
# The channel runs across between the plate and the pad's skin and opens at the pad's sides,
# inside the shells' back opening like the cup's lips. A rib near the top keeps the pack parallel.
STRAP_W = 27.0
STRAP_T = 2.0  # the strap's thickness, one layer
CHANNEL_GAP = STRAP_T + 0.2
CHANNEL_H = STRAP_W + 1.0
CHANNEL_Z1 = -4.5  # channel top: the strap from Z -5 to -32, centred on the pack's part below the shells
CHANNEL_Z0 = CHANNEL_Z1 - CHANNEL_H
CHANNEL_IN_PLATE = 1.0  # the channel's front 1 mm is cut into the plate, which keeps 1 mm in front of it
SKIN_T = 1.2  # the pad's skin behind the channel
CHANNEL_WALL = 2.0  # pad above the channel
PAD_Y = CUP_IN_Y + LIP_T  # 19.5, as the cup
# The face the pack rests on, 2.4 mm behind the old plate's back face: in the simulation the
# forward roll still works as with the old battery with the pack up to about 2.4 mm further back.
REST_X = PLATE_BACK_X - (CHANNEL_GAP - CHANNEL_IN_PLATE) - SKIN_T  # -25.4
RIB_Z = (16.0, 24.0)
RIB_Y = 12.0
CUP_IN_X = REST_X - (LIPO[2] + LIPO_TOL) - 0.75  # inside of the back lip

# The BNO055 (Adafruit 4646: 25.4 x 20.32 mm, M2.5 holes 20.32 x 15.24 mm apart) on the plate's
# front face, just under the hip-yaw servos (their bottom is at Z -3.0) and the trunk floor,
# standing on end (its long side up, 20.32 mm across the robot) with its parts facing forward.
# Across the robot it stays inside |Y| 10.2: the hip-roll servos swing in front of it, to X -12.4
# at |Y| 15-20 while the robot walks, gets up or rolls. One Qwiic plug, in the socket at the
# board's bottom edge, points down; the top socket stays empty (the servos are above it).
# Its centre is 2 mm in front of the IMU site of the Microduck model (-21, 0, -14.7) and 2.3 mm
# lower, so the accelerometer reads as the simulated one does. The gap between the legs is too
# narrow (12 mm) to move it further toward the middle of the trunk.
BNO_BOARD = (20.32, 25.4)  # across (Y), up (Z)
BNO_HOLES = (15.24, 20.32)
BNO_TOP_Z = -4.3  # 1.3 mm under the hip-yaw servos
BNO_CENTER = (0.0, BNO_TOP_Z - BNO_BOARD[1] / 2)  # Y, Z
STANDOFF_H = 2.0  # low, so the hip-roll servos swinging in front of it (to X -11.3) stay clear
STANDOFF_D = 4.5
M25_PILOT_D = 2.2
PCB_T = 1.6
BNO_PARTS_H = 3.0  # the parts on the board, taken as a 3 mm block (the Qwiic sockets are the tallest)
QWIIC_H, QWIIC_W, QWIIC_OUT = 3.2, 7.0, 6.0  # the plug: height, width, reach past the board's edge
PILOT_SKIN = 0.4  # the pilot holes stop this far from the strap channel (M2.5 x 4 screws)

# The pack's leads leave at its bottom, backwards through the cup's back lip and floor.
LEAD_EXIT_W = 14.0
LEAD_EXIT_DEPTH = 9.0  # how far the opening reaches into the floor from the back lip


def lipo_box(tol=0.0):
    """The pack standing on the cup's floor, flat on the pad: (x0, x1, y0, y1, z0, z1).
    tol=LIPO_TOL gives the largest pack the cup takes."""
    length, width, thick = (v + tol for v in LIPO)
    return (REST_X - thick, REST_X, -width / 2, width / 2, FLOOR_TOP_Z, FLOOR_TOP_Z + length)


def bno_holes():
    y0, z0 = BNO_CENTER
    return [(y0 + sy * BNO_HOLES[0] / 2, z0 + sz * BNO_HOLES[1] / 2) for sy in (-1, 1) for sz in (-1, 1)]
