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
class PlanBase:
    """A framed, scaled plan sheet with the grid on it, ready to be drawn into.

    Every discipline sheet starts here, so the electrical plan and the floor
    plan sit at the same scale in the same place on the paper and can be
    overlaid on a light table -- or in a browser."""

    __slots__ = ("sheet", "view", "scale", "level", "floorplan", "grid",
                 "bbox", "project")

    def __init__(self, project, i, number, title, subtitle="", notes=None,
                 paper="A1"):
        lv = project.massing.levels[i]
        s = Sheet(number, title, "1 : %d", paper, subtitle, project.info,
                  notes or ["Generated from the parametric model.",
                            "Do not scale; figured dimensions govern."])
        x0, y0, x1, y1 = s.area()
        grid = project.grid
        bx = _expanded_bbox(lv.plate.bbox(), grid)
        scale = fit_scale(bx, x1 - x0, y1 - y0, margin_mm=30.0)
        s.scale_text = "1 : %d" % scale
        s.frame()
        mx, my = (bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0
        v = View(s, scale, (x0 + x1) / 2.0 - mx * 1000.0 / scale,
                 (y0 + y1) / 2.0 + my * 1000.0 / scale)
        self.sheet, self.view, self.scale = s, v, scale
        self.level, self.floorplan = lv, project.floorplans[i]
        self.grid, self.bbox, self.project = grid, bx, project

    def walls(self, z_offset=1.5):
        s, v = self.sheet, self.view
        s.path(cut_path(v, self.project.massing.cut(self.level.ffl + z_offset)),
               w="cut", color=INK, fill=s.pattern("concrete"), rule="evenodd")

    def gridlines(self):
        draw_grid(self.sheet, self.view, self.grid, self.bbox)

    def furniture_ghost(self, opacity=0.30):
        """Room outlines, faint, so a services sheet still reads as a plan."""
        for r in self.floorplan.rooms:
            self.sheet.path(ring_path(self.view, r.ring), w="fine",
                            color="#b9bec4", fill="#fbfbfa")

    def finish(self, legend_items=None, notes_title="NOTES", notes=None,
               bar=True):
        s, v = self.sheet, self.view
        x0, y0, x1, y1 = s.area()
        A.north_arrow(s, x1 - 26, y0 + 28)
        if bar:
            A.scale_bar(s, v, x0 + 8, y1 - 26, _bar_len(self.scale), 4,
                        label="SCALE 1:%d" % self.scale)
        if legend_items:
            A.legend(s, x0 + 8, y0 + 18, legend_items)
        if notes:
            A.notes_block(s, x0 + 8, y1 - 40 - 3.4 * len(notes), notes_title, notes)
        return s


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


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def _line_hit_u(a, b, p0, u):
    """Where a plan line a-b crosses the section plane, as a u coordinate."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = u[0] * ey - u[1] * ex
    if abs(den) < 1e-12:
        return None
    rx, ry = a[0] - p0[0], a[1] - p0[1]
    t = (rx * ey - ry * ex) / den
    s = (rx * u[1] - ry * u[0]) / den
    return t if -1e-9 <= s <= 1 + 1e-9 else None


def _section_extent(res):
    lo = hi = None
    for (z, a, b) in res.beyond:
        lo = a if lo is None else min(lo, a)
        hi = b if hi is None else max(hi, b)
    if lo is None:
        lo, hi = -1.0, 1.0
    return lo, hi


def draw_section(s, v, project, res, ground=True):
    poche = s.pattern("concrete")
    lo, hi = _section_extent(res)
    pad = (hi - lo) * 0.12 + 4.0

    if ground:
        s.path(d_poly(v, [(lo - pad, 0), (hi + pad, 0), (hi + pad, -1.6),
                          (lo - pad, -1.6)], True), w=None, fill=s.pattern("earth"))
        a, b = v.p(lo - pad, 0), v.p(hi + pad, 0)
        s.line(a[0], a[1], b[0], b[1], w="cut", color=INK)

    # Everything past the cut plane. Drawn as an elevation rather than a solid
    # fill, so a courtyard reads as a courtyard with the far wing behind it and
    # not as a block of material.
    if res.beyond:
        left = [(a, z) for (z, a, b) in res.beyond]
        right = [(b, z) for (z, a, b) in res.beyond]
        s.path(d_poly(v, left + right[::-1], True), w=None, fill="#f7f7f5")
        for (name, z) in res.levels:
            lo_z = min((b for (zz, a, b) in res.beyond if abs(zz - z) < 0.2), default=None)
            hi_z = max((b for (zz, a, b) in res.beyond if abs(zz - z) < 0.2), default=None)
            lo_a = min((a for (zz, a, b) in res.beyond if abs(zz - z) < 0.2), default=None)
            if lo_a is None:
                continue
            p, q = v.p(lo_a, z), v.p(hi_z, z)
            s.line(p[0], p[1], q[0], q[1], w="fine", color="#c3c3bc")
        s.path(d_poly(v, left + right[::-1], True), w="fine", color="#c9c9c2")

    for (u0, u1, z, t) in res.slabs:
        s.path(d_poly(v, [(u0, z), (u1, z), (u1, z - t), (u0, z - t)], True),
               w="cut", color=INK, fill=poche)

    for (poly, closed) in res.cut:
        s.path(d_poly(v, poly, closed), w="cut", color=INK, fill=poche)

    for (name, z) in res.levels:
        A.level_tag(s, *v.p(hi + pad * 0.55, z), z, name.upper())
    top = project.massing.height
    A.level_tag(s, *v.p(hi + pad * 0.55, top), top, "ROOF")

    A.dim_linear(s, v, (lo, 0), (hi, 0), -14.0)
    A.dim_linear(s, v, (lo - pad * 0.5, 0), (lo - pad * 0.5, top), 8.0)
    for (name, z) in res.levels[:-1]:
        nxt = [zz for (_, zz) in res.levels if zz > z + 1e-6]
        if nxt:
            A.dim_linear(s, v, (lo - pad * 0.2, z), (lo - pad * 0.2, min(nxt)), 8.0)
    return lo, hi


def draw_section_grid(s, v, project, p0, u, top):
    grid = project.grid
    if not isinstance(grid, OrthoGrid):
        return
    seen = []
    for ln in grid.lines():
        t = _line_hit_u(ln.a, ln.b, p0, u)
        if t is None or any(abs(t - q) < 0.05 for q in seen):
            continue
        seen.append(t)
        a, b = v.p(t, -0.9), v.p(t, top + 1.6)
        s.line(a[0], a[1], b[0], b[1], w="grid", color=BLUE, dash="6,2,1,2")
        cx, cy = v.p(t, top + 2.6)
        s.circle(cx, cy, 3.4, w="grid", color=BLUE, fill="#ffffff")
        s.text(cx, cy + 0.75, ln.label, 2.1, "middle", BLUE, "600")


def section_sheet(project, cuts, out, paper="A1", number="A-300"):
    P = project.info
    s = Sheet(number, "Sections", "1 : 100", paper,
              " and ".join("%s-%s" % (c[0], c[0]) for c in cuts), P,
              ["Section planes located on the floor plans.",
               "Generated from the parametric model."])
    x0, y0, x1, y1 = s.area()
    aw, ah = x1 - x0, y1 - y0

    results = [(tag, cap, project.massing.section(p0, d), p0, d)
               for (tag, p0, d, cap) in cuts]
    top = project.massing.height
    widest = 0.0
    for (_, _, res, _, _) in results:
        lo, hi = _section_extent(res)
        widest = max(widest, (hi - lo) * 1.30)
    n = len(results)
    lane = ah / n
    scale = fit_scale((0, 0, widest, (top + 6.0) * n * 1.25), aw, ah, margin_mm=30.0)
    s.scale_text = "1 : %d" % scale
    s.frame()

    for i, (tag, cap, res, p0, d) in enumerate(results):
        base = y0 + lane * (i + 1) - lane * 0.30
        cx = (x0 + x1) / 2.0
        lo, hi = _section_extent(res)
        v = View(s, scale, cx - ((lo + hi) / 2.0) * 1000.0 / scale, base)
        draw_section(s, v, project, res)
        l = math.hypot(d[0], d[1]) or 1.0
        draw_section_grid(s, v, project, p0, (d[0] / l, d[1] / l), top)
        s.text(x0 + 10, base + 30, "SECTION %s-%s" % (tag, tag), 5.0, "start",
               INK, "700", spacing=0.8)
        s.text(x0 + 10, base + 37, cap, 2.4, "start", GREY)

    A.scale_bar(s, View(s, scale, 0, 0), x0 + 8, y1 - 24, _bar_len(scale), 4,
                label="SCALE 1:%d" % scale)
    return s.save(out)


# ---------------------------------------------------------------------------
# Elevations
# ---------------------------------------------------------------------------
COMPASS = {0: "EAST", 90: "NORTH", 180: "WEST", 270: "SOUTH"}


def facade_bays(project, azimuth):
    """Grid positions that read as vertical lines in this elevation."""
    a = math.radians(azimuth)
    right = (-math.sin(a), math.cos(a))
    out = []
    for ln in project.grid.lines():
        if ln.a is None:
            continue
        pa = ln.a[0] * right[0] + ln.a[1] * right[1]
        pb = ln.b[0] * right[0] + ln.b[1] * right[1]
        if abs(pa - pb) < 0.25:                      # edge-on: a vertical line
            out.append((pa + pb) / 2.0)
    return sorted(set(round(x, 3) for x in out))


def draw_windows(s, v, project, azimuth, lo, hi, sill=0.95, head_gap=0.75,
                 reveal=0.85):
    """One window per structural bay per storey, clipped to the silhouette."""
    bays = [x for x in facade_bays(project, azimuth) if lo - 0.01 <= x <= hi + 0.01]
    if len(bays) < 2:
        n = max(2, int(round((hi - lo) / project.brief.room_width)) + 1)
        bays = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    levels = project.massing.levels
    for k, lv in enumerate(levels):
        top = (levels[k + 1].ffl if k + 1 < len(levels)
               else project.massing.height)
        z0, z1 = lv.ffl + sill, top - head_gap
        if z1 - z0 < 0.6:
            continue
        e0, e1 = project.massing.extent_at(lv.ffl + 1.2, _axis(azimuth))
        for i in range(len(bays) - 1):
            a0, a1 = bays[i] + reveal, bays[i + 1] - reveal
            if a1 - a0 < 0.5 or a0 < e0 or a1 > e1:
                continue
            s.path(d_poly(v, [(a0, z0), (a1, z0), (a1, z1), (a0, z1)], True),
                   w="thin", color="#5c6a76", fill="#cfdae4")


def _axis(azimuth):
    a = math.radians(azimuth)
    return (-math.sin(a), math.cos(a))


def draw_elevation(s, v, project, el, top, azimuth=270):
    lo = hi = None
    for (poly, closed) in el.outline:
        for (x, z) in poly:
            lo = x if lo is None else min(lo, x)
            hi = x if hi is None else max(hi, x)
    if lo is None:
        return 0.0, 0.0
    pad = (hi - lo) * 0.12 + 4.0
    s.path(d_poly(v, [(lo - pad, 0), (hi + pad, 0), (hi + pad, -1.6),
                      (lo - pad, -1.6)], True), w=None, fill=s.pattern("earth"))
    a, b = v.p(lo - pad, 0), v.p(hi + pad, 0)
    s.line(a[0], a[1], b[0], b[1], w="cut", color=INK)

    for (poly, closed) in el.outline:
        s.path(d_poly(v, poly, closed), w=None, fill="#eef2f6")
    draw_windows(s, v, project, azimuth, lo, hi)
    for (z, chains) in el.joints:
        for (poly, closed) in chains:
            s.path(d_poly(v, poly, closed), w="med", color="#5c6a76")
    for (poly, closed) in el.outline:
        s.path(d_poly(v, poly, closed), w="outline", color=INK)

    for (name, z) in [(l.name, l.ffl) for l in project.massing.levels] + [("ROOF", top)]:
        A.level_tag(s, *v.p(hi + pad * 0.55, z), z, name.upper())
    A.dim_linear(s, v, (lo, 0), (hi, 0), -14.0)
    A.dim_linear(s, v, (lo - pad * 0.5, 0), (lo - pad * 0.5, top), 8.0)
    return lo, hi


def elevation_sheet(project, azimuths, out, paper="A1", number="A-200"):
    P = project.info
    names = " and ".join(COMPASS.get(int(a) % 360, "%d°" % a) for a in azimuths)
    s = Sheet(number, "Elevations", "1 : 100", paper, names.title(), P,
              ["Orthographic projection.",
               "Generated from the parametric model."])
    x0, y0, x1, y1 = s.area()
    aw, ah = x1 - x0, y1 - y0
    top = project.massing.height
    els = [(az, project.massing.silhouette(az)) for az in azimuths]

    widest = 0.0
    for (_, el) in els:
        xs = [x for (poly, _) in el.outline for (x, z) in poly]
        if xs:
            widest = max(widest, (max(xs) - min(xs)) * 1.30)
    n = len(els)
    lane = ah / n
    scale = fit_scale((0, 0, widest, (top + 6.0) * n * 1.25), aw, ah, margin_mm=30.0)
    s.scale_text = "1 : %d" % scale
    s.frame()

    for i, (az, el) in enumerate(els):
        base = y0 + lane * (i + 1) - lane * 0.30
        xs = [x for (poly, _) in el.outline for (x, z) in poly]
        mid = (min(xs) + max(xs)) / 2.0 if xs else 0.0
        v = View(s, scale, (x0 + x1) / 2.0 - mid * 1000.0 / scale, base)
        draw_elevation(s, v, project, el, top, az)
        label = COMPASS.get(int(az) % 360, "%d°" % az)
        s.text(x0 + 10, base + 30, "%s ELEVATION" % label, 5.0, "start", INK,
               "700", spacing=0.8)
        s.text(x0 + 10, base + 37, "Looking %s" % _looking(az), 2.4, "start", GREY)

    A.scale_bar(s, View(s, scale, 0, 0), x0 + 8, y1 - 24, _bar_len(scale), 4,
                label="SCALE 1:%d" % scale)
    return s.save(out)


def _looking(az):
    return {0: "west", 90: "south", 180: "east", 270: "north"}.get(int(az) % 360,
                                                                  "toward the centre")
