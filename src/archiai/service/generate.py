"""Turn a request into a project, sheets, a mesh and a manifest."""

import io
import os
import json
import time
import uuid

from ..engine import brief as B
from ..engine import geom2d as G
from ..engine import layout as L
from ..engine import massing as M
from ..engine import project as PJ
from ..engine import export as EX
from ..engine import draw
from .config import settings

PAPER_MM = {"A1": (841, 594), "A2": (594, 420), "A3": (420, 297)}


class Refused(ValueError):
    """The request is valid JSON but not a buildable brief."""


def _guard(storeys, area):
    if storeys > settings.max_storeys:
        raise Refused("storeys above the configured limit of %d" % settings.max_storeys)
    if area and area > settings.max_area:
        raise Refused("floor area above the configured limit of %.0f m2" % settings.max_area)
    # One plan is drawn per storey, so the work is storeys x plate perimeter.
    # Cap the product rather than each factor, or a 60-storey megablock ties up
    # a worker for minutes while passing both limits individually.
    if area and storeys * area > settings.max_area * 12:
        raise Refused("storeys x floor area is too large for a single request; "
                      "split the scheme or raise ARCHIAI_MAX_AREA_M2")


def assemble(req):
    """Request -> (spec | None, Project). Pure; no file or network access."""
    mode = req.mode()
    info = {"number": req.number or "AAI-%s" % uuid.uuid4().hex[:6].upper()}
    if req.client:
        info["client"] = req.client

    if mode == "brief":
        spec = B.parse(req.brief)
        _guard(spec.storeys, spec.area)
        massing, brf = B.build(spec)
        info["subtitle"] = spec.name
        return spec, PJ.Project(massing, brf, info)

    if mode == "spec":
        s = req.spec
        spec = B.Spec(use=s.use, shape=s.shape, storeys=s.storeys, area=s.area_m2,
                      entrance=s.entrance_azimuth, name=s.name,
                      floor_to_floor=s.floor_to_floor)
        if spec.floor_to_floor is None:
            spec.floor_to_floor = B.USE_DEFAULTS.get(spec.use, B.USE_DEFAULTS["office"])["f2f"]
        _guard(spec.storeys, spec.area)
        massing, brf = B.build(spec)
        info["subtitle"] = spec.name
        return spec, PJ.Project(massing, brf, info)

    f = req.footprint
    _guard(f.storeys, None)
    outer = [(float(x), float(y)) for (x, y) in f.outer]
    holes = [[(float(x), float(y)) for (x, y) in h] for h in f.holes]
    region = G.Region(outer, holes)
    if region.area < 25.0:
        raise Refused("footprint encloses only %.1f m2; expected metres, not "
                      "millimetres or screen pixels" % region.area)
    d = B.USE_DEFAULTS.get(f.use, B.USE_DEFAULTS["office"])
    massing = M.Extrusion(region, storeys=f.storeys,
                          floor_to_floor=f.floor_to_floor)
    brf = L.Brief(use=f.use, daylight_depth=d["daylight"], corridor_w=d["corridor"],
                  room_width=d["room_w"], entrance_azimuth=f.entrance_azimuth,
                  name=f.name or "Drawn footprint")
    brf.accommodation = B.ACCOMMODATION.get(f.use, B.ACCOMMODATION["office"])
    info["subtitle"] = brf.name
    return None, PJ.Project(massing, brf, info)


def render_sheets(project, out_dir, elevations):
    """Produce every sheet as bytes, without touching remote storage."""
    project.build(out_dir, elevations=tuple(elevations))
    sheets = []
    d = os.path.join(out_dir, "drawings")
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".svg"):
            continue
        number = fn.rsplit("-A-", 1)[-1].replace(".svg", "")
        with open(os.path.join(d, fn), "rb") as fh:
            data = fh.read()
        sheets.append({"filename": fn, "number": "A-%s" % number, "data": data})
    return sheets


SHEET_TITLES = {
    "100": "Floor Plan", "200": "Elevations", "201": "Elevations", "300": "Sections",
}


def describe_sheet(number, project):
    n = number.replace("A-", "")
    if n.startswith("1"):
        i = int(n[1:])
        lv = project.massing.levels[i] if i < len(project.massing.levels) else None
        return ("%s — Floor Plan" % (lv.name if lv else "Level"), "plan")
    return (SHEET_TITLES.get(n, "Drawing"), "elevation" if n.startswith("2") else "section")


def build_all(req, tmp_root):
    """Full synchronous generation. Returns (spec, project, artefacts, timing)."""
    t0 = time.time()
    spec, project = assemble(req)
    gen_id = uuid.uuid4().hex
    out_dir = os.path.join(tmp_root, gen_id)
    sheets = render_sheets(project, out_dir, req.elevations)

    artefacts = []
    w, h = PAPER_MM["A1"]
    for s in sheets:
        title, kind = describe_sheet(s["number"], project)
        artefacts.append({
            "kind": "drawing", "number": s["number"], "title": title,
            "filename": s["filename"], "data": s["data"],
            "content_type": "image/svg+xml", "width": w, "height": h,
            "meta": {"sheet": s["number"], "sheet_kind": kind, "paper": "A1",
                     "units": "mm"},
        })

    model = None
    if req.include_model:
        obj_path = os.path.join(out_dir, "model", "building.obj")
        _, nv, nf = EX.write_obj(project.massing.mesh(), obj_path,
                                 project.info.get("name", "building"), "building.mtl")
        mtl_path = EX.write_mtl(os.path.join(out_dir, "model", "building.mtl"))
        for path, ct in ((obj_path, "model/obj"), (mtl_path, "model/mtl")):
            with open(path, "rb") as fh:
                artefacts.append({
                    "kind": "model", "filename": os.path.basename(path),
                    "data": fh.read(), "content_type": ct, "width": 0, "height": 0,
                    "meta": {"format": os.path.splitext(path)[1][1:],
                             "vertices": nv, "faces": nf, "units": "m", "up": "z"},
                })
        model = {"format": "obj", "vertices": nv, "faces": nf,
                 "filename": "building.obj"}

    sheet_index = [{"number": a["number"], "title": a["title"],
                    "filename": a["filename"], "paper": "A1"}
                   for a in artefacts if a["kind"] == "drawing"]
    man = EX.manifest(project, sheet_index, spec, model)
    artefacts.append({
        "kind": "manifest", "filename": "manifest.json",
        "data": json.dumps(man, indent=2).encode("utf-8"),
        "content_type": "application/json", "width": 0, "height": 0, "meta": {},
    })
    return spec, project, artefacts, man, gen_id, int((time.time() - t0) * 1000)
