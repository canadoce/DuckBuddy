# /// script
# dependencies = ["numpy", "pillow", "scipy", "scikit-image", "shapely"]
# ///
"""Make the one-color silkscreen art of the PDB/IMU board.

Every item is drawn as a high resolution image, cleaned so that no printed line
or gap is thinner than the silkscreen minimum, traced into polygons and written
as filled SVG paths:

- brazil, pernambuco: from the reference flag drawings in src/ (Wikimedia
  Commons, public domain). White and yellow print; green, blue and red are bare
  board. On the Brazil flag the motto band prints solid and each star is a
  round dot. On the Pernambuco flag the red and green rainbow arcs print and the
  yellow one is bare, so the rainbow shows its stripes; the sun and star are
  drawn larger so their rays and points print.
- microduck: the robot seated with its head up, in isometric view
  (src/microduck_iso_parts.png, made by robot_outline.py from the MuJoCo model).
  Drawn as a hand-tuned flat icon (see microduck() below): bare face plate
  with a round eye, printed jaw, and thin bare lines between the main parts.
- dog: the woodcut drawing in src/dog.png; the black ink prints.
- name, handle, label, place1..3: text set in JetBrains Mono Bold (set
  JBMONO to the .ttf path if it is not in ~/Library/Fonts).

Top side (top_art.ts, not mirrored): the designators of the main parts, the
connector labels with the text cut out of a printed box, and the icons (IMU
axes, battery, servo, "A" and "V" meters). tscircuit's own silkscreen text is
too thin to print, so all top-side text is drawn here too. Their positions on
the board come from art/place_top.py.

Outputs: preview/*.svg (as seen from below the board), art.ts (mirrored,
because that art sits on the bottom side), preview/top/*.svg and top_art.ts;
both .ts files are used by index.circuit.tsx.

Needs rsvg-convert (librsvg) on the PATH.
Run (from hardware/pcb/pdb-imu): uv run art/make_art.py
"""
import os, pathlib, subprocess, tempfile, urllib.parse
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from skimage import measure
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import unary_union, split
from shapely import affinity

HERE = pathlib.Path(__file__).parent
SRC = HERE / "src"
PX = 100  # pixels per mm while drawing
MIN_FEATURE = 0.15  # mm, smallest printed line and smallest gap
FONT = os.environ.get("JBMONO", str(pathlib.Path.home() / "Library/Fonts/JetBrainsMono-Bold.ttf"))


def disk(r_px):
    y, x = np.ogrid[-r_px:r_px + 1, -r_px:r_px + 1]
    return x * x + y * y <= r_px * r_px


def clean(mask):
    """Close gaps and remove lines thinner than MIN_FEATURE."""
    k = disk(int(MIN_FEATURE * PX / 2))
    mask = ndimage.binary_closing(mask, structure=k, border_value=0)
    mask = ndimage.binary_opening(mask, structure=k)
    return mask


def trace(mask):
    """Binary image (rows down) -> shapely geometry in mm, y down, origin top-left."""
    padded = np.pad(mask, 2).astype(float)
    rings = []
    for c in measure.find_contours(padded, 0.5):
        pts = [((x - 2) / PX, (y - 2) / PX) for y, x in c]
        if len(pts) < 4:
            continue
        p = Polygon(pts).buffer(0)
        if p.area > (MIN_FEATURE ** 2) / 4:
            rings.append(p)
    rings.sort(key=lambda p: -p.area)
    # Even-odd nesting: a ring inside an odd number of larger rings is a hole.
    geom = Polygon()
    for p in rings:
        depth = sum(1 for q in rings if q.area > p.area and q.contains(p.representative_point()))
        geom = geom.union(p) if depth % 2 == 0 else geom.difference(p)
    return geom.simplify(0.01)


def rasterize_svg(svg_text, width_mm):
    with tempfile.TemporaryDirectory() as tmp:
        src, png = pathlib.Path(tmp) / "in.svg", pathlib.Path(tmp) / "out.png"
        src.write_text(svg_text)
        subprocess.run(["rsvg-convert", "-w", str(int(width_mm * PX)), "-b", "#000000", str(src), "-o", str(png)], check=True)
        return np.array(Image.open(png).convert("RGB")).astype(int)


