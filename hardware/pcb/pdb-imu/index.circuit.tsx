/**
 * DuckBuddy PDB/IMU, revision R3 — power distribution + IMU on the servo bus.
 *
 * Replacement for the R2f board (same interface), made to lie flat on the
 * hip servos: 55 × 31 mm (R2f is 55 × 28; the extra 3 mm is at the bottom edge) with both top corners
 * cut away (6 × 3 mm) for the neck servo, 2 layers. Same connector pinouts and the same MCU pin map as
 * firmware/imu-feetech. J4/J6 are side-entry PH2.0 headers whose plugs point to the bottom edge (the
 * roof of the body leaves no room for a vertical plug), and the board is held by two M2 screws on
 * standoffs in the free servo-top holes at the bottom corners.
 *
 * Added over R2f:
 *  - Power switch + reverse polarity protection: Q1/Q2, two N-FETs back to back
 *    in the ground return. SW1 (or an outside switch on J3) turns both on.
 *  - Bulk input capacitance (C1 100 µF + 10 µF at every branch).
 *  - ESD diode on the shared bus DATA net (D3).
 *  - Pad for an optional DATA pull-up (R12, not fitted).
 *  - One LED per fused branch (lit = branch has power), one MCU status LED.
 *  - INT1 of the IMU wired to PB3 for future use.
 *  - Bus speed jumper JP1 on PC15: open = 500 kbit/s (DuckBuddy), bridged = 1 Mbit/s
 *    (STS3215 servos at their factory speed, Frankenduck).
 *  - Hardware low-battery cutoff (U6, Q3), 2S/3S by jumper JP2.
 *  - Battery voltage (PA0) and current (RS1 + U5 INA180A2, PB7) readings for the firmware.
 *  - Self-resetting PPTC branch fuses (F1-F3), test points TP1-TP4, Tag-Connect SWD pads J7.
 *
 * Coordinates are in the R2f frame: origin at the R2f board center, 1.5 mm above the center of
 * this board (R3 is 3 mm taller, all of it at the bottom edge). +X runs toward the right-leg
 * connector J6, +Y toward the head connector J5 (the front of the robot).
 */
import React from "react"
import { STM32G031F8P6 } from "./imports/STM32G031F8P6"
import { LSM6DSV16XTR } from "./imports/LSM6DSV16XTR"
import { A_74LVC1G126GW } from "./imports/A_74LVC1G126GW"
import { TPS70933DBVR } from "./imports/TPS70933DBVR"
import { AON7524 } from "./imports/AON7524"
import { MS_1290N } from "./imports/MS_1290N"
import { S3B_PH_K_S_LF__SN_ } from "./imports/S3B_PH_K_S_LF__SN_"
import { B3B_XH_A_LF__SN_ } from "./imports/B3B_XH_A_LF__SN_"
import { RVT100UF25V67RV0011 } from "./imports/RVT100UF25V67RV0011"
import { PESD5V0S1BA } from "./imports/PESD5V0S1BA"
import { INA180A2IDBVR } from "./imports/INA180A2IDBVR"
import { CJ431 } from "./imports/CJ431"
import { S8550 } from "./imports/S8550"
import { A_1210L300_24WR } from "./imports/A_1210L300_24WR"
import { RLM12FTCMR002 } from "./imports/RLM12FTCMR002"
import { KT_0805G } from "./imports/KT_0805G"
import { KT_0603R } from "./imports/KT_0603R"
import { brazilArt, pernambucoArt, microduckArt, microduckLabelArt, nameArt, handleArt, place1Art, place2Art, place3Art, dogArt, jp1Art } from "./art/art"
import { topArt } from "./art/top_art"

// LCSC part numbers for the generic parts.
const LCSC = {
  r33: "C25105",
  r1k: "C11702",
  r3k3: "C25890",
  r4k7: "C25900",
  r10k: "C25744",
  r22k: "C25768",
  r33k: "C25779",
  r100k: "C25741",
  r27k_0603: "C22967",
  r680k_0603: "C25822", // JLCPCB preferred part (no extended fee)
  r39k_0603: "C23153",
  c100n_0402: "C1525", // 16 V, 3.3 V nets only
  c100n_50v: "C14663", // 0603 50 V, battery nets
  c1u_50v: "C15849", // 0603 50 V
  c4u7: "C19666", // 0603 16 V
  c10u_25v: "C15850", // 0805 25 V X5R (JLCPCB basic part)
  c22u_25v: "C45783", // 0805 25 V X5R (JLCPCB basic part)
  fuse1a: "C99544", // 0438001.WR, 0603
  tvs: "C152106", // SMBJ14A
  zener10: "C173431", // BZT52C10 (9.4-10.6 V), below the FETs' 12 V gate limit
  esd: "C2827694", // PESD5V0S1BA
  diode: "C2128", // 1N4148WS, SOD-323
  header4: "C2691448",
}

// JP1/JP2: two bare pads, 1.29 mm apart, with no solder paste, so reflow cannot bridge them.
// (The built-in solderjumper footprint puts paste on both pads.)
const SOLDER_JUMPER = (
  <footprint>
    <smtpad portHints={["pin1"]} shape="rect" width="0.75mm" height="1.2mm" pcbX="-0.645mm" pcbY="0mm" noSolderPaste />
    <smtpad portHints={["pin2"]} shape="rect" width="0.75mm" height="1.2mm" pcbX="0.645mm" pcbY="0mm" noSolderPaste />
  </footprint>
)

// Diodes from LCSC have pin 1 on the cathode (marked end).
const cathodeFirst = {
  pin1: ["cathode", "neg"],
  pin2: ["anode", "pos"],
} as const
// Top-side silkscreen. tscircuit draws silkscreen text with a line 9% of its height (0.07 mm at
// 0.8 mm), too thin for JLCPCB to print, so every designator is hidden on its part and the
// top-side labels and icons are drawn as graphics instead (art/top_art.ts, made by art/make_art.py).
// Only the main parts get a designator; the small passives are listed in the assembly drawing.
// [art key, x, y] in board coordinates; "servo#J4" is the "servo" icon placed next to J4.
// The positions come from art/place_top.py, which keeps every item 0.2 mm from exposed copper,
// outside part bodies and off the footprint outlines. Run it again after any layout change.
const TOP_ART: [string, number, number][] = [
  ["DIO", 15.94, -5.25],  // moved 0.39 mm
  ["CLK", 18.23, -5.25],  // moved 0.30 mm
  ["GND", 20.77, -5.25],  // moved 0.30 mm
  ["3V3", 23.31, -5.25],  // moved 0.30 mm
  ["title", -16.05, 7.20],
  ["J4", -24.45, 5.30],  // moved 0.55 mm
  ["J6", 23.90, 5.30],
  ["J5", 0.40, 6.85],  // moved 0.40 mm
  ["J2", 19.50, -9.00],
  ["battery", 3.25, -15.30],
  ["imu", -2.10, 2.50],  // moved 1.21 mm
  ["servo#J4", -24.40, 7.60],
  ["servo#J6", 25.10, 7.60],  // moved 0.70 mm
  ["amps", 1.50, -9.30],  // moved 2.70 mm
  ["volts", 1.60, -7.20],  // moved 1.80 mm
  ["ON", -18.55, -13.65],  // moved 2.26 mm
  ["2S", -19.00, -12.00],
  ["U1", 11.50, 5.85],  // moved 0.05 mm
  ["U2", 3.60, 5.55],  // moved 1.30 mm
  ["U3", -0.55, -0.35],  // moved 1.75 mm
  ["U4", 15.00, -2.85],  // moved 0.87 mm
  ["U5", -3.70, -15.40],
  ["U6", -15.50, -2.30],  // moved 0.30 mm
  ["Q1", 4.85, -13.75],  // moved 2.22 mm
  ["Q2", 5.95, -4.25],  // moved 1.11 mm
  ["SW1", -14.10, -9.30],
  ["F1", -14.50, -0.85],  // moved 0.05 mm
  ["F2", -5.30, 4.10],  // moved 0.82 mm
  ["F3", -11.65, 8.50],  // moved 0.60 mm
  ["RS1", -0.60, -8.20],  // moved 0.41 mm
  ["D1", -11.10, -15.75],  // moved 0.72 mm
  ["LED1", -17.30, 11.10],  // moved 0.20 mm
  ["LED2", 19.00, 12.05],  // moved 0.15 mm
  ["LED3", -6.55, 10.60],  // moved 0.35 mm
  ["LED4", 17.00, 5.55],  // moved 0.15 mm
  ["JP2", -19.70, -10.70],  // moved 0.60 mm
  ["J3", -20.90, -14.10],  // moved 2.30 mm
  ["J7", 19.50, -12.40],
  ["TP1 VB", -10.30, -8.20],  // moved 0.70 mm
  ["TP2 3V3", 16.30, -10.60],
  ["TP3 G", 23.95, -11.90],  // moved 2.21 mm
  ["TP4 D", 21.30, -3.85],  // moved 1.55 mm
]
const lab = (_n: string) => ({ pcbSx: { "& silkscreentext": { visibility: "hidden" as const } } })

// The LEDs (KT-0805G, KT-0603R) use the exact JLCPCB footprints from imports/: on those,
// pad 1 (anode) is on the +X side, the opposite of the generic 0805/0603 footprints.

// Parts the hand-routed power copper is drawn around (board coordinates, mm; rot in degrees).
const P = {
  J1: { x: 3.25, y: -15.3 }, // BAT+ at x = -0.5, BAT- at x = 7 (7.5 mm apart)
  RS1: { x: -0.5, y: -10.9, rot: 90 },
  D1: { x: -8.1, y: -13.15, rot: 90 }, // upright, left of U5; cathode at the bottom (y -15.3)
  J3: { x: -20.9, y: -15.2, rot: 180 }, // SW_ON at x = -22.17, VBAT at x = -19.63
  SW1: { x: -14.1, y: -12.55 }, // the lever reaches the bottom edge
  Q1: { x: 7, y: -11.75, rot: 180 },
  Q2: { x: 7, y: -7 },
  C1: { x: -8, y: -0.7, rot: 90 },
  F1: { x: -14.5, y: 1, rot: 180 },
  F2: { x: -4.5, y: 6.1 },
  F3: { x: -9.4, y: 7.9, rot: 90 },
  F4: { x: -2.6, y: -4 },
  C3: { x: -17.3, y: 3.9 },
  C4: { x: 21.6, y: 8, rot: 180 },
  C5: { x: 7.65, y: 7.6 },
  U2: { x: 3, y: 2.5 },
  R8: { x: 1.2, y: 0.3 },
  R4: { x: 18.45, y: 2.3, rot: 90 },
}
type Part = { x: number; y: number; rot?: number }
type Placed = Record<string, Part>

