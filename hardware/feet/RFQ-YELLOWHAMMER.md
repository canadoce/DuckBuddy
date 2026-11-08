# Quote request to Yellowhammer: cast foot soles

This file records the quote request for the soft soles (and optional rigid feet) at
[Yellowhammer](https://yellowhammer.pl/en/get-a-quote/?form=4) (Poland, urethane vacuum casting):
the files, the text of every form field, and the status. Keep it up to date with each quote and order.
Why vacuum casting, and the geometry facts, are in the [README](README.md).

## Status

| Date | Step | State |
|---|---|---|
| 2026-11-07 | RFQ package | Files made (below). |
| 2026-11-07 | Review | Independent review: rim height and tilt on the drawing fixed (13.3 / 10.0 mm, 4.9°); the sole is now 0.8 % smaller than the foot with ±0.3 mm (was nominal +0.0/−0.4); quantities added to the material PDF; zip holds STEP files only. |
| 2026-11-07 | Second review | Thinnest wall is 1.2 mm (true thickness at the toe and heel), not 1.4 mm; wall tolerance now +0.3/−0.2 mm, never under 1.0 mm. The form's technology boxes allow one tick: SLA only. Ankle hole sizes, fit wording and section labels fixed. |
| 2026-11-07 | Third review | The thin wall (1.2–1.5 mm) is a band at Z = 3–7 all round, not only at the toe and heel; inspection heights added. Pilot hole may be cleaned to Ø1.6 if printed small. Hardness to be confirmed in the quotation. Form notes: PDF-only fields, 2000-character text box. Quality PDF tolerance table had a collapsed first column (fixed widths now). |
| 2026-11-08 | Colour | Soles and feet in bright orange (for example RAL 2004), not black. Feet as SLS PA12 dyed orange (standard MJF PA12 is grey). |
| 2026-11-08 | Sent | Sent through the web form (`?form=4`); the page answered "Your inquiry has been sent". Waiting for the quote by e-mail. |

## Files

All in [`rfq/`](rfq/). Rebuild with `hardware/feet/src/make_rfq.sh` (after `feet_parts.py` and `drawing.py`).

| Form field | File | SHA-256 |
|---|---|---|
| Project file (.stp/.step, or a .zip of them) | `duckbuddy-feet-cad.zip`: the 4 STEP files | `6e9670c2c73dd936fb6f0f3f38ea26792c62674a9353b48488bf25eeb4e0cc6b` (19.5 MB) |
| Technical drawing | `duckbuddy-feet-drawing.pdf` (A3, 2 sheets: sole, foot + assembly section) | `7b2823b090c4042d7a9980aae65f317675be73903e2ee56195ba29bd895888d4` |
| Quality requirements | `duckbuddy-feet-quality-requirements.pdf` | `c1631426416455201a696717ad2efa33911ceade980fef8f379c2a3f75a1d0c9` |
| Material requirements | `duckbuddy-feet-material-requirements.pdf` | `a7826b9efd32175de645c0156694961d1bf7f4e00ba791a9692ab8aeed44ae11` |

The form page says "Extensions: .stp and .step (max. 100Mb)" and "Do you have several similar files? Add them in one .zip file".
The zip holds only the STEP files, as asked. STL copies are in [`STL/`](STL/) if the bureau wants them.

## Form fields

Form: *Get a quote → Silicone injection molding and vacuum casting* (`?form=4`).

| Field | Value |
|---|---|
| Project file | `duckbuddy-feet-cad.zip` |
| Prototyping technology | Tick **SLA** only (for the master). The boxes allow one choice: ticking one unticks the others. The text below says the feet are SLS PA12. |
| Technical drawing | `duckbuddy-feet-drawing.pdf` (the field takes PDF only) |
| Quality requirements | `duckbuddy-feet-quality-requirements.pdf` (PDF only) |
| Material requirements | `duckbuddy-feet-material-requirements.pdf` (PDF only) |
| Project requirements | The text below (the field takes at most 2000 characters) |
| First name and last name | Rafael Caricio |
| E-mail | rafael@caricio.com |
| Phone | (fill in; optional on the form) |
| Shipping address | (fill in; optional on the form) |
| VAT invoice | (your choice) |
| Terms of sale | Read them first: [general terms of sale](https://yellowhammer.pl/en/general-terms-of-sale/) |

The form has a reCAPTCHA and the terms checkbox, so it is filled in and sent by hand.

### Project requirements (paste into the text box)

```text
Request for quotation: soft foot soles for a small two-legged walking robot (DuckBuddy).

Parts (STEP files in duckbuddy-feet-cad.zip; drawing and requirements as PDFs):
1. sole_left.step and sole_right.step (a mirror pair). Vacuum-cast PU elastomer, Shore 60A +-5
   (target 55-60A, never above 65A), bright orange (e.g. RAL 2004). A thin cup, 53.6 x 40.9 x 13.3 mm, walls 1.2-2.1 mm,
   floor 2.0 mm, 6.1 cm3 each. Property target: Polytek PT Flex 60. Please propose your
   vacuum-casting PU at about 60A and send its datasheet.
2. Optional, please quote separately: foot_left.step and foot_right.step. Rigid, SLS PA12 dyed
   bright orange (same shade as the soles), or rigid PU cast in orange. 54.0 x 39.9 x 16.4 mm, 12.2 cm3 each.

Quantities (1 set = 1 left + 1 right): soles for 2, 5 and 10 sets, with the master and mould
cost on its own line. Feet: 2 sets.

Key requirements (details in the attached PDFs):
- The sole STEP is the finished part: it is already 0.8 % smaller than the foot, so the
  sole stretches over the foot. Please add only your usual shrinkage compensation.
- General tolerance +-0.3 mm, cavity included.
- Ground face: no gate, vent, parting line or flash, matte, no release-agent film.
  Gates and vents on the rim top face (it is hidden under the foot).
- Hardness report (Shore A) from a test button of the same mix.
- Left and right marked on the bags.

Technology: SLA for the master model (ticked on the form), SLS PA12 for the optional feet.
Please tell us the lead time and how many castings one mould gives. Thank you.
```

## E-mail version

If the form fails, or for a follow-up, send the same request to contact@yellowhammer.pl with the four files attached
(the zip is under 100 MB, but check the mail size limit; if it is too big, send the PDFs and offer a download link for the zip).

```text
Subject: RFQ - vacuum-cast PU soles, Shore 60A, 2/5/10 sets (+ optional PA12 feet)

Hello,

I would like a quote for vacuum-cast soft soles for a small walking robot.

<paste the "Project requirements" text above>

Attached:
- duckbuddy-feet-cad.zip (STEP files of the 4 parts)
- duckbuddy-feet-drawing.pdf
- duckbuddy-feet-quality-requirements.pdf
- duckbuddy-feet-material-requirements.pdf

Best regards,
Rafael Caricio
rafael@caricio.com
```

## Facts for questions from the bureau

- **Source of the geometry:** mesh parts (upstream Microduck/OpenMicroDuck), so the STEP files are faceted solids.
  The flat faces are flat; the curved faces are fine facets. Accuracy of the mesh is far better than ±0.3 mm.
- **Part frame:** ground face of the sole at Z = 0, sole and foot of one side in their assembled position
  (the sole is 0.8 % smaller, so in CAD the two overlap a little).
- **Parting line idea:** the sole is an open cup, so a mould split at the rim with a core for the cavity keeps every
  parting line and gate off the ground face.
- **Why the sole is 0.8 % smaller than the foot:** it is a stretch fit. The cavity is about 0.4 mm shorter and 0.3 mm
  narrower than the foot, so at the edge of ±0.3 mm the cavity is the same width as the foot (never looser) and at most
  stretches about 1.6 %, which a 60A elastomer takes easily.
- **Hardness:** 55–65A is acceptable; 60A is the target. Softer parts tear more easily at 2 mm walls; harder ones
  grip and damp less.
- **Release agent:** the inside may be glued with cyanoacrylate and the outside must grip, so the parts must be clean.
