# PDB/IMU R3 — open power distribution + IMU board

R3 is an open version of the PDB/IMU board, written in [tscircuit](https://tscircuit.com) (`index.circuit.tsx`).
It follows the interface in [`docs/hardware/INTERFACE-CN.md`](../../../docs/hardware/INTERFACE-CN.md) §3 and is a drop-in replacement for R2f:

- 55 × 31 mm, 2 layers, made to lie flat on the hip servos. R2f is 55 × 28 mm: R3 is 3 mm taller, all of it at the
  bottom edge (the J1 side), and both top corners (the J5 side) are cut away, 6 × 3 mm, so the neck servo clears the board.
  It is held by two M2 screws on standoffs, not by the R2f holes: see [Mounting](#mounting);
- same connectors and pin order as R2f (J1 battery, J4/J6 PH2.0 3P, J5 XH 3P, J2 SWD). J4 and J6 are side-entry
  headers: their plugs lie flat and point to the bottom edge, because the body leaves no room for a vertical plug;
- same MCU pin map as R2f, so [`firmware/imu-feetech`](../../../firmware/imu-feetech/README.md) runs without changes
  (firmware 1.1 or later is needed for the 1 Mbit/s setting of JP1, 1.2 or later for the battery readings);
- all SMD parts, the IMU (U2) included, are on the **top side**, so JLCPCB assembles one side only.
  On R2f the IMU is on the bottom, so R3 needs a different host setting: see [IMU direction](#imu-direction);
- works with 2S and 3S batteries (3S LiHV included, 13.05 V when full). JP2 selects the low-battery cutoff.

**Status: not fabricated yet.** The circuit, placement and routing pass the tscircuit checks (see below), but no board has been built or tested.

## What R3 adds over R2f

| Feature | Parts | Notes |
|---|---|---|
| Power switch + reverse polarity protection | Q1, Q2 (AON7524), SW1, J3 | Two N-MOSFETs back to back in the battery ground return. Closing SW1 (or an outside switch on J3) turns both on. With the battery reversed, Q1 stays off and its body diode is reverse biased, so no current flows |
| Soft start | R1, D4, C2, R2, D2, Q4 | The gate charges through R1 and D4; C2 (1 µF) slows the turn-on, which limits the inrush current into the bulk capacitors. Q4 empties the gate fast at turn-off. R2 holds the gate off, D2 (BZT52C10) clamps Vgs at about 10 V, below the FETs' 12 V limit |
| Low-battery cutoff | U6 (TL431 type), Q3, R18–R25, C17, JP2 | Turns the FETs off when the battery runs low, with no firmware involved. See [Low-battery cutoff](#low-battery-cutoff) for the levels |
| Battery voltage reading | R16, R17, C16 → PA0 | 100 kΩ / 22 kΩ divider, full scale 18.3 V. Served on the bus (firmware 1.2) |
| Battery current reading | RS1 (2 mΩ), U5 (INA180A2), R15, C15 → PB7 | 0.1 V per A, full scale 33 A. Counts all current drawn from the battery |
| Self-resetting branch fuses | F1–F3 (1210L300/24WR, PPTC) | Hold 3 A, trip at 6 A, reset by themselves once the fault is gone. F4 (1 A, 0603) feeds the 3.3 V supply |
| Bulk input capacitance | C1 (100 µF), C3/C4/C5 (10 µF per branch) | Reduces sag and spikes from servo stalls and back-feed. The 0805 10 µF parts (25 V X5R) keep roughly 30–50% of their value at 12 V, which is normal for this size |
| Bus ESD protection | D3 (PESD5V0S1BA) | On the shared DATA line |
| Optional bus pull-up | R12 (10 kΩ, not fitted) | The HAT's transceiver sets the idle level by default; fit R12 only if needed |
| LEDs | LED1–LED3 (green, 0805), LED4 (red, 0603) | LED1–3 sit after each fuse: on = the branch has power, off = tripped fuse or switch off. LED4 is on PA11 and shows firmware status |
| Spare interrupt | IMU INT1 → PB3 | Not used by the current firmware |
| Bus speed jumper | JP1 (bottom side, marked "1M") | Open = 500 kbit/s (DuckBuddy). Bridge it with solder for 1 Mbit/s (STS3215 servos, Frankenduck). The firmware reads it at start-up. JP1 and JP2 have no solder paste, so reflow cannot bridge them |
| Test points | TP1 VB, TP2 3V3, TP3 G (GND), TP4 D (DATA) | 1.2 mm round pads for probes. TP1 is VBAT (the battery side of SW1); TP4 sits next to R13. They keep their solder paste, so reflow leaves a small solder dome on each, which is fine for probes |
| Tag-Connect SWD pads | J7 | For a TC2030-NL cable (TC2030-CTX pinout: 1 3V3, 2 SWDIO, 3 NRST, 4 SWCLK, 5 GND). J2 stays for a plain header |

LED4 (firmware `imu-feetech`): fast blink = the IMU does not answer; 1 Hz blink = orientation data is flowing.

The LEDs use the exact JLCPCB footprints (`imports/KT_0805G.tsx`, `imports/KT_0603R.tsx`). On these, pad 1 (anode) is on the +X side,
the opposite of the generic 0805/0603 footprints, so the LEDs face the right way when JLCPCB places them.

## Power

```
J1 battery + ─┬─ RS1 (2 mΩ) ─ VBAT ─ C1 ─┬─ F1 3 A ─ left leg J4
              └─ D1 (SMBJ14A)             ├─ F2 3 A ─ right leg J6
                                          ├─ F3 3 A ─ head J5 (incl. HAT)
                                          └─ F4 1 A ─ U3 TPS70933 ─ 3.3 V (MCU, IMU, U4, U5)
J1 battery − ─ Q1 ─ Q2 ─ GND (copper pour on both sides)
```

- U3 is rated for 30 V input, above the TVS clamp voltage (about 23 V), so it survives spikes.
- The switch opens only the ground return: when off, the VBAT net still carries battery voltage, but no load has a return path.
- The cutoff circuit is referenced to the FETs' common source (FET_S), not GND, so the reverse-battery block stays intact.
  When the FETs are off, its current returns through Q1's body diode.
- The VBAT copper from RS1 to the fuses is 3 mm wide (1 oz copper), for the full battery current of up to about 9 A
  (three branches near their 3 A hold current).

## Low-battery cutoff

U6 compares the battery voltage, divided by R18–R21, with its 2.5 V reference. R22 feeds back from the FET drive (DRV),
so the turn-on level is higher than the turn-off level, and a pack that sags under load does not switch the board off and on.
C17 filters short dips (about 0.5 s with JP2 open, 0.4 s with JP2 bridged).

| JP2 | Battery | Turns off below | Turns back on above |
|---|---|---|---|
| Open (default) | 3S | 9.3 V | 10.7–11.0 V |
| Bridged | 2S | 6.2 V | 6.9–7.2 V |

The turn-on level depends on Q1's body diode (0.3–0.6 V), because the cutoff current returns through it while the FETs are off.

- Open is the safe default: a 2S pack never reaches the 3S turn-on level, so the board stays off.
- A 3S pack resting below about 10.8 V (about 20% charge left) does not turn the board on. Charge it first.
- After a cutoff, with SW1 still on, the cutoff divider keeps drawing about 0.09 mA from the battery.
  Switch SW1 off (or unplug the battery) soon after a cutoff, or the pack keeps discharging.

## Mounting

The board lies flat on the tops of the hip servos, top side up, J5 toward the front and J4 toward the robot's left.
Two M2 holes (Ø2.2 mm) sit at the bottom corners, at (±25.5, −14.5) mm in the R2f frame (the frame of `index.circuit.tsx`,
1.5 mm above the center of this board). They line up with the free holes on top of the two rear hip servos
(trunk x −16.5 mm, y ±25.5 mm on the robot model in `hardware/print/DuckBuddy.3mf`). Use M2 screws through standoffs of about 6.5 mm.
A keepout keeps all copper 2 mm around each hole, so the screw head (Ø3.8 mm) and the standoff touch bare board only.
The R2f holes (and the R2f support part) are not used.

Fit, checked against the robot model:

- Every part clears the fixed body. J4/J6 with their plugs have 1.1 mm to the body roof; SW1 and J3 have more.
- When the head nods through its full range, the neck reaches down to the board at the front middle (C1, J5, F2, F3, C5).
  Nothing else is in its way. Check on the robot that the head's real range stays clear of C1 and the J5 plug.
- The wall behind the bottom edge is about 1.5 mm away, so SW1 cannot be reached with the board in the body (see [Check before ordering](#check-before-ordering)).
- J2 (the 2.54 mm SWD header) does not fit inside the body, and its pins sit where the J6 plug lies. Flash through J7 (Tag-Connect),
  or fit J2 only on a board used on the bench.

The hole positions come from the robot model and have **not been checked on a real robot**.

## Build and check

Needs [bun](https://bun.sh). In this folder:

```bash
bun install
bunx tsci check netlist
bunx tsci check placement
bunx tsci check schematic-placement
bunx tsci build --pcb-png --schematic-png --3d-png   # output in dist/index/
bunx tsci check shorts dist/index/circuit.json
bunx tsci check pcb-style dist/index/circuit.json
```

Current results: netlist passes; build 0 errors (0 DRC errors); no shorts; no PCB style issues; `check placement` finds no placement issues.
Its two warnings say that J4 and J6 do not open toward the side edges. That is on purpose: the plugs point to the bottom edge
and their wires leave over the side edges. `check schematic-placement` lists only drawing hints for the schematic (parts that
could be turned, decoupling capacitors drawn apart, two section titles close together); they do not change the circuit.

The smallest copper-to-copper gap is 0.15 mm (JLCPCB 2-layer minimum: 0.1 mm).

**Routing.** Every line is drawn by hand: `POWER` (battery and branch copper, 0.8–3 mm wide, all on the top side), `CUT_LINES` (the cutoff),
`IMU_LINES` and `HAND_LINES` (everything else), in `index.circuit.tsx`. The board has `routeRemaining={false}`, so the autorouter does not run.
GND has no lines: the GND pours on both sides reach every GND pad, joined by the vias in `GND_VIAS`. A few signal lines cross on the bottom layer.

After a change to the layout, place the top-side labels and icons again with `art/place_top.py` (see [`art/README.md`](art/README.md)).

Fabrication files (Gerbers, drill files, BOM, pick-and-place): `bunx tsci export index.circuit.tsx -f gerbers -o <file>.zip`,
or `bunx tsci dev` and the export menu in the web page. See [`ORDERING.md`](ORDERING.md) for how to split the zip for JLCPCB and the order settings.

## Parts

Every part has a JLCPCB/LCSC part number except J1 (battery pads), J3 (2-pin pads for an outside switch), the test points, J7, JP1/JP2 (bare pads)
and R12 (optional pull-up), which are not fitted. See the `LCSC` table in `index.circuit.tsx` and the files in `imports/`.

- Resistors (except R22), ceramic capacitors, LEDs, Q3/Q4, U6 and D4 are JLCPCB **basic** parts (no extended-part fee).
  Q3/Q4 are S8550 (JSCJ, C105432; pin order 1 B, 2 E, 3 C as in the data sheet; 25 V, above the 23 V TVS clamp).
  R22 (680 kΩ, C25822) stays extended: the nearest basic values (510 kΩ, 1 MΩ) would move the cutoff levels.
  The FETs, fuses, TVS, Zener, ESD diode, switch, shunt, current amplifier, LDO, MCU, IMU and bus driver have no basic part with the same rating, so they stay extended.
- The through-hole connectors J2, J4, J5 and J6 are marked `doNotPlace`: they are left out of the JLCPCB assembly and soldered by hand.
- JLCPCB needs **standard** assembly: U2 (LGA-14) is marked "Standard Only", so economic assembly cannot place it.
  Standard assembly adds edge rails (the board is under 70 mm) and X-ray inspection.
- JLCPCB price of 4 November 2026 for 5 assembled boards: €131.40
  (boards €4.64, setup €22.98, stencil €7.38, parts €37.46, extended-part feeders €48.42, X-ray €7.36, other €3.15).
  With DHL shipping to the Netherlands (€23.99), a €4.64 coupon and 21% VAT: about €182.
  The order value is below the €150 import limit. Details, settings and the review steps are in [`ORDERING.md`](ORDERING.md).

### Soldering the connectors

The top silkscreen shows the outline of each connector body. Put the body inside its outline, because the other way round it would sit on SMD parts:

- J4 and J6 (S3B-PH-K-S, side entry): the opening faces the bottom edge (the J1 side). The body reaches 1.35 mm above the pins
  and 6.25 mm below them; the plug then lies flat in the strip below the body, where there are no parts.
- J5 (XH): the deep side of the body (3.4 mm from the pins) faces the board center, so the body stays inside the board outline.

## IMU direction

U2 sits on the top side with rotation 0. Its axes on the board: sensor X = board −x (toward J4), sensor Y = board −y (toward J1), sensor Z = up.

The host setting assumes the board lies flat, top side up, with J4 toward the robot's left and J5 toward the front.
Then trunk x (forward) = −sensor Y, trunk y (left) = sensor X, trunk z (up) = sensor Z:

```toml
[bus]
imu_axes = "-y,x,z"   # PDB/IMU R3; R2f is "y,x,-z"
```

The board's direction in the robot has not been checked. Check it with the IMU test in [`tools/bringup`](../../../tools/bringup/README.md):
tilt the robot nose down, then to its left, and check that the pitch and the roll it shows change the right way. If not, change `imu_axes`.

## Use on Frankenduck (STS3215 servos)

The board also works on a bus of Feetech STS3215 servos, such as the one on Frankenduck (a Microduck build with STS3215 servos).
Its Waveshare Bus Servo Adapter (A) keeps the bus at 3.3 V with a 10 kΩ pull-up, the same level this board drives, and uses the same Feetech protocol.

1. Bridge **JP1** with solder: the board then talks at 1 Mbit/s, the STS3215 factory speed. It needs IMU firmware 1.1 or later.
   Register 6 then reads 0 (1 Mbit/s), as on the servos.
2. Wiring: the servo plugs (3-pin, 2.5 mm pitch, Molex 5264 type) do not fit PH2.0 or XH.
   Use short adapter cables. The pin order is the same on both sides: GND, V, DATA.
   Join the adapter's servo port to this board's bus (any of J4/J5/J6) so the host sees ID 200.
3. Power: battery into J1. Frankenduck runs 2S (8.4 V full), so **bridge JP2** (2S cutoff); each servo's voltage limit is set to 9.5 V.
   The 3 A hold current per branch is above what Frankenduck draws today: the adapter is rated 6 A in total.
4. Host: the Frankenduck backend (`frankenduck-sts`) does not read ID 200 yet. It needs to add ID 200 to its `SYNC_READ`
   and decode the block the way `duck-control/src/feetech.rs` does (`SflpDecoder`), with its own mount setting.

## Silkscreen

**Top side.** The main parts have a designator: the ICs, FETs, fuses, LEDs, the switch, the shunt, D1, JP2, J3, J7 and the test points.
The small resistors and capacitors have none: see the assembly drawing (`bunx tsci export -f assembly-svg`).
The connectors have printed labels with the text cut out: "J4 L LEG", "J6 R LEG", "J5 HEAD", "J2 SWD" (with the pin names
DIO, CLK, GND, 3V3 above J2), "ON" next to SW1, "2S" next to JP2, and the board name. There are also icons:

- the IMU axes next to U2: z out of the board, x toward J4, y toward J1 (the sensor's own axes, see [IMU direction](#imu-direction));
- a servo next to J4 and J6 (the leg buses);
- a battery between the J1 pads, with + on the BAT+ side;
- "A" next to the shunt RS1 (current reading) and "V" next to the R16/R17 divider (voltage reading).

All top-side text is drawn as graphics, because tscircuit's silkscreen font draws its lines at 9% of the text height
(0.07 mm for 0.8 mm text), too thin for JLCPCB to print (minimum 0.15 mm).

**Bottom side.** The microduck drawing, the Brazil and Pernambuco flags, the author's name and handle,
and on the left side "Designed in Vila Mauricéia, IPSEP" with a woodcut dog. "1M" marks JP1.

See [`art/README.md`](art/README.md) for how the art is made.

## Check before ordering

1. Mounting hole positions and the fit (see [Mounting](#mounting)): check them against the printed body and the real servos.
2. SW1's lever sits at the bottom edge, about 1.5 mm from the body wall, so it cannot be reached inside the body.
   For use in the robot, wire an outside switch to J3 (it is in parallel with SW1; leave SW1 off).
3. PH2.0 connectors are rated 2 A per pin, while the fuses hold 3 A and trip at 6 A. Watch for heating under long high-current use.
4. The IMU direction: set `imu_axes = "-y,x,z"` and check it on the robot (see [IMU direction](#imu-direction)).
5. JP2 matches the battery: open for 3S, bridged for 2S. With JP2 open and a 2S pack, the board does not turn on.
6. The "ON" label sits at the end of SW1 that is assumed to switch on. Check it against the switch's data sheet or on the first board.
7. U6 (CJ431, LCSC C3113): the board uses the pin order of the JCET data sheet (1 REF, 2 K, 3 A), not the EasyEDA library part,
   which has 1 and 2 swapped. TL431-type parts in SOT-23 come in different pin orders from different makers, so check that C3113
   is still the JCET part before ordering. With the wrong order the cutoff does not work.
8. In the JLCPCB assembly preview, check the rotation and polarity of U2 (pin 1), C1 (+), D1, D2, D4, the LEDs and the SOT-23 parts
   (Q3, Q4, U3, U6) before confirming the order. The pin-1 side of every part is listed in [`ORDERING.md`](ORDERING.md#orientation-and-polarity).
9. Order with "Confirm Parts Placement: Yes" and "Do not confirm automatically" (see [`ORDERING.md`](ORDERING.md#assembly-settings)).