// Low-battery cutoff parts (board coordinates).
// The core (U6 and its divider) sits right of the J4 header; Q3, R24, R18, R19 and JP2 sit below the
// J4 plug, above SW1/J3 (where SW_ON is); Q4 and D4 sit by the FET gates. Every line of the cutoff is
// drawn by hand (CUT_LINES): DRV runs up from Q3.C and along the top (R25, R22), FET_S down the column
// at x = -18 (R25, U6.A, C17, R21), CUT_REF down the column at x = -12.7 (R22, U6.R, R21, R20) and CUT_A
// along the bottom (R20, C17, R19/JP2). The J4 plug lies flat over the strip below the J4 header
// (y -3.25 to -6.5), so no part sits there, only lines.
const CUT: Placed = {
  R24: { x: -25.41, y: -7.9, rot: 90 }, Q3: { x: -22.6, y: -7.9, rot: 180 }, R23: { x: -17.85, y: -1.7 },
  R25: { x: -18, y: -3.4, rot: 270 }, U6: { x: -15.5, y: -4.43 }, R22: { x: -12.7, y: -3.7, rot: 270 },
  R21: { x: -15, y: -7.1, rot: 180 }, R20: { x: -12.7, y: -7.9, rot: 90 }, C17: { x: -18, y: -7.94, rot: 90 },
  JP2: { x: -21.7, y: -12.0 }, R19: { x: -22.1, y: -10.5 }, R18: { x: -24.9, y: -10.5 },
  Q4: { x: 10.5, y: -14.2 }, D4: { x: 13.5, y: -14.3, rot: 270 }, R1: { x: 15.0, y: -14.84, rot: 270 },
}
// Battery voltage and current sense parts.
const SNS: Placed = {
  RS1: P.RS1, U5: { x: -3.7, y: -12.4 }, C14: { x: -4.65, y: -9.4, rot: 90 },
  R15: { x: 6.6, y: -0.4 }, C15: { x: 6.6, y: -1.6, rot: 180 },
  R16: { x: 1.6, y: -10.8 }, R17: { x: 1.75, y: -12.4, rot: 180 }, C16: { x: 3.4, y: -12.4, rot: 270 },
}
// Test points and the SWD pads.
const TPS: Placed = {
  TP1: { x: -11.0, y: -9.8 }, TP2: { x: 16.3, y: -12.0 }, TP3: { x: 21.8, y: -11.0 }, TP4: { x: 18.45, y: 0.4 },
  J7: { x: 19.5, y: -14.6 },
}

// Other parts the hand-routed lines start from (board coordinates).
const L: Placed = {
  U3: { x: 1.2, y: -2.2, rot: 180 }, C6: { x: -3, y: -1.2, rot: 180 }, C7: { x: 4.2, y: -2.2, rot: 270 }, C9: { x: 8.0, y: -3.25, rot: 180 },
  C10: { x: 12.75, y: -5.6 }, C11: { x: 5.6, y: 4.6 }, C12: { x: 2.3, y: 4.6 },
  U4: { x: 16.65, y: -3 }, C13: { x: 16.65, y: -0.7 }, R11: { x: 14, y: -4.5, rot: 180 }, R13: { x: 18.45, y: -2.6, rot: 90 },
  R10: { x: 16.4, y: 2.6 }, R12: { x: 7, y: 12.6 }, J2: { x: 19.5, y: -7 },
  R3: { x: -21.2, y: 5.6, rot: 270 }, R6: { x: -19.6, y: 9.5 }, R7: { x: 15.65, y: 10.4 }, R9: { x: -10.2, y: 12.2 },
  D2: { x: 3.5, y: -6.5, rot: 90 }, R2: { x: 9.2, y: -9.4, rot: 270 }, C2: { x: 10.6, y: -10.3, rot: 270 },
}

// A trace's pcbPath is in the frame of its first part (center, turned by the part's rotation).
// at() takes board coordinates and converts them to that frame.
const at = (part: Part, pts: [number, number][]) => {
  const a = (-(part.rot ?? 0) * Math.PI) / 180
  return pts.map(([x, y]) => {
    const dx = x - part.x
    const dy = y - part.y
    return { x: dx * Math.cos(a) - dy * Math.sin(a), y: dx * Math.sin(a) + dy * Math.cos(a) }
  })
}

/* Hand-routed copper, all on the top layer, so no battery current changes layer.
   Each entry: from port, to port, width (mm), first part, corner points (board coordinates).
   Battery plus goes from J1+ through the shunt RS1; from RS1 VBAT runs up to y = -4.5, along it to
   the left side (x = -11), up, and along y = 6.1 to the fuses;
   V_RIGHT then runs along y = 6.1 to x = 23.5 and down to J6. The bottom layer is mostly GND pour,
   crossed by a few signal lines. */
const POWER: [string, string, number, Part, [number, number][]][] = [
  // Battery side of the shunt (the TVS D1 clamps here)
  [".J1 > .BAT_P", ".RS1 > .pin1", 2.0, P.J1, []],
  [".J1 > .BAT_P", ".D1 > .cathode", 1.5, P.J1, []],
  // VBAT trunk, 3 mm wide (all battery current, up to about 9 A). The 45-degree run stays
  // 0.25 mm from F4's output pad; the column at x = -10.4 runs between R22 and C1's GND pad.
  [".RS1 > .pin2", ".F2 > .pin1", 3.0, P.RS1, [[-0.5, -8.62], [-4.62, -4.5], [-10.4, -4.5], [-10.4, 6.1]]],
  [".F4 > .pin1", ".C1 > .pos", 0.8, P.F4, [[-4, -4.5], [-8, -4.5]]],
  [".C1 > .pos", ".RS1 > .pin2", 3.0, P.C1, [[-8, -4.5], [-4.62, -4.5], [-0.5, -8.62]]],
  [".F1 > .pin1", ".F2 > .pin1", 2.4, P.F1, [[-10.4, 1], [-10.4, 6.1]]],
  [".F3 > .pin1", ".F2 > .pin1", 1.2, P.F3, [[-9.4, 6.1]]],
  // To the switch and J3 (switch current only). TP1 sits on this line. J3 joins SW1 from below,
  // between SW1's two locating holes.
  [".SW1 > .pin2", ".C1 > .pos", 0.5, P.SW1, [[-13.35, -10.3], [-11, -10.3], [-11, -4.5], [-8, -4.5]]],
  [".J3 > .VBAT", ".SW1 > .pin2", 0.4, P.J3, [[-14.9, -15.2], [-14.2, -14.5], [-14.2, -13.4], [-13.35, -12.55]]],
  // Branch outputs. J4/J6 pin 2 is fed from below its pins (V_LEFT), or from above (V_RIGHT).
  [".F1 > .pin2", ".J4 > .pin2", 1.0, P.F1, [[-17.3, 1.0], [-17.7, 0.6], [-22.8, 0.6], [-23.2, 1.0]]],
  [".C3 > .pin1", ".F1 > .pin2", 0.8, P.C3, [[-18.25, 1.0]]],
  [".F2 > .pin2", ".J6 > .pin2", 1.2, P.F2, [[23.25, 6.1]]],
  [".C4 > .pin1", ".J6 > .pin2", 0.8, P.C4, [[23.25, 8]]],
  [".F3 > .pin2", ".J5 > .pin2", 1.2, P.F3, [[-9.4, 9.2], [0, 9.2]]],
  [".C5 > .pin1", ".J5 > .pin2", 0.8, P.C5, [[1.2, 7.6], [0, 9.2]]],
  // Battery minus through Q1 (reverse block) and Q2 (switch); Q2's drain is GND.
  // J1- sits right under Q1's drain pins.
  // 2.1 mm wide: its round end on the drain pad then stays 0.25 mm from the source link below.
  [".J1 > .BAT_N", ".Q1 > .D5", 2.1, P.J1, [[7, -13.2]]],
  // Each drain pin joins the drain pad (D5) straight across; the source pins join each other.
  ...([["D1", 7.97], ["D2", 7.33], ["D3", 6.67], ["D4", 6.02]].map(([d, x]) => [`.Q1 > .${d}`, ".Q1 > .D5", 0.4, P.Q1, [[x, -12.6]]]) as [string, string, number, Part, [number, number][]][]),
  ...([["D1", 6.03], ["D2", 6.67], ["D3", 7.33], ["D4", 7.97]].map(([d, x]) => [`.Q2 > .${d}`, ".Q2 > .D5", 0.4, P.Q2, [[x, -6.1]]]) as [string, string, number, Part, [number, number][]][]),
  [".Q1 > .S1", ".Q1 > .S2", 0.4, P.Q1, [[7.33, -10.25]]],
  [".Q1 > .S2", ".Q1 > .S3", 0.4, P.Q1, [[6.67, -10.25]]],
  [".Q2 > .S1", ".Q2 > .S2", 0.4, P.Q2, [[6.67, -8.5]]],
  [".Q2 > .S2", ".Q2 > .S3", 0.4, P.Q2, [[7.33, -8.5]]],
  // As wide as the two gate pins beside it allow (Q1.G at x = 6.03, Q2.G at x = 7.97).
  [".Q1 > .S2", ".Q2 > .S2", 1.1, P.Q1, [[7, -10.25], [7, -8.5]]],
]

