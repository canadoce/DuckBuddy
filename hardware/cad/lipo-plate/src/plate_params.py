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

# The LiPo: OVONIC 3S 2200 mAh 35C, 75 x 33 x 26 mm (+-3 mm), 142 g weighed, standing up, flat on the
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
# back. The pack rests on the pad's back (REST_X), the strap pulls it on.
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

# The two brackets on the plate's front face that screw the plate to the two rear hip servos, as on
# the old plate (measured from the print part): one under the servos, one on their tops, each with
# two tabs and an M2 screw hole into the servo's inner screw holes (X -16.5, Y +-9.5), a thin bar
# between the tabs and a lip at each tab's outer end. They hold the plate, and with it the pack,
# to the servos and the body.
BRACKET_X1 = -14.0  # the tabs' front end
BRACKET_HOLE = (-16.5, 9.5)  # X, |Y|
BRACKET_HOLE_D = 2.5
BRACKET_TAB_Y = (6.5, 12.5)  # |Y|
BRACKET_TAB_T = 2.0
BRACKET_BAR_X1, BRACKET_BAR_T = -16.5, 1.0
BRACKET_LIP_Y0, BRACKET_LIP_H = 11.5, 2.0
SERVO_BOTTOM_Z, SERVO_TOP_Z = -1.26, 23.14  # the faces the lower and upper tabs rest on
BRACKET_LIP_X1 = {-1: -16.8, 1: -17.0}  # lower, upper

# The BNO055 (Adafruit 4646: 25.4 x 20.32 mm, M2.5 holes 20.32 x 15.24 mm apart) is not on the
# plate: the lower bracket's screws go up into the servos from below, where it stood. It lies flat,
# chip up, straight on the tops of the two rear hip servos, held by its own mount (imu_mount in
# src/plate.py): a thin frame on the servo tops, screwed into each servo's horn screw hole (the
# passive horns are left off) and outer top hole (X -16.5, Y +-25.5, as hardware/pcb/pdb-imu uses
# them). The board slides into the frame from behind, under a lip along each side, up to the front
# rail; the plate's upper bracket tabs, 0.2 mm behind it, keep it from sliding back out. It sits
# low because the head bows forward in the stand-up and the roll and the neck comes down to Z 31
# over the front of the servos (tools/head_reach.py); its parts' top stays 3.4 mm under that.
# The board's long side runs across the robot, its Qwiic sockets at its left and right ends.
BNO_BOARD = (25.4, 20.32)  # across (Y), along (X)
PCB_T = 1.6
BNO_PARTS_H = 3.0  # the parts on the board, taken as a 3 mm block (the Qwiic sockets are the tallest)
QWIIC_H, QWIIC_W, QWIIC_OUT = 3.2, 7.0, 6.0  # the plug: height, width, reach past the board's edge
BNO_X0 = BRACKET_X1 + 0.2  # the board's back edge, 0.2 mm in front of the upper bracket's tabs
BOARD_GAP = 0.2  # between the board's edges and the frame
FRAME_T = 1.4  # the rails, under the board's top face
RAIL_W = 2.0
RAIL_LIP_OVER, RAIL_LIP_T, RAIL_LIP_GAP = 0.8, 0.8, 0.1  # the side lips: over the board's edge, thickness, over its top face
RAIL_LIP_SKIP = 4.5  # no lip within this of the Qwiic sockets' centre (X), on both sides
RAIL_LIP_SETBACK = 0.5  # the lips start this far in front of the board's back edge, clear of the bracket tabs' rounded fronts
MOUNT_HOLE = (-16.5, 25.5)  # X, |Y|: the servos' outer top holes
HORN_HOLE = (6.0, 17.5)  # X, |Y|: the servos' axes, where the passive horn's screw goes
HORN_BOSS_D, HORN_BOSS_H = 6.0, 3.0  # as tall as the horn left off (Z 23 to 26), so its screw fits
ARM_T = 2.0
ARM_BACK_X = -18.4  # flat backs of the arms to the outer holes, 1 mm in front of the shells' back wall
ARM_Y0 = 13.0  # the arms' inner side, 0.5 mm outside the upper bracket's tabs
M2_CLEAR_D = 2.4
STANDOFF_D = 5.0  # the round ends of the arms around the outer holes (1.2 mm from the shells' sides)


def bno_center():
    """The board's centre (X, Y) and the Z of its underside (on the servo tops)."""
    return BNO_X0 + BNO_BOARD[1] / 2, 0.0, SERVO_TOP_Z


# The pack's leads leave at its bottom, backwards through the cup's back lip and floor.
LEAD_EXIT_W = 14.0
LEAD_EXIT_DEPTH = 9.0  # how far the opening reaches into the floor from the back lip


def lipo_box(tol=0.0):
    """The pack standing on the cup's floor, flat on the pad: (x0, x1, y0, y1, z0, z1).
    tol=LIPO_TOL gives the largest pack the cup takes."""
    length, width, thick = (v + tol for v in LIPO)
    return (REST_X - thick, REST_X, -width / 2, width / 2, FLOOR_TOP_Z, FLOOR_TOP_Z + length)
