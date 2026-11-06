# Ordering PDB/IMU R3 from JLCPCB

This file records how the board is ordered: the files, every order setting and why it was chosen, the price,
and the facts needed to answer questions from the JLCPCB engineers (part orientation, polarity, parts left out on purpose).
Keep it up to date with each quote and order.

## Status

| Date | Step | State |
|---|---|---|
| 2026-11-04 | JLCPCB quote | Files uploaded, BOM and placement processed. Saved in the JLCPCB account as the project **pdb-imu-r3-gerbers** (see the cart row below). |
| 2026-11-04 | Q3/Q4 changed | After the quote, Q3/Q4 changed from MMBT3906 (C7420354, extended) to S8550 (C105432, basic) to save one extended-part fee. Only the BOM changed: `pdb-imu-r3-bom-v2.csv`. The Gerbers and the CPL are the same (checked file by file, only the date lines differ). The change saved nothing in the standard-PCBA quote (the feeder fee stayed €48.42), but it costs nothing either. |
| 2026-11-04 | JLCPCB cart | In the cart as **pdb-imu-r3-gerbers_Y8**: 5 boards, the v2 BOM (S8550), standard PCBA, Confirm Parts Placement Yes. Merchandise €131.40, DHL €23.99, coupon −€4.64, subtotal **€150.75** before VAT, est. shipping date 2026-11-09. Removed from the cart on 2026-11-04 (old outline). (An earlier try with 15 boards was €216.54 before VAT, over the €150 import limit.) |
| 2026-11-04 | PCBWay quote | Not wanted (JLCPCB only). |
| 2026-11-04 | Flat-mount layout | The board now lies flat on the hip servos: 55 × 31 mm, both top (J5-side) corners cut away 6 × 3 mm, two M2 holes at the bottom corners, J4/J6 side-entry PH2.0 with the plugs toward the bottom edge, and many parts moved. Same circuit and the same BOM (identical to `pdb-imu-r3-bom-v2.csv`). New files in `fab/2026-11-04-jlcpcb-flat-mount/`. |
| 2026-11-04 | JLCPCB cart (new files) | Uploaded as a new quote and saved in the cart as **pdb-imu-r3-gerbers_Y9**: 5 boards, standard PCBA, Confirm Parts Placement Yes with "Do not confirm automatically", all 64 parts matched and selected (U2 included). Merchandise €131.40, DHL €23.99, coupon −€4.64, subtotal **€150.75** before VAT, est. shipping date 2026-11-09. **Not paid.** |
| 2026-11-04 | JLCPCB cart | Removed the old `_Y8` item. `_Y9` is now the only item in the cart. |

**Order `pdb-imu-r3-gerbers_Y9`.** It is the only item in the cart; the old `pdb-imu-r3-gerbers_Y8` (55 × 34 mm outline with
the R2f holes) was removed. After any further change to the board, make new files, upload them again
and repeat the placement review below.

## Files

The files of the flat-mount layout (cart item `_Y9`, the ones to order) are in [`fab/2026-11-04-jlcpcb-flat-mount/`](fab/2026-11-04-jlcpcb-flat-mount/):

| File | Uploaded as | SHA-256 |
|---|---|---|
| `pdb-imu-r3-gerbers.zip` | Gerber file (Gerbers and drill files only) | `f6833c23d4514949c3f374f2d18b06ae1f426e92102cd23f1594a165405929c7` |
| `pdb-imu-r3-bom.csv` | BOM file (the same bytes as the v2 BOM below) | `8d3bbc6097dd2b1a9c226511b2b74c5a22d07eb0cbc802dd3c68d6cf3ad25811` |
| `pdb-imu-r3-cpl.csv` | CPL (pick-and-place) file | `911f6682c29b9b0db4d7fe389ad2c9c1d623a2c6208b6542ddcb7f243ea6e159` |

