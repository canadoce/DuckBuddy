"""Dimensions shared by the open head shell generator, the parts assembly and the fit check.

Head frame: X forward, Y to the robot's left, Z up, in mm. The origin is on the
head-roll servo axis. The reference meshes in ../reference use the same frame.
Plain Python on purpose: the shell generator runs outside the CAD server.
"""

# Mount points shared with the bottom head shell (measured on the DuckBuddy shells).
BOSS_BACK = (-31.5, 0.0)
BOSS_FRONT = ((67.5, 39.0), (67.5, -39.0))
BOSS_Z0 = -1.2            # contact plane (bottom-shell boss tops at -1.25 to -1.38)
BOSS_D = 7.0
M3_PILOT_D = 2.5          # M3 self-tapping into PETG
M3_PILOT_DEPTH = 12.0
M3_CHAMFER = 0.6

# The roll servo's back face is at X -29.0, 2.5 mm from the back screw axis. The back
# boss is flattened there with a 0.5 mm gap (the servo is fixed in the head; the old
# top shell touched it). The pilot keeps a 0.75 mm wall on that side.
ROLL_SERVO_BACK_X = -29.0
ROLL_SERVO_GAP = 0.5
ROLL_SERVO_TOP_Z = 10.0

# Robot HAT E1 placement. HAT STEP frame: origin on the hole next to the fuse,
# X along the board towards the Pi-header end, Y across, component side +Z.
HAT_X0 = -23.5            # head X of the HAT's x = 0 hole line
HAT_Y0 = 2.0              # head Y of the HAT's y = 0 hole line
HAT_BOTTOM_Z = 25.2       # underside of the HAT board (see HAT_MOVING_MARGIN)
HAT_HOLES = ((0.0, 0.0), (58.0, 0.0), (0.0, -23.0), (58.0, -23.0))
HAT_BOARD_X = (-22.5, 61.5)  # board outline in the HAT frame
HAT_BOARD_Y = (-26.5, 4.4)
STANDOFF_D = 6.0
M25_PILOT_D = 2.2         # M2.5 self-tapping
M25_PILOT_DEPTH = 7.0

# Speaker QY2831F16 (2 W, 6 ohm): body 28 x 31 x 15, ear holes 2 mm at 36.5 mm,
# ear flange top 6 mm above the box bottom (measured).
SPK_BODY = (28.0, 31.0, 15.0)
SPK_EAR_PITCH = 36.5
SPK_EAR_TOP = 6.0
SPK_EAR_T = 2.0           # assumed flange thickness
SPK_EAR_W = 8.0           # flange width across the ears (stand-in)
SPK_EAR_END = 3.75        # flange beyond the ear hole centre (44 mm across the ears)
SPK_CENTER = (16.0, 29.0)  # body centre in head X, Y
SPK_SEAT_Z = 18.5         # speaker box bottom
SPK_CLEAR = 0.5
M2_PILOT_D = 1.6
M2_PILOT_DEPTH = 6.0

# Face plate clamp (collar). Plate back face at X 72.2, front face at X 73.4.
FACE_SLOT_X = (71.8, 73.9)
COLLAR_X = (69.4, 76.2)
COLLAR_OUT = 2.8          # wall beyond the plate edge
COLLAR_LIP = 2.5          # lips over the plate faces
COLLAR_GAP = 0.4          # radial clearance at the plate edge
COLLAR_Z_MIN = 18.0       # collar covers the plate edge above this height
# Upper Pi standoffs on the back of the face plate: the collar keeps clear of them.
FACE_STANDOFFS = ((29.0, 26.9), (-29.0, 26.9))
FACE_STANDOFF_CLEAR_R = 3.9

# Orange Pi Zero 3W on the face-plate standoffs: board 65 x 30 x 1.6, component side
# facing back, 40-pin header on the top edge, cooling shield about 12 mm tall.
PI_BOARD_X = (59.2, 60.8)
PI_Y = 32.5
PI_Z = (0.4, 30.4)
PI_SHIELD_T = 12.0
PI_SHIELD_Y = 24.0
PI_HEADER = dict(y=(-25.4, 25.4), z=(24.6, 29.6), length=8.5)
DUPONT_LENGTH = 14.0

# Clearances the shell keeps (the fit check measures them).
MOVING_MARGIN = 3.0       # shell and speaker to the neck parts that move under the head
# The HAT's underside parts (U1, J2) come within 1 mm of the neck parts at full head roll
# (-25 deg). Accepted: raising the HAT 2 mm would give 3 mm.
HAT_MOVING_MARGIN = 1.0
STATIC_MARGIN = 1.0       # to the parts fixed in the head
PI_MARGIN = 2.0           # to the Pi, its cooling shield and the Dupont plugs
HAT_PARTS_MARGIN = 1.0    # to the parts under the HAT board
ROLL_SERVO_MARGIN = ROLL_SERVO_GAP


def hat_hole_xy(hx, hy):
    return HAT_X0 + hx, HAT_Y0 + hy
