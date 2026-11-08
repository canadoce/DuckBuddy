# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh", "numpy", "scipy", "networkx", "rtree", "shapely", "matplotlib"]
# ///
"""Technical drawing (A3, 2 sheets, PDF) of the DuckBuddy foot sole and foot.

Every number on the sheets is measured from `hardware/feet/STL/*_left.stl` (made by `feet_parts.py`),
so a change of the parts moves the dimensions. Tolerances and notes come from TOL and the note lists
below; they are design requirements, not measurements.

Run from the repository root:  uv run hardware/feet/src/drawing.py [out.pdf]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MPath
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

FEET = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else FEET / "rfq/duckbuddy-feet-drawing.pdf"
REV = "A"
DATE = "2026-11-07"
AUTHOR = "Rafael Caricio"
SCALE = 2.0  # drawing scale 2:1
SOLE_SCALE = 1.0  # read from parts.json: the sole files are this much smaller than the modelled sole

# Tolerances (design requirements, mm)
TOL = {
    "general": 0.3,  # Yellowhammer's standard vacuum-casting accuracy (+-0.3 %, min +-0.3 mm)
}

W3, W5, W2 = 0.25, 0.5, 0.18  # line weights in mm: thin, visible, dims
MM = 72 / 25.4  # points per mm
FS = 7.0  # text size in pt


# ---------------------------------------------------------------- geometry helpers
def section_polys(m: trimesh.Trimesh, origin, normal, axes) -> list[Polygon]:
    """Section of a mesh as shapely polygons (with holes), in the 2 model axes given."""
    sec = m.section(plane_normal=normal, plane_origin=origin)
    if sec is None:
        return []
    lines = [LineString(d[:, axes]) for d in sec.discrete]
    # polygonize returns every face of the line arrangement, so take only the outer rings
    rings = sorted({Polygon(p.exterior) for p in polygonize(unary_union(lines))}, key=lambda p: -p.area)
    # even-odd nesting: a ring inside an odd number of larger rings is a hole of the smallest of them
    inside = [[j for j in range(i) if rings[j].contains(rings[i].representative_point())] for i in range(len(rings))]
    shells = {i: [] for i in range(len(rings)) if len(inside[i]) % 2 == 0}
    for i in range(len(rings)):
        if len(inside[i]) % 2 == 1:
            parent = max((j for j in inside[i] if j in shells), key=lambda j: len(inside[j]))
            shells[parent].append(rings[i].exterior)
    return [Polygon(rings[i].exterior, h) for i, h in shells.items()]


def silhouette(m: trimesh.Trimesh, axes) -> Polygon:
    tri = m.triangles[:, :, axes]
    polys = [Polygon(t) for t in tri if Polygon(t).area > 1e-6]
    return unary_union(polys).buffer(0)


def ray_hits(m: trimesh.Trimesh, origin, direction) -> np.ndarray:
    loc, _, _ = m.ray.intersects_location([origin], [direction], multiple_hits=True)
    return loc


# ---------------------------------------------------------------- drawing helpers
class Sheet:
    def __init__(self, pdf: PdfPages, title: str, part_no: str, material: str, sheet: int, of: int):
        self.pdf = pdf
        self.fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, 420)
        self.ax.set_ylim(0, 297)
        self.ax.axis("off")
        a = self.ax
        a.add_patch(Rectangle((10, 10), 400, 277, fill=False, lw=0.7 * MM))
        # title block, bottom right, 180 x 36
        x0, y0, w = 230, 10, 180
        rows = [
            ("TITLE", title, 12),
            ("PART NO.", part_no, 8),
            ("MATERIAL", material, 8),
        ]
        a.add_patch(Rectangle((x0, y0), w, 40, fill=False, lw=0.5 * MM))
        y = y0 + 40
        for label, text, h in rows:
            y -= h
            a.plot([x0, x0 + w], [y, y], "k", lw=W3 * MM)
            a.text(x0 + 2, y + h - 1.5, label, fontsize=4.5, va="top")
            a.text(x0 + 22, y + h / 2, text, fontsize=FS + (2 if label == "TITLE" else 0), va="center",
                   weight="bold" if label == "TITLE" else "normal")
        cells = [("SCALE", f"{SCALE:g}:1"), ("UNITS", "mm"), ("PROJECTION", "Views as labelled"), ("REV", REV),
                 ("DATE", DATE), ("DRAWN", AUTHOR), ("SHEET", f"{sheet} OF {of}")]
        cw = w / len(cells)
        for i, (label, text) in enumerate(cells):
            cx = x0 + i * cw
            if i:
                a.plot([cx, cx], [y0, y], "k", lw=W3 * MM)
            a.text(cx + 1.5, y - 1.5, label, fontsize=4.5, va="top")
            a.text(cx + cw / 2, y0 + 4, text, fontsize=6, ha="center", va="center")

    def view_label(self, x, y, text):
        self.ax.text(x, y, text, fontsize=FS + 1, ha="center", va="top", weight="bold")

    def notes(self, x, y, title, lines, width=95):
        self.ax.text(x, y, title, fontsize=FS + 1, weight="bold", va="top")
        y -= 5
        import textwrap

        for i, ln in enumerate(lines, 1):
            wrapped = textwrap.wrap(ln, width=width)
            self.ax.text(x, y, f"{i}.", fontsize=FS, va="top")
            for w in wrapped:
                self.ax.text(x + 5, y, w, fontsize=FS, va="top")
                y -= 3.4
            y -= 0.8
        return y

    def save(self):
        self.pdf.savefig(self.fig)
        plt.close(self.fig)


class View:
    """Maps model coordinates (2 chosen axes, mm) to sheet mm at the drawing scale."""

    def __init__(self, sheet: Sheet, at, axes, flip=(1, 1)):
        self.s, self.at, self.axes, self.flip = sheet, np.array(at, float), axes, np.array(flip, float)

    def p(self, u, v):
        return self.at + SCALE * self.flip * np.array([u, v])

    def ring(self, coords, lw=W5, ls="-", color="k"):
        c = np.array([self.p(*q) for q in np.asarray(coords)])
        self.s.ax.plot(c[:, 0], c[:, 1], color=color, lw=lw * MM, ls=ls, solid_joinstyle="round")

    def poly(self, poly: Polygon, lw=W5, ls="-"):
        self.ring(poly.exterior.coords, lw, ls)
        for r in poly.interiors:
            self.ring(r.coords, lw, ls)

    def hatched(self, poly: Polygon):
        verts, codes = [], []
        for r in [poly.exterior, *poly.interiors]:
            c = [self.p(*q) for q in r.coords]
            verts += c
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(c) - 2) + [MPath.CLOSEPOLY]
        self.s.ax.add_patch(PathPatch(MPath(verts, codes), facecolor="none", edgecolor="k", hatch="////", lw=W5 * MM))

    def line(self, a, b, lw=W3, ls="-"):
        pa, pb = self.p(*a), self.p(*b)
        self.s.ax.plot([pa[0], pb[0]], [pa[1], pb[1]], "k", lw=lw * MM, ls=ls)

    def dim(self, a, b, offset, text, horizontal=True):
        """Linear dimension between model points a and b; offset is in sheet mm from the points."""
        ax = self.s.ax
        pa, pb = self.p(*a), self.p(*b)
        if horizontal:
            yl = (max(pa[1], pb[1]) if offset > 0 else min(pa[1], pb[1])) + offset
            for q in (pa, pb):
                ax.plot([q[0], q[0]], [q[1] + np.sign(offset) * 1, yl + np.sign(offset) * 1.5], "k", lw=W2 * MM)
            ax.annotate("", (pa[0], yl), (pb[0], yl), arrowprops=dict(arrowstyle="<|-|>", lw=W2 * MM, color="k",
                        shrinkA=0, shrinkB=0, mutation_scale=6))
            ax.text((pa[0] + pb[0]) / 2, yl + 0.8, text, fontsize=FS, ha="center", va="bottom")
        else:
            xl = (max(pa[0], pb[0]) if offset > 0 else min(pa[0], pb[0])) + offset
            for q in (pa, pb):
                ax.plot([q[0] + np.sign(offset) * 1, xl + np.sign(offset) * 1.5], [q[1], q[1]], "k", lw=W2 * MM)
            ax.annotate("", (xl, pa[1]), (xl, pb[1]), arrowprops=dict(arrowstyle="<|-|>", lw=W2 * MM, color="k",
                        shrinkA=0, shrinkB=0, mutation_scale=6))
            ax.text(xl + (0.8 if offset > 0 else -0.8), (pa[1] + pb[1]) / 2, text, fontsize=FS, rotation=90,
                    ha="left" if offset > 0 else "right", va="center")

    def leader(self, a, dx, dy, text):
        pa = self.p(*a)
        pt = pa + np.array([dx, dy])
        self.s.ax.annotate(text, pa, pt, fontsize=FS, ha="left" if dx >= 0 else "right", va="center",
                           arrowprops=dict(arrowstyle="-|>", lw=W2 * MM, color="k", mutation_scale=5, shrinkA=1, shrinkB=0))

    def cut_line(self, a, b, label):
        self.line(a, b, lw=W2, ls=(0, (8, 2, 1, 2)))
        for q in (a, b):
            pq = self.p(*q)
            self.s.ax.text(pq[0], pq[1], label, fontsize=FS + 2, weight="bold", ha="center", va="center",
                           bbox=dict(boxstyle="circle,pad=0.15", fc="white", ec="k", lw=W2 * MM))


def f1(v):
    return f"{v:.1f}"


# ---------------------------------------------------------------- measurements
def measure(sole: trimesh.Trimesh, foot: trimesh.Trimesh) -> dict:
    lo, hi = sole.bounds
    m = {"L": hi[0] - lo[0], "W": hi[1] - lo[1], "H": hi[2] - lo[2], "zmin": lo[2], "zmax": hi[2]}
    # floor thickness at the centre: ground hit and cavity floor hit
    z = np.sort(ray_hits(sole, [0, 0, -5], [0, 0, 1])[:, 2])
    m["floor"] = z[1] - z[0]
    # cavity size at Z = 6
    p = max(section_polys(sole, [0, 0, 6.0], [0, 0, 1], [0, 1]), key=lambda q: q.area)
    ib = Polygon(max(p.interiors, key=lambda r: Polygon(r).area)).bounds
    m["cav_L"], m["cav_W"], m["cav_bounds"] = ib[2] - ib[0], ib[3] - ib[1], ib
    # rim height on the two long sides (rim top is not parallel to the ground face)
    # highest point of each long side in the YZ section at X = 0 (the walls lean, so a ray can miss the rim top)
    sec = np.vstack(sole.section(plane_normal=[1, 0, 0], plane_origin=[0, 0, 0]).discrete)
    rim, rim_y = {}, {}
    for side, sel in (("-Y", sec[:, 1] < lo[1] / 2), ("+Y", sec[:, 1] > hi[1] / 2)):
        q = sec[sel]
        rim[side], rim_y[side] = q[:, 2].max(), q[q[:, 2].argmax(), 1]
    m["rim"] = rim
    m["rim_tilt_deg"] = float(np.degrees(np.arctan2(abs(rim["-Y"] - rim["+Y"]), rim_y["+Y"] - rim_y["-Y"])))
    # wall thickness at the middle of each side: horizontal rays from the cavity centre, from Z = 4 up to 1 mm
    # below the rim top of that side (the rim top edge itself is not a wall)
    walls = []
    for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
        d = np.array(d, float)
        for zc in np.arange(4.0, hi[2], 0.5):
            start = np.array([0.0, 0.0, zc])
            hits = ray_hits(sole, start, d)
            if len(hits) < 2:
                continue
            t = np.sort((hits - start) @ d)
            mid = start + d * (t[0] + t[1]) / 2
            top = ray_hits(sole, [mid[0], mid[1], 40], [0, 0, -1])[:, 2]
            if len(top) and zc < top.max() - 1.0:
                walls.append(t[1] - t[0])
    m["wall_max"] = max(walls)
    # thinnest wall: from every cavity-wall face, a ray along the face normal into the material to the outer
    # surface. This is the true thickness where the cavity chamfer meets the rounded outside (toe and heel),
    # which a horizontal ray reads too thick. Faces within 1 mm of the rim top and the floor are left out.
    c, n = sole.triangles_center, sole.face_normals
    rxy = c[:, :2] / np.linalg.norm(c[:, :2], axis=1, keepdims=True)
    z_rim = np.interp(c[:, 1], [rim_y["-Y"], rim_y["+Y"]], [rim["-Y"], rim["+Y"]])
    inner = ((n[:, :2] * rxy).sum(1) < -0.3) & (c[:, 2] > m["floor"] + 0.3) & (c[:, 2] < z_rim - 1.0)
    o = c[inner] - n[inner] * 1e-4
    loc, ri, _ = sole.ray.intersects_location(o, -n[inner], multiple_hits=False)
    t = np.linalg.norm(loc - o[ri], axis=1)
    m["wall_min"], m["wall_min_at"] = float(t.min()), c[inner][ri[t.argmin()]].tolist()
    # the thin band runs all round the sole: its height range (walls under 1.5 mm) and the wall above it
    zc = c[inner][ri][:, 2]
    band = zc[t < 1.5]
    m["wall_band_z"] = [float(np.floor(band.min())), float(np.ceil(band.max()))]
    m["wall_upper_min"] = float(t[zc > m["wall_band_z"][1]].min())
    # flat ground patch (faces facing straight down at Z = 0)
    sel = (sole.face_normals[:, 2] < -0.9995) & (sole.triangles_center[:, 2] < 0.05)
    v = sole.vertices[sole.faces[sel].ravel()]
    m["flat"] = (v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max())
    # foot
    flo, fhi = foot.bounds
    m["foot"] = {"L": fhi[0] - flo[0], "W": fhi[1] - flo[1], "H": fhi[2] - flo[2], "lo": flo, "hi": fhi}
    # round holes in the foot (pilot holes for self-tapping screws)
    holes = {}
    for zc in np.arange(flo[2] + 0.5, fhi[2], 0.5):
        for p in section_polys(foot, [0, 0, zc], [0, 0, 1], [0, 1]):
            for r in p.interiors:
                q = Polygon(r)
                circ = 4 * np.pi * q.area / q.length**2
                if circ > 0.92 and q.area < 30:
                    # one hole per axis: the axis may lean a little (the part frame is tilted), so group by distance
                    key = next((k for k in holes if np.hypot(k[0] - q.centroid.x, k[1] - q.centroid.y) < 1.0),
                               (q.centroid.x, q.centroid.y))
                    holes.setdefault(key, []).append((zc, 2 * np.sqrt(q.area / np.pi), q.centroid.x, q.centroid.y))
    m["holes"] = {}
    for k, v in holes.items():
        d_min = min(h[1] for h in v)
        zp = [h[0] for h in v if h[1] < d_min + 0.1]  # sections through the pilot bore (not the chamfer)
        m["holes"][k] = {"d_min": d_min, "z": (min(h[0] for h in v), max(h[0] for h in v)),
                         "depth": max(zp) - min(zp) + 0.5, "x": v[0][2], "y": v[0][3]}
    inter = foot.intersection(sole)
    m["overlap"] = 0.0 if inter.is_empty else inter.volume
    return m


# ---------------------------------------------------------------- sheets
def sole_sheet(pdf, sole, foot, m):
    s = Sheet(pdf, "Foot sole, LEFT shown, RIGHT is mirror image", "DB-FOOT-SOLE-L / DB-FOOT-SOLE-R",
              "Cast PU elastomer, Shore 60A +-5, bright orange (e.g. RAL 2004)", 1, 2)
    L, W = m["L"], m["W"]
    # TOP VIEW (looking down into the cavity): X right, Y up
    top = View(s, (95, 200), [0, 1])
    top.poly(silhouette(sole, [0, 1]))
    for p in section_polys(sole, [0, 0, 6.0], [0, 0, 1], [0, 1]):
        for r in p.interiors:
            top.ring(r.coords, lw=W3, ls=(0, (4, 2)))
    top.cut_line((-L / 2 - 4, 0), (L / 2 + 4, 0), "A")
    top.cut_line((0, -W / 2 - 4), (0, W / 2 + 4), "B")
    top.dim((-L / 2, W / 2), (L / 2, W / 2), 24, f"{f1(L)}")
    top.dim((L / 2, -W / 2), (L / 2, W / 2), 16, f"{f1(W)}", horizontal=False)
    cb = m["cav_bounds"]
    top.dim((cb[0], cb[3]), (cb[2], cb[3]), 14 + SCALE * (W / 2 - cb[3]),
            f"{f1(m['cav_L'])} ±{TOL['general']:.1f}  cavity at Z=6")
    top.dim((cb[0], cb[1]), (cb[0], cb[3]), -18 - SCALE * (cb[0] + L / 2),
            f"{f1(m['cav_W'])} ±{TOL['general']:.1f}  cavity at Z=6", horizontal=False)
    s.view_label(95, 200 + SCALE * W / 2 + 40, "TOP VIEW (into cavity, dashed: cavity at Z=6)")

    # BOTTOM VIEW: ground face, flat contact patch
    bot = View(s, (95, 75), [0, 1], flip=(1, -1))
    bot.poly(silhouette(sole, [0, 1]))
    fx0, fx1, fy0, fy1 = m["flat"]
    bot.ring([(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1), (fx0, fy0)], lw=W3, ls=(0, (8, 2, 1, 2)))
    bot.dim((fx0, fy1), (fx1, fy1), -8 - SCALE * (W / 2 - fy1), f"({f1(fx1 - fx0)}) flat ground face, approx.")
    bot.dim((fx1, fy0), (fx1, fy1), 8 + SCALE * (L / 2 - fx1), f"({f1(fy1 - fy0)})", horizontal=False)
    bot.leader((fx0 + 6, -fy0 - 6), -22, 0, "Datum A")
    s.view_label(95, 75 - SCALE * W / 2 - 18, "BOTTOM VIEW (ground face; dash-dot: flat area, edges blend up)")

    # SECTION A-A (XZ at Y=0)
    aa = View(s, (270, 230), [0, 2])
    for p in section_polys(sole, [0, 0, 0], [0, 1, 0], [0, 2]):
        aa.hatched(p)
    aa.line((-L / 2 - 3, 0), (L / 2 + 3, 0), lw=W2, ls=(0, (8, 2, 1, 2)))
    aa.s.ax.text(*(aa.p(L / 2, 0) + [16, 0]), "Datum A (ground)", fontsize=FS, va="center")
    zr = ray_hits(sole, [L / 2 - 1.0, 0, 40], [0, 0, -1])[:, 2].max()
    aa.dim((L / 2, 0), (L / 2, zr), 10, f"({f1(zr)})", horizontal=False)
    aa.dim((0, 0), (0, m["floor"]), -SCALE * (L / 2) - 10, f"{m['floor']:.1f} floor", horizontal=False)
    for x, t in ((-L / 2, "-X (heel)"), (L / 2, "+X (toe)")):
        aa.s.ax.text(*(aa.p(x, 0) + [0, -4]), t, fontsize=FS, ha="center", va="top")
    s.view_label(270, 230 - 8, f"SECTION A-A (plane Y=0, seen from -Y; ({f1(zr)}): rim at the toe, ref.)")

    # SECTION B-B (YZ at X=0), Y to the right
    bb = View(s, (270, 160), [1, 2])
    for p in section_polys(sole, [0, 0, 0], [1, 0, 0], [1, 2]):
        bb.hatched(p)
    bb.line((-W / 2 - 3, 0), (W / 2 + 3, 0), lw=W2, ls=(0, (8, 2, 1, 2)))
    bb.dim((-W / 2, 0), (-W / 2, m["rim"]["-Y"]), -10, f"{f1(m['rim']['-Y'])}", horizontal=False)
    bb.dim((W / 2, 0), (W / 2, m["rim"]["+Y"]), 10, f"{f1(m['rim']['+Y'])}", horizontal=False)
    bb.s.ax.text(*bb.p(0, max(m["rim"].values()) + 3), f"Rim top is {m['rim_tilt_deg']:.1f} deg to the ground face (ref.)",
                 fontsize=FS, ha="center")
    for y, t in ((-W / 2, "-Y"), (W / 2, "+Y")):
        bb.s.ax.text(*(bb.p(y, 0) + [0, -4]), t, fontsize=FS, ha="center", va="top")
    s.view_label(270, 160 - 8, "SECTION B-B (plane X=0, seen from +X)")

    s.notes(225, 128, "NOTES", [
        "The STEP file is the master geometry. This drawing gives the critical dimensions and tolerances only.",
        f"General tolerance +-{TOL['general']:.1f} mm (Yellowhammer standard vacuum casting accuracy: +-0.3 %, min +-0.3 mm).",
        f"The STEP is the finished sole: it is already {(1 - SOLE_SCALE) * 100:.1f} % smaller than the foot, so the soft sole "
        "stretches over the rigid foot and grips it. Add only your usual casting-shrinkage compensation, no other scaling.",
        f"Wall as modelled: {m['wall_upper_min']:.1f}-{m['wall_max']:.1f} mm above Z={m['wall_band_z'][1]:.0f}; {m['wall_min']:.1f}-1.5 mm in a band "
        f"at Z={m['wall_band_z'][0]:.0f}-{m['wall_band_z'][1]:.0f} all round, where the cavity chamfer meets the rounded outside (thinnest at the toe). "
        f"Wall +0.3/-0.2 mm and never under 1.0 mm. Floor {m['floor']:.1f} +-0.3 mm. No voids or bubbles.",
        "Hardness Shore 60A +-5 (ISO 48-4 / ASTM D2240 type A, at 23 C, after full post-cure). Hardness not to be changed without written agreement.",
        "Ground face (datum A): matte as-cast finish, no gloss, no release-agent film, no gate, vent, flash or parting line.",
        "Gates and vents on the rim top face (it sits under the foot edge). Trim flash flush, max 0.2 mm.",
        "Right sole = mirror image of the left sole about the XZ plane. Separate files: sole_left.step, sole_right.step.",
        "Pack left and right soles in separate labelled bags, not compressed or folded.",
    ])
    s.save()


def foot_sheet(pdf, sole, foot, m):
    s = Sheet(pdf, "Foot (rigid), LEFT shown, RIGHT is mirror image", "DB-FOOT-L / DB-FOOT-R",
              "PA12 (SLS, dyed), bright orange (e.g. RAL 2004)", 2, 2)
    f = m["foot"]
    lo, hi = f["lo"], f["hi"]
    top = View(s, (95, 205), [0, 1])
    top.poly(silhouette(foot, [0, 1]))
    for p in section_polys(foot, [0, 0, 12.0], [0, 0, 1], [0, 1]):
        top.poly(p, lw=W3, ls=(0, (3, 1.5)))
    top.cut_line((lo[0] - 4, 0), (hi[0] + 4, 0), "A")
    top.dim((lo[0], hi[1]), (hi[0], hi[1]), 14, f"{f1(f['L'])}")
    top.dim((hi[0], lo[1]), (hi[0], hi[1]), 14, f"{f1(f['W'])}", horizontal=False)
    for h in m["holes"].values():
        for d in ((-2.5, 0, 2.5, 0), (0, -2.5, 0, 2.5)):
            top.line((h["x"] + d[0], h["y"] + d[1]), (h["x"] + d[2], h["y"] + d[3]), lw=W2, ls=(0, (3, 1, 1, 1)))
        top.leader((h["x"], h["y"]), 8, -SCALE * (h["y"] - lo[1]) - 10,
                   f"Pilot hole dia {h['d_min']:.1f}, {h['depth']:.0f} deep, for M2 self-tapping screw.\nIf printed smaller, clean to dia {h['d_min']:.1f} with a drill. Do not enlarge.")
    s.view_label(95, 205 + SCALE * f["W"] / 2 + 34, "TOP VIEW (dashed: section at Z=12)")

    # SECTION A-A of foot alone
    aa = View(s, (95, 70), [0, 2])
    for p in section_polys(foot, [0, 0, 0], [0, 1, 0], [0, 2]):
        aa.hatched(p)
    aa.dim((lo[0], lo[2]), (lo[0], hi[2]), -10, f"{f1(f['H'])}", horizontal=False)
    s.view_label(95, 70 - 8, "SECTION A-A")

    # ASSEMBLY SECTION: foot in sole
    asm = View(s, (285, 215), [0, 2])
    for p in section_polys(sole, [0, 0, 0], [0, 1, 0], [0, 2]):
        asm.hatched(p)
    for p in section_polys(foot, [0, 0, 0], [0, 1, 0], [0, 2]):
        asm.poly(p)
    asm.line((-m["L"] / 2 - 3, 0), (m["L"] / 2 + 3, 0), lw=W2, ls=(0, (8, 2, 1, 2)))
    asm.leader((m["L"] / 2 - 1, 8), 16, 0, "Sole (hatched)")
    asm.leader((hi[0] - 1.0, hi[2] - 2.0), 16, 10, "Foot")
    s.ax.text(285, 215 - 14, f"The sole is {(1 - SOLE_SCALE) * 100:.1f} % smaller than the foot (stretch fit), so the outlines overlap.",
              fontsize=FS, ha="center", va="top")
    s.view_label(285, 215 - 8, "ASSEMBLY, SECTION A-A (for reference)")

    s.notes(225, 175, "NOTES", [
        "The STEP file is the master geometry. Make the part as modelled, no changes to holes, slots, lugs or ribs.",
        "General tolerance +-0.3 mm or the printing process standard, whichever is tighter.",
        f"Outer surfaces below the foot edge go into the sole cavity, which is made {(1 - SOLE_SCALE) * 100:.1f} % smaller "
        "(stretch fit). Do not add material on these surfaces (no thick coating).",
        "Finish: as printed, bead blasted or vapour smoothed. Colour: bright orange, the same shade as the soles, dyed or pigmented through.",
        "Right foot = mirror image of the left foot about the XZ plane. Separate files: foot_left.step, foot_right.step.",
        "The foot is an optional line item. Quote it separately from the soles.",
    ])
    s.save()


def main():
    global SOLE_SCALE
    SOLE_SCALE = json.loads((FEET / "parts.json").read_text())["sole_scale"]
    sole = trimesh.load(FEET / "STL/sole_left.stl")
    foot = trimesh.load(FEET / "STL/foot_left.stl")
    m = measure(sole, foot)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUT, metadata={"Title": "DuckBuddy foot sole and foot", "Author": AUTHOR, "CreationDate": None}) as pdf:
        sole_sheet(pdf, sole, foot, m)
        foot_sheet(pdf, sole, foot, m)
    summary = {k: (v if not isinstance(v, np.ndarray) else v.tolist()) for k, v in m.items() if k not in ("foot", "holes", "cav_bounds")}
    summary["foot"] = {k: float(v) if np.isscalar(v) else [float(x) for x in v] for k, v in m["foot"].items()}
    summary["holes"] = [{kk: (float(vv) if np.isscalar(vv) else [float(x) for x in vv]) for kk, vv in h.items()} for h in m["holes"].values()]
    # rounded so that mesh-boolean noise in the last digits does not change the file
    def rnd(v):
        if isinstance(v, dict):
            return {k: rnd(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [rnd(x) for x in v]
        return round(float(v), 3) if isinstance(v, (float, np.floating)) else v
    summary = rnd(summary)
    (FEET / "measurements.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    print(f"wrote {OUT}")
    print(json.dumps(summary, indent=1, default=float))


if __name__ == "__main__":
    main()