def outline_frame(w, h):
    """Thin printed border so the bare (dark) parts of a flag still read as a flag."""
    t = MIN_FEATURE + 0.02
    return box(0, 0, w, h).difference(box(t, t, w - t, h - t))


def brazil(width_mm):
    rgb = rasterize_svg((SRC / "Flag_of_Brazil.svg").read_text(), width_mm)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    yellow = (r > 150) & (g > 150) & (b < 120)
    white = (r > 200) & (g > 200) & (b > 200)
    # The band: the largest white area, with the motto letters filled in (too small to print).
    lab, n = ndimage.label(ndimage.binary_closing(white, structure=disk(int(0.12 * PX))))
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    band = lab == (int(np.argmax(sizes)) + 1)
    # The stars: each one becomes a round dot at least 0.2 mm across.
    dots = np.zeros_like(white)
    yy, xx = np.indices(white.shape)
    for i in range(1, n + 1):
        if i == int(np.argmax(sizes)) + 1:
            continue
        cy, cx = ndimage.center_of_mass(lab == i)
        rad = max(0.1 * PX, np.sqrt(sizes[i - 1] / np.pi))
        dots |= (yy - cy) ** 2 + (xx - cx) ** 2 <= rad ** 2
    h_mm = rgb.shape[0] / PX
    return width_mm, h_mm, unary_union([trace(clean(yellow | band | dots)), outline_frame(width_mm, h_mm)])


def scaled(svg, path_id, cx, cy, k):
    """Wrap one path of the flag drawing in a scale about (cx, cy)."""
    start = svg.index(f'<path id="{path_id}"')
    end = svg.index("/>", start) + 2
    return (svg[:start] + f'<g transform="translate({cx} {cy}) scale({k}) translate({-cx} {-cy})">'
            + svg[start:end] + "</g>" + svg[end:])


def pernambuco(width_mm):
    svg = (SRC / "Bandeira_de_Pernambuco.svg").read_text()
    # Print: white band, red and green rainbow arcs, sun and star.
    # Bare: blue field, yellow rainbow arc (so the rainbow shows its stripes) and red cross.
    # The arcs are 12/540 of the flag wide; at board size that is below the silkscreen
    # minimum, so they are redrawn a little wider (15/540) around the same centre.
    arcs = {"arco_vermelho": (207, "#FFFFFF"), "arco_amarelo": (192, "#000000"), "arco_verde": (177, "#FFFFFF")}
    for arc_id, (rad, color) in arcs.items():
        start = svg.index(f'<path id="{arc_id}"')
        end = svg.index("/>", start) + 2
        svg = (svg[:start] + f'<path id="{arc_id}" d="M{270 - rad} 270 A {rad} {rad} 0 0 1 {270 + rad},270" '
               f'fill="none" stroke-width="15" stroke="{color}"/>' + svg[end:])
    svg = svg.replace('stroke="#C34342" fill="none"', 'stroke="#000000" fill="none"')  # the cross
    svg = svg.replace('fill="#FFB511"', 'fill="#FFFFFF"').replace('fill="#3155A4"', 'fill="#000000"')
    # The sun's rays and the star's points are also below the minimum, so both are drawn larger (same centres).
    svg = scaled(svg, "sol", 270, 157.5, 1.45)
    svg = scaled(svg, "strela", 270, 33, 1.6)
    rgb = rasterize_svg(svg, width_mm)
    ink = rgb.min(axis=2) > 128
    h_mm = rgb.shape[0] / PX
    return width_mm, h_mm, unary_union([trace(clean(ink)), outline_frame(width_mm, h_mm)])


# Levels in src/microduck_iso_parts.png (see PARTS in robot_outline.py).
SHELL, FACE, EYE, JAW, NECK, TRUNK, LEFT_LEG, RIGHT_LEG = 10, 20, 30, 40, 50, 60, 70, 80


