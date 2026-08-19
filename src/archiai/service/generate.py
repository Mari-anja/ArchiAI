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
from . import images as IMG
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


def _from_region(region, opts, info, default_name):
    """A traced or drawn outline plus a use becomes a Project."""
    if region.area < 25.0:
        raise Refused("the outline encloses only %.1f m2; give an area or a "
                      "width so it can be scaled" % region.area)
    d = B.USE_DEFAULTS.get(opts.use, B.USE_DEFAULTS["office"])
    massing = M.Extrusion(region, storeys=opts.storeys,
                          floor_to_floor=opts.floor_to_floor)
    brf = L.Brief(use=opts.use, daylight_depth=d["daylight"],
                  corridor_w=d["corridor"], room_width=d["room_w"],
                  entrance_azimuth=opts.entrance_azimuth,
                  name=getattr(opts, "name", None) or default_name)
    brf.accommodation = B.ACCOMMODATION.get(opts.use, B.ACCOMMODATION["office"])
    info["subtitle"] = brf.name
    return PJ.Project(massing, brf, info)


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

    if mode == "image":
        im = req.image
        _guard(im.storeys, im.area_m2)
        try:
            region = IMG.footprint_from_upload(
                im.data, area_m2=im.area_m2, width_m=im.width_m,
                simplify=im.simplify, straighten=im.straighten)
        except ValueError as e:
            raise Refused(str(e))
        return None, _from_region(region, im, info,
                                  im.name or "Traced from an upload")

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


def render_sheets(project, out_dir, elevations, disciplines=None):
    """Produce every sheet as bytes, without touching remote storage.

    Takes the register the build returns rather than scanning the directory,
    so sheet numbers stay authoritative across every discipline prefix."""
    register = project.build(out_dir, elevations=tuple(elevations),
                             disciplines=disciplines)
    sheets = []
    for (number, title, scale, path) in register:
        with open(path, "rb") as fh:
            sheets.append({"filename": os.path.basename(path), "number": number,
                           "title": title, "scale": scale, "data": fh.read()})
    return sheets


DISCIPLINE = {"A": "architectural", "S": "structural", "E": "electrical",
              "M": "mechanical", "P": "public_health", "FS": "fire"}


def build_all(req, tmp_root):
    """Full synchronous generation. Returns (spec, project, artefacts, timing)."""
    t0 = time.time()
    spec, project = assemble(req)
    gen_id = uuid.uuid4().hex
    out_dir = os.path.join(tmp_root, gen_id)
    sheets = render_sheets(project, out_dir, req.elevations, req.disciplines)

    artefacts = []
    w, h = PAPER_MM["A1"]
    for s in sheets:
        prefix = s["number"].split("-")[0]
        artefacts.append({
            "kind": "drawing", "number": s["number"], "title": s["title"],
            "filename": s["filename"], "data": s["data"],
            "content_type": "image/svg+xml", "width": w, "height": h,
            "meta": {"sheet": s["number"], "paper": "A1", "units": "mm",
                     "scale": s["scale"],
                     "discipline": DISCIPLINE.get(prefix, "architectural")},
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
                    "filename": a["filename"], "paper": "A1",
                    "scale": a["meta"].get("scale"),
                    "discipline": a["meta"].get("discipline")}
                   for a in artefacts if a["kind"] == "drawing"]
    man = EX.manifest(project, sheet_index, spec, model)
    artefacts.append({
        "kind": "manifest", "filename": "manifest.json",
        "data": json.dumps(man, indent=2).encode("utf-8"),
        "content_type": "application/json", "width": 0, "height": 0, "meta": {},
    })
    return spec, project, artefacts, man, gen_id, int((time.time() - t0) * 1000)
