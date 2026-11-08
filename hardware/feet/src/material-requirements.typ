#import "rfq-style.typ": doc, m, f1
#show: doc.with(title: "Material requirements")

= Use of the parts
The soles are the ground contact of a small two-legged walking robot. Each sole is a thin cup
(#f1(m.L) × #f1(m.W) × #f1(m.H) mm, walls #f1(m.wall_min)–#f1(m.wall_max) mm, floor #f1(m.floor) mm)
that is stretched over a rigid printed foot. The sole must grip the floor, damp the impact of each
step and stay on the foot.

- Floors: wood, laminate, tile and short carpet, indoors, dry.
- Temperature 10–40 °C. No oil, fuel or solvents.
- Load: repeated impacts and short slides at every step, low load (small robot).

= Soles: cast polyurethane elastomer
#table(columns: (auto, 1fr),
  [Property], [Requirement],
  [Process], [Vacuum casting in a silicone mould (or the process Yellowhammer recommends for this hardness and wall thickness).],
  [Hardness], [*Shore 60A ± 5* (target 55–60A, never above 65A). Measured to ISO 48-4 / ASTM D2240 type A at 23 °C after full post-cure.],
  [Tensile strength], [≥ 2 MPa],
  [Elongation at break], [≥ 200 %],
  [Tear strength], [≥ 12 kN/m (ISO 34-1 / ASTM D624 die C)],
  [Colour], [*Bright orange*, for example RAL 2004 (pure orange). Opaque, coloured through (pigmented, not painted). The same shade as the feet if you also make them.],
  [Surface], [Matte, as cast. Clean: no release-agent film (it lowers grip, and the inside is glued to the foot).],
)

*Reference material.* The robot was tuned with Polytek *PT Flex 60* in mind: Shore A 55–60,
tensile 2.1–2.4 MPa, elongation 222–235 %, tear (die C) 70–71 pli (about 12.4 kN/m), linear shrinkage
about 0.25 % (Polytek data sheets; the ranges cover the 2008 sheet and the 2021 technical bulletin). PT Flex 60 is an open-pour RTV rubber, so it is named only as the property target.
A vacuum-casting PU elastomer set to about 60A is preferred, for example SikaBiresin PX840 at 60–65A,
Hei-Cast 8400 at 60A or ALCHEMIX VC 3300 at 60A. Please name the resin you will use and send its datasheet with the quote.

*Hardness is the key value.* Please do not change the hardness or the material without written agreement
(your general terms allow small hardness deviations unless agreed in writing; this document is that written requirement).

= Feet (optional line item): rigid
#table(columns: (auto, 1fr),
  [Property], [Requirement],
  [Process], [SLS printing, dyed. MJF only if you can make it bright orange (standard MJF PA12 is grey). Vacuum casting in a rigid PU (Shore D 80 or more), pigmented orange, is also fine if it is cheaper for the quantity.],
  [Material], [PA12 (for example HP 3D HR PA 12), or a rigid PU of similar strength.],
  [Colour], [*Bright orange*, the same shade as the soles (for example RAL 2004). Dyed or pigmented through, not painted.],
  [Screws], [The part takes M2 self-tapping screws in its modelled pilot holes, so the material must not crack when screwed.],
)

= Quantities
One set is one left and one right part.
- Soles: please quote *2, 5 and 10 sets*, with the master and mould cost on its own line.
- Feet (optional): *2 sets*, quoted separately from the soles.

= Please send with the quote
- The resin name and datasheet for the soles, and the hardness you will cast (60A ± 5), confirmed in the quotation itself.
- Price per set for each quantity in the request, with the mould/master cost shown on its own line.
- Lead time, and how many castings one silicone mould gives for this part.