def microduck(height_mm):
    """The robot as a flat icon, hand tuned for a small one-color print.

    - Each part's outline is smoothed, so the lines between parts are clean curves.
    - Small fragments (brackets, screws, bits of a part seen through gaps) join the part around them.
    - Small holes inside a printed part (gaps between brackets) are filled.
    - The face plate stays bare, inside a thin printed rim that keeps the head outline whole. The eye becomes a round printed disc with a small bare
      highlight, placed on the lens; the jaw is the printed strip under the face.
    - Thin bare lines separate head shell, jaw, trunk and the two legs.
    """
    parts = Image.open(SRC / "microduck_iso_parts.png")
    size = (int(round(parts.width * height_mm * PX / parts.height)), int(height_mm * PX))
    lab = np.array(parts.resize(size, Image.NEAREST)).astype(int)
    levels = [SHELL, FACE, EYE, JAW, NECK, TRUNK, LEFT_LEG, RIGHT_LEG]

    # Eye position and size, taken from the lens before smoothing.
    eye = lab == EYE
    el, n = ndimage.label(eye)
    big = 1 + int(np.argmax(ndimage.sum(eye, el, range(1, n + 1))))
    ey, ex = ndimage.center_of_mass(el == big)
    er = np.sqrt((el == big).sum() / np.pi)
    lab[eye] = FACE

    # Smooth every part: each pixel takes the part with the most weight around it.
    sigma = 0.08 * PX
    silhouette = ndimage.gaussian_filter((lab > 0).astype(float), sigma) > 0.5
    weights = np.stack([ndimage.gaussian_filter((lab == L).astype(float), sigma) for L in levels])
    lab = np.where(silhouette, np.array(levels)[np.argmax(weights, axis=0)], 0)

    # Fragments: any piece of a part smaller than 0.25 mm2 takes the label of the part next to it.
    min_px = 0.25 * PX * PX
    for L in levels:
        comp, n = ndimage.label(lab == L)
        sizes = ndimage.sum(np.ones_like(comp), comp, range(1, n + 1))
        for i, sz in enumerate(sizes, start=1):
            if sz < min_px:
                lab[comp == i] = -1
    hole = lab == -1
    if hole.any():
        idx = ndimage.distance_transform_edt(hole, return_distances=False, return_indices=True)
        lab = lab[tuple(idx)]

    # Fill small holes inside the robot (they are gaps between parts, not features).
    inside = ndimage.binary_fill_holes(lab > 0)
    holes, n = ndimage.label(inside & (lab == 0))
    for i in range(1, n + 1):
        if (holes == i).sum() < 0.6 * PX * PX:
            m_i = holes == i
            idx = ndimage.distance_transform_edt(m_i, return_distances=False, return_indices=True)
            lab[m_i] = lab[tuple(idx)][m_i]

    # Print everything but the face; bare lines between printed parts.
    ink = (lab > 0) & (lab != FACE)

    edge = np.zeros_like(ink)
    for dy, dx in ((0, 1), (1, 0)):
        a, b = lab, np.roll(lab, (dy, dx), axis=(0, 1))
        edge |= (a != b) & (a > 0) & (b > 0) & (a != FACE) & (b != FACE)
    edge = ndimage.binary_dilation(edge, structure=disk(int(MIN_FEATURE * PX / 2) + 1))
    ink &= ~edge
    # Printed rim along the head's outline, so the bare face does not open it.
    sil = lab > 0
    rim = sil & ~ndimage.binary_erosion(sil, structure=disk(int(0.18 * PX)))
    ink |= rim & np.isin(lab, [SHELL, FACE, JAW])

    # The eye: a round disc on the lens, with a highlight towards the upper left.
    yy, xx = np.indices(ink.shape)
    r = max(er * 0.9, 0.35 * PX)
    ink |= (yy - ey) ** 2 + (xx - ex) ** 2 <= r ** 2
    hr = max(r * 0.3, MIN_FEATURE * PX * 0.75)
    ink &= ~((yy - (ey - r * 0.35)) ** 2 + (xx - (ex - r * 0.35)) ** 2 <= hr ** 2)

    ink = clean(ink)
    g = trace(ink).buffer(0.03).buffer(-0.03)  # round off pixel corners
    return size[0] / PX, height_mm, g


