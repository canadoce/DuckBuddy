# /// script
# requires-python = ">=3.11"
# dependencies = ["trimesh", "numpy", "scipy", "networkx", "rtree", "shapely", "manifold3d", "lxml", "build123d"]
# ///
"""Export the DuckBuddy feet and soles as leveled STL and STEP files for manufacturing.

Source: the foot and sole meshes inside `hardware/print/DuckBuddy.3mf` (the same shapes as the
upstream Microduck / OpenMicroDuck `foot_*.stl` and `sole_*.stl`).

What the script does:
1. Reads `foot_left` and `sole_left` from the 3MF. Bambu Studio stores each object centred on its
   own bounding box, so the sole is placed back on the foot with the offset of the upstream
   assembly STL files (SOLE_OFFSET below).
2. Fits a plane to the flat middle of the sole's ground face and rotates both parts so that plane
   is Z = 0. In the robot's zero pose the ground face is tilted about 4.9 deg; the part frame here
   removes that tilt, so drawings and moulds use the ground face as datum A.
3. Makes the right parts as mirror images of the left parts (the upstream right parts are exact
   mirrors) and checks them against the right meshes of the 3MF.
4. Scales the soles down by SOLE_SCALE about the part origin, so the sole cavity is smaller than the
   foot and the soft sole grips it (a stretch fit). The sole files are the finished part: the bureau
   adds only its usual casting-shrinkage compensation.
5. Writes STL and STEP (sewn B-rep, coplanar triangles merged into planar faces).

Part frame (left foot): origin on the ground plane at the centre of the sole outline,
+X along the foot length (the robot's forward direction in the upstream assembly), +Z up,
+Y = Z x X. Right parts: mirrored in Y.

Run from the repository root:  uv run hardware/feet/src/feet_parts.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import trimesh
from lxml import etree

HERE = Path(__file__).resolve().parent
FEET = HERE.parent
REPO = FEET.parent.parent
SRC_3MF = REPO / "hardware/print/DuckBuddy.3mf"

# Sole bounding-box centre minus foot bounding-box centre, in the upstream assembly frame
# (upstream foot_left.stl / sole_left.stl, which are identical in shape to the 3MF meshes). It equals the
# difference of the left parts' source_offset in the 3MF's model_settings.config. The 3MF's right parts sit
# slightly differently, so the right side is made by mirroring the left assembly (line-to-line fit).
SOLE_OFFSET = np.array([0.0, -3.999173, 0.118861])

# Finished sole = modelled sole scaled by this factor about the part origin (centre of the ground face).
# 0.8 % smaller makes the cavity 0.4 mm shorter and 0.3 mm narrower than the foot. With the bureau's
# +-0.3 mm accuracy the cavity at worst comes out the same width as the foot (never looser).
SOLE_SCALE = 0.992

# Upstream assembly frame -> part frame axes, before leveling: X = x, Y = -z, Z = y.
ASM_TO_PART = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])


def read_3mf_meshes(path: Path) -> dict[str, trimesh.Trimesh]:
    """Return {object name: mesh in the object's own frame} for the objects of a Bambu 3MF."""
    z = zipfile.ZipFile(path)
    settings = etree.fromstring(z.read("Metadata/model_settings.config"))
    names = {o.get("id"): o.find("metadata[@key='name']").get("value") for o in settings.findall("object")}
    root = etree.fromstring(z.read("3D/3dmodel.model"))
    ns = {"m": root.nsmap[None]}
    p_ns = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
    out = {}
    for obj in root.findall(".//m:resources/m:object", ns):
        name = names.get(obj.get("id"))
        if name is None:
            continue
        meshes = []
        for comp in obj.findall("m:components/m:component", ns):
            sub = etree.fromstring(z.read(comp.get(p_ns + "path").lstrip("/")))
            sns = {"m": sub.nsmap[None]}
            t = np.array([float(v) for v in comp.get("transform").split()])
            T = np.eye(4)
            T[:3, :3] = t[:9].reshape(3, 3).T  # 3MF matrices are row-vector form
            T[:3, 3] = t[9:]
            for me in sub.findall(".//m:object/m:mesh", sns):
                v = np.array([[float(x.get(k)) for k in "xyz"] for x in me.find("m:vertices", sns)])
                f = np.array([[int(x.get(k)) for k in ("v1", "v2", "v3")] for x in me.find("m:triangles", sns)])
                m = trimesh.Trimesh(v, f, process=True)
                m.apply_transform(T)
                meshes.append(m)
        if meshes:
            out[name.removesuffix(".stl")] = trimesh.util.concatenate(meshes)
    return out


def ground_plane(sole: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    """Fit a plane to the flat middle of the ground face. Returns (point, unit normal pointing up)."""
    lo, hi = sole.bounds
    c = (lo + hi) / 2
    pts = []
    for x in np.linspace(c[0] - 10, c[0] + 10, 21):
        for y in np.linspace(c[1] - 12, c[1] + 12, 25):
            loc, _, _ = sole.ray.intersects_location([[x, y, lo[2] - 20]], [[0, 0, 1]], multiple_hits=False)
            if len(loc):
                pts.append(loc[0])
    pts = np.array(pts)
    A = np.c_[pts[:, 0], pts[:, 1], np.ones(len(pts))]
    (a, b, d), *_ = np.linalg.lstsq(A, pts[:, 2], rcond=None)
    resid = np.abs(pts[:, 2] - A @ [a, b, d]).max()
    if resid > 0.1:
        sys.exit(f"ground face is not flat in the middle (residual {resid:.3f} mm); check the source mesh")
    n = np.array([-a, -b, 1.0])
    return np.array([c[0], c[1], a * c[0] + b * c[1] + d]), n / np.linalg.norm(n)


def rotation_to_z(n: np.ndarray) -> np.ndarray:
    """Rotation about the X axis only that turns n into +Z (the tilt is about the foot's long axis)."""
    n = n / np.linalg.norm(n)
    assert abs(n[0]) < np.sin(np.radians(0.2)), f"ground normal leans along X by {np.degrees(np.arcsin(n[0])):.2f} deg"
    ang = np.arctan2(n[1], n[2])
    c, s = np.cos(ang), np.sin(ang)
    R = np.eye(4)
    R[1:3, 1:3] = [[c, -s], [s, c]]
    return R


def mesh_to_step(mesh: trimesh.Trimesh, path: Path, name: str) -> int:
    """Sew the triangles into a closed solid, merge coplanar faces and write STEP. Returns face count."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.gp import gp_Pnt
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.Interface import Interface_Static
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    sew = BRepBuilderAPI_Sewing(1e-4)
    V = mesh.vertices
    for tri in mesh.faces:
        poly = BRepBuilderAPI_MakePolygon(*(gp_Pnt(*V[i]) for i in tri), True)
        sew.Add(BRepBuilderAPI_MakeFace(poly.Wire(), True).Face())
    sew.Perform()
    exp = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
    shells = []
    while exp.More():
        shells.append(TopoDS.Shell(exp.Current()))
        exp.Next()
    if len(shells) != 1:
        sys.exit(f"{name}: sewing gave {len(shells)} shells, expected 1")
    solid = BRepBuilderAPI_MakeSolid(shells[0]).Solid()
    # Merge coplanar triangles into planar faces. A small tolerance merges more (STL vertices are
    # float32), but on some meshes it gives an invalid solid; then use the exact merge.
    shape = None
    for tol in (2e-3, None):
        unify = ShapeUpgrade_UnifySameDomain(solid, True, True, True)
        if tol is not None:
            unify.SetLinearTolerance(tol)
            unify.SetAngularTolerance(np.radians(0.05))
        unify.Build()
        if BRepCheck_Analyzer(unify.Shape()).IsValid():
            shape = unify.Shape()
            break
    if shape is None:
        sys.exit(f"{name}: STEP solid is not valid")
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    vol = props.Mass()  # signed: a negative volume means an inside-out solid
    if abs(vol - mesh.volume) > 1e-3 * mesh.volume:
        sys.exit(f"{name}: STEP volume {vol:.2f} differs from mesh volume {mesh.volume:.2f}")
    nf = 0
    e = TopExp_Explorer(shape, TopAbs_FACE)
    while e.More():
        nf += 1
        e.Next()
    w = STEPControl_Writer()  # create first: the first writer resets these settings to defaults
    Interface_Static.SetCVal_s("write.step.schema", "AP214")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 0)  # no pcurves: much smaller file, same solid
    Interface_Static.SetCVal_s("write.step.product.name", name)
    w.Transfer(shape, STEPControl_AsIs)
    if w.Write(str(path)) != IFSelect_RetDone:
        sys.exit(f"{name}: STEP write failed")
    return nf


def strip_step_timestamp(path: Path) -> None:
    """Make STEP output reproducible: blank the FILE_NAME time stamp."""
    lines = path.read_text().splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("FILE_NAME("):
            parts = ln.split("'")
            if len(parts) > 3:
                parts[3] = "2026-11-07T00:00:00"
            lines[i] = "'".join(parts)
            break
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    meshes = read_3mf_meshes(SRC_3MF)
    foot = meshes["foot_left"].copy()
    sole = meshes["sole_left"].copy()
    # Put the sole back on the foot (assembly frame offsets), then go to the part axes.
    sole.apply_translation(foot.bounds.mean(0) + SOLE_OFFSET - sole.bounds.mean(0))
    M = np.eye(4)
    M[:3, :3] = ASM_TO_PART
    for m in (foot, sole):
        m.apply_transform(M)
    p, n = ground_plane(sole)
    tilt = np.degrees(np.arctan2(n[1], n[2]))
    R = rotation_to_z(n)
    for m in (foot, sole):
        m.apply_transform(R)
    lo, hi = sole.bounds
    shift = -np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0.0])
    gp = (R @ np.r_[p, 1])[:3]
    shift[2] = -gp[2]
    for m in (foot, sole):
        m.apply_translation(shift)

    fit = foot.intersection(sole)
    overlap = 0.0 if fit.is_empty else fit.volume

    mirror = np.diag([1.0, -1.0, 1.0, 1.0])
    parts = {"foot_left": foot, "sole_left": sole}
    for k in ("foot", "sole"):
        r = parts[f"{k}_left"].copy()
        r.apply_transform(mirror)  # trimesh flips the winding itself for a reflection
        parts[f"{k}_right"] = r

    # Check the mirrored right parts against the right meshes of the 3MF (rigid fit, no scale).
    checks = {}
    for k in ("foot_right", "sole_right"):
        src = meshes[k]
        tgt = parts[k]
        T0 = np.eye(4)
        T0[:3, 3] = tgt.bounds.mean(0) - src.bounds.mean(0)
        best = None
        # Try the 3MF object's frame turned into the part frame both ways, then refine with ICP.
        for pre in (M, np.eye(4)):
            s = src.copy()
            s.apply_transform(pre)
            s.apply_translation(tgt.bounds.mean(0) - s.bounds.mean(0))
            T, _, cost = trimesh.registration.icp(s.vertices, tgt, max_iterations=60, scale=False, reflection=False)
            if best is None or cost < best[1]:
                best = (s, cost, T)
        s, _, T = best
        s.apply_transform(T)
        d = trimesh.proximity.closest_point(tgt, s.vertices)[1]  # point-to-surface distance
        checks[k] = {"max_dev_mm": round(float(d.max()), 4), "volume_3mf_mm3": round(float(src.volume), 2), "volume_out_mm3": round(float(tgt.volume), 2)}
        if d.max() > 0.05:
            sys.exit(f"{k}: mirrored left part differs from the 3MF right part by {d.max():.3f} mm")

    # Finished soles: scaled down about the part origin (ground stays at Z = 0).
    for k in ("sole_left", "sole_right"):
        parts[k].apply_scale(SOLE_SCALE)
    fit = parts["foot_left"].intersection(parts["sole_left"])
    interference = 0.0 if fit.is_empty else fit.volume

    (FEET / "STL").mkdir(exist_ok=True)
    (FEET / "STEP").mkdir(exist_ok=True)
    report = {"source": "hardware/print/DuckBuddy.3mf", "ground_tilt_removed_deg": round(float(tilt), 3),
              "foot_sole_overlap_mm3": round(float(overlap), 3), "sole_scale": SOLE_SCALE,
              "foot_sole_interference_after_scale_mm3": round(float(interference), 1),
              "right_part_checks": checks, "parts": {}}
    for name, m in parts.items():
        if not m.is_watertight or m.volume <= 0:
            sys.exit(f"{name}: mesh is not a closed solid")
        stl = FEET / "STL" / f"{name}.stl"
        m.export(stl)
        step = FEET / "STEP" / f"{name}.step"
        nf = mesh_to_step(m, step, name)
        strip_step_timestamp(step)
        lo, hi = m.bounds
        report["parts"][name] = {
            "bbox_mm": [round(float(v), 2) for v in (hi - lo)],
            "bbox_min_mm": [round(float(v), 2) for v in lo],
            "volume_cm3": round(float(m.volume) / 1000, 3),
            "surface_cm2": round(float(m.area) / 100, 2),
            "step_faces": nf,
            "stl_sha256": hashlib.sha256(stl.read_bytes()).hexdigest(),
            "step_sha256": hashlib.sha256(step.read_bytes()).hexdigest(),
        }
        print(f"{name}: bbox {report['parts'][name]['bbox_mm']} mm, {report['parts'][name]['volume_cm3']} cm3, STEP faces {nf}")
    (FEET / "parts.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"ground tilt removed: {tilt:.3f} deg; foot/sole overlap as modelled {overlap:.3f} mm3, "
          f"after scaling the sole to {SOLE_SCALE}: {interference:.1f} mm3")
    print("right part checks:", checks)


if __name__ == "__main__":
    main()
