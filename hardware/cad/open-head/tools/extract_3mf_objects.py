# /// script
# dependencies = ["numpy", "trimesh"]
# ///
"""Write named objects of a Bambu Studio project (.3mf) as STL files, in the object's own frame.

Usage (from hardware/cad/open-head):
    uv run tools/extract_3mf_objects.py ../../print/DuckBuddy.3mf OUT_DIR \
        bottom_head_shell top_head_shell:1 face_part

Each NAME matches one object whose name contains it, written to OUT_DIR/NAME.stl.
NAME:N keeps only the first N parts of the object (the top head shell's later parts
are negative cutters, not geometry).
"""

import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PATH = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path"
NS = {"m": CORE}


def transform(text):
    v = [float(x) for x in (text or "1 0 0 0 1 0 0 0 1 0 0 0").split()]
    M = np.eye(4)
    M[:3, :3] = np.array(v[:9]).reshape(3, 3).T
    M[:3, 3] = v[9:]
    return M


def main(src, out, *wanted):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(src)
    cfg = ET.fromstring(z.read("Metadata/model_settings.config"))
    names = {}
    for o in cfg.findall("object"):
        for md in o.findall("metadata"):
            if md.get("key") == "name":
                names[o.get("id")] = md.get("value")
                break
    root = ET.fromstring(z.read("3D/3dmodel.model"))
    parts = {}

    def part(path, oid):
        if path not in parts:
            r = ET.fromstring(z.read(path.lstrip("/")))
            parts[path] = {o.get("id"): o for o in r.iter(f"{{{CORE}}}object")}
        mesh = parts[path][oid].find("m:mesh", NS)
        V = np.array([[float(v.get(a)) for a in "xyz"] for v in mesh.find("m:vertices", NS)])
        F = np.array([[int(t.get(a)) for a in ("v1", "v2", "v3")] for t in mesh.find("m:triangles", NS)])
        return V, F

    for spec in wanted:
        word, _, n = spec.partition(":")
        objs = [o for o in root.find("m:resources", NS) if word in names.get(o.get("id"), "")]
        if len(objs) != 1:
            sys.exit(f"{word}: {len(objs)} objects match, expected 1")
        comps = list(objs[0].find("m:components", NS))
        if n:
            comps = comps[:int(n)]
        meshes = []
        for c in comps:
            V, F = part(c.get(PATH), c.get("objectid"))
            Vh = np.c_[V, np.ones(len(V))] @ transform(c.get("transform")).T
            meshes.append(trimesh.Trimesh(Vh[:, :3], F, process=False))
        m = trimesh.util.concatenate(meshes)
        m.export(out / f"{word}.stl")
        print(word, "parts", len(meshes), "extents", np.round(m.extents, 2).tolist())


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
