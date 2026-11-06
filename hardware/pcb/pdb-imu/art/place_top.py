# /// script
# dependencies = ["shapely"]
# ///
"""Place the top-side silkscreen items of art/top_art.ts, each at the clear spot nearest to its target.

Clear means: at least CU from exposed copper (pads, plated holes, holes), outside part bodies
(the box around each part's pads, and the connector outlines), SK from footprint silkscreen,
GAP from the items already placed, and EDGE inside the board. Vias are covered by solder mask
and traces are under it, so silkscreen may cross them.

Run it on a build, after any change to the layout or to the art (from hardware/pcb/pdb-imu):
    bunx tsci build index.circuit.tsx
    uv run art/place_top.py dist/index/circuit.json art/top_art.ts
and paste the printed rows into TOP_ART in index.circuit.tsx. A row printed as a comment found no
clear spot within its distance: move its target in T below, or give it a larger distance.
Targets are in board coordinates (the layout group's frame: circuit y - 1.5).
"""
import json, sys, re, math, collections
from shapely.geometry import Point, LineString, Polygon, box
from shapely import affinity
from shapely.ops import unary_union

DY = 1.5; CU = 0.2; SK = 0.12; GAP = 0.25; EDGE = 0.4
d = json.load(open(sys.argv[1]))
size = {m[0]: (float(m[1]), float(m[2])) for m in re.findall(r'"([^"]+)": \{ url: "[^"]*", width: ([\d.]+), height: ([\d.]+) \}', open(sys.argv[2]).read())}

# (art key, target x, target y, max distance), placed in this order. "servo#J4" is the "servo" icon next to J4.
T = [
    ("DIO", 15.69, -5.55, 0.6), ("CLK", 18.23, -5.55, 0.6), ("GND", 20.77, -5.55, 0.6), ("3V3", 23.31, -5.55, 0.6),
    ("title", -16.05, 7.2, 2), ("J4", -23.9, 5.3, 2), ("J6", 23.9, 5.3, 2), ("J5", 0, 6.9, 2), ("J2", 19.5, -9.0, 2.5),
    ("battery", 3.25, -15.3, 2.5), ("imu", -1.6, 3.6, 4), ("servo#J4", -24.4, 7.6, 3), ("servo#J6", 24.4, 7.6, 4),
    ("amps", 1.4, -12.0, 4), ("volts", 1.6, -9.0, 3),
    ("ON", -17.0, -15.3, 3), ("2S", -19.0, -12.0, 3),
    ("U1", 11.5, 5.8, 3), ("U2", 3, 4.4, 3), ("U3", 1.2, -0.4, 2.5), ("U4", 15.2, -2.0, 2.5), ("U5", -3.7, -15.4, 2.5),
    ("U6", -15.5, -2.6, 2.5), ("Q1", 7, -14.3, 3), ("Q2", 7, -4.6, 3), ("SW1", -14.1, -9.3, 3),
    ("F1", -14.5, -0.8, 2.5), ("F2", -4.5, 4.3, 2.5), ("F3", -11.6, 7.9, 2.5), ("RS1", -0.5, -8.6, 3.5),
    ("D1", -10.4, -15.6, 2.5), ("LED1", -17.3, 10.9, 2.5), ("LED2", 19.0, 11.9, 2.5), ("LED3", -6.9, 10.6, 2.5),
    ("LED4", 17, 5.4, 2.5), ("JP2", -19.7, -11.3, 3), ("J3", -20.9, -16.4, 3), ("J7", 19.5, -12.4, 3),
    ("TP1 VB", -11.0, -8.2, 5), ("TP2 3V3", 16.3, -10.6, 3), ("TP3 G", 21.8, -12.4, 3), ("TP4 D", 21.3, -2.3, 2.5),
]
NOBODY = {"J1", "J3", "J7", "JP2", "TP1", "TP2", "TP3", "TP4"}  # bare pads, nothing fitted on top of them

