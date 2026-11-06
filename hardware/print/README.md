# Printed parts

`DuckBuddy.3mf` is the Bambu Studio project of all the robot's printed parts, in 6 plates: shell parts, head, wheels, TPU soft parts, structural parts (including the head top shell with the added cooling holes and microphone holes), and a BAM arm. The parts come from the original Microduck printed parts, with these changes:

- **Head face plate (face_part)**: the mounts are changed to hold the **8×8 ToF module** (VL53L5CX type) and the **IMX219 camera module**;
- **Head shell (top_head_shell)**: **cooling holes** and **two microphone holes** added (one left, one right, matching J2/J9 on the HAT, used to tell which direction a sound comes from);
- **BAM arm** (plate 6, new): a 120×20×3 mm flat plate. Two holes at one end mount it on the servo output horn. It swings on the servo during servo parameter identification ([BAM](https://github.com/Rhoban/bam)). You do not need to print it if you only build the robot;
- All other parts (legs, hips, feet, body shell, battery tray and so on) are the original ones. The HL-2915 servos fit directly (same outer shape, hole positions and output shaft as the XL330, M2×6 self-tapping screws).

**Print settings** (already set in the project):

| Item | Value |
|---|---|
| Printer | Bambu Lab P1S, 0.4 mm nozzle (for other printers, import the parts yourself) |
| Material | PETG; TPU for the soft parts (soles, soft beak and so on) |
| Layer height | 0.2 mm |
| Walls / infill | 2 walls, 30% infill |
| Supports | on |

Other slicers (OrcaSlicer, PrusaSlicer and so on) can also open the 3MF directly.

License: the parts come from Microduck (Apache-2.0), and the changes are also released under Apache-2.0.

Change log:
- 2026-10-25: the project was renamed to `DuckBuddy.3mf` and tidied into 6 plates (it was `microduck2.3mf`, with 9 plates).
- 2026-10-30: the unmodified old head top shell was removed, the reworked head top shell moved to plate 5 (structural parts); plate 6 is now the BAM arm.

---

`DuckBuddy.3mf` is a Bambu Studio project of all the printed parts, in 6 plates (shell parts, head, wheels,
TPU soft parts, structure with the head's top shell, and a BAM arm): Microduck's parts with the
head's face plate reworked to mount an 8×8 ToF module and an IMX219 camera, and the head shell given
cooling vents and two microphone holes (left and right, for the sound direction). PETG, TPU for the soft
parts; 0.2 mm layers, 2 walls, 30% infill, supports on; printed on a Bambu Lab P1S. Apache-2.0, as Microduck.
Plate 6 is a 120×20×3 mm arm for identifying the servos with BAM (not needed for the robot itself).
2026-10-25: renamed from `microduck2.3mf` (9 plates) and tidied into 6 plates.
2026-10-30: the unmodified old head top shell removed, the reworked one moved to plate 5; plate 6 is now the BAM arm.

**Open head shell** (optional, not in `DuckBuddy.3mf`): a development head that replaces the head top
shell and holds the [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT) beside the Orange Pi and the speaker, with the electronics exposed. Model,
print files and assembly steps: [`hardware/cad/open-head`](../cad/open-head/README.md). It needs the three
holes of the bottom head shell drilled to 3.2 mm for M3 screws.

**LiPo plate** (optional, not in `DuckBuddy.3mf`): replaces the battery plate (`power_support`) for a
3S 2200 mAh LiPo (75 × 33 × 26 mm) held by one 27 mm velcro strap, with the BNO055 breakout (Adafruit
4646) on its front face, just under the hip servos. It drops the old plate's NP-F970 holder and the
front mounts of the PDB/IMU board. Model, print files and assembly steps:
[`hardware/cad/lipo-plate`](../cad/lipo-plate/README.md).
