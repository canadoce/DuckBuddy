# /// script
# dependencies = ["numpy", "scipy", "trimesh", "rtree", "manifold3d"]
# ///
"""Fit check of the open head shell against the DuckBuddy head.

Run from hardware/cad/open-head, after `uv run src/organic_shell.py`:

    uv run checks/fit_check.py [tmp/open_head_shell.stl]

It measures, in the head frame (X forward, Y left, Z up, mm):
- the shell against the parts it rests on or holds (bottom shell, face plate, HAT board,
  speaker): no overlap;
- the shell against the parts fixed in the head, the Pi with its cooling shield and Dupont
  plugs, and the parts under the HAT board: at least the clearances in head_params.py;
- the shell, the HAT and the speaker against the neck parts that move under the head
  (head roll +-25 deg in 1 deg steps, head yaw +-170 deg in 15 deg steps): at least 3 mm
  for the shell and the speaker, 1 mm for the HAT (head_params.HAT_MOVING_MARGIN).
"""

import sys
from pathlib import Path

import manifold3d as m3
import numpy as np
import trimesh
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import head_meshes as hm  # noqa: E402
import head_params as p  # noqa: E402

OVERLAP_LIMIT = 1.0  # mm3: meshing noise at a contact face
CONTACT_DEPTH = 0.15  # mm: at a contact face the smoothed mesh may sit this far into a resting part


def manifold(m):
    man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                              tri_verts=np.asarray(m.faces, np.uint32)))
    return man if man.status() == m3.Error.NoError else None


def overlap(a, b):
    """Overlap volume of two meshes (mm3), or None when one is not a closed solid."""
    ma, mb = manifold(a), manifold(b)
    if ma is None or mb is None:
        return None
    return (ma ^ mb).volume()


class Surface:
    """Dense points on a closed mesh with their outward normals: distance and inside tests."""

    def __init__(self, mesh, spacing=0.12):
        n = int(mesh.area / spacing ** 2)
        pts, faces = trimesh.sample.sample_surface_even(mesh, n)
        self.pts = np.vstack([pts, mesh.vertices])
        self.normals = np.vstack([mesh.face_normals[faces], mesh.vertex_normals])
        self.tree = cKDTree(self.pts)

    def query(self, P, **kw):
        return self.tree.query(P, workers=-1, **kw)

    def inside(self, P, depth=0.05, k=4):
        """How many points lie more than `depth` inside: the normals of the k nearest surface
        points all face away from them (one normal alone is ambiguous next to a sharp edge)."""
        d, i = self.query(P, k=k)
        side = np.einsum("ijk,ijk->ij", P[:, None, :] - self.pts[i], self.normals[i])
        return int((np.all(side < 0, axis=1) & (d[:, 0] > depth)).sum())


def main():
    shell_path = Path(sys.argv[1]) if len(sys.argv) > 1 else hm.TMP / "open_head_shell.stl"
    shell = trimesh.load(shell_path)
    if not hm.PARTS_GLB.exists():
        hm.build_parts()
    parts = hm.load_parts()
    print(f"shell {shell_path.name}: bounds {np.round(shell.bounds, 1).tolist()}, watertight {shell.is_watertight}, "
          f"volume {shell.volume / 1000:.1f} cm3, pieces {len(shell.split(only_watertight=False))}")
    fails = []
    if not shell.is_watertight:
        fails.append("shell mesh is not watertight")
    surf = Surface(shell)
    S = hm.surface_points(shell, 0.25, cap=600000)

    print("\n-- parts the shell rests on or holds: overlap must be 0")
    held = {
        "bottom_head_shell": hm.ref("bottom_head_shell_duckbuddy"),
        "face_part": hm.ref("face_part_duckbuddy"),
        "hat_board": parts["hat_board"],
        "speaker": parts["speaker"],
    }
    for name, m in held.items():
        d, _ = surf.query(hm.surface_points(m))
        v = overlap(shell, m)
        if v is None:
            n = surf.inside(hm.surface_points(m, 0.2), CONTACT_DEPTH)
            note = f"{n} of its surface points inside the shell"
            bad = n > 0
        else:
            note = f"overlap {v:.2f} mm3"
            bad = v > OVERLAP_LIMIT
        print(f"  {name:22s} gap {d.min():5.2f} mm, {note}" + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"shell overlaps {name} ({note})")

    print("\n-- clearances to fixed parts (min surface distance, mm)")
    keep = {name: (hm.ref(f), p.STATIC_MARGIN) for name, f in hm.FIXED_PARTS.items()}
    keep["roll_servo"] = (hm.ref(hm.ROLL_SERVO), p.ROLL_SERVO_MARGIN)
    keep["pi"] = (parts["pi"], p.PI_MARGIN)
    keep["pi_header_dupont_zone"] = (parts["pi_zone"], p.PI_MARGIN)
    keep["hat_parts"] = (parts["hat_parts"], p.HAT_PARTS_MARGIN)
    for name, (m, need) in keep.items():
        P = hm.surface_points(m, 0.2, cap=1500000)
        d, _ = surf.query(P)
        k = np.argmin(d)
        n = surf.inside(P)
        bad = d[k] < need or n > 0
        print(f"  {name:22s} {d[k]:5.2f} mm (need {need:.1f}) at {np.round(P[k], 1).tolist()}"
              + (f", {n} points inside the shell" if n else "") + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"shell vs {name}: {d[k]:.2f} mm")
    spk = hm.surface_points(parts["speaker"])
    for name in ("hat_parts", "pi_zone"):
        d, _ = cKDTree(hm.surface_points(parts[name])).query(spk, workers=-1)
        print(f"  speaker vs {name:11s} {d.min():5.2f} mm")

    print(f"\n-- moving neck parts (head roll +-{hm.ROLL_RANGE_DEG:.0f} deg, head yaw +-{hm.YAW_RANGE_DEG:.0f} deg)")
    above, below = hm.moving_meshes()
    A, B = hm.surface_points(above, 0.35), hm.surface_points(below, 0.35)
    hat = trimesh.util.concatenate([parts["hat_board"], parts["hat_parts"]])
    clouds = {"shell": S, "hat": hm.surface_points(hat), "speaker": spk}
    trees = {k: cKDTree(v) for k, v in clouds.items()}
    worst = {k: (np.inf, 0.0, None) for k in clouds}
    for roll, P in hm.sweep(A, B, roll_step=1.0, yaw_step=15.0):
        for k, t in trees.items():
            lo, hi = clouds[k].min(0) - 6, clouds[k].max(0) + 6
            Q = P[np.all((P > lo) & (P < hi), axis=1)]
            if not len(Q):
                continue
            d, _ = t.query(Q, distance_upper_bound=min(worst[k][0], 20.0), workers=-1)
            i = np.argmin(d)
            if d[i] < worst[k][0]:
                worst[k] = (d[i], roll, Q[i])
    for k, (d, roll, at) in worst.items():
        need = p.HAT_MOVING_MARGIN if k == "hat" else p.MOVING_MARGIN
        bad = d < need
        where = f" at roll {roll:+.0f} deg near {np.round(at, 1).tolist()}" if at is not None else ""
        print(f"  {k:8s} {d:5.2f} mm (need {need:.1f}){where}" + ("  <-- FAIL" if bad else ""))
        if bad:
            fails.append(f"{k} vs moving neck parts: {d:.2f} mm")

    print("\nRESULT:", "PASS" if not fails else "FAIL\n  " + "\n  ".join(fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