def dog(height_mm):
    """The dog from src/dog.png, a black and white woodcut drawing.

    The black ink prints. The drawing is cropped to the dog and scaled to the
    height asked for. Its carving strokes are far thinner than the silkscreen
    minimum, so the drawing is blurred by 0.05 mm and cut at a light grey level:
    groups of thin strokes become one printed area, and only the wide light
    areas (chest, legs, face) stay bare. Then it is cleaned as usual.
    """
    gray = np.array(Image.open(SRC / "dog.png").convert("L"))
    ys, xs = np.nonzero(gray < 128)
    gray = gray[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    size = (int(round(gray.shape[1] * height_mm * PX / gray.shape[0])), int(height_mm * PX))
    small = np.array(Image.fromarray(gray).resize(size, Image.LANCZOS)).astype(float)
    ink = clean(ndimage.gaussian_filter(small, 0.05 * PX) < 200)
    g = trace(ink).buffer(0.03).buffer(-0.03)
    return size[0] / PX, height_mm, g


def text(s, em_mm):
    font = ImageFont.truetype(FONT, int(em_mm * PX))
    l, t, r, b = font.getbbox(s)
    img = Image.new("L", (r - l + 4, b - t + 4), 0)
    ImageDraw.Draw(img).text((2 - l, 2 - t), s, font=font, fill=255)
    # The font's strokes are just under the silkscreen minimum at these sizes, so thicken them
    # by 0.02 mm a side (to about 0.18 mm) instead of cleaning.
    ink = ndimage.binary_dilation(np.array(img) > 128, structure=disk(2))
    return img.width / PX, img.height / PX, trace(ink)


def flat_pieces(geom):
    """Split the art into polygons whose holes never hold other art.

    tscircuit turns each SVG ring into a filled shape with holes, and a filled
    island inside a hole cancels out. So a polygon whose hole holds other art
    is cut in two by a vertical line through that hole.
    """
    todo = [p for p in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]) if not p.is_empty]
    done = []
    while todo:
        p = todo.pop()
        others = todo + done
        busy = [h for h in p.interiors if any(Polygon(h).contains(q.representative_point()) for q in others)]
        if not busy:
            done.append(p)
            continue
        x = Polygon(busy[0]).centroid.x
        _, miny, _, maxy = p.bounds
        todo.extend(g for g in split(p, LineString([(x, miny - 1), (x, maxy + 1)])).geoms)
    return done


def ring_d(coords, k):
    pts = list(coords)[:-1]
    return "M" + " L".join(f"{x * k:.2f} {y * k:.2f}" for x, y in pts) + " Z"


def to_svg(w, h, pieces):
    k = 10  # SVG units of 0.1 mm
    d = []
    for q in pieces:
        d.append(ring_d(q.exterior.coords, k))
        d += [ring_d(i.coords, k) for i in q.interiors]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w * k:.1f} {h * k:.1f}" '
            f'width="{w:.2f}mm" height="{h:.2f}mm"><path fill-rule="evenodd" d="{" ".join(d)}"/></svg>')


def canvas(w, h):
    img = Image.new("L", (int(round(w * PX)), int(round(h * PX))), 0)
    return img, ImageDraw.Draw(img)


def at(x, y):
    return (x * PX, y * PX)


def drawn(img):
    """Traced drawing. Icons and labels are drawn with lines and gaps of at least 0.18 mm,
    so they skip clean(), which would close the narrow cut-out letters."""
    return img.width / PX, img.height / PX, trace(np.array(img) > 128)


def letter(d, s, x, y, em_mm, fill=255):
    """Letters centred on (x, y), with the strokes thickened like text()."""
    font = ImageFont.truetype(FONT, int(em_mm * PX))
    d.text(at(x, y), s, font=font, fill=fill, anchor="mm", stroke_width=2, stroke_fill=fill)


