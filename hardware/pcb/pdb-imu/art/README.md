# Silkscreen art

`make_art.py` draws all the silkscreen text and pictures of the board as filled shapes. tscircuit's own silkscreen font
draws its lines at 9% of the text height (0.07 mm for 0.8 mm text), too thin for JLCPCB to print, and it has no "é".

**Bottom side** (`art.ts`):
- a drawing of the microduck robot, seated with its head up, in isometric view;
- the word "microduck";
- the flags of Brazil and Pernambuco;
- "Rafael Caricio" and "@rafaelcaricio" in JetBrains Mono;
- on the left side, "Designed in / Vila Mauricéia, / IPSEP" in JetBrains Mono, next to a drawing of a
  sitting dog (`src/dog.png`, a black and white woodcut-style drawing);
- "1M" next to the bus speed jumper JP1.

Each bottom item is placed in an area with no pads, holes, vias or bottom-side traces, 2 mm clear of the mounting holes.
The positions are in `index.circuit.tsx`.

**Top side** (`top_art.ts`):
- the designators of the main parts (ICs, FETs, fuses, LEDs, switch, shunt, D1, JP2, J3, J7, the test points) and the J2 pin names;
- the connector labels, with the text cut out of a printed box: "J4 L LEG", "J6 R LEG", "J5 HEAD", "J2 SWD", "ON", "2S" and the board name;
- icons: the IMU axes (z out of the board, x and y as the sensor's own axes), a servo (the leg connectors), a battery
  (J1, + on the BAT+ side), and "A" / "V" meters (the current and voltage readings).

The top items are placed by `place_top.py` (see below). The small resistors and capacitors have no designator on the board.

`art.ts` and `top_art.ts` are generated, so do not edit them by hand. To change the art:

1. Robot drawing (only when the robot model or pose changes). The robot meshes come with
   [microduck_rl](https://github.com/pollen-robotics/microduck_rl):

   ```bash
   uv run art/robot_outline.py <microduck_rl>/src/mjlab_microduck/robot/microduck/assets
   ```

   This writes `src/microduck_iso_parts.png`. `NECK_PITCH`, `HEAD_PITCH` (rad) and `AZIMUTH` (deg) change the pose and view.

2. All art. This needs `rsvg-convert` (librsvg) and JetBrains Mono Bold. Set `JBMONO` to the `.ttf` file if it is not in `~/Library/Fonts`:

   ```bash
   uv run art/make_art.py
   ```

   This writes `art.ts` and `top_art.ts`, plus `preview/*.svg` (the bottom items as seen from below the board) and
   `preview/top/*.svg`.

3. Top-side positions. After any change to the layout or to the top art, build the board and place the items again:

   ```bash
   bunx tsci build index.circuit.tsx
   uv run art/place_top.py dist/index/circuit.json art/top_art.ts
   ```

   Paste the printed rows into `TOP_ART` in `index.circuit.tsx`. Each item goes to the clear spot nearest to its target
   (the list `T` in `place_top.py`): at least 0.2 mm from exposed copper, outside part bodies and connector outlines,
   off the footprint outlines and 0.25 mm from the other items. A row printed as a comment found no clear spot: move its target.

## Rules the script follows

- Silkscreen is one color. Flag colors are mapped to ink (white, yellow) or bare board (green, blue, red).
- No printed line is thinner than 0.15 mm, the JLCPCB silkscreen minimum, and no gap either, except in the sharp
  inside corners of letters (N, @). Details below that size are drawn larger or left out:
  - the text strokes are thickened by 0.02 mm a side, to about 0.18 mm;
  - the letters cut out of the label boxes are widened the same way, so they stay open;
  - the Brazil motto is filled in, and each star becomes a round dot;
  - on the Pernambuco flag, the rainbow arcs are drawn slightly wider, and the sun and star are drawn larger;
  - the dog drawing is blurred by 0.05 mm before it is cut to one color, so its many thin carving strokes merge into
    printed areas and only the wide light areas (chest, legs, face) stay bare.
- The bottom art is mirrored left to right in `art.ts`, because it is printed on the bottom side. The top art is not.
- tscircuit fills each SVG ring as a shape with holes, and a filled shape inside a hole would cancel out. So any shape with art inside one of its holes is split in two.

Flag sources, both public domain from Wikimedia Commons: `src/Flag_of_Brazil.svg` and `src/Bandeira_de_Pernambuco.svg`.
