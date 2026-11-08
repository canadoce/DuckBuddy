# Feet and soles

The robot stands on two rigid feet, each covered by a soft sole. This folder holds the manufacturing
files for these four parts and the plan to have the soles cast in a soft polyurethane (Shore 60A)
instead of printed in TPU 95A.

| Part | Part no. | Role | Size (mm) | Volume |
|---|---|---|---|---|
| `sole_left`, `sole_right` | DB-FOOT-SOLE-L/R | Soft cup over the foot, the only part that touches the floor | 53.6 × 40.9 × 13.3 (finished, 0.8 % under the model) | 6.10 cm³ |
| `foot_left`, `foot_right` | DB-FOOT-L/R | Rigid ribbed foot, screwed to the ankle part | 54.0 × 39.9 × 16.4 | 12.18 cm³ |

The shapes are the feet and soles of `hardware/print/DuckBuddy.3mf`, which are the upstream Microduck /
OpenMicroDuck parts unchanged. [`src/feet_parts.py`](src/feet_parts.py) takes them out of the 3MF, puts each
sole back on its foot, makes the soles 0.8 % smaller (see "Fit" below), and writes [`STL/`](STL/) and [`STEP/`](STEP/). It also writes [`parts.json`](parts.json)
(sizes, volumes, SHA-256 of every file, and the checks below).

## Part frame

In the robot's zero pose the ground face of the sole is tilted 4.9° about the foot's long axis. The exported
files remove that tilt: the flat middle of the ground face is Z = 0 (datum A), X runs along the foot,
Z points up, and the origin is under the centre of the sole. The two parts of one side keep their
assembled position, so a sole and its foot open together in the same place.

Checks done by the script:

- The ground face is flat in its middle (39 × 28 mm) to within 0.1 mm (mesh faceting).
- The right parts are the left parts mirrored. They match the right meshes of the 3MF within 0.024 mm.
- As modelled, the sole cavity and the foot are line to line: they overlap by only 0.75 mm³ in total.
- Every STEP file is a closed, valid solid with the same volume as its mesh.

The STEP files are faceted (one flat face per mesh triangle, merged where coplanar), because the source is a
mesh. That is fine for casting and printing: the bureau prints the master from it.

## Geometry that matters

- The sole is a cup: floor 2.0 mm, walls 1.8–2.1 mm above Z = 7, and 1.2–1.5 mm in a band at Z = 3–7 all round, where the
  cavity's bottom chamfer meets the rounded outside (thinnest, 1.2 mm, at the toe). The rim is 13.3 mm high along one long side and 10.0 mm along
  the other: the rim top is tilted 4.9° to the ground face. It is level in the robot frame, under the foot's edge;
  only the ground face is tilted.
- The ground face is flat in the middle (about 39 × 28 mm) and blends up into the walls toward the toe, heel and sides.
- The foot ribs stand on the sole floor, and the foot's edge rests on the full width of the sole rim all round (the rim
  top is 1.5–2.1 mm wide). Below the rim on the −Y side the sole's outer wall bulges about 1 mm past the foot. So the
  rim is held down (not wrapped), and the floor carries the load through the ribs.
- The foot joins the ankle part with **one M2 self-tapping screw**: it goes down through the ankle part
  (Ø2.3 mm hole, Ø4.0 mm head recess) into the foot's Ø1.6 mm, 5 mm deep pilot hole (small Ø3.0 chamfer at the top). Two lugs on the foot
  hold the ankle part in place. The servo horn drives the ankle part; the foot has no servo-horn holes.

## Fit of the sole on the foot

As modelled, the sole cavity is exactly the size of the foot (line to line), so a cast sole would only grip the
foot through its casting shrinkage (about 0.25 %, 0.1 mm), and the bureau's ±0.3 mm accuracy could just as well
make it loose. So the sole files are the modelled sole scaled to **99.2 %** about the centre of the ground face
(`SOLE_SCALE` in `feet_parts.py`). The cavity is then about 0.4 mm shorter and 0.3 mm narrower than the foot. At the
edge of ±0.3 mm the cavity width is the same as the foot (never looser than line to line), and at most it stretches
the 60A sole about 1.6 % across and 1.4 % along it. The
outside of the sole and the rim height change by 0.1–0.4 mm, which does not matter. The RFQ says the STEP is the
finished part and asks the bureau to add only its usual shrinkage compensation.

## Which way to make the soles