def knockout(s, em_mm=1.0, pad=0.25):
    """Text cut out of a printed box: the letters are bare board."""
    font = ImageFont.truetype(FONT, int(em_mm * PX))
    l, _, r, _ = font.getbbox(s)
    _, t, _, b = font.getbbox("HJ")  # same height for every label
    p = int(pad * PX)
    img = Image.new("L", (r - l + 2 * p, b - t + 2 * p), 0)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=int(0.2 * PX), fill=255)
    # Widen the cut-out letters by 0.02 mm a side, so their strokes stay above 0.15 mm.
    d.text((p - l, p - t), s, font=font, fill=0, stroke_width=2, stroke_fill=0)
    return drawn(img)


def imu_axes():
    """The IMU's axes as seen from above: Z out of the board (circle with a dot),
    X toward board -x (left), Y toward board -y (down)."""
    w, h, lw = 4.6, 4.0, 0.2
    img, d = canvas(w, h)
    cx, cy, r = 3.6, 1.4, 0.62
    d.ellipse([at(cx - r, cy - r), at(cx + r, cy + r)], outline=255, width=int(0.2 * PX))
    d.ellipse([at(cx - 0.2, cy - 0.2), at(cx + 0.2, cy + 0.2)], fill=255)
    tip = 0.85  # X arrow
    d.line([at(cx - r - 0.1, cy), at(tip + 0.4, cy)], fill=255, width=int(lw * PX))
    d.polygon([at(tip, cy), at(tip + 0.6, cy - 0.36), at(tip + 0.6, cy + 0.36)], fill=255)
    tip = h - 0.05  # Y arrow
    d.line([at(cx, cy + r + 0.1), at(cx, tip - 0.4)], fill=255, width=int(lw * PX))
    d.polygon([at(cx, tip), at(cx - 0.36, tip - 0.6), at(cx + 0.36, tip - 0.6)], fill=255)
    letter(d, "x", 0.33, cy - 0.08, 0.95)
    letter(d, "y", cx + 0.75, h - 0.6, 0.95)
    letter(d, "z", cx - 1.15, 0.42, 0.95)
    return drawn(img)


def battery():
    """A battery cell, + end (with the terminal) on the left, like J1."""
    w, h, lw = 3.4, 1.6, 0.2
    img, d = canvas(w, h)
    d.rectangle([at(0.4, 0.05), at(w - 0.05, h - 0.05)], outline=255, width=int(lw * PX))
    d.rectangle([at(0.05, h / 2 - 0.38), at(0.42, h / 2 + 0.38)], fill=255)
    for x, plus in ((1.15, True), (w - 0.75, False)):
        d.rectangle([at(x - 0.35, h / 2 - 0.1), at(x + 0.35, h / 2 + 0.1)], fill=255)
        if plus:
            d.rectangle([at(x - 0.1, h / 2 - 0.35), at(x + 0.1, h / 2 + 0.35)], fill=255)
    return drawn(img)


def servo():
    """A servo from above: case with mounting ears, and the horn on the output shaft."""
    w, h = 3.4, 2.4
    img, d = canvas(w, h)
    top, bot = 0.4, h - 0.4
    d.rectangle([at(0.42, top), at(w - 0.42, bot)], outline=255, width=int(0.2 * PX))
    for x0 in (0.05, w - 0.47):
        d.rectangle([at(x0, h / 2 - 0.35), at(x0 + 0.42, h / 2 + 0.35)], fill=255)
    sx, hw = 2.2, 0.2  # shaft x, half width of the horn arm
    # Clear a 0.18 mm gap around the horn where it crosses the case outline, then draw it.
    g = hw + 0.18
    d.rounded_rectangle([at(sx - g, 0.05 - 0.18), at(sx + g, h - 0.05 + 0.18)], radius=int(g * PX), fill=0)
    d.rounded_rectangle([at(sx - hw, 0.05), at(sx + hw, h - 0.05)], radius=int(hw * PX), fill=255)
    d.ellipse([at(sx - 0.45, h / 2 - 0.45), at(sx + 0.45, h / 2 + 0.45)], fill=255)
    return drawn(img)