// Signal lines around U1, drawn by hand.
// The IMU lines pass under U1 between its pad rows and rise into the top-row pads (PA7 MOSI, PA6 MISO,
// PA5 SCK, PA4 CS). SDO takes one hop on the bottom layer to cross SDA. SWDIO, SWCLK and PA11 drop
// through vias between the pad rows and run on the bottom layer to J2 and the status LED.
const U1_AT = { x: 11.5, y: 1.5 }
const via = (part: Part, x: number, y: number, fromLayer: string, toLayer: string) => ({ ...at(part, [[x, y]])[0], via: true, fromLayer, toLayer })
const IMU_LINES: [string, string, any[]][] = [
  [".U2 > .SDA", ".U1 > .PA7", at(P.U2, [[3.5, 1.1], [6.4, 1.1], [6.4, 2], [12.47, 2]])],
  [".U2 > .SCL", ".U1 > .PA5", at(P.U2, [[3, 0.7], [7, 0.7], [7, 1.4], [13.78, 1.4]])],
  [".U2 > .CS", ".U1 > .PA4", at(P.U2, [[2.5, 0.3], [7.6, 0.3], [7.6, 0.8], [14.43, 0.8]])],
  [".R8 > .pin2", ".U2 > .CS", at(P.R8, [[2.5, 0.3]])],
  [".U2 > .SDO", ".U1 > .PA6", [
    ...at(P.U2, [[5.8, 1.75]]),
    via(P.U2, 5.8, 1.75, "top", "bottom"),
    ...at(P.U2, [[5.8, 1.75], [12.6, 1.75], [13.12, 2.3], [13.12, 2.6]]),
    via(P.U2, 13.12, 2.6, "bottom", "top"),
    ...at(P.U2, [[13.12, 2.6]]),
  ]],
  [".U2 > .INT1", ".U1 > .PB3", at(P.U2, [[4.6, 3.3], [8.57, 3.3]])],
  // SDx/SCx are tied to GND through the via at (5, 2.5).
  [".U2 > .SDx", ".U2 > .SCx", at(P.U2, [[5, 2.5]])],
  [".U1 > .SWCLK", ".J2 > .SWCLK", [
    ...at(U1_AT, [[9, 2.85]]), via(U1_AT, 9, 2.85, "top", "bottom"),
    ...at(U1_AT, [[9, 2.85], [9, 5.4], [16.5, 5.4], [16.5, -4.5]]),
  ]],
  [".U1 > .SWDIO", ".J2 > .SWDIO", [
    ...at(U1_AT, [[9.95, 2.85]]), via(U1_AT, 9.95, 2.85, "top", "bottom"),
    ...at(U1_AT, [[9.95, 2.85], [9.95, 4.8], [15.9, 4.8], [15.9, -5]]),
  ]],
  // DATA from TP4 (right-leg side) across to the head side (R12 pad, then D3, R5, J5). On the bottom
  // layer it passes right of the SWCLK/SWDIO/PA11 lines, then above them.
  [".TP4 > .pin1", ".R12 > .pin2", [
    ...at(TPS.TP4, [[17.85, 1.0], [17.2, 1.0]]), via(TPS.TP4, 17.2, 1.0, "top", "bottom"),
    ...at(TPS.TP4, [[17.2, 1.0], [17.2, 5.8], [13.7, 9.3], [10.34, 9.3], [10.34, 11.76]]),
    via(TPS.TP4, 10.34, 11.76, "bottom", "top"), ...at(TPS.TP4, [[10.34, 11.76], [8.35, 11.76]]),
  ]],
  [".R12 > .pin2", ".D3 > .pin1", []],
  [".D3 > .pin1", ".R5 > .pin1", []],
  [".R5 > .pin2", ".J5 > .pin3", []],
  // The bus speed jumper JP1 sits on the bottom side right under U1's PC15 and VSS pads:
  // each pad drops through a via between U1's pad rows onto its own JP1 pad.
  [".U1 > .PC15", ".JP1 > .pin2", [
    ...at(U1_AT, [[9.88, 0]]), via(U1_AT, 9.88, 0, "top", "bottom"), ...at(U1_AT, [[9.88, 0]]),
  ]],
  [".U1 > .VSS", ".JP1 > .pin1", [
    ...at(U1_AT, [[11.18, 0]]), via(U1_AT, 11.18, 0, "top", "bottom"), ...at(U1_AT, [[11.18, 0]]),
  ]],
  // Battery voltage: PA0 drops through a via between the pad rows, runs on the bottom layer
  // under U1 and left of Q2, and comes back up beside the divider (R16/R17/C16).
  [".U1 > .PA0", ".C16 > .pin1", [
    ...at(U1_AT, [[12.47, 0]]), via(U1_AT, 12.47, 0, "top", "bottom"),
    ...at(U1_AT, [[12.47, 0], [12.47, -2.1], [4.2, -2.1], [4.2, -11.2]]),
    via(U1_AT, 4.2, -11.2, "bottom", "top"), ...at(U1_AT, [[4.2, -11.2]]),
  ]],
  // Current sense: the output filter R15/C15 sits right beside PB7.
  [".C15 > .pin1", ".U1 > .PB7", at(SNS.C15, [[8.57, -1.6]])],
  [".R15 > .pin2", ".C15 > .pin1", at(SNS.R15, [[7.11, -1.6]])],
  [".U1 > .PA11", ".R10 > .pin1", [
    ...at(U1_AT, [[11.18, 2.85]]), via(U1_AT, 11.18, 2.85, "top", "bottom"),
    ...at(U1_AT, [[11.18, 2.85], [11.18, 4.2], [15.3, 4.2], [15.3, 2.6]]),
    via(U1_AT, 15.3, 2.6, "bottom", "top"), ...at(U1_AT, [[15.3, 2.6]]),
  ]],
]

// The cutoff, drawn by hand (pads listed in CUT). Each entry: from port, to port, width (mm),
// first part, points in board coordinates; ["v", x, y, from, to] changes layer there.
// CUT_B and DRV run up from Q3 through the J4 plug strip to R23 and R25. CUT_K hops over DRV on the
// bottom layer. DRV also drops through a via above Q3.C and runs on the bottom layer below the core,
// under U5 and above the battery pads, across the board to R1. FET_S leaves through a via above R21
// and runs on the bottom layer beside DRV (above it) to Q4's collector.
type Seg = [number, number] | ["v", number, number, string, string]
const route = (part: Part, segs: Seg[]) =>
  segs.flatMap((s) => (s[0] === "v" ? [...at(part, [[s[1], s[2]]]), via(part, s[1], s[2], s[3], s[4]), ...at(part, [[s[1], s[2]]])] : at(part, [s as [number, number]])))
const CUT_LINES: [string, string, number, Part, Seg[]][] = [
  [".R24 > .pin2", ".Q3 > .B", 0.25, CUT.R24, [[-25.41, -6.95]]],
  [".Q3 > .B", ".R23 > .pin1", 0.25, CUT.Q3, [[-23.6, -1.7]]],
  [".R23 > .pin2", ".U6 > .K", 0.25, CUT.R23, [["v", -16.5, -1.7, "top", "bottom"], [-15.5, -2.7], ["v", -15.5, -3.6, "bottom", "top"]]],
  [".R24 > .pin1", ".Q3 > .E", 0.3, CUT.R24, [[-25.41, -8.85]]],
  [".R18 > .pin1", ".R24 > .pin1", 0.3, CUT.R18, []],
  // SW_ON from SW1 (and J3) runs left under JP2 and up to R18.
  [".SW1 > .pin1", ".R18 > .pin1", 0.3, P.SW1, [[-16.35, -13.0], [-23.1, -13.0], [-23.1, -12.0], [-25.41, -12.0]]],
  [".Q3 > .C", ".R25 > .pin1", 0.25, CUT.Q3, [[-20.3, -7.9], [-20.3, -3.4], [-19.79, -2.89]]],
  [".R25 > .pin1", ".R22 > .pin1", 0.25, CUT.R25, [[-15, -2.89]]],
  [".Q3 > .C", ".R1 > .pin1", 0.2, CUT.Q3, [
    [-20.3, -7.9], ["v", -20.3, -6.9, "top", "bottom"], [-19.6, -7.6], [-19.6, -9.0], [-19.0, -9.6], [-11.7, -9.6],
    [-6.8, -14.5], [-3.9, -14.5], [-2.7, -13.3], [14.8, -13.3], ["v", 15.0, -13.5, "bottom", "top"],
  ]],
  [".R25 > .pin2", ".C17 > .pin2", 0.3, CUT.R25, [[-18, -7.03]]],
  [".U6 > .A", ".R25 > .pin2", 0.3, CUT.U6, [[-18, -4.43]]],
  [".R21 > .pin2", ".C17 > .pin2", 0.3, CUT.R21, [[-17.2, -7.1]]],
  [".R21 > .pin2", ".Q4 > .C", 0.3, CUT.R21, [
    [-15.9, -6.5], ["v", -15.9, -5.9, "top", "bottom"], [-11.6, -5.9], [-11.6, -8.99], [-6.59, -14.0], [-4.3, -14.0],
    [-2.95, -12.65], [9.5, -12.65], ["v", 9.5, -12.65, "bottom", "top"],
  ]],
  [".U6 > .R", ".R22 > .pin2", 0.25, CUT.U6, [[-12.7, -5.45]]],
  [".R21 > .pin1", ".R22 > .pin2", 0.25, CUT.R21, [[-12.7, -7.1]]],
  [".R20 > .pin2", ".R21 > .pin1", 0.25, CUT.R20, [[-12.7, -7.1]]],
  [".R20 > .pin1", ".C17 > .pin1", 0.25, CUT.R20, [[-12.7, -8.6], [-17.6, -8.6]]],
  [".C17 > .pin1", ".R19 > .pin2", 0.25, CUT.C17, [[-18.0, -10.5]]],
  [".JP2 > .pin2", ".R19 > .pin2", 0.25, CUT.JP2, [[-21.055, -10.5]]],
  [".JP2 > .pin1", ".R19 > .pin1", 0.25, CUT.JP2, [[-22.345, -10.5]]],
  [".R18 > .pin2", ".R19 > .pin1", 0.25, CUT.R18, []],
]