Target: Shore 55–60A, like Polytek PT Flex 60 (Shore A 55–60, 2.1–2.4 MPa tensile, about 230 % elongation,
about 12 kN/m tear). The stock sole is FDM TPU 95A, which is much harder.

| Route | Real hardness | Fit for this part | Cost and effort | Verdict |
|---|---|---|---|---|
| **Vacuum casting** (Yellowhammer) | Any 30–95A. PU elastomers such as SikaBiresin PX840, Hei-Cast 8400 or ALCHEMIX VC 3300 set to 60A | Good. 1.2–2.1 mm walls are over their 1 mm minimum; accuracy ±0.3 mm. Smooth, solid, no layer lines | One SLA master and one silicone mould per side, then a low price per casting. A mould gives a few dozen castings (Yellowhammer: up to 30–50) | **Chosen.** Right hardness, best part quality, no work for us |
| FDM soft TPU (Filaflex 60A) | 60A nominal (63A measured, per a retailer's data table) | Works, but a 60A filament is hard to feed and prints slowly; layer lines on the ground face | Cheapest; needs a direct-drive printer and tuning | Good cheap test while the quote is open |
| SLA elastic resin (Formlabs Flexible 50A) | 55A | Right hardness, but low tear strength and the resin ages | Needs a Form printer or a bureau | Second choice |
| Carbon EPU 40 | about 68A | Very good, tough | Expensive, only at Carbon bureaus | Not worth it for 2–10 pairs |
| MJF / SLS TPU | 86–90A | Too hard | — | No |
| Own silicone mould, cast PT Flex 60 ourselves | 55–60A (the reference) | Works, but a 2 mm wall needs a two-part mould with a core and degassing, or it gets bubbles | Low material cost, a lot of work and learning | Only if many pairs are needed later |

Notes:

- PT Flex 60 is an open-pour rubber, not a vacuum-casting resin. The RFQ names it as the property target and asks the
  bureau for its own 60A vacuum-casting PU, with datasheet.
- Yellowhammer's terms allow "limited deviations" in Shore hardness unless agreed in writing. The material requirements
  document is that written requirement (60A ± 5).

## Which way to make the feet

The feet do not need to be cast. Options, best first:

1. **SLS PA12 dyed bright orange** at the same bureau (optional line in the RFQ; standard MJF PA12 is grey, so it
   is asked for only if they can make it orange). Strong, accurate, takes M2 self-tapping screws well.
2. Keep printing them in PETG (as now, plate "TPU soft parts" / structural parts of `DuckBuddy.3mf`).
3. Rigid vacuum-cast PU (Shore D 67–86 at Yellowhammer). Only worth it with the same mould run and more than about 10 pairs.

## Assembly

1. Wipe the inside of the sole with isopropyl alcohol, to remove any release agent. Let it dry.
2. Push the foot into the sole by hand, heel first, then press the toe in. The ribs must sit on the sole floor and the
   rim must touch the underside of the foot's edge all round.
3. **First test without glue.** The sole is 0.8 % smaller than the foot, so it stretches on and grips; the foot's edge
   on the rim also holds it down. Walk the robot. If the sole stays on, leave it unglued: it can be replaced in seconds.
4. If the sole slips or creeps: take it off, sand the foot's outer walls and rib tips with 320 grit, clean both parts
   with isopropyl alcohol and glue with a cyanoacrylate for plastics and rubber (Loctite 401 or 406). Use a few small
   drops on the rib tips and along the rim, not a full film, so the sole stays soft. Try it first on a spare sole: no
   test data was found for cast PU on PETG or PA12. The closest published test, TPU on PA12
   ([Sci Rep 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12824215/)), got the strongest bond with Loctite 401 plus
   the Loctite SF 770 primer. SF 770 is made for polyolefins (PE, PP), which PETG and PA12 are not, so use it only if
   the bond without it is weak.
5. Put the foot on the ankle part and drive the M2 self-tapping screw (M2 × 6, as in the upstream BOM) through the ankle
   into the foot's pilot hole. In PA12 or PETG the screw cuts its own thread; do not over-tighten (stop when the head seats).
   No inserts are needed. Heat-set inserts would need a bigger hole (about Ø3.2) and a model change.

## Ordering

See [RFQ-YELLOWHAMMER.md](RFQ-YELLOWHAMMER.md) for the quote request: the files to upload, the text of each form field,
and the status.

## Rebuild the files

```bash
uv run hardware/feet/src/feet_parts.py
uv run hardware/feet/src/drawing.py
hardware/feet/src/make_rfq.sh
```
