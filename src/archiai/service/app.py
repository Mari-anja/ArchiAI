"""HTTP surface.

Generation is synchronous because it is fast: a full set of plans, elevations,
sections, a mesh and a manifest takes well under a second. Only the upload of
the results is I/O bound, and those run concurrently.
"""

import asyncio
import hmac
import os
import tempfile
import time
import uuid
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool

from ..engine import brief as B
from ..engine import export as EX
from ..engine import geom2d as G
from .config import settings
from .storage import make_storage
from .models import (GenerateRequest, GenerateResponse, ParseRequest,
                     ParseResponse, TraceRequest, TraceResponse, ViewRequest,
                     ReviseRequest, PhotorealRequest,
                     Asset)
from . import generate as gen
from . import images as IMG

app = FastAPI(
    title="ArchiAI building engine",
    version=EX.ENGINE_VERSION,
    description="Turns a brief or a drawn footprint into a coordinated "
                "architectural drawing set and 3D model.",
)

TMP_ROOT = os.environ.get("ARCHIAI_TMP", os.path.join(tempfile.gettempdir(), "archiai-gen"))
IDEMPOTENCY_MAX = int(os.environ.get("ARCHIAI_IDEMPOTENCY_CACHE", "256"))
_idempotent = OrderedDict()


def _remember(key, body):
    _idempotent[key] = body
    _idempotent.move_to_end(key)
    while len(_idempotent) > IDEMPOTENCY_MAX:
        _idempotent.popitem(last=False)


def require_key(request: Request):
    if settings.allow_anonymous:
        return None
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not any(hmac.compare_digest(token, k) for k in settings.api_keys):
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")
    return token


async def _publish(storage, prefix, artefacts):
    """Upload everything concurrently and describe it back to the caller."""
    async def one(a):
        stored = await storage.put("%s/%s" % (prefix, a["filename"]),
                                   a["data"], a["content_type"])
        return Asset(kind=a["kind"], number=a.get("number"),
                     title=a.get("title"), scale=a.get("scale"),
                     key=stored.key, url=stored.url, bytes=stored.size,
                     content_type=stored.content_type,
                     width=a.get("width", 0), height=a.get("height", 0),
                     meta=a.get("meta", {}))

    try:
        return list(await asyncio.gather(*(one(a) for a in artefacts)))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail="storage: %s" % e)


ASSETS = os.path.join(os.path.dirname(__file__), "assets")


@app.get("/", include_in_schema=False)
def playground():
    """A page for trying the engine by hand before wiring it into anything."""
    return FileResponse(os.path.join(ASSETS, "playground.html"),
                        media_type="text/html")


@app.get("/playground.js", include_in_schema=False)
def playground_js():
    return FileResponse(os.path.join(ASSETS, "playground.js"),
                        media_type="application/javascript")


@app.get("/v1/health")
def health():
    return {"status": "ok", "engine": EX.ENGINE_VERSION, **settings.describe()}


@app.post("/v1/parse", response_model=ParseResponse)
def parse(req: ParseRequest, _=Depends(require_key)):
    """Read a brief without generating anything. Free, and safe to call on
    every keystroke so the UI can show what was understood before committing."""
    spec = B.parse(req.brief)
    sheets = spec.storeys + 3
    return ParseResponse(
        spec={"use": spec.use, "shape": spec.shape, "storeys": spec.storeys,
              "area_m2": spec.area, "entrance_azimuth": spec.entrance,
              "floor_to_floor_m": spec.floor_to_floor, "name": spec.name},
        assumptions=spec.assumptions,
        estimated_sheets=sheets,
        estimated_cost_units=20 + 6 * sheets + 2 * spec.storeys,
    )


@app.post("/v1/trace", response_model=TraceResponse)
async def trace(req: TraceRequest, _=Depends(require_key)):
    """Trace an uploaded sketch and hand back the outline, nothing more.

    The point is to show someone what was read from their drawing before a
    whole set is generated from it. The same outline posted back as a
    footprint builds exactly the building this returns."""
    im = req.image
    try:
        region = await run_in_threadpool(
            IMG.footprint_from_upload, im.data, im.area_m2, im.width_m,
            im.simplify, im.straighten)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    x0, y0, x1, y1 = region.bbox()
    notes = []
    if not (im.area_m2 or im.width_m):
        notes.append("No size given, so the outline is at one pixel to the "
                     "metre. Send area_m2 or width_m to scale it.")
    if len(region.outer) > 40:
        notes.append("The outline came back with %d corners; raise simplify "
                     "to smooth it further." % len(region.outer))
    if region.holes:
        notes.append("%d opening(s) read as courtyards." % len(region.holes))
    return TraceResponse(
        outer=[[round(x, 3), round(y, 3)] for (x, y) in region.outer],
        holes=[[[round(x, 3), round(y, 3)] for (x, y) in h] for h in region.holes],
        area_m2=round(region.area, 1),
        perimeter_m=round(G.perimeter(region.outer), 1),
        width_m=round(x1 - x0, 2), depth_m=round(y1 - y0, 2),
        vertices=len(region.outer), notes=notes)