// Every other line, drawn by hand (the board has no autorouting: routeRemaining is off, and the
// GND pours join every GND pad). Same format as CUT_LINES.
// - V_LDO: F4 -> C6 on top; F4 -> U3.IN hops under the V3V3 line on the bottom layer.
// - V3V3: a top trunk U3.OUT -> C7 -> C9 -> U1.VDD below the LDO, a channel left of U3 up to R8 and the
//   IMU, and bottom-layer links to U5/C14, to R12, and from C9 to J2, U4/C13 and TP2 -> J7.
// - SWD reaches J7 (bottom right) from J2; NRST through the bottom layer.
// - DATA runs along the top board edge, round the top-left corner cut, down to the left leg (R3).
//   On the right it passes under the J6 header body, below its pins, to J6 pin 3.
// - The FET gates: Q2.G, R2, C2 and Q4.E on top; Q1.G joins them on the bottom layer.
const HAND_LINES: [string, string, number, Part, Seg[]][] = [
  // V_LDO: F4 -> C6 -> U3.IN, all on the left of U3
  [".F4 > .pin2", ".U3 > .IN", 0.3, P.F4, [[-1.78, -3.0], [-2.17, -2.3], [-2.17, -1.25]]],
  [".C6 > .pin1", ".U3 > .IN", 0.3, L.C6, []],
  // V3V3 trunk: U3.OUT -> C7 -> C9 -> U1.VDD (passing over the C7 and C9 pads), and the IMU
  [".U3 > .OUT", ".C7 > .pin1", 0.3, L.U3, []],
  [".U3 > .OUT", ".U1 > .VDD", 0.25, L.U3, [[4.2, -1.38], [5.1, -1.38], [5.1, -4.0], [10.19, -4.0], [10.19, -2.95], [10.53, -2.5]]],
  [".C9 > .pin1", ".C8 > .pin1", 0.25, L.C9, [[9.6, -3.0]]],
  [".U3 > .OUT", ".R8 > .pin1", 0.25, L.U3, [[2.5, -0.5], [0.69, -0.5]]],
  [".R8 > .pin1", ".U2 > .Vdd", 0.25, P.R8, [[0.69, 3.25]]],
  [".C12 > .pin1", ".U2 > .Vdd", 0.25, L.C12, []],
  [".R8 > .pin1", ".U2 > .Vdd_IO", 0.2, P.R8, [[0.69, 5.2], [3.5, 5.2]]],
  [".U2 > .Vdd_IO", ".C11 > .pin1", 0.2, P.U2, [[3.5, 4.05], [4.6, 4.05]]],
  [".U2 > .Vdd_IO", ".R12 > .pin1", 0.25, P.U2, [[3.5, 4.05], ["v", 4.3, 4.05, "top", "bottom"], [4.3, 12.0], ["v", 5.8, 12.6, "bottom", "top"]]],
  // V3V3 to the current sense amplifier (inside the battery copper, so on the bottom layer)
  [".U5 > .VS", ".U3 > .OUT", 0.25, SNS.U5, [[-4.65, -9.91], ["v", -5.4, -9.91, "top", "bottom"], [-2.6, -7.1], [-2.6, -4.5], ["v", 1.25, -0.55, "bottom", "top"], [2.5, -0.5]]],
  [".U5 > .VS", ".C14 > .pin1", 0.25, SNS.U5, []],
  // V3V3 to the right side: J2, U4/C13, TP2 and J7
  [".U1 > .VDD", ".J2 > .V3V3", 0.25, U1_AT, [[10.53, -2.5], [10.19, -2.95], ["v", 10.19, -4.0, "top", "bottom"], [10.19, -4.7], [12.145, -6.655], [13.8, -8.3], [23.31, -8.3]]],
  [".C13 > .pin1", ".U4 > .VCC", 0.25, L.C13, []],
  [".U4 > .VCC", ".J2 > .V3V3", 0.25, L.U4, [[16.05, -0.75], [15.6, -0.75], ["v", 15.3, -1.05, "top", "bottom"], [15.3, -3.5], [12.145, -6.655], [13.8, -8.3], [23.31, -8.3]]],
  [".TP2 > .pin1", ".J2 > .V3V3", 0.25, TPS.TP2, [[15.9, -11.6], [15.2, -10.9], ["v", 15.2, -8.3, "top", "bottom"], [23.31, -8.3]]],
  [".TP2 > .pin1", ".J7 > .V3V3", 0.25, TPS.TP2, [[16.0, -12.3], [16.0, -15.6], [16.4, -16.0], [17.85, -16.0], [18.23, -15.62]]],
  // NRST: C10 beside the line; J7 through the bottom layer
  [".C10 > .pin1", ".U1 > .NRST", 0.25, L.C10, [[11.9, -5.6], [11.9, -2.3]]],
  // NRST leaves J7 downward between its pads and runs on the bottom along the bottom edge, right of J7's holes.
  [".J7 > .NRST", ".U1 > .NRST", 0.2, TPS.J7, [["v", 19.5, -16.3, "top", "bottom"], [19.75, -16.55], [22.55, -16.55], [23.0, -16.1], [23.0, -9.0], [11.9, -9.0], ["v", 11.9, -8.3, "bottom", "top"], [11.9, -2.3]]],
  // SWD from J2 down to the Tag-Connect pads
  [".J2 > .SWDIO", ".J7 > .SWDIO", 0.2, L.J2, [[15.69, -8.0], [18.23, -10.54]]],
  [".J2 > .SWCLK", ".J7 > .SWCLK", 0.2, L.J2, [[18.23, -7.8], [19.5, -9.07]]],
  // Bus driver
  [".U1 > .PA3", ".R13 > .pin1", 0.2, U1_AT, [[14.43, -2.7], [18.09, -2.7]]],
  [".U4 > .Y", ".R13 > .pin1", 0.2, L.U4, [[17.3, -2.7], [18.09, -2.7]]],
  [".U1 > .PA2", ".U4 > .A", 0.2, U1_AT, [[13.78, -3.2], [16.65, -3.2]]],
  [".U1 > .PA1", ".U4 > .OE", 0.2, U1_AT, [[13.12, -3.75], [15.65, -3.75]]],
  [".R11 > .pin1", ".U1 > .PA1", 0.2, L.R11, [[14.51, -3.75], [13.12, -3.75]]],
  // DATA
  [".R13 > .pin2", ".TP4 > .pin1", 0.2, L.R13, []],
  [".TP4 > .pin1", ".R4 > .pin1", 0.2, TPS.TP4, []],
  [".R12 > .pin2", ".R3 > .pin1", 0.2, L.R12, [[7.51, 13.35], [-20.5, 13.35], [-20.9, 12.95], [-20.9, 10.7], [-21.2, 10.4]]],
  [".R3 > .pin2", ".J4 > .pin3", 0.2, L.R3, []],
  [".R4 > .pin2", ".J6 > .pin3", 0.2, P.R4, [[19.15, 2.81], [20.55, 1.41], [24.85, 1.41], [25.25, 1.81]]],
  // Branch LEDs
  [".R6 > .pin2", ".LED1 > .anode", 0.25, L.R6, []],
  [".R6 > .pin1", ".C3 > .pin1", 0.25, L.R6, [[-20.11, 4.81], [-19.2, 3.9]]],
  [".R7 > .pin2", ".LED2 > .anode", 0.25, L.R7, []],
  [".R7 > .pin1", ".J6 > .pin2", 0.25, L.R7, [[15.14, 6.1], [23.25, 6.1]]],
  [".R9 > .pin2", ".LED3 > .anode", 0.25, L.R9, []],
  [".R9 > .pin1", ".F3 > .pin2", 0.25, L.R9, [[-10.4, 11.5], [-10.4, 10.0]]],
  [".R10 > .pin2", ".LED4 > .A", 0.2, L.R10, [[16.91, 3.2], [16.4, 3.71]]],
  // Current sense: shunt sense lines (Kelvin) and the output to R15/PB7
  [".U5 > .IN_POS", ".RS1 > .pin1", 0.25, SNS.U5, [[-1.57, -12.38]]],
  [".U5 > .IN_NEG", ".RS1 > .pin2", 0.25, SNS.U5, [[-2.0, -10.5], [-1.0, -10.5], [-1.0, -9.92]]],
  [".U5 > .OUT", ".R15 > .pin1", 0.2, SNS.U5, [["v", -5.4, -13.2, "top", "bottom"], [-2.0, -9.8], [2.5, -9.8], [2.5, -1.35], ["v", 3.4, -0.45, "bottom", "top"], [5.4, -0.4]]],
  // FET gates (FET_G) and sources (FET_S), and the gate discharge transistor Q4
  [".Q2 > .G", ".R2 > .pin1", 0.25, P.Q2, [[8.6, -8.5]]],
  [".R2 > .pin1", ".C2 > .pin1", 0.25, L.R2, [[9.8, -8.89], [10.2, -9.3]]],
  [".C2 > .pin1", ".Q4 > .E", 0.25, L.C2, [[11.5, -9.48], [11.5, -12.2]]],
  [".Q1 > .G", ".Q4 > .E", 0.25, P.Q1, [["v", 5.3, -10.25, "top", "bottom"], [6.0, -10.95], [10.6, -10.95], ["v", 11.45, -12.0, "bottom", "top"], [11.5, -12.2]]],
  [".D2 > .cathode", ".Q1 > .G", 0.25, L.D2, [[3.9, -9.2], [4.9, -10.25]]],
  [".Q4 > .E", ".D4 > .cathode", 0.25, CUT.Q4, []],
  [".Q4 > .B", ".D4 > .anode", 0.25, CUT.Q4, []],
  [".D4 > .anode", ".R1 > .pin2", 0.25, CUT.D4, []],
  [".Q1 > .S1", ".R2 > .pin2", 0.3, P.Q1, [[8.6, -10.25]]],
  [".R2 > .pin2", ".C2 > .pin2", 0.3, L.R2, [[9.6, -10.3], [9.9, -11.12]]],
  [".C2 > .pin2", ".Q4 > .C", 0.3, L.C2, [[10.1, -11.6], [9.5, -12.2]]],
  [".D2 > .anode", ".Q2 > .S1", 0.25, L.D2, [[4.42, -4.85], [4.42, -8.4], [5.6, -8.4]]],
]

// GND stitching vias: they join the top GND copper at the high-current GND pads to the bottom plane.
const GND_VIAS: [number, number][] = [
  [5.2, -5.4], [5.2, -6.4], [5.2, -7.4], [9, -5.5], [9, -6.5], [6.4, -4.75], [7.6, -4.75], // Q2 drain
  [-6.3, -10.2], [-6.3, -11.3], // D1 anode
  [-6.5, 1], [-6.5, 2.2], [-6.5, 3.4], // C1 minus
  [-15.3, 3.9], [19.6, 8], [9.8, 7.6], // C3, C4, C5
  [5, 2.5], // U2 SDx/SCx
  [6.3, -2.9], [6.65, 4.6], // C9 and C11 (their pour pieces are closed in by the V3V3 lines)
  [11.21, -4], // C8
  [1.24, -14.0], [3.4, -14.0], // R17, C16 (joined by their GND lines below)
  [18.6, 4.45], // LED4
]