def meter(s):
    """A meter symbol: the letter in a circle (A = current, V = voltage)."""
    w = h = 1.8
    img, d = canvas(w, h)
    d.ellipse([at(0.05, 0.05), at(w - 0.05, h - 0.05)], outline=255, width=int(0.18 * PX))
    letter(d, s, w / 2, h / 2 - 0.04, 0.95)
    return drawn(img)


ITEMS = [
    ("brazil", lambda: brazil(5.8)),
    ("pernambuco", lambda: pernambuco(5.8)),
    ("microduck", lambda: microduck(9.2)),
    ("microduckLabel", lambda: text("microduck", 1.25)),
    ("name", lambda: text("Rafael Caricio", 1.15)),
    ("handle", lambda: text("@rafaelcaricio", 1.15)),
    ("place1", lambda: text("Designed in", 1.0)),
    ("place2", lambda: text("Vila Mauricéia,", 1.0)),
    ("place3", lambda: text("IPSEP", 1.0)),
    ("dog", lambda: dog(5.9)),
    ("jp1", lambda: knockout("1M")),
]

# Top side: designators, labels and icons. tscircuit draws silkscreen text with a line 9% of
# its height (0.07 mm at 0.8 mm), too thin to print, so every top-side label is drawn here.
DESIGNATORS = ["U1", "U2", "U3", "U4", "U5", "U6", "Q1", "Q2", "SW1", "F1", "F2", "F3", "RS1", "D1",
               "LED1", "LED2", "LED3", "LED4", "JP2", "J3", "J7", "TP1 VB", "TP2 3V3", "TP3 G", "TP4 D",
               "DIO", "CLK", "GND", "3V3"]
TOP_ITEMS = [(s, lambda s=s: text(s, 1.0)) for s in DESIGNATORS] + [
    ("title", lambda: knockout("PDB/IMU R3 2S/3S")),
    ("J4", lambda: knockout("J4 L LEG")),
    ("J6", lambda: knockout("J6 R LEG")),
    ("J5", lambda: knockout("J5 HEAD")),
    ("J2", lambda: knockout("J2 SWD")),
    ("ON", lambda: knockout("ON")),
    ("2S", lambda: knockout("2S")),
    ("imu", imu_axes),
    ("battery", battery),
    ("servo", servo),
    ("amps", lambda: meter("A")),
    ("volts", lambda: meter("V")),
]

(HERE / "preview").mkdir(exist_ok=True)
ts = ["// Generated by art/make_art.py. Do not edit by hand.\n",
      "// The art goes on the bottom side, so it is mirrored left to right here to read correctly from below.\n"]
for name, fn in ITEMS:
    w, h, g = fn()
    (HERE / "preview" / f"{name}.svg").write_text(to_svg(w, h, flat_pieces(g)))
    mirrored = affinity.scale(g, -1, 1, origin=(w / 2, h / 2))
    url = "data:image/svg+xml," + urllib.parse.quote(to_svg(w, h, flat_pieces(mirrored)))
    ts.append(f'export const {name}Art = {{ url: "{url}", width: {w:.2f}, height: {h:.2f} }}\n')
    print(f"{name:15} {w:5.2f} x {h:5.2f} mm")
(HERE / "art.ts").write_text("".join(ts))

(HERE / "preview" / "top").mkdir(exist_ok=True)
ts = ["// Generated by art/make_art.py. Do not edit by hand.\n",
      "// Top-side designators, labels and icons, as seen from above (not mirrored).\n",
      "export const topArt: Record<string, { url: string; width: number; height: number }> = {\n"]
for name, fn in TOP_ITEMS:
    w, h, g = fn()
    svg = to_svg(w, h, flat_pieces(g))
    (HERE / "preview" / "top" / f"{name.replace(' ', '_')}.svg").write_text(svg)
    url = "data:image/svg+xml," + urllib.parse.quote(svg)
    ts.append(f'  "{name}": {{ url: "{url}", width: {w:.2f}, height: {h:.2f} }},\n')
    print(f"top {name:11} {w:5.2f} x {h:5.2f} mm")
ts.append("}\n")
(HERE / "top_art.ts").write_text("".join(ts))