@app.post("/v1/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, _=Depends(require_key)):
    try:
        req.mode()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if req.idempotency_key and req.idempotency_key in _idempotent:
        _idempotent.move_to_end(req.idempotency_key)
        return _idempotent[req.idempotency_key]

    try:
        spec, project, artefacts, man, gen_id, ms = await run_in_threadpool(
            gen.build_all, req, TMP_ROOT)
    except gen.Refused as e:
        raise HTTPException(status_code=422, detail=str(e))

    storage = make_storage()
    prefix = "%s/%s" % (req.project_id or "anonymous", gen_id)
    assets = await _publish(storage, prefix, artefacts)

    body = GenerateResponse(
        generation_id=gen_id, project_id=req.project_id, duration_ms=ms,
        cost_units=man["totals"]["cost_units"], manifest=man, assets=assets)
    if req.idempotency_key:
        _remember(req.idempotency_key, body)
    return body


@app.post("/v1/revise", response_model=GenerateResponse)
async def revise(req: ReviseRequest, _=Depends(require_key)):
    """The same building with one thing changed, as the next revision.

    Send the `source` block from a previous generation's manifest and what you
    want different. You get a full set back, numbered P02, with a plain note
    of what changed and the measured difference it made."""
    if req.idempotency_key and req.idempotency_key in _idempotent:
        _idempotent.move_to_end(req.idempotency_key)
        return _idempotent[req.idempotency_key]
    try:
        spec, project, artefacts, man, gen_id, ms = await run_in_threadpool(
            gen.build_all, req, TMP_ROOT)
    except gen.Refused as e:
        raise HTTPException(status_code=422, detail=str(e))

    prefix = "%s/%s" % (req.project_id or "anonymous", gen_id)
    assets = await _publish(make_storage(), prefix, artefacts)
    body = GenerateResponse(
        generation_id=gen_id, project_id=req.project_id, duration_ms=ms,
        cost_units=man["totals"]["cost_units"], manifest=man, assets=assets)
    if req.idempotency_key:
        _remember(req.idempotency_key, body)
    return body


@app.post("/v1/view", response_model=GenerateResponse)
async def view(req: ViewRequest, _=Depends(require_key)):
    """Pictures of a building that has already been described.

    The building is rebuilt from the same input rather than stored, because
    the engine is deterministic: the same brief, footprint, spec or image
    always gives the same building, so a view asked for a week later is a view
    of the same thing."""
    try:
        req.mode()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if req.idempotency_key and req.idempotency_key in _idempotent:
        _idempotent.move_to_end(req.idempotency_key)
        return _idempotent[req.idempotency_key]
    t0 = time.time()
    try:
        _spec, project = await run_in_threadpool(gen.assemble, req)
        views = await run_in_threadpool(gen.render_views, project, req.views)
    except gen.Refused as e:
        raise HTTPException(status_code=422, detail=str(e))

    gen_id = uuid.uuid4().hex
    prefix = "%s/%s" % (req.project_id or "anonymous", gen_id)
    assets = await _publish(make_storage(), prefix, views)
    body = GenerateResponse(
        status="complete", generation_id=gen_id, project_id=req.project_id,
        duration_ms=int((time.time() - t0) * 1000),
        cost_units=len(views), assets=assets,
        manifest={"engine": EX.ENGINE_VERSION,
                  "project": {"name": project.info.get("name"),
                              "number": project.info.get("number"),
                              "storeys": len(project.massing.levels),
                              "gia_m2": round(project.gia, 1)},
                  "views": [{"number": v["number"], "title": v["title"],
                             "filename": v["filename"], **v["meta"]}
                            for v in views]})
    if req.idempotency_key:
        _remember(req.idempotency_key, body)
    return body


@app.post("/v1/photoreal", response_model=GenerateResponse)
async def photoreal(req: PhotorealRequest, _=Depends(require_key)):
    """Prepare a photoreal pass, and run it if an image service is configured.

    The control images and the description come back either way. They are what
    the model can say exactly and a photograph can only be guessed from: how
    far away each surface is, which way it faces, what it is made of, and where
    its edges are."""
    try:
        req.mode()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if req.idempotency_key and req.idempotency_key in _idempotent:
        _idempotent.move_to_end(req.idempotency_key)
        return _idempotent[req.idempotency_key]
    t0 = time.time()
    try:
        _spec, project = await run_in_threadpool(gen.assemble, req)
        made = await run_in_threadpool(gen.render_photoreal, project, req.shots)
    except gen.Refused as e:
        raise HTTPException(status_code=422, detail=str(e))

    gen_id = uuid.uuid4().hex
    prefix = "%s/%s" % (req.project_id or "anonymous", gen_id)
    assets = await _publish(make_storage(), prefix, made)
    kinds = {}
    for a in made:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    body = GenerateResponse(
        status="complete" if kinds.get("photoreal") else "controls_only",
        generation_id=gen_id, project_id=req.project_id,
        duration_ms=int((time.time() - t0) * 1000),
        cost_units=len(req.shots) * 4, assets=assets,
        manifest={"engine": EX.ENGINE_VERSION,
                  "image_service": settings.image_backend,
                  "project": {"name": project.info.get("name"),
                              "number": project.info.get("number"),
                              "storeys": len(project.massing.levels),
                              "gia_m2": round(project.gia, 1)},
                  "shots": [{"number": a["number"], "title": a["title"],
                             "filename": a["filename"], **a["meta"]}
                            for a in made],
                  "produced": kinds})
    if req.idempotency_key:
        _remember(req.idempotency_key, body)
    return body


@app.get("/files/{path:path}")
def files(path: str):
    """Serves local-storage output. Not mounted when running on Supabase."""
    if settings.backend != "local":
        raise HTTPException(status_code=404, detail="not found")
    root = settings.local_root
    full = os.path.normpath(os.path.join(root, path))
    if os.path.commonpath([full, root]) != root or not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(full)


@app.exception_handler(ValueError)
def value_error(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})
