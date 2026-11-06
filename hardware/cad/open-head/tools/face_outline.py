# /// script
# dependencies = ["numpy", "trimesh", "shapely", "networkx", "scipy", "rtree"]
# ///
"""Write the face plate's outline, as (y, z) points, from a section of the aligned face part.

Usage (from hardware/cad/open-head):
    uv run tools/face_outline.py reference/face_part_duckbuddy.stl reference/face_outline.json

The section is the plane X = 72.8 (inside the plate, which spans X 72.2..73.4 at its
edge and has its back features from X 61). The collar of the open head shell is
built from this outline.
"""

import json
import sys

import numpy as np
import trimesh
from shapely.geometry import Polygon

SECTION_X = 72.8


def main(src, out):
    face = trimesh.load(src)
    loops = face.section([1, 0, 0], [SECTION_X, 0, 0]).discrete
    big = max(loops, key=lambda a: Polygon(a[:, 1:3]).area)
    poly = Polygon(big[:, 1:3]).simplify(0.2)
    pts = [list(map(float, p)) for p in poly.exterior.coords]
    with open(out, "w") as f:
        json.dump(pts, f)
    a = np.array(pts)
    print(f"{len(pts)} points, y {a[:, 0].min():.1f}..{a[:, 0].max():.1f}, z {a[:, 1].min():.1f}..{a[:, 1].max():.1f}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