// Battery input: two large plated holes for the battery leads, 7.5 mm apart (4.7 mm of bare
// board between the pads, so a blob of solder cannot join them).
const BatteryPads = (props: { name: string; pcbX: number; pcbY: number; schX: number; schY: number; schSectionName: string; pcbSx?: Record<string, { visibility?: "hidden" }> }) => (
  <chip
    {...props}
    pinLabels={{ pin1: ["BAT_P"], pin2: ["BAT_N"] }}
    schWidth={1.4}
    schHeight={1.6}
    schPinArrangement={{ topSide: { pins: ["BAT_P"], direction: "left-to-right" }, bottomSide: { pins: ["BAT_N"], direction: "left-to-right" } }}
    footprint={
      <footprint insertionDirection="from_above">
        <platedhole portHints={["pin1"]} pcbX="-3.75mm" pcbY="0mm" shape="circle" holeDiameter="1.8mm" outerDiameter="2.8mm" />
        <platedhole portHints={["pin2"]} pcbX="3.75mm" pcbY="0mm" shape="circle" holeDiameter="1.8mm" outerDiameter="2.8mm" />
      </footprint>
    }
    doNotPlace
  />
)

export default () => (
  <board
    // 55 mm wide like R2f, 31 mm tall: R2f's 28 mm plus 3 mm at the bottom edge. Both top corners
    // are cut away (6 mm wide, 3 mm deep) so the neck servo clears the board when the head nods.
    // Board coordinates here (the layout group below is 1.5 mm higher).
    outline={[
      { x: -27.5, y: -15.5 }, { x: 27.5, y: -15.5 }, { x: 27.5, y: 12.5 }, { x: 21.5, y: 12.5 },
      { x: 21.5, y: 15.5 }, { x: -21.5, y: 15.5 }, { x: -21.5, y: 12.5 }, { x: -27.5, y: 12.5 },
    ]}
    layers={2}
    // Every line is drawn by hand; GND is joined by the pours on both sides.
    routeRemaining={false}
    title="DuckBuddy PDB/IMU R3"
    minTraceWidth="0.15mm"
    minTraceToPadEdgeClearance="0.15mm"
    minTraceToHoleEdgeClearance="0.3mm"
    minBoardEdgeClearance="0.3mm"
    minViaHoleDiameter="0.3mm"
    minViaPadDiameter="0.6mm"
    minViaEdgeToPadEdgeClearance="0.2mm"
    pcbStyle={{ viaHoleDiameter: "0.3mm", viaPadDiameter: "0.6mm" }}
  >
    <net name="GND" isGroundNet />
    <net name="V3V3" isPowerNet />

    <schematicsection name="input" displayName="Battery input, switch, reverse protection" />
    <schematicsection name="branches" displayName="Fused branches and connectors" />
    <schematicsection name="ldo" displayName="3.3 V supply" />
    <schematicsection name="mcu" displayName="MCU (STM32G031) and SWD" />
    <schematicsection name="imu" displayName="IMU (LSM6DSV16X)" />
    <schematicsection name="bus" displayName="Servo bus driver" />
    <schematicsection name="cutoff" displayName="Low-battery cutoff (2S/3S by JP2)" />
    <schematicsection name="sense" displayName="Battery voltage and current sense" />
    <schematicsection name="test" displayName="Test points and SWD pads" />

    {/* Every coordinate in this file is in the R2f frame: origin at the R2f board center, which is
        1.5 mm above the center of this taller board. This group moves the whole layout up 1.5 mm. */}
    <group name="layout" pcbY={1.5}>

    {/* ── Mounting: two M2 screws through standoffs (about 6.5 mm) into the free servo-top holes of the
        two rear hip servos, at trunk x -16.5, y ±25.5 on the robot model (hardware/print/DuckBuddy.3mf).
        The keepout keeps the pours, and so the copper, out from under the screw head (Ø3.8 mm) and
        the standoff. ── */}
    {[-1, 1].map((sx, i) => (
      <React.Fragment key={`h${i}`}>
        <hole name={`H${i + 1}`} diameter="2.2mm" pcbX={sx * 25.5} pcbY={-14.5} />
        <keepout shape="circle" radius="2mm" pcbX={sx * 25.5} pcbY={-14.5} />
      </React.Fragment>
    ))}

    {/* ── Battery input ── */}
    <BatteryPads name="J1" {...lab("J1")} pcbX={P.J1.x} pcbY={P.J1.y} schX={-24} schY={0} schSectionName="input" />
    {POWER.map(([from, to, w, part, pts], i) => (
      <trace key={`pw${i}`} from={from} to={to} thickness={`${w}mm`} pcbPath={at(part, pts)} />
    ))}
    {CUT_LINES.map(([from, to, w, part, segs], i) => (
      <trace key={`cut${i}`} from={from} to={to} thickness={`${w}mm`} pcbPath={route(part, segs)} />
    ))}
    {HAND_LINES.map(([from, to, w, part, segs], i) => (
      <trace key={`hand${i}`} from={from} to={to} thickness={`${w}mm`} pcbPath={route(part, segs)} />
    ))}
    {GND_VIAS.map(([x, y], i) => (
      <via key={`gv${i}`} connectsTo="net.GND" pcbX={x} pcbY={y} holeDiameter="0.4mm" outerDiameter="0.8mm" fromLayer="top" toLayer="bottom" />
    ))}
    {/* U5 GND: a small via under U5, between its pad rows (the battery line to D1 closes in the pour below U5). */}
    <via connectsTo="net.GND" pcbX={-3.7} pcbY={-12.4} holeDiameter="0.3mm" outerDiameter="0.6mm" fromLayer="top" toLayer="bottom" />

    {/* Q1 blocks a reversed battery, Q2 is the switch. Common source FET_S. */}
    <AON7524 name="Q1" {...lab("Q1")} schHeight={1} pcbX={P.Q1.x} pcbY={P.Q1.y} pcbRotation={P.Q1.rot} schX={-18} schY={-3} schSectionName="input" />
    <AON7524 name="Q2" {...lab("Q2")} schHeight={1} pcbX={P.Q2.x} pcbY={P.Q2.y} pcbRotation={0} schX={-13} schY={-3} schSectionName="input" />
    {/* Q1/Q2 drains and sources are joined by the POWER copper above; these name the nets. */}
    <trace from=".Q2 > .S1" to="net.FET_S" />
    <trace from=".Q2 > .D5" to="net.GND" />
    <trace from=".Q1 > .G" to="net.FET_G" />
    <trace from=".Q2 > .G" to="net.FET_G" />

    {/* Gate drive: switch closed and battery above the cutoff -> Q3 drives DRV high and the gate
        charges through R1 and D4. R2 discharges the gate when the switch opens; D2 clamps Vgs at
        12 V; C2 slows turn-on (soft start into the bulk capacitance). */}
    <MS_1290N name="SW1" {...lab("SW1")} pcbX={P.SW1.x} pcbY={P.SW1.y} schX={-22} schY={4} schSectionName="input" />
    <trace from=".SW1 > .pin1" to="net.SW_ON" />
    <chip
      name="J3" {...lab("J3")}
      schWidth={1.4}
      schHeight={1.6}
      schPinArrangement={{ topSide: { pins: ["VBAT"], direction: "left-to-right" }, bottomSide: { pins: ["SW_ON"], direction: "left-to-right" } }}
      footprint="pinrow2_p2.54mm"
      pinLabels={{ pin1: ["VBAT"], pin2: ["SW_ON"] }}
      pcbX={P.J3.x}
      pcbY={P.J3.y}
      pcbRotation={P.J3.rot}
      schX={-22}
      schY={7}
      schSectionName="input"
      doNotPlace
    />
    {/* J3 sits in parallel with SW1 (its VBAT pin is wired in POWER); SW_ON joins the line from SW1 to R18. */}
    <trace from=".J3 > .SW_ON" to=".SW1 > .pin1" thickness="0.3mm" pcbPath={at(P.J3, [[-22.17, -13.0], [-16.35, -13.0]])} />
    <resistor name="R1" {...lab("R1")} schRotation={-90} schSize="sm" resistance="10k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r10k] }} pcbX={CUT.R1.x} pcbY={CUT.R1.y} pcbRotation={CUT.R1.rot} schX={-13} schY={6.4} schSectionName="input" />
    <trace from=".R1 > .pin1" to="net.DRV" />
    <trace from=".R1 > .pin2" to="net.GATE_X" />
    <diode name="D4" {...lab("D4")} schRotation={90} schSize="sm" pinLabels={cathodeFirst} footprint="sod323" supplierPartNumbers={{ jlcpcb: [LCSC.diode] }} pcbX={CUT.D4.x} pcbY={CUT.D4.y} pcbRotation={CUT.D4.rot} schX={-11} schY={8} schSectionName="cutoff" />
    <trace from=".D4 > .anode" to="net.GATE_X" />
    <trace from=".D4 > .cathode" to="net.FET_G" />
    {/* Q4 empties the gate fast when DRV falls (D4 then blocks the slow path through R1). */}
    <S8550 name="Q4" {...lab("Q4")} pcbX={CUT.Q4.x} pcbY={CUT.Q4.y} pcbRotation={CUT.Q4.rot} schX={-8} schY={8} schSectionName="cutoff" />
    <trace from=".Q4 > .E" to="net.FET_G" />
    <trace from=".Q4 > .B" to="net.GATE_X" />
    <trace from=".Q4 > .C" to="net.FET_S" />

    {/* ── Low-battery cutoff. Everything is referenced to FET_S (the FETs' common source), not GND,
        so the reverse-battery block stays intact; when the FETs are off, this circuit's few µA
        return through Q1's body diode.
        Divider SW_ON -R18-(R19 | JP2)- CUT_A -R20- CUT_REF -R21- FET_S, filtered by C17 (~0.5 s).
        U6 (CJ431, 2.5 V) pulls Q3's base low when CUT_REF passes 2.5 V; Q3 then drives DRV high.
        R22 from DRV to CUT_REF gives the hysteresis.
        Battery levels, JP2 open (3S): off below 9.3 V, back on above 10.7-11.0 V. JP2 bridged (2S):
        off below 6.2 V, on above 6.9-7.2 V. The turn-on level includes Q1's body diode (0.3-0.6 V),
        which carries the cutoff current while the FETs are off. ── */}
    <S8550 name="Q3" {...lab("Q3")} pcbX={CUT.Q3.x} pcbY={CUT.Q3.y} pcbRotation={CUT.Q3.rot} schX={-16} schY={11} schSectionName="cutoff" />
    <trace from=".Q3 > .E" to="net.SW_ON" />
    <trace from=".Q3 > .B" to="net.CUT_B" />
    <trace from=".Q3 > .C" to="net.DRV" />
    <CJ431 name="U6" {...lab("U6")} pcbX={CUT.U6.x} pcbY={CUT.U6.y} pcbRotation={CUT.U6.rot} schX={-16} schY={15} schSectionName="cutoff" />
    <trace from=".U6 > .A" to="net.FET_S" />
    <trace from=".U6 > .R" to="net.CUT_REF" />
    <trace from=".U6 > .K" to="net.CUT_K" />
    {[
      { n: "R18", r: "33k", lcsc: LCSC.r33k, fp: "0402", a: "net.SW_ON", b: "net.CUT_MID", sx: -22, sy: 11 },
      { n: "R19", r: "39k", lcsc: LCSC.r39k_0603, fp: "0603", a: "net.CUT_MID", b: "net.CUT_A", sx: -22, sy: 13.5 },
      { n: "R20", r: "10k", lcsc: LCSC.r10k, fp: "0402", a: "net.CUT_A", b: "net.CUT_REF", sx: -19.5, sy: 15 },
      { n: "R21", r: "27k", lcsc: LCSC.r27k_0603, fp: "0603", a: "net.CUT_REF", b: "net.FET_S", sx: -18.5, sy: 17 },
      { n: "R22", r: "680k", lcsc: LCSC.r680k_0603, fp: "0603", a: "net.DRV", b: "net.CUT_REF", sx: -13, sy: 14 },
      { n: "R23", r: "4.7k", lcsc: LCSC.r4k7, fp: "0402", a: "net.CUT_B", b: "net.CUT_K", sx: -13.5, sy: 11.5 },
      { n: "R24", r: "10k", lcsc: LCSC.r10k, fp: "0402", a: "net.SW_ON", b: "net.CUT_B", sx: -18.5, sy: 9 },
      { n: "R25", r: "10k", lcsc: LCSC.r10k, fp: "0402", a: "net.DRV", b: "net.FET_S", sx: -11, sy: 12 },
    ].map((r) => (
      <React.Fragment key={r.n}>
        <resistor name={r.n} {...lab(r.n)} schRotation={-90} schSize="sm" resistance={r.r} footprint={r.fp} supplierPartNumbers={{ jlcpcb: [r.lcsc] }} pcbX={CUT[r.n].x} pcbY={CUT[r.n].y} pcbRotation={CUT[r.n].rot} schX={r.sx} schY={r.sy} schSectionName="cutoff" />
        <trace from={`.${r.n} > .pin1`} to={r.a} />
        <trace from={`.${r.n} > .pin2`} to={r.b} />
      </React.Fragment>
    ))}
    <capacitor name="C17" {...lab("C17")} schRotation={-90} schSize="sm" capacitance="22uF" footprint="0805" supplierPartNumbers={{ jlcpcb: [LCSC.c22u_25v] }} pcbX={CUT.C17.x} pcbY={CUT.C17.y} pcbRotation={CUT.C17.rot} schX={-21} schY={17} schSectionName="cutoff" />
    <trace from=".C17 > .pin1" to="net.CUT_A" />
    <trace from=".C17 > .pin2" to="net.FET_S" />
    {/* JP2: battery type. Open = 3S (the safe default: a 2S pack never reaches the 3S turn-on
        voltage, so the board stays off). Bridged = 2S. Bare pads, nothing to assemble. */}
    <solderjumper name="JP2" {...lab("JP2")} footprint={SOLDER_JUMPER} pinCount={2} pcbX={CUT.JP2.x} pcbY={CUT.JP2.y} pcbRotation={CUT.JP2.rot} schRotation={-90} schX={-24} schY={13.5} schSectionName="cutoff" doNotPlace />
    <trace from=".JP2 > .pin1" to="net.CUT_MID" />
    <trace from=".JP2 > .pin2" to="net.CUT_A" />
    <resistor name="R2" {...lab("R2")} schRotation={-90} schSize="sm" resistance="100k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r100k] }} pcbX={L.R2.x} pcbY={L.R2.y} pcbRotation={L.R2.rot} schX={-15} schY={5} schSectionName="input" />
    <trace from=".R2 > .pin1" to="net.FET_G" />
    <trace from=".R2 > .pin2" to="net.FET_S" />
    <diode name="D2" {...lab("D2")} schRotation={90} schSize="sm" zener pinLabels={cathodeFirst} footprint="sod123" supplierPartNumbers={{ jlcpcb: [LCSC.zener10] }} pcbX={3.5} pcbY={-6.5} pcbRotation={90} schX={-11} schY={5} schSectionName="input" />
    <trace from=".D2 > .cathode" to="net.FET_G" />
    <trace from=".D2 > .anode" to="net.FET_S" />
    <capacitor name="C2" {...lab("C2")} schRotation={-90} schSize="sm" capacitance="1uF" footprint="0603" supplierPartNumbers={{ jlcpcb: [LCSC.c1u_50v] }} pcbX={L.C2.x} pcbY={L.C2.y} pcbRotation={L.C2.rot} schX={-13} schY={5} schSectionName="input" />
    <trace from=".C2 > .pin1" to="net.FET_G" />
    <trace from=".C2 > .pin2" to="net.FET_S" />

    {/* Surge clamp and bulk capacitance, after the FETs. */}
    <diode name="D1" {...lab("D1")} schRotation={90} tvs pinLabels={cathodeFirst} footprint="smb" supplierPartNumbers={{ jlcpcb: [LCSC.tvs] }} pcbX={P.D1.x} pcbY={P.D1.y} pcbRotation={P.D1.rot} schX={-9} schY={0} schSectionName="input" />
    <trace from=".D1 > .anode" to="net.GND" />
    <RVT100UF25V67RV0011 name="C1" {...lab("C1")} maxDecouplingTraceLength={20} schRotation={-90} pcbX={P.C1.x} pcbY={P.C1.y} pcbRotation={P.C1.rot} schX={-6} schY={0} schSectionName="input" />
    <trace from=".C1 > .neg" to="net.GND" />

    {/* ── Fused branches: left leg (J4), right leg (J6), head + HAT (J5) ── */}
    {[
      { side: "LEFT", f: "F1", c: "C3", r: "R3", rl: "R6", led: "LED1", j: "J4", rx: L.R3.x, ry: L.R3.y, rrot: L.R3.rot, lx: L.R6.x, ly: L.R6.y },
      { side: "RIGHT", f: "F2", c: "C4", r: "R4", rl: "R7", led: "LED2", j: "J6", rx: P.R4.x, ry: P.R4.y, rrot: P.R4.rot, lx: L.R7.x, ly: L.R7.y },
      { side: "HEAD", f: "F3", c: "C5", r: "R5", rl: "R9", led: "LED3", j: "J5", rx: 5.95, ry: 9.05, rrot: 180, dataByHand: true, lx: -10.2, ly: 12.2 },
    ].map((b, i) => (
      <React.Fragment key={b.side}>
        {/* Fuse and capacitor power pins are wired in POWER. */}
        {/* PPTC: holds 3 A, trips at 6 A, resets by itself once the fault is gone. */}
        <A_1210L300_24WR name={b.f} {...lab(b.f)} schRotation={-90} pcbX={P[b.f].x} pcbY={P[b.f].y} pcbRotation={P[b.f].rot ?? 0} schX={2} schY={6 - i * 6} schSectionName="branches" />
        <capacitor name={b.c} {...lab(b.c)} capacitance="10uF" footprint="0805" supplierPartNumbers={{ jlcpcb: [LCSC.c10u_25v] }} pcbX={P[b.c].x} pcbY={P[b.c].y} pcbRotation={P[b.c].rot ?? 0} schX={5} schY={5 - i * 6} schOrientation="vertical" schSectionName="branches" />
        <trace from={`.${b.c} > .pin2`} to="net.GND" />
        <resistor name={b.r} {...lab(b.r)} resistance="33" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r33] }} pcbX={b.rx} pcbY={b.ry} pcbRotation={b.rrot ?? 0} schX={8} schY={4 - i * 6} schSectionName="branches" />
        {!b.dataByHand && <trace from={`.${b.r} > .pin1`} to="net.DATA" />}
        {!b.dataByHand && <trace from={`.${b.r} > .pin2`} to={`net.DATA_${b.side}`} />}
        <resistor name={b.rl} {...lab(b.rl)} schRotation={-90} resistance="3.3k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r3k3] }} pcbX={b.lx} pcbY={b.ly} schX={5} schY={7 - i * 6} schSectionName="branches" />
        <trace from={`.${b.rl} > .pin1`} to={`.${b.j} > .pin2`} />
        <trace from={`.${b.rl} > .pin2`} to={`net.LED_${b.side}`} />
        <KT_0805G name={b.led} {...lab(b.led)} schRotation={-90} color="green" pcbX={b.lx + 3.3} pcbY={b.ly} pcbRotation={180} schX={8} schY={7 - i * 6} schSectionName="branches" />
        <trace from={`.${b.led} > .anode`} to={`net.LED_${b.side}`} />
        <trace from={`.${b.led} > .cathode`} to="net.GND" />
      </React.Fragment>
    ))}

    {/* Connectors: pin 1 GND, pin 2 V, pin 3 DATA (as on R2f). Through-hole, soldered by hand
        (doNotPlace: not fitted by the assembly service). Pin 2 is wired in POWER.
        J4/J6 are side-entry PH2.0 headers (4.8 mm tall) at the side edges, pins at y = 3, opening toward
        the bottom edge: the plug goes in from the bottom and lies flat on the board, and its wires leave
        over the side edge. The roof of the body leaves 5.4-7.9 mm above them. */}
    <S3B_PH_K_S_LF__SN_ name="J4" {...lab("J4")} pcbX={-23.2} pcbY={3.0} schX={12} schY={6} schSectionName="branches" doNotPlace />
    <trace from=".J4 > .pin1" to="net.GND" />
    <trace from=".J4 > .pin3" to="net.DATA_LEFT" />
    <S3B_PH_K_S_LF__SN_ name="J6" {...lab("J6")} pcbX={23.25} pcbY={3.0} schX={12} schY={0} schSectionName="branches" doNotPlace />
    <trace from=".J6 > .pin1" to="net.GND" />
    <trace from=".J6 > .pin3" to="net.DATA_RIGHT" />
    <B3B_XH_A_LF__SN_ name="J5" {...lab("J5")} pcbX={0} pcbY={11} schX={12} schY={-6} schSectionName="branches" doNotPlace />
    <trace from=".J5 > .pin1" to="net.GND" />
    {/* J5 pin 3 (DATA_HEAD) is wired in IMU_LINES. */}
    {/* Connector bodies, drawn on the top silkscreen so they are soldered the right way round.
        J4/J6 (S3B-PH-K-S): 7.9 × 7.6 mm, the pins 1.35 mm from the back, the opening toward the bottom
        edge; the outer sides stop 0.25-0.3 mm short of the board edge. An XH body is 5.75 mm deep with the
        pins 2.35 mm from one side; J5: the deep side faces the board centre, so the body stays inside
        the outline. */}
    <silkscreenrect pcbX={-23.2} pcbY={0.55} width={7.9} height={7.6} strokeWidth={0.15} />
    <silkscreenrect pcbX={23.25} pcbY={0.55} width={7.9} height={7.6} strokeWidth={0.15} />
    <silkscreenrect pcbX={0} pcbY={10.475} width={9.9} height={5.75} strokeWidth={0.15} />

    {/* ── 3.3 V: 1 A fuse, 30 V LDO (survives the TVS clamp voltage) ── */}
    <fuse name="F4" {...lab("F4")} schRotation={-90} currentRating="1A" voltageRating="32V" footprint="0603" supplierPartNumbers={{ jlcpcb: [LCSC.fuse1a] }} pcbX={P.F4.x} pcbY={P.F4.y} schX={-22} schY={-12} schSectionName="ldo" />
    <trace from=".F4 > .pin2" to="net.V_LDO" />
    <capacitor name="C6" {...lab("C6")} maxDecouplingTraceLength={2.5} capacitance="1uF" footprint="0603" supplierPartNumbers={{ jlcpcb: [LCSC.c1u_50v] }} pcbX={L.C6.x} pcbY={L.C6.y} pcbRotation={L.C6.rot} schX={-19} schY={-13} schOrientation="vertical" schSectionName="ldo" />
    <trace from=".C6 > .pin1" to="net.V_LDO" />
    <trace from=".C6 > .pin2" to="net.GND" />
    <TPS70933DBVR name="U3" {...lab("U3")} schHeight={0.6} pcbX={L.U3.x} pcbY={L.U3.y} pcbRotation={L.U3.rot} schX={-15} schY={-12} schSectionName="ldo" />
    <trace from=".U3 > .IN" to="net.V_LDO" />
    {/* EN is left open: the TPS709 has an internal pull-up on EN, so it is on whenever IN has power.
        (EN is clamped inside at 6.5 V, so it must never be tied to the battery.) */}
    <trace from=".U3 > .GND" to="net.GND" />
    <trace from=".U3 > .OUT" to="net.V3V3" />
    <capacitor name="C7" {...lab("C7")} maxDecouplingTraceLength={2.5} capacitance="4.7uF" footprint="0603" supplierPartNumbers={{ jlcpcb: [LCSC.c4u7] }} pcbX={L.C7.x} pcbY={L.C7.y} pcbRotation={L.C7.rot} schX={-16.0} schY={-16.0} schOrientation="vertical" schSectionName="ldo" />
    <trace from=".C7 > .pin1" to="net.V3V3" />
    <trace from=".C7 > .pin2" to="net.GND" />

    {/* ── MCU ── */}
    <STM32G031F8P6 name="U1" {...lab("U1")} pcbX={11.5} pcbY={1.5} schX={6} schY={-14} schSectionName="mcu" />
    <trace from=".U1 > .VDD" to=".C8 > .pin1" thickness="0.25mm" pcbPath={at(U1_AT, [[10.53, -2.5]])} />
    <trace from=".U1 > .VSS" to=".C8 > .pin2" thickness="0.25mm" pcbPath={at(U1_AT, [[11.18, -2.5]])} />
    <capacitor name="C8" {...lab("C8")} maxDecouplingTraceLength={2.5} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={10.7} pcbY={-2.95} schX={-14.7} schY={-16.0} schOrientation="vertical" schSectionName="ldo" />
    <trace from=".C8 > .pin2" to="net.GND" thickness="0.3mm" pcbPath={at({ x: 10.7, y: -2.95 }, [[11.21, -4]])} />
    <capacitor name="C9" {...lab("C9")} maxDecouplingTraceLength={3} capacitance="4.7uF" footprint="0603" supplierPartNumbers={{ jlcpcb: [LCSC.c4u7] }} pcbX={L.C9.x} pcbY={L.C9.y} pcbRotation={L.C9.rot} schX={-13.4} schY={-16.0} schOrientation="vertical" schSectionName="ldo" />
    <trace from=".C9 > .pin1" to="net.V3V3" />
    <trace from=".C9 > .pin2" to="net.GND" />
    <capacitor name="C10" {...lab("C10")} maxDecouplingTraceLength={5} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={L.C10.x} pcbY={L.C10.y} schX={1.5} schY={-17.5} schOrientation="vertical" schSectionName="mcu" />
    {/* C10 sits on the NRST line below U1 (HAND_LINES); its GND pad is in the top pour. */}
    <trace from=".C10 > .pin2" to="net.GND" />

    {/* SWD, same order as R2f J2: 1 SWDIO, 2 SWCLK, 3 GND, 4 3V3. */}
    <chip
      name="J2" {...lab("J2")}
      schWidth={1.4}
      footprint="pinrow4_p2.54mm"
      pinLabels={{ pin1: ["SWDIO"], pin2: ["SWCLK"], pin3: ["GND"], pin4: ["V3V3"] }}
      supplierPartNumbers={{ jlcpcb: [LCSC.header4] }}
      doNotPlace
      pcbX={19.5} pcbY={-7}
      schX={11}
      schY={-14}
      schSectionName="mcu"
    />
    <trace from=".J2 > .GND" to="net.GND" />
    <trace from=".J2 > .V3V3" to="net.V3V3" />

    {/* Status LED on PA11 (free on R2f; the firmware can blink it). */}
    <resistor name="R10" {...lab("R10")} resistance="1k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r1k] }} pcbX={16.4} pcbY={2.6} schX={10} schY={-18} schSectionName="mcu" />
    <trace from=".R10 > .pin2" to="net.LED_STATUS" />
    {/* JP1: bus speed. Open = 500 kbit/s (DuckBuddy); bridged with solder = 1 Mbit/s (STS3215 bus,
        Frankenduck). The firmware reads PC15 once at start-up with its internal pull-up.
        Bare pads on the bottom side, nothing to assemble. pin1 is GND (under VSS), pin2 is PC15. */}
    <solderjumper name="JP1" {...lab("JP1")} footprint={SOLDER_JUMPER} pinCount={2} layer="bottom" pcbX={11.18} pcbY={-1.0} schRotation={-90} schX={3.3} schY={-15.5} schSectionName="mcu" doNotPlace />
    <KT_0603R name="LED4" {...lab("LED4")} schRotation={-90} pcbX={17.0} pcbY={4.2} pcbRotation={180} schX={12.5} schY={-18} schSectionName="mcu" />
    <trace from=".LED4 > .A" to="net.LED_STATUS" />
    <trace from=".LED4 > .K" to="net.GND" />

    {/* ── IMU, on the top side with every other part (one-sided assembly). Host config: [bus] imu_axes, see README. ── */}
    <LSM6DSV16XTR name="U2" {...lab("U2")} pcbX={3} pcbY={2.5} schX={6} schY={-26} schSectionName="imu" />
    <trace from=".U2 > .Vdd" to="net.V3V3" />
    <trace from=".U2 > .Vdd_IO" to="net.V3V3" />
    <trace from=".U2 > .GND1" to="net.GND" />
    <trace from=".U2 > .GND2" to="net.GND" />
    <trace from=".U2 > .SCx" to="net.GND" />
    {/* IMU, SWD and status LED lines: IMU_LINES (hand-routed). */}
    {IMU_LINES.map(([from, to, pts], i) => (
      <trace key={`imu${i}`} from={from} to={to} thickness="0.2mm" pcbPath={pts} />
    ))}
    <capacitor name="C11" {...lab("C11")} maxDecouplingTraceLength={3} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={5.6} pcbY={4.6} schX={-16.0} schY={-17.4} schOrientation="vertical" schSectionName="ldo" />
    <trace from=".C11 > .pin1" to="net.V3V3" />
    <trace from=".C11 > .pin2" to="net.GND" />
    <capacitor name="C12" {...lab("C12")} maxDecouplingTraceLength={2} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={2.3} pcbY={4.6} schX={-14.7} schY={-17.4} schOrientation="vertical" schSectionName="ldo" />
    <trace from=".C12 > .pin1" to="net.V3V3" />
    <trace from=".C12 > .pin2" to="net.GND" />
    {/* R8: CS pull-up keeps the IMU in SPI-idle while the MCU is in reset. */}
    <resistor name="R8" {...lab("R8")} schRotation={-90} resistance="10k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r10k] }} pcbX={P.R8.x} pcbY={P.R8.y} schX={11} schY={-25} schSectionName="imu" />
    <trace from=".R8 > .pin1" to="net.V3V3" />

    {/* ── Bus driver: PA2 -> U4 -> DATA_IMU; PA1 = USART2 DE = U4 OE; PA3 listens ── */}
    <A_74LVC1G126GW name="U4" {...lab("U4")} schHeight={0.6} pcbX={L.U4.x} pcbY={L.U4.y} schX={-14} schY={-24} schSectionName="bus" />
    <trace from=".U4 > .VCC" to="net.V3V3" />
    <trace from=".U4 > .GND" to="net.GND" />
    <trace from=".U4 > .A" to=".U1 > .PA2" />
    <trace from=".U4 > .OE" to=".U1 > .PA1" />
    <trace from=".U4 > .Y" to="net.DATA_IMU" />
    <trace from=".U1 > .PA3" to="net.DATA_IMU" />
    <capacitor name="C13" {...lab("C13")} maxDecouplingTraceLength={2} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={L.C13.x} pcbY={L.C13.y} schX={-13.4} schY={-17.4} schOrientation="vertical" schSectionName="ldo" />
    <trace from=".C13 > .pin1" to="net.V3V3" />
    <trace from=".C13 > .pin2" to="net.GND" />
    {/* R11: holds OE low so the board never drives the bus while the MCU is in reset or being flashed. */}
    <resistor name="R11" {...lab("R11")} schRotation={-90} resistance="100k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r100k] }} pcbX={L.R11.x} pcbY={L.R11.y} pcbRotation={L.R11.rot} schX={-18} schY={-22} schSectionName="bus" />
    <trace from=".R11 > .pin1" to=".U1 > .PA1" />
    <trace from=".R11 > .pin2" to="net.GND" />
    <resistor name="R13" {...lab("R13")} resistance="33" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r33] }} pcbX={L.R13.x} pcbY={L.R13.y} pcbRotation={L.R13.rot} schX={-10} schY={-24} schSectionName="bus" />
    <trace from=".R13 > .pin1" to="net.DATA_IMU" />
    <trace from=".R13 > .pin2" to="net.DATA" />
    {/* D3 is bidirectional, so its two pins are interchangeable. */}
    <PESD5V0S1BA name="D3" {...lab("D3")} pcbX={7} pcbY={10.45} schX={-6} schY={-23.5} schRotation={90} schSectionName="bus" />
    <trace from=".D3 > .pin2" to="net.GND" />
    {/* R12: optional DATA idle pull-up, not fitted (the HAT's transceiver normally sets the idle level). */}
    <resistor name="R12" {...lab("R12")} schRotation={-90} resistance="10k" footprint="0402" pcbX={7} pcbY={12.6} schX={-6} schY={-22} schSectionName="bus" doNotPlace />
    <trace from=".R12 > .pin1" to="net.V3V3" />

    {/* ── Battery voltage and current, read by the MCU's ADC (served on the bus, see firmware). ── */}
    {/* PA0: VBAT through 100k / 22k (12.6 V -> 2.27 V; full scale 18.3 V). */}
    <resistor name="R16" {...lab("R16")} schRotation={-90} resistance="100k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r100k] }} pcbX={SNS.R16.x} pcbY={SNS.R16.y} pcbRotation={SNS.R16.rot} schX={14} schY={-24} schSectionName="sense" />
    <trace from=".R16 > .pin1" to=".RS1 > .pin2" thickness="0.3mm" pcbPath={at(SNS.R16, [[-0.5, -10.8]])} />
    {/* R17 and C16 join their GND vias below them (the battery pads close in their pour). */}
    <trace from=".R16 > .pin2" to=".R17 > .pin1" thickness="0.25mm" pcbPath={at(SNS.R16, [[2.11, -12.4]])} />
    <resistor name="R17" {...lab("R17")} schRotation={-90} resistance="22k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r22k] }} pcbX={SNS.R17.x} pcbY={SNS.R17.y} pcbRotation={SNS.R17.rot} schX={14} schY={-27} schSectionName="sense" />
    <trace from=".R17 > .pin2" to="net.GND" thickness="0.25mm" pcbPath={at(SNS.R17, [[1.24, -14.0]])} />
    <capacitor name="C16" {...lab("C16")} schRotation={-90} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={SNS.C16.x} pcbY={SNS.C16.y} pcbRotation={SNS.C16.rot} schX={16} schY={-27} schSectionName="sense" />
    <trace from=".C16 > .pin1" to=".R16 > .pin2" thickness="0.25mm" pcbPath={at(SNS.C16, [[2.11, -11.89]])} />
    <trace from=".C16 > .pin2" to="net.GND" thickness="0.25mm" pcbPath={at(SNS.C16, [[3.4, -14.0]])} />
    {/* PA0 (VSENSE) is wired in IMU_LINES. */}
    {/* PB7: battery current. RS1 (2 mΩ) in the battery plus line, U5 (INA180A2, ×50): 0.1 V per A,
        full scale 33 A. R15/C15 filter the output and feed the ADC's sampling capacitor. */}
    <RLM12FTCMR002 name="RS1" {...lab("RS1")} schRotation={-90} pcbX={SNS.RS1.x} pcbY={SNS.RS1.y} pcbRotation={SNS.RS1.rot} schX={-24} schY={-5} schSectionName="input" />
    <INA180A2IDBVR name="U5" {...lab("U5")} pcbX={SNS.U5.x} pcbY={SNS.U5.y} pcbRotation={SNS.U5.rot} schX={19} schY={-24} schSectionName="sense" />
    <trace from=".U5 > .VS" to="net.V3V3" />
    <trace from=".U5 > .GND" to="net.GND" thickness="0.25mm" pcbPath={at(SNS.U5, [[-3.7, -12.4]])} />
    <trace from=".U5 > .OUT" to=".R15 > .pin1" />
    <capacitor name="C14" {...lab("C14")} maxDecouplingTraceLength={2} schRotation={-90} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={SNS.C14.x} pcbY={SNS.C14.y} pcbRotation={SNS.C14.rot} schX={22} schY={-27} schSectionName="sense" />
    <trace from=".C14 > .pin1" to="net.V3V3" />
    <trace from=".C14 > .pin2" to="net.GND" />
    <resistor name="R15" {...lab("R15")} resistance="1k" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.r1k] }} pcbX={SNS.R15.x} pcbY={SNS.R15.y} pcbRotation={SNS.R15.rot} schX={22} schY={-22} schSectionName="sense" />
    <capacitor name="C15" {...lab("C15")} maxDecouplingTraceLength={2.5} schRotation={-90} capacitance="100nF" footprint="0402" supplierPartNumbers={{ jlcpcb: [LCSC.c100n_0402] }} pcbX={SNS.C15.x} pcbY={SNS.C15.y} pcbRotation={SNS.C15.rot} schX={23.7} schY={-24} schSectionName="sense" />
    <trace from=".C15 > .pin2" to="net.GND" />

    {/* ── Test points and the SWD pads ── */}
    {[
      { n: "TP1", net: ".SW1 > .pin2", path: [[-11.0, -10.3], [-13.35, -10.3]] as [number, number][] },
      { n: "TP2", net: "net.V3V3" },
      { n: "TP3", net: "net.GND" },
      { n: "TP4", net: "net.DATA" },
    ].map((t) => (
      <React.Fragment key={t.n}>
        <testpoint name={t.n} {...lab(t.n)} footprintVariant="pad" padShape="circle" padDiameter="1.2mm" doNotPlace pcbX={TPS[t.n].x} pcbY={TPS[t.n].y} schX={26} schY={-14 - Number(t.n.slice(2)) * 1.5} schSectionName="test" />
        <trace from={`.${t.n} > .pin1`} to={t.net} {...(t.path ? { thickness: "0.5mm", pcbPath: at(TPS[t.n], t.path) } : {})} />
      </React.Fragment>
    ))}
    {/* J7: Tag-Connect TC2030-NL pads (spring-pin cable, nothing fitted). Pinout of the TC2030-CTX
        cable: 1 3V3, 2 SWDIO, 3 NRST, 4 SWCLK, 5 GND, 6 SWO (not used). No paste on the pads. */}
    <chip
      name="J7" {...lab("J7")}
      footprint={
        <footprint insertionDirection="from_above">
          {[[1, -1.27, -0.635], [2, -1.27, 0.635], [3, 0, -0.635], [4, 0, 0.635], [5, 1.27, -0.635], [6, 1.27, 0.635]].map(([n, x, y]) => (
            <smtpad key={n} portHints={[`pin${n}`]} shape="circle" radius="0.3935mm" pcbX={`${x}mm`} pcbY={`${y}mm`} noSolderPaste />
          ))}
          <hole pcbX="-2.54mm" pcbY="0mm" diameter="0.991mm" />
          <hole pcbX="2.54mm" pcbY="1.016mm" diameter="0.991mm" />
          <hole pcbX="2.54mm" pcbY="-1.016mm" diameter="0.991mm" />
        </footprint>
      }
      pinLabels={{ pin1: ["V3V3"], pin2: ["SWDIO"], pin3: ["NRST"], pin4: ["SWCLK"], pin5: ["GND"], pin6: ["SWO"] }}
      pcbX={TPS.J7.x}
      pcbY={TPS.J7.y}
      pcbRotation={TPS.J7.rot}
      schX={26.31}
      schY={-24}
      schWidth={1.4}
      schSectionName="test"
      doNotPlace
    />
    {/* J7's V3V3, SWDIO, SWCLK and NRST lines are in HAND_LINES; GND is in the top pour. */}
    <trace from=".J7 > .GND" to="net.GND" />


    {TOP_ART.map(([k, x, y]) => {
      const a = topArt[k.split("#")[0]]
      return <silkscreengraphic key={`top${k}`} layer="top" imageUrl={a.url} width={a.width} height={a.height} pcbX={x} pcbY={y} />
    })}
    {/* Bottom-side art, placed in areas with no parts or traces. Made by art/make_art.py (see art/README.md). */}
    {/* k scales an item up (the drawings are vector, so lines only get thicker). */}
    {[
      // The robot drawing with "microduck" under it, in the free area left of J5.
      { a: microduckArt, x: -10.55, y: 9.0 },
      { a: microduckLabelArt, x: -10.55, y: 3.78 },
      // The flags, stacked in the upper left, beside the corner notch.
      { a: brazilArt, x: -17.9, y: 11.35, k: 1.1 },
      { a: pernambucoArt, x: -17.9, y: 6.85, k: 1.1 },
      { a: nameArt, x: 17.85, y: -9.85 },
      { a: handleArt, x: 17.85, y: -11.15 },
      // Left middle: "Designed in / Vila Mauricéia, / IPSEP", left aligned at x -22.57, and the dog to its right.
      { a: place1Art, x: -22.57 + place1Art.width / 2, y: 0.7 },
      { a: place2Art, x: -22.57 + place2Art.width / 2, y: -0.65 },
      { a: place3Art, x: -22.57 + place3Art.width / 2, y: -1.95 },
      { a: dogArt, x: -10.2, y: -0.65 },
      // JP1 (bottom side): bridged = 1 Mbit/s.
      { a: jp1Art, x: 8.85, y: -3.1 },
    ].map(({ a, x, y, k = 1 }, i) => (
      <silkscreengraphic key={`art${i}`} layer="bottom" imageUrl={a.url} width={a.width * k} height={a.height * k} pcbX={x} pcbY={y} />
    ))}
    </group>

    {/* GND pours on both sides, the return path for every branch, joined by stitching vias. */}
    <copperpour connectsTo="net.GND" layer="bottom" clearance="0.25mm" boardEdgeMargin="0.4mm" />
    <copperpour connectsTo="net.GND" layer="top" clearance="0.25mm" boardEdgeMargin="0.4mm" />
  </board>
)
