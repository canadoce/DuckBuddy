# /// script
# dependencies = ["numpy", "scipy", "trimesh", "manifold3d"]
# ///
"""Build the LiPo battery plate (src/plate.py) with the CAD server and export it.

Run from hardware/cad/lipo-plate:

    uv run src/build_plate.py

It writes tmp/lipo_plate.stl, .3mf and .step and tmp/imu_mount.stl, .3mf and .step (trunk
frame), tmp/parts.glb (the LiPo and the BNO055 stand-ins) and tmp/lipo_plate_review.glb (the
plate and the mount with the LiPo, the BNO055 and the trunk parts around them).
"""

import re
import subprocess
import sys
from pathlib import Path

import manifold3d as m3  # noqa: F401  (to_manifold, used by the fit check)
import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plate_params as p  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"
REF = ROOT / "reference"
GLTF_TO_MM = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]) @ np.diag([1000.0, 1000.0, 1000.0, 1.0])
BIG = 500.0


def cad_build():
    """Run src/plate.py with the CAD server; export the plate and the mount (STL, 3MF, STEP) and
    the stand-ins (GLB)."""
    TMP.mkdir(exist_ok=True)
    out = subprocess.run(["cad", "run", "src/plate.py"], cwd=ROOT, capture_output=True, text=True)
    ids = re.findall(r"id: ([0-9a-f-]{36})", out.stdout + out.stderr)
    if out.returncode or len(ids) != 3:
        sys.exit(out.stdout + out.stderr)
    for doc, name in zip(ids, ("lipo_plate", "imu_mount")):
        subprocess.run(["cad", "export", "--tolerance", "0.02", doc, str(TMP / f"{name}.stl"),
                        str(TMP / f"{name}.3mf")], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["cad", "export", doc, str(TMP / f"{name}.step")], cwd=ROOT, check=True, capture_output=True)
    subprocess.run(["cad", "export", ids[2], str(TMP / "parts.glb")], cwd=ROOT, check=True, capture_output=True)


def to_manifold(m):
    man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                              tri_verts=np.asarray(m.faces, np.uint32)))
    assert man.status() == m3.Error.NoError, man.status()
    return man


def to_trimesh(man):
    mesh = man.to_mesh()
    return trimesh.Trimesh(mesh.vert_properties[:, :3], mesh.tri_verts, process=False)


def box(x0, x1, y0, y1, z0, z1):
    return m3.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def load_parts():
    """The stand-ins of tmp/parts.glb in the trunk frame, by label."""
    scene = trimesh.load(TMP / "parts.glb")
    out = {}
    for node in scene.graph.nodes_geometry:
        T, g = scene.graph[node]
        m = scene.geometry[g].copy()
        m.apply_transform(GLTF_TO_MM @ T)
        out.setdefault(node.split("/")[-1].split(".")[0], []).append(m)
    return {k: trimesh.util.concatenate(v) for k, v in out.items()}


HORN_X0 = -2.5  # the passive horn on the rear hip servos' tops: X -2 to 14, Z 23 to 26 in their meshes


def without_horn(mesh):
    """A rear hip servo's mesh without its passive horn on the top (left off on this robot)."""
    c = mesh.triangles_center
    keep = ~((c[:, 2] > p.SERVO_TOP_Z - 0.1) & (c[:, 0] > HORN_X0))
    return trimesh.Trimesh(mesh.vertices, mesh.faces[keep], process=True)


def load_fixed(f):
    """A trunk part's mesh; the rear hip servos without their passive horns."""
    m = trimesh.load(f)
    return without_horn(m) if f.stem.startswith("xl330") else m


def fixed_parts():
    """The trunk parts around the plate: the print parts where there is one, else the Microduck mesh."""
    printed = {f.stem.removesuffix("_duckbuddy") for f in REF.glob("*_duckbuddy.stl")}
    for f in sorted(REF.glob("*.stl")):
        name = f.stem.removesuffix("_duckbuddy").split("__")[0]
        if name in ("power_support", "np_f970") or ("__" in f.stem and name in printed):
            continue
        yield f


def main():
    cad_build()
    for name in ("lipo_plate", "imu_mount"):
        mesh = trimesh.load(TMP / f"{name}.stl")
        pieces = mesh.split(only_watertight=False)
        print(f"{name}: bounds {np.round(mesh.bounds, 1).tolist()}, watertight {mesh.is_watertight}, "
              f"volume {mesh.volume / 1000:.2f} cm3, {len(mesh.faces)} faces, pieces {len(pieces)}")
        assert mesh.is_watertight and len(pieces) == 1
    plate = trimesh.load(TMP / "lipo_plate.stl")
    scene = trimesh.Scene()

    def add(m, name, rgb):
        m = m.copy()
        m.visual.face_colors = (*rgb, 255)
        m.apply_transform(np.linalg.inv(GLTF_TO_MM))
        scene.add_geometry(m, node_name=name)

    add(plate, "lipo_plate", (40, 40, 40))
    add(trimesh.load(TMP / "imu_mount.stl"), "imu_mount", (70, 70, 70))
    colours = {"lipo": (48, 96, 192), "bno055_pcb": (26, 26, 64), "bno055_parts": (90, 90, 90),
               "qwiic_plug": (220, 220, 220)}
    for name, m in load_parts().items():
        add(m, name, colours.get(name, (200, 200, 200)))
    for f in fixed_parts():
        rgb = (112, 150, 80) if "shell" in f.stem else (230, 120, 40) if "locker" in f.stem else (150, 150, 155)
        add(load_fixed(f), f.stem, rgb)
    scene.export(TMP / "lipo_plate_review.glb")
    print("wrote tmp/lipo_plate.*, tmp/imu_mount.* and tmp/lipo_plate_review.glb")


if __name__ == "__main__":
    main()
