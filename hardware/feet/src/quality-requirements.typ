#import "rfq-style.typ": doc, m, f1
#show: doc.with(title: "Quality requirements")

= Master geometry
The STEP files are the master geometry. The drawing `duckbuddy-feet-drawing.pdf` adds the
tolerances and the critical dimensions. Left and right parts are mirror images; each side has its own file.
The parts are in a "part frame": the flat ground face of the sole is Z = 0 (datum A).

= Tolerances: soles
#table(columns: (1fr, 1.3fr, 1fr),
  [Feature], [Nominal (mm)], [Tolerance (mm)],
  [General, all dimensions], [as modelled], [± 0.3 (your standard vacuum-casting accuracy)],
  [Cavity length at Z = 6 (fit to the foot)], [#f1(m.cav_L)], [± 0.3],
  [Cavity width at Z = 6 (fit to the foot)], [#f1(m.cav_W)], [± 0.3],
  [Wall thickness], [#f1(m.wall_min)–#f1(m.wall_max) (as modelled; #f1(m.wall_min)–1.5 in a band at Z = #m.wall_band_z.at(0)–#m.wall_band_z.at(1) all round)], [\+0.3 / −0.2, never under 1.0],
  [Floor thickness], [#f1(m.floor)], [± 0.3],
)
The sole is a stretch fit over the rigid foot. *The sole STEP files are the finished part*: they are already
0.8 % smaller than the foot, so the cavity is about 0.4 mm shorter and 0.3 mm narrower than the foot.
Please add only your usual casting-shrinkage compensation, no other scaling.

= Tolerances: feet (optional)
General ± 0.3 mm, or the printing process standard if tighter. No changes to the holes, slots, lugs or ribs.

= Surface and cosmetic
- Ground face (bottom, datum A): matte as cast, no gate, vent, parting line, flash or sink.
- Gates and vents: on the rim top face, which sits under the foot edge. Trim flash flush (≤ 0.2 mm).
- No bubbles or voids in the walls or the floor. Pinholes ≤ 0.3 mm are acceptable inside the cavity only.
- No tears, no thin spots at the rim, uniform bright orange colour.
- No release-agent film on any surface (wipe clean before packing).

= Inspection report
Please measure and report, on the sample size of your standard inspection (ISO 2859-1):
+ The three overall dimensions (your standard).
+ Cavity length and width at Z = 6, with your usual method; a soft cup does not need to be measured better than ± 0.3 mm.
+ Wall thickness at the middle of each of the four sides at Z = 8, at the toe and heel at Z = 4.5, and floor thickness at the centre.
+ Hardness Shore A of each casting batch (mix), measured on a test button at least 6 mm thick cast from the same mix, after post-cure.
+ If you also make the feet: push each sole onto its foot by hand. The foot must seat on the sole floor and the rim top must touch the underside of the foot edge with no gap over 0.3 mm.

= First article
If the order is for more than one set, please send photos of the first good casting (ground face, rim, cavity)
and its hardness value before casting the rest.

= Marking and packing
- Mark the side on the bag, not on the part: "SOLE LEFT", "SOLE RIGHT" (and "FOOT LEFT", "FOOT RIGHT").
- Pack the soles flat, not folded or compressed.

= Changes
Any change of material, hardness, colour or geometry needs written agreement before production.