comp = {e["source_component_id"]: e["name"] for e in d if e["type"] == "source_component"}
pname = {e["pcb_component_id"]: comp.get(e["source_component_id"]) for e in d if e["type"] == "pcb_component"}
board = next(e for e in d if e["type"] == "pcb_board")
bx, by, bw, bh = board["center"]["x"], board["center"]["y"], board["width"], board["height"]
inside = (Polygon([(p["x"], p["y"]) for p in board["outline"]]) if board.get("outline")
          else box(bx - bw / 2, by - bh / 2, bx + bw / 2, by + bh / 2)).buffer(-EDGE)

def padg(e):
    if e.get("shape") == "circle":
        return Point(e["x"], e["y"]).buffer(e["radius"])
    g = box(e["x"] - e["width"] / 2, e["y"] - e["height"] / 2, e["x"] + e["width"] / 2, e["y"] + e["height"] / 2)
    return affinity.rotate(g, e.get("ccw_rotation") or 0, origin=(e["x"], e["y"]))

copper, bodies, silk = [], [], []
pads = collections.defaultdict(list)
for e in d:
    t = e["type"]
    if t == "pcb_smtpad" and e["layer"] == "top":
        g = padg(e); copper.append(g); pads[pname.get(e.get("pcb_component_id"))].append(g)
    elif t == "pcb_plated_hole":
        r = (e.get("outer_diameter") or max(e.get("outer_width", 0), e.get("outer_height", 0), e.get("rect_pad_width", 0))) / 2
        g = Point(e["x"], e["y"]).buffer(r); copper.append(g); pads[pname.get(e.get("pcb_component_id"))].append(g)
    elif t == "pcb_hole":
        # Mounting holes: keep clear of the M2 screw head (4 mm across); small holes get 0.3 mm.
        hd = e.get("hole_diameter") or 2.2
        copper.append(Point(e["x"], e["y"]).buffer(2.0 if hd >= 2 else hd / 2 + 0.3))
    elif t == "pcb_silkscreen_path" and e["layer"] == "top" and e.get("pcb_component_id"):
        # Board-level paths come from the art placed by an earlier run, so they are skipped.

        silk.append(LineString([(p["x"], p["y"]) for p in e["route"]]).buffer(e.get("stroke_width", 0.1) / 2))
    elif t == "pcb_silkscreen_rect" and e["layer"] == "top":
        c = e["center"]; bodies.append(box(c["x"] - e["width"] / 2, c["y"] - e["height"] / 2, c["x"] + e["width"] / 2, c["y"] + e["height"] / 2))
    elif t == "pcb_silkscreen_circle" and e["layer"] == "top":
        silk.append(Point(e["center"]["x"], e["center"]["y"]).buffer(e["radius"] + 0.05))
for n, v in pads.items():
    if n in NOBODY or len(v) < 2:
        continue
    env = unary_union(v).envelope
    if n == "J2":  # 2.54 mm header body
        env = env.buffer(1.27 - 0.75, join_style=2)
    bodies.append(env.buffer(-0.05))
copper = unary_union(copper).buffer(CU)
bodies = unary_union(bodies).buffer(0.1)
silk = unary_union(silk).buffer(SK)
block = unary_union([copper, bodies, silk])

placed, out = [], []
for key, tx, ty, rmax in T:
    art = key.split("#")[0]
    w, h = size[art]
    ty += DY
    best = None
    n = int(rmax / 0.05)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            r = math.hypot(i, j) * 0.05
            if r > rmax or (best and r >= best[0]):
                continue
            x, y = tx + i * 0.05, ty + j * 0.05
            g = box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            if not inside.contains(g) or g.intersects(block) or any(g.distance(p) < GAP for p in placed):
                continue
            best = (r, x, y, g)
    if best:
        r, x, y, g = best; placed.append(g)
        out.append(f'  ["{key}", {x:.2f}, {y - DY:.2f}],' + (f"  // moved {r:.2f} mm" if r > 0.01 else ""))
    else:
        out.append(f'  // ["{key}", {tx:.2f}, {ty - DY:.2f}],  NO CLEAR SPOT within {rmax} mm')
print("\n".join(out))
