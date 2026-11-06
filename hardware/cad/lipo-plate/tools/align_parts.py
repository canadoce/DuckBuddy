# /// script
# dependencies = ["numpy", "scipy", "trimesh", "rtree"]
# ///
"""Place DuckBuddy print parts in the trunk frame by fitting them to the Microduck meshes.

Usage (from hardware/cad/lipo-plate):
    uv run ../open-head/tools/extract_3mf_objects.py ../../print/DuckBuddy.3mf tmp/extracted \
        power_support left_shell right_shell banana_pcb_locker trunk_base.stl
    uv run tools/align_parts.py tmp/extracted reference

Each tmp/extracted/<name>.stl is fitted (ICP from all 24 axis rotations) to
reference/<name>__<geom id>.stl from tools/trunk_meshes.py, and written as
reference/<name>_duckbuddy.stl. The Microduck model's meshes are simplified copies (its
power_support is not even closed), so the fit check and the build use the print parts.
"""

import itertools
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree


def rotations():
    for p in itertools.permutations(range(3)):
        for s in itertools.product([1, -1], repeat=3):
            R = np.zeros((3, 3))
            for i in range(3):
                R[i, p[i]] = s[i]
            if np.linalg.det(R) > 0:
                yield R


def main(extracted, ref):
    extracted, ref = Path(extracted), Path(ref)
    for f in sorted(extracted.glob("*.stl")):
        name = f.stem.removesuffix(".stl")
        targets = sorted(ref.glob(f"{name}__*.stl"))
        if not targets:
            print(f"{name}: no Microduck mesh, skipped")
            continue
        a = trimesh.load(f)
        b = trimesh.load(targets[0])
        pa, pb = a.sample(30000), b.sample(30000)
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
        a.export(ref / f"{name}_duckbuddy.stl")
        print(f"{name}: median {np.median(d):.3f} mm, p95 {np.percentile(d, 95):.3f} mm, bounds",
              np.round(a.bounds, 1).tolist(), "watertight", a.is_watertight)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