Compared with the first quote, the CPL rotation changed for D1 (180 → 90), R1 (90 → 270), R11 (0 → 180), R3 (0 → 270)
and R4 (0 → 90); the other changes are positions only.

The files of the first quote (old outline, cart item `_Y8`, removed from the cart) are in [`fab/2026-11-04-jlcpcb-quote/`](fab/2026-11-04-jlcpcb-quote/):

| File | Uploaded as | SHA-256 |
|---|---|---|
| `pdb-imu-r3-gerbers.zip` | Gerber file (Gerbers and drill files only) | `77b0a7429df985e9a89d1ca8bb5ccf09956e4bdb51d819a0afa4a9d0b43d84d2` |
| `pdb-imu-r3-bom.csv` | BOM file | `c9fb6d5c7ec8f7b5083416a94d1adb8656cd9d604d6086d745c98612b593c5cb` |
| `pdb-imu-r3-cpl.csv` | CPL (pick-and-place) file | `578fa296c647104d256ece8c2d3315907617139d7efc8239c6010b238340bc19` |
| `pdb-imu-r3-bom-v2.csv` | BOM with Q3/Q4 = S8550 C105432 (use this one from now on) | `8d3bbc6097dd2b1a9c226511b2b74c5a22d07eb0cbc802dd3c68d6cf3ad25811` |

How they are made (from `hardware/pcb/pdb-imu`):

```sh
bunx tsci export index.circuit.tsx -f gerbers -o /tmp/pdb/export.zip
cd /tmp/pdb && mkdir x && unzip -q export.zip -d x && cd x     # any empty folder will do
zip ../pdb-imu-r3-gerbers.zip *.gbr *.drl     # the Gerber upload must not contain the CSV files
cp bom.csv ../pdb-imu-r3-bom.csv && cp pick_and_place.csv ../pdb-imu-r3-cpl.csv
```

