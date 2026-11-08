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

# Face plate rim. Plate back face at X 72.2, front face at X 73.4. The rim frames the
# plate like the original top shell: a band around the plate's arched edge (top and both
# sides, down to the bottom shell), with a lip on the back face, a slot for the plate edge,
# and a brim in front whose face is tilted like the original shell's front (measured on it:
# X 78.3 at the plate's bottom corners, X 84.1 at the top).
FACE_SLOT_X = (71.8, 73.9)
BACK_LIP_X = (69.4, 71.8)
RIM_OUT = 2.5             # band beyond the plate edge (the original: 2.0 to 2.4)
BACK_LIP = 2.5            # lip over the plate's back face
FRONT_LIP = 1.0           # lip over the plate's front face (the original: about 0.7)
RIM_GAP = 0.4             # radial clearance at the plate edge
RIM_ROUND = 1.0           # edge rounding of the band
BRIM_X_BOTTOM = 78.3      # brim front face at the plate's bottom edge (Z OUTLINE_Z_MIN) ...
BRIM_SLOPE = 0.13         # ... rising this much per mm of height ...
BRIM_X_MAX = 84.1         # ... up to the original shell's front
OUTLINE_Z_MIN = -5.3      # bottom edge of the plate outline
# Where the rim meets the bottom shell: on its back lip (top at Z -1.3, like the bosses)
# and on its lower front lip (top at Z -4.3 at the plate's bottom corners). The floor
# ramps between the two across the plate slot, starting and ending clear of the slot faces
# (a ramp edge on a slot face leaves zero-thickness slivers in the mesh).
FLOOR_FRONT_Z = -4.1
FLOOR_RAMP_X = (71.4, 74.3)
# Upper Pi standoffs on the back of the face plate: the rim keeps clear of them.
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


# Camera: Radxa Camera 8M 219 (IMX219) behind the face plate, lens through the plate's hole.
# From Radxa's drawing: board 32 x 32, PCB 1.6, four 2 mm holes at 28 x 28, lens on the board
# centre; lens module 13.2 mm square base, barrel up to 14 mm across, 16 mm in front of the
# board; 15-pin 1.0 mm FPC connector on the back, at the bottom edge.
CAM_AXIS = (0.13, 15.51)  # lens axis in head Y, Z: the plate's lens hole (measured)
CAM_BOARD = 32.0
CAM_BOARD_T = 1.6
CAM_HOLE_PITCH = 28.0
CAM_HOLE_D = 2.0
CAM_FRONT_X = 65.9        # board front face, on the standoff tops (the back parts 1 mm off the Pi)
CAM_LENS = ((13.2, 4.1), (12.0, 5.2), (14.0, 6.7))  # (across, length): square base, neck, barrel
CAM_FPC = (18.0, 4.5, 2.5)  # connector: across, up the board, height off the back face
CAM_MARGIN = 1.0          # shell to the camera

# Face plate: the DuckBuddy plate with the camera and ToF mounts changed (../face-plate). Plate
# faces measured on the reference mesh; the old camera standoffs (21 x 13.5 mm pattern, 4.5 mm
# square) are cut off and 5 mm round standoffs with M2 pilots take the Radxa pattern.
PLATE_FRONT_X = 73.39
PLATE_BACK_X = 72.08      # 72.07 to 72.09 on the mesh
PLATE_LENS_HOLE_D = 15.0  # was 14.5; the lens barrel is 14 at most
PLATE_OLD_BOSSES = ((10.62, 8.90), (10.55, 22.40), (-10.37, 8.78), (-10.45, 22.28))
PLATE_OLD_BOSS_W = 4.5
PLATE_TOF_FRAME = dict(x=(69.1, 72.1), y=(10.2, 35.1), z=(10.1, 20.9))  # the old ToF frame (see below)
CAM_BOSS_D = 5.0
CAM_BOSS_ROOT = 0.3       # the standoffs start this far inside the plate
# Print frame of the plate: front face down on the bed. print = R @ head + T.
PLATE_PRINT_R = ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0), (-1.0, 0.0, 0.0))
PLATE_PRINT_T = (0.0, 0.0, PLATE_FRONT_X)


