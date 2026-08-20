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
from ..engine import revise as RV
from ..engine import pdf as PDF
from ..engine import webpage as WEB
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


def num_of(project):
    return project.info.get("number", "project")


def _with_source(project, source):
    project.source = source
    return project


def _from_region(region, opts, info, default_name, traced=False):
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
    return _with_source(
        PJ.Project(massing, brf, info),
        RV.source_from_footprint(region, opts.storeys, opts.floor_to_floor,
                                 opts.use, opts.entrance_azimuth, brf.name,
                                 traced=traced))


def assemble(req):
    """Request -> (spec | None, Project). Pure; no file or network access."""
    mode = req.mode()
    info = {"number": getattr(req, "number", None)
            or "AAI-%s" % uuid.uuid4().hex[:6].upper()}
    if getattr(req, "client", None):
        info["client"] = req.client

    if mode == "brief":
        spec = B.parse(req.brief)
        _guard(spec.storeys, spec.area)
        massing, brf = B.build(spec)
        info["subtitle"] = spec.name
        return spec, _with_source(PJ.Project(massing, brf, info),
                                  RV.source_from_spec(spec, req.brief))

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
        return spec, _with_source(PJ.Project(massing, brf, info),
                                  RV.source_from_spec(spec))

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
                                  im.name or "Traced from an upload",
                                  traced=True)

    f = req.footprint
    _guard(f.storeys, None)
    outer = [(float(x), float(y)) for (x, y) in f.outer]
    holes = [[(float(x), float(y)) for (x, y) in h] for h in f.holes]
    region = G.Region(outer, holes)
    if region.area < 25.0:
        raise Refused("footprint encloses only %.1f m2; expected metres, not "
                      "millimetres or screen pixels" % region.area)
    d = B.USE_DEFAULTS.get(f.use, B.USE_DEFAULTS["office"])
    return None, _from_region(region, f, info, f.name or "Drawn footprint")


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
                           "title": title, "scale": scale, "path": path,
                           "data": fh.read()})
    return sheets


MAX_VIEW_PIXELS = 4000 * 4000


def render_views(project, views):
    """Every requested view, as an SVG artefact with what it shows recorded."""
    from ..engine import view as VW
    out = []
    for i, v in enumerate(views):
        if v.width * v.height > MAX_VIEW_PIXELS:
            raise Refused("view %d is larger than the pixel limit" % (i + 1))
        try:
            svg = VW.render(project, name=v.name, style=v.style,
                            addons=tuple(v.addons) if v.addons is not None else None,
                            width=v.width, height=v.height,
                            latitude=v.latitude, day=v.day_of_year, hour=v.hour,
                            sky=v.sky, fov=v.fov, azimuth=v.azimuth,
                            elevation=v.elevation, distance=v.distance,
                            eye_height=v.eye_height, cut_azimuth=v.cut_azimuth)
        except ValueError as e:
            raise Refused(str(e))
        meta = VW.describe(project, v.name, v.latitude, v.day_of_year, v.hour)
        meta.update({"style": v.style,
                     "addons": list(v.addons) if v.addons is not None
                     else list(VW.DEFAULT_ADDONS),
                     "sky": v.sky, "label": v.label or v.name})
        out.append({
            "kind": "view", "number": "V-%03d" % (i + 1),
            "title": v.label or v.name.replace("-", " ").title(),
            "filename": "view-%02d-%s.svg" % (i + 1, v.name.replace("/", "-")),
            "data": svg.encode("utf-8"), "content_type": "image/svg+xml",
            "width": v.width, "height": v.height, "meta": meta,
        })
    return out


DISCIPLINE = {"A": "architectural", "S": "structural", "E": "electrical",
              "M": "mechanical", "P": "public_health", "FS": "fire"}


