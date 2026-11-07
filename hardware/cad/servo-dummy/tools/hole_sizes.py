"""Measure the dummy's screw holes from its STL: sections across each face, the inner loops'
equivalent diameters (sqrt(4 * area / pi)) and centres.

    uv run --no-project --with trimesh --with numpy --with shapely --with networkx --with rtree \
        python tools/hole_sizes.py STL/servo_dummy.stl
"""
import sys

import numpy as np
import trimesh

m = trimesh.load(sys.argv[1])
lo, hi = m.bounds
print("bounds", lo.round(2), hi.round(2))


def loops(origin, normal, label):
    sec = m.section(plane_origin=origin, plane_normal=normal)
    if sec is None:
        print(label, "no section")
        return
    planar, _ = sec.to_2D()
    holes = []
    for poly in planar.polygons_full:
        for ring in poly.interiors:
            from shapely.geometry import Polygon
            p = Polygon(ring)
            holes.append((np.sqrt(4 * p.area / np.pi), p.centroid.x, p.centroid.y))
    print(f"{label}: {len(holes)} holes")
    for d, x, y in sorted(holes):
        print(f"   d {d:.2f} mm at ({x:.2f}, {y:.2f})")


# horns: the 29 mm axis is X; sections 0.7 mm inside each horn face
loops([hi[0] - 0.7, 0, 0], [1, 0, 0], "horn +X")
loops([lo[0] + 0.7, 0, 0], [1, 0, 0], "horn -X")
# body faces, 1 mm in from the horn-side faces of the body (X = +-13), and the Z ends
loops([13.0 - 1.0, 0, 0], [1, 0, 0], "body near +X")
loops([0, 0, hi[2] - 1.0], [0, 0, 1], "body top Z")
loops([0, 0, lo[2] + 1.0], [0, 0, 1], "body bottom Z")