def cam_holes():
    """The camera board's four holes in head Y, Z."""
    cy, cz = CAM_AXIS
    h = CAM_HOLE_PITCH / 2
    return ((cy + h, cz + h), (cy - h, cz + h), (cy + h, cz - h), (cy - h, cz - h))


# ToF: SparkFun Qwiic Mini ToF Imager VL53L5CX (SEN-19013), from SparkFun's board file: board
# 25.4 x 12.7 x 0.8, two 3.3 mm holes 20.32 mm apart, 2.54 mm from one long edge; the sensor
# (6.4 x 3.0 x 1.5) on the front side at the board's middle, 8.89 mm from that edge; two vertical
# Qwiic connectors (6.6 x 4.6 footprint, 4.25 mm tall) on the back at the two ends. The board lies
# on the plate's back, holes edge up, sensor in the plate's ToF window (the old window, unchanged).
TOF_SENSOR_AT = (22.63, 13.5)  # sensor centre in head Y, Z: the plate's ToF window centre
TOF_BOARD = (25.4, 12.7, 0.8)
TOF_HOLE_D = 3.3
TOF_HOLES_X = (2.54, 22.86)    # along the board, from one end
TOF_HOLE_Y = 2.54              # from the holes edge
TOF_SENSOR_XY = (12.7, 8.89)   # sensor centre on the board
TOF_SENSOR = (6.4, 3.0, 1.5)
TOF_CONNECTORS_X = ((0.37, 4.97), (20.43, 25.03))
TOF_CONNECTOR_Y = (5.6, 12.2)
TOF_CONNECTOR_H = 4.25
TOF_PLUG = 3.0                 # cable plug and wires beyond the connector top (the cable on the far end)
TOF_PAD = 0.3                  # pads under the board: the sensor ends 0.1 mm behind the front face
TOF_PIN_D = 3.0
TOF_PIN_PROUD = 1.5            # pins stand out of the board's back by this much, to heat-stake
TOF_PAD_D = 5.5
TOF_CORNER_PAD = 2.4
TOF_MARGIN = 0.5               # camera and Pi to the ToF board and its connectors
# The old ToF frame on the plate (for a 19.8 mm hole-pitch board), removed with its two blind holes.
PLATE_OLD_TOF = dict(frame=((68.9, 10.0, 9.9), (35.3, 21.1)), ring=((70.9, 16.0, 9.3), (29.2, 17.7)),
                     holes=((12.73, 15.5), (32.53, 15.5)), hole_d=2.05, hole_end_x=73.25)


def tof_board_front_x():
    return PLATE_BACK_X - TOF_PAD


def tof_to_head(bx, by):
    """A point on the ToF board (along it from the camera end, down from the holes edge) in head Y, Z."""
    sy, sz = TOF_SENSOR_AT
    return sy - TOF_SENSOR_XY[0] + bx, sz + TOF_SENSOR_XY[1] - by


def tof_holes():
    return tuple(tof_to_head(x, TOF_HOLE_Y) for x in TOF_HOLES_X)


# LED: a 1 W high-power LED emitter (warm white, about 3.3 V, 330 mA) on the robot's right of the
# camera, mirroring the ToF window. Given by the seller: collar 7.3 mm, lead span 15 mm, heat slug
# 6 mm. Assumed (usual for these emitters, not given): body 8.0 mm, dome 5.6 mm and 2.0 mm high,
# collar 1.0 mm, body 2.6 mm; leads 2.0 x 0.3 mm. The collar's front face rests on the plate's
# back face, the dome looks out through the hole; a cup on the plate's back centres the body,
# with slots for the leads.
LED_AT = (-22.63, 13.5)   # head Y, Z
LED_BODY = (8.0, 2.6)     # diameter, length (assumed)
LED_COLLAR = (7.3, 1.0)   # diameter (given), length (assumed)
LED_DOME = (5.6, 2.0)     # diameter, height (assumed)
LED_LEADS = (15.0, 2.0, 0.3)  # span (given), width, thickness; the leads run along Z
LED_HOLE_D = 6.4          # through the plate: the dome passes, the collar does not
LED_CUP_ID = 8.6          # the body's seat
LED_CUP_WALL = 1.2
LED_CUP_DEPTH = 2.6       # back from the plate's back face
LED_SLOT_W = 3.0          # lead slots, along Z
LED_MARGIN = 0.5          # camera and Pi to the LED
