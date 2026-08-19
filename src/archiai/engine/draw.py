"""Sheet generators that work on any typology.

These consume the Massing protocol and the Floorplan, never a shape. The
drafting kit, the title block and the annotation conventions are the ones the
torus set already uses -- this layer just stops assuming the building is round.
"""

import math
from ..svgkit import (Sheet, View, d_poly, d_poly_mm, INK, GREY, LIGHT, BLUE,
                      RED, GREEN, f, DASH_HID)
from .. import annot as A
from . import geom2d as G
from . import layout as L
from .grid import OrthoGrid, RadialGrid

STD_SCALES = [20, 50, 100, 150, 200, 250, 500, 1000, 2000]


def fit_scale(bbox, w_mm, h_mm, margin_mm=26.0):
    """Largest standard scale at which the model fits the drawing area."""
    x0, y0, x1, y1 = bbox
    bw, bh = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    for s in STD_SCALES:
        if bw * 1000.0 / s <= w_mm - 2 * margin_mm and bh * 1000.0 / s <= h_mm - 2 * margin_mm:
            return s
    return STD_SCALES[-1]


# ---------------------------------------------------------------------------
# Geometry -> SVG paths
# ---------------------------------------------------------------------------
def ring_path(v, ring, close=True):
    return d_poly(v, ring, close)


def region_path(v, region):
    return " ".join(d_poly(v, r, True) for r in region.rings)


def band_path(v, band):
    return " ".join(d_poly(v, r, True) for r in band.rings)


def cut_path(v, cut):
    """`cut(z)` returns a Band or a list of Bands, depending on typology."""
    bands = cut if isinstance(cut, (list, tuple)) else [cut]
    return " ".join(band_path(v, b) for b in bands)


# ---------------------------------------------------------------------------
def draw_grid(s, v, grid, bbox, label_size=2.4, bubble=4.0):
    if isinstance(grid, RadialGrid):
        for ln in grid.lines():
            if ln.kind == "ring":
                continue
            a, b = v.p(*ln.a), v.p(*ln.b)
            s.line(a[0], a[1], b[0], b[1], w="grid", color=BLUE, dash="6,2,1,2")
            s.circle(b[0], b[1], bubble, w="grid", color=BLUE, fill="#ffffff")
            s.text(b[0], b[1] + 0.85, ln.label, label_size, "middle", BLUE, "600")
        return
    for ln in grid.lines():
        a, b = v.p(*ln.a), v.p(*ln.b)
        s.line(a[0], a[1], b[0], b[1], w="grid", color=BLUE, dash="6,2,1,2")
        for (px, py), (qx, qy) in ((a, b), (b, a)):
            dx, dy = px - qx, py - qy
            d = math.hypot(dx, dy) or 1.0
            cx, cy = px + dx / d * bubble, py + dy / d * bubble
            s.circle(cx, cy, bubble, w="grid", color=BLUE, fill="#ffffff")
            s.text(cx, cy + 0.85, ln.label, label_size, "middle", BLUE, "600")


def draw_columns(s, v, pts, dia=0.4):
    r = max(0.7, v.mm(dia / 2.0) * 1.4)
    for (x, y) in pts:
        cx, cy = v.p(x, y)
        s.circle(cx, cy, r, w="fine", color=INK, fill=INK)


def draw_rooms(s, v, fp, tag=True, min_tag_area=14.0):
    if fp.circulation:
        s.path(region_path(v, fp.circulation), w=None,
               fill=L.CATEGORY["circ"][0], rule="evenodd")
    for r in fp.rooms:
        s.path(ring_path(v, r.ring), w="med", color=INK, fill=r.fill)
    if not tag:
        return
    for r in fp.rooms:
        if r.area < min_tag_area:
            continue
        cx, cy = v.p(*r.centroid)
        size = 2.6 if r.area > 60 else 2.1
        s.text(cx, cy - 1.0, r.name, size, "middle", INK, "600", halo="#ffffff")
        s.text(cx, cy + size * 1.25 - 1.0, "%.0f m²" % r.area, size - 0.6,
               "middle", GREY, halo="#ffffff")


def draw_plate_edge(s, v, plate):
    s.path(region_path(v, plate), w="fine", color=GREY, fill="none", dash=DASH_HID)