def assemble_revision(req):
    """A previous source plus a change, as a Project ready to draw."""
    try:
        new_source, notes = RV.apply(req.source, req.changes)
    except RV.Rejected as e:
        raise Refused(str(e))
    if req.revision:
        new_source["revision"] = req.revision
    try:
        spec, massing, brf = RV.build(new_source)
    except RV.Rejected as e:
        raise Refused(str(e))
    _guard(len(massing.levels), massing.gia())

    info = {"number": req.number or "AAI-%s" % uuid.uuid4().hex[:6].upper(),
            "rev": new_source.get("revision", "P02")}
    if req.client:
        info["client"] = req.client
    info["subtitle"] = (new_source.get("spec") or
                        new_source.get("footprint") or {}).get("name") or ""
    project = _with_source(PJ.Project(massing, brf, info), new_source)
    return spec, project, notes


def build_all(req, tmp_root):
    """Full synchronous generation. Returns (spec, project, artefacts, timing)."""
    t0 = time.time()
    notes = None
    if getattr(req, "source", None) is not None:
        spec, project, notes = assemble_revision(req)
    else:
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
            "filename": s["filename"], "data": s["data"], "path": s["path"],
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

    views = render_views(project, req.views or [])
    artefacts.extend(views)

    if getattr(req, "include_pdf", True):
        pages = [a["data"].decode("utf-8") for a in artefacts
                 if a["kind"] in ("drawing", "view")]
        if pages:
            buf = io.BytesIO()
            PDF.write(pages, buf,
                      title="%s — %s" % (project.info.get("name", "Project"),
                                         project.info.get("number", "")),
                      author=project.info.get("architect", "ArchiAI"),
                      subject=project.info.get("subtitle", ""))
            artefacts.append({
                "kind": "document", "number": None,
                "title": "Drawing set", "filename": "%s-drawings.pdf" % num_of(project),
                "data": buf.getvalue(), "content_type": "application/pdf",
                "width": 0, "height": 0,
                "meta": {"format": "pdf", "pages": len(pages),
                         "paper": "A1 sheets", "vector": True},
            })

    if getattr(req, "include_page", True):
        page_views = [{"svg": v["data"].decode("utf-8"), "title": v["title"],
                       "note": v["meta"].get("label", "")} for v in views]
        buf = io.BytesIO()
        WEB.build(project, buf,
                  sheets=[(a["number"], a["title"], a["meta"].get("scale"),
                           a["path"]) for a in artefacts if a["kind"] == "drawing"],
                  views=page_views,
                  turntable=int(getattr(req, "turntable", 8) or 0))
        artefacts.append({
            "kind": "document", "number": None, "title": "Project page",
            "filename": "%s-project.html" % num_of(project),
            "data": buf.getvalue(), "content_type": "text/html",
            "width": 0, "height": 0,
            "meta": {"format": "html", "self_contained": True,
                     "sheets": sum(1 for a in artefacts if a["kind"] == "drawing"),
                     "views": len(page_views)},
        })

    sheet_index = [{"number": a["number"], "title": a["title"],
                    "filename": a["filename"], "paper": "A1",
                    "scale": a["meta"].get("scale"),
                    "discipline": a["meta"].get("discipline")}
                   for a in artefacts if a["kind"] == "drawing"]
    if getattr(project, "source", None):
        RV.record_result(project.source, project)
    man = EX.manifest(project, sheet_index, spec, model)
    if views:
        man["views"] = [{"number": v["number"], "title": v["title"],
                         "filename": v["filename"], **v["meta"]} for v in views]
    docs = [a for a in artefacts if a["kind"] == "document"]
    if docs:
        man["documents"] = [{"filename": d["filename"], **d["meta"]}
                            for d in docs]
    if notes is not None:
        man["revision"] = {
            "of": (req.source or {}).get("revision", "P01"),
            "now": project.source.get("revision", "P02"),
            "parent": getattr(req, "parent_generation_id", None),
            "changed": notes,
            "measured": RV.compare((req.source or {}).get("result"), project),
        }
    artefacts.append({
        "kind": "manifest", "filename": "manifest.json",
        "data": json.dumps(man, indent=2).encode("utf-8"),
        "content_type": "application/json", "width": 0, "height": 0, "meta": {},
    })
    return spec, project, artefacts, man, gen_id, int((time.time() - t0) * 1000)
