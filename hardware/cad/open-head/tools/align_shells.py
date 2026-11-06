# /// script
# dependencies = ["numpy", "scipy", "trimesh", "rtree"]
# ///
"""Place the DuckBuddy head parts in the head frame by fitting them to the Microduck meshes.

Usage (from hardware/cad/open-head):
    uv run tools/align_shells.py EXTRACTED_DIR reference/microduck reference

EXTRACTED_DIR holds bottom_head_shell.stl, top_head_shell.stl and face_part.stl from
extract_3mf_objects.py. Each one is fitted (ICP from all 24 axis rotations) to the
Microduck mesh of the same name and written as reference/<name>_duckbuddy.stl.
Takes several minutes.
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

PARTS = ["bottom_head_shell", "top_head_shell", "face_part"]


def rotations():
    for p in itertools.permutations(range(3)):
        for s in itertools.product([1, -1], repeat=3):
            R = np.zeros((3, 3))
            for i in range(3):
                R[i, p[i]] = s[i]
            if np.linalg.det(R) > 0:
                yield R


def main(extracted, microduck, out):
    extracted, microduck, out = Path(extracted), Path(microduck), Path(out)
    for name in PARTS:
        a = trimesh.load(extracted / f"{name}.stl")
        b = trimesh.util.concatenate([trimesh.load(f) for f in sorted(microduck.glob(f"*__{name}__*.stl"))])
        pb = b.sample(30000)
        pa = a.sample(30000)
        best = None
        for R in rotations():
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = pb.mean(0) - (pa @ R.T).mean(0)
            M, _, cost = trimesh.registration.icp(pa, pb, initial=T, max_iterations=60, reflection=False, scale=False)
            if best is None or cost < best[1]:
                best = (M, cost)
        M, cost = best
        d, _ = cKDTree(pb).query(trimesh.transform_points(pa, M))
        a.apply_transform(M)
        a.export(out / f"{name}_duckbuddy.stl")
        print(f"{name}: icp cost {cost:.3f}, median {np.median(d):.3f} mm, p95 {np.percentile(d, 95):.3f} mm,",
              "bounds", np.round(a.bounds, 1).tolist())


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