def dimension_ortho(s, v, grid, offset=14.0):
    x0, y0, x1, y1 = grid.bbox
    m = grid.margin
    pts = [(x, y0 - m) for x in grid.xs]
    A.dim_chain(s, v, pts, -offset, total=True, total_off=8.0)
    pts = [(x0 - m, y) for y in grid.ys]
    A.dim_chain(s, v, pts, offset, total=True, total_off=8.0)


# ---------------------------------------------------------------------------
def plan_sheet(project, i, out, paper="A1"):
    lv = project.massing.levels[i]
    fp = project.floorplans[i]
    P = project.info
    s = Sheet("A-1%02d" % i, "%s — Floor Plan" % lv.name,
              "1 : %d", paper, "FFL %+.3f" % lv.ffl, P,
              ["Generated from the parametric model.",
               "Do not scale; figured dimensions govern."])
    x0, y0, x1, y1 = s.area()
    aw, ah = x1 - x0, y1 - y0
    grid = project.grid
    bx = _expanded_bbox(lv.plate.bbox(), grid)
    scale = fit_scale(bx, aw, ah, margin_mm=30.0)
    s.scale_text = "1 : %d" % scale
    s.frame()
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    mx, my = (bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0
    v = View(s, scale, cx - mx * 1000.0 / scale, cy + my * 1000.0 / scale)

    draw_plate_edge(s, v, lv.plate)
    draw_rooms(s, v, fp)
    s.path(cut_path(v, project.massing.cut(lv.ffl + 1.5)), w="cut", color=INK,
           fill=s.pattern("concrete"), rule="evenodd")
    draw_grid(s, v, grid, bx)
    if isinstance(grid, OrthoGrid):
        draw_columns(s, v, grid.columns(lv.plate))
        dimension_ortho(s, v, grid)

    A.north_arrow(s, x1 - 26, y0 + 28)
    A.scale_bar(s, v, x0 + 8, y1 - 26, _bar_len(scale), 4, label="SCALE 1:%d" % scale)
    _legend(s, x0 + 8, y0 + 18, fp)
    _notes(s, x0 + 8, y1 - 78, project, fp, lv, scale)
    z = lv.ffl
    A.level_tag(s, *v.p(*_tag_point(lv.plate)), z, "FFL")
    return s.save(out)


def _bar_len(scale):
    return {20: 2, 50: 5, 100: 10, 150: 20, 200: 20, 250: 25, 500: 50,
            1000: 100, 2000: 200}.get(scale, 20)


def _expanded_bbox(bbox, grid):
    m = getattr(grid, "margin", 6.0) + 6.0
    return (bbox[0] - m, bbox[1] - m, bbox[2] + m, bbox[3] + m)


def _tag_point(plate):
    x0, y0, x1, y1 = plate.bbox()
    for t in (0.25, 0.35, 0.5, 0.65, 0.75):
        p = (x0 + (x1 - x0) * t, y0 + (y1 - y0) * 0.5)
        if plate.contains(p):
            return p
    return G.centroid(plate.outer)


def _legend(s, x, y, fp):
    seen = []
    for r in fp.rooms:
        if r.cat not in seen:
            seen.append(r.cat)
    items = [{"kind": "fill", "fill": L.CATEGORY[c][0], "stroke": L.CATEGORY[c][1],
              "label": L.CATEGORY[c][2]} for c in seen]
    items.append({"kind": "fill", "fill": L.CATEGORY["circ"][0],
                  "stroke": L.CATEGORY["circ"][1], "label": "Primary circulation"})
    items.append({"kind": "line", "stroke": BLUE, "dash": "6,2,1,2", "w": "grid",
                  "label": "Structural grid"})
    items.append({"kind": "line", "stroke": GREY, "dash": DASH_HID, "w": "fine",
                  "label": "Plate edge"})
    A.legend(s, x, y, items)


def _notes(s, x, y, project, fp, lv, scale):
    g = project.grid
    lines = ["Plan cut 1 500 above FFL."]
    if isinstance(g, OrthoGrid):
        sx, sy = g.actual_spacing
        lines.append("Grid at %d x %d centres." % (round(sx * 1000), round(sy * 1000)))
    lines += [
        "Daylight band %d deep." % round(project.brief.daylight_depth * 1000),
        "Circulation %d wide." % round(project.brief.corridor_w * 1000),
        "",
        "GIA this level: %s m²" % "{:,.0f}".format(lv.area).replace(",", " "),
        "Rooms this level: %d" % len(fp.rooms),
    ]
    A.notes_block(s, x, y, "GENERAL NOTES", lines)