The export prints `cannot verify jlcpcb pick-and-place rotation (incompatible_pin1_locations)` for Q1, Q2, U1 and U4.
This is a limit of the export tool, not an error: see [Rotation of Q1, Q2, U1 and U4](#rotation-of-q1-q2-u1-and-u4).

## PCB settings

JLCPCB detected a 2-layer board of 31 × 55 mm (the first quote: 34 × 55 mm).

| Setting | Value | Why |
|---|---|---|
| Base material, layers | FR-4, 2 | |
| Quantity | 5 | |
| Different designs, delivery | 1, single PCB | |
| Thickness | 1.6 mm | default; the design assumes it |
| Colour, silkscreen | green, white | cheapest; the silkscreen art was checked on green |
| Material | FR4 TG135 | default |
| Surface finish | **LeadFree HASL** | The new default is OSP. Economic assembly is not offered with OSP. Lead-free also suits the EU. |
| Copper | 1 oz | The VBAT copper is 3 mm wide for 1 oz (see README). |
| Via covering | tented | |
| Min via hole | 0.3 mm (0.4/0.45 mm) | default, no extra cost |
| Outline tolerance | ±0.2 mm | |
| Confirm production file | No | Can be set to Yes (free in this quote) to also approve the Gerber review. |
| All other options | defaults, not changed | |

## Assembly settings

| Setting | Value | Why |
|---|---|---|
| PCBA type | **Standard** | U2 (LSM6DSV16XTR, LGA-14) is marked "Standard Only". With economic assembly the site leaves U2 unselected, so the boards would arrive without the IMU. |
| Assembly side | top | All SMD parts are on the top side. |
| PCBA quantity | 5 | |
| Edge rails / fiducials | added by JLCPCB | Standard assembly needs sides longer than 70 mm, so JLCPCB adds rails to the 55 × 31 mm board and removes them. |
| **Confirm Parts Placement** | **Yes**, with **"Do not confirm automatically"** ticked | A JLCPCB engineer checks every part's position, rotation and polarity on our board and sends pictures for approval. Without the tick the order goes into production by itself 72 hours after their message. With it, nothing is built until we approve. |
| Stencil storage, fixture storage | No | |
| PCB build time | 24 hours ("PCBA Only", €0) | The default once assembly is on; assembly is 3–4 days. |
| Parts selection | by customer (self-service) | We give the LCSC number of every part in the BOM. |
| Product description (customs) | Research\Education\DIY\Entertainment / DIY Hobby Circuit Board, HS code 902300 | Required before saving to the cart. |

**After switching from economic to standard, U2 was unselected again** (quantity 0, checkbox greyed) in the first quote.
It had to be picked again with the search icon in its row (C5267406, 15,085 in stock on 2026-11-04).
In the second upload (`_Y9`, standard chosen before the BOM step) all 64 parts were selected at once.
Check that all 64 parts are selected before going on.

## Price (JLCPCB, 2026-11-04, 5 boards)

The new outline did not change the price: `_Y9` is the same as `_Y8`.

In the cart with the v2 BOM: **€131.40** (components €37.46, the rest as below), DHL Express **€23.99**, coupon −€4.64:
subtotal **€150.75**, plus 21% VAT at checkout ≈ **€182**. The order value after the coupon (€126.76) is below the €150 import limit.

First quote (v1 BOM, before the cart):

| Item | € |
|---|---|
| PCB (special offer 3.57 + lead-free HASL 1.07) | 4.64 |
| Setup fee | 22.98 |
| Stencil | 7.38 |
| Components (35 part types, 64 places per board) | 37.38 |
| Feeders loading fee (extended parts) | 48.42 |
| SMT assembly | 2.30 |
| Confirm parts placement | 0.40 |
| X-ray inspection | 7.36 |
| Packaging | 0.45 |
| **Total before shipping and VAT** | **131.32** |

- Build time: PCB 2 days, assembly 3–4 days (2–3 days costs €44.30 more).
- Weight 527 g; the cart showed DHL Express at €23.99.
- 21% NL VAT is charged at checkout. The order value is below the €150 import limit, so the VAT is paid at checkout and there should be no customs fees on delivery.

Each extended part type costs about €3 in feeder fees. After this quote:

- Q3/Q4 changed to the basic S8550 (C105432). In the standard-PCBA quote this did not lower the feeder fee (€48.42 before and after). Checked: JSCJ data sheet pin order 1 B, 2 E, 3 C (the same as MMBT3906);
  VCEO 25 V is above the most Q3 sees (the battery, or the 23.2 V TVS clamp in a surge); Q4 sees at most the 10 V gate clamp;
  hFE 120–400. The board keeps its SOT-23 pads; JLCPCB's S8550 footprint has the same pin positions and pin 1 side.
- R22 (680 kΩ, C25822) stays extended. There is no basic 680 kΩ; the nearest basic values change the cutoff:
  510 kΩ gives 3S off 9.0 V / on 10.8–11.1 V, 1 MΩ gives off 9.5 V / on 10.6–10.9 V (now 9.3 / 10.7–11.0 V).

## Parts in the assembly

All 64 places matched the BOM's LCSC numbers. Extended (E) and basic (B) as shown by JLCPCB:

| Designators | Part | LCSC | Type |
|---|---|---|---|
| C1 | RVT100UF25V67RV0011, 100 µF 25 V electrolytic | C2836443 | E |
| C2, C6 | 1 µF 50 V 0603 | C15849 | B |
| C3, C4, C5 | 10 µF 25 V 0805 | C15850 | B |
| C7, C9 | 4.7 µF 16 V 0603 | C19666 | B |
| C8, C10–C16 | 100 nF 16 V 0402 | C1525 | B |
| C17 | 22 µF 25 V 0805 | C45783 | B |
| D1 | SMBJ14A TVS (SMB) | C152106 | E |
| D2 | BZT52C10 Zener (SOD-123) | C173431 | E |
| D3 | PESD5V0S1BA ESD (SOD-323) | C2827694 | E |
| D4 | 1N4148WS (SOD-323) | C2128 | B |
| F1, F2, F3 | 1210L300/24WR PPTC | C22379947 | E |
| F4 | 0438001.WR 1 A fuse 0603 | C99544 | E |
| LED1, LED2, LED3 | KT-0805G green | C2297 | B |
| LED4 | KT-0603R red | C2286 | B |
| Q1, Q2 | AON7524 N-FET (DFN-8 3×3) | C431195 | E |
| Q3, Q4 | S8550 PNP (SOT-23) — in the first quote MMBT3906 C7420354 (E) | C105432 | B |
| R1, R8, R20, R24, R25 | 10 kΩ 0402 | C25744 | B |
| R2, R11, R16 | 100 kΩ 0402 | C25741 | B |
| R3, R4, R5, R13 | 33 Ω 0402 | C25105 | B |
| R6, R7, R9 | 3.3 kΩ 0402 | C25890 | B |
| R10, R15 | 1 kΩ 0402 | C11702 | B |
| R17 | 22 kΩ 0402 | C25768 | B |
| R18 | 33 kΩ 0402 | C25779 | B |
| R19 | 39 kΩ 0603 | C23153 | B |
| R21 | 27 kΩ 0603 | C22967 | B |
| R22 | 680 kΩ 0603 | C25822 | E |
| R23 | 4.7 kΩ 0402 | C25900 | B |
| RS1 | RLM12FTCMR002, 2 mΩ shunt 1206 | C710257 | E |
| SW1 | MS-1290N slide switch | C19188866 | E |
| U1 | STM32G031F8P6 (TSSOP-20) | C529334 | E |
| U2 | LSM6DSV16XTR IMU (LGA-14) | C5267406 | E |
| U3 | TPS70933DBVR LDO (SOT-23-5) | C89347 | E |
| U4 | 74LVC1G126GW (SOT-353) | C52140429 | E |
| U5 | INA180A2IDBVR (SOT-23-5) | C192764 | E |
| U6 | CJ431 (SOT-23) | C3113 | B |

### Left out on purpose

If an engineer asks about these, they are correct as they are:

| Designator | What | Why it has no part |
|---|---|---|
| J1 | battery pads | wires are soldered by hand |
| J2 | SWD header (through-hole) | `doNotPlace`, soldered by hand |
| J3 | 2 pads for an outside switch | optional, bare pads |
| J4, J6 | PH2.0 3-pin (through-hole) | `doNotPlace`, soldered by hand |
| J5 | XH2.54 3-pin (through-hole) | `doNotPlace`, soldered by hand |
| J7 | bare pads | |
| JP1 (bottom, "1M"), JP2 ("2S") | solder jumpers | **no solder paste on purpose**, so reflow does not bridge them. JP1 open = 500 kbit/s, JP2 open = 3S. |
| R12 | 10 kΩ pull-up | not fitted on purpose (optional) |
| TP1–TP4 | 1.2 mm test pads | keep their paste on purpose; a small solder dome is fine |

## Orientation and polarity

Board directions as seen in the JLCPCB viewer (top side): **up = the J5 HEAD edge, down = the battery (J1) edge,
left = J4 L LEG, right = J6 R LEG.** Pin 1 of each part with an orientation, from the design:

| Part | Pin 1 | Pin 1 side | Note |
|---|---|---|---|
| U1 STM32G031 | PB7 | bottom left | pins in a row along the bottom and top |
| U2 LSM6DSV16X | SDO | bottom right | JLCPCB viewer: pink pin-1 dot and the model's dot both bottom right (matches) |
| U3 TPS70933 | IN | top left | silkscreen triangle at top left (matches the viewer's dot) |
| U4 74LVC1G126 | OE | bottom left | 3 pins at the bottom, 2 at the top |
| U5 INA180 | OUT | bottom left | |
| U6 CJ431 | 1 = REF | bottom right | see the pin-order note below |
| Q1 AON7524 | S1 | top right | |
| Q2 AON7524 | S1 | bottom left | |
| Q3 S8550 | B | top left | |
| Q4 S8550 | B | bottom right | |
| C1 100 µF | + (pin 1) | bottom | the silkscreen "+" is below C1; the dark stripe on the can (−) must face up |
| D1 SMBJ14A | cathode | bottom | band at the bottom (toward the J1 edge); D1 stands upright left of U5 |
| D2 BZT52C10 | cathode | bottom | band at the bottom |
| D3 PESD5V0S1BA | — | — | bidirectional, either way works |
| D4 1N4148WS | cathode | top | band at the top |
| LED1, LED2, LED3 | anode | left | cathode to the right |
| LED4 | anode | left | cathode to the right |

### Rotation of Q1, Q2, U1 and U4

The tscircuit export could not check these four itself. They were checked by hand on 2026-11-04: JLCPCB's own footprints
(EasyEDA, `TSSOP-20_L6.5-W4.4-P0.65-LS6.4-BL` for C529334, `SOT-353-5_L2.0-W1.6-P0.65-LS2.1-BL` for C52140429 and
`DFN-8_L3.0-W3.0-P0.65-BL` for C431195) were downloaded and every pad compared with the board, in each part's own frame:

- U1: all 20 pads at the same positions, pin 1 bottom left. CPL rotation 0 is correct.
- U4: all 5 pads at the same positions, pin 1 bottom left. CPL rotation 0 is correct.
- Q1, Q2: all 9 pads (8 pins and the drain pad) at the same positions, pin 1 bottom left in the part frame.
  Q2 has CPL rotation 0; Q1 is turned, with CPL rotation 180 (pin 1 then sits top right on the board). Both are correct.

In the JLCPCB viewer the pin-1 dots of U1 and U4 are at bottom left.

### U3 EN pin

U3's EN pin (pin 3) is not connected on purpose. The TPS709 data sheet: EN is pulled high by an internal 300 nA source,
so it "can be left floating to enable the device", and EN must not be connected to VIN. Pin 4 is NC.

### U6 pin order

The board uses the JCET CJ431 data sheet order for SOT-23: **1 REF, 2 K (cathode), 3 A (anode)**.
The EasyEDA library part for C3113 has pins 1 and 2 swapped. If the engineer flags a footprint mismatch on U6,
the answer is: place the part by its body and pin 1 as on our footprint; do not follow the EasyEDA pin names.
With the wrong order the low-battery cutoff does not work. Check that C3113 is still the JCET part before ordering.

### Still to check in the viewer before confirming

The viewer was looked at for U1–U4 and U6 in the first quote, and for D1, D2, Q3, Q4 and U5 in `_Y9`
(D1 and D2: the cathode band and the viewer's "−" mark at the bottom; Q3 dot top left, Q4 dot bottom right, U5 dot bottom left; all match).
Before ordering, zoom in on the remaining rows, mainly C1, D4, the LEDs, Q1 and Q2, and compare the pink pin-1 / polarity marks with the table.

## Answering the JLCPCB engineers

When an email about this order arrives:

1. Open this file and the pictures in the email (or the order page).
2. For each question, find the part in the tables above: orientation and polarity, left out on purpose, the U3 EN note or the U6 note.
3. Answer with the designator, the pin-1 or polarity side in the board directions above, and confirm or correct their picture.
   Example: "C1: the + pad is the lower pad (toward the battery pads J1); the dark stripe of the can faces J5. Your picture is correct."
4. For anything not covered here (DFM, silkscreen, drill or pad questions), check the design in `index.circuit.tsx` and the
   README before answering, then add the question and answer below.

### Questions and answers so far

None yet.
