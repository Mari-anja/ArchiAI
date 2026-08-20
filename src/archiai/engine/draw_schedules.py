"""Cover, register, schedules, site plan and the 3D view."""

import math
from ..svgkit import (Sheet, View, d_poly, d_poly_mm, INK, GREY, LIGHT, BLUE,
                      RED, GREEN, f, DASH_HID)
from .. import annot as A
from ..axo import Cam, Scene
from . import geom2d as G
from . import layout as L
from . import services as SV
from .draw import PlanBase, ring_path, region_path, fit_scale, _bar_len, _expanded_bbox


def _sp(v):
    return "{:,.0f}".format(v).replace(",", " ")


# ---------------------------------------------------------------------------
# 3D
# ---------------------------------------------------------------------------
WALL = (196, 200, 204)
ROOFC = (182, 186, 188)
SLABC = (208, 202, 194)
GROUNDC = (214, 220, 206)


def _rgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _scene(project, cam, cutaway=False, keep=0.72):
    """Ground, floor plates drawn as their actual rooms, then the envelope.

    Using the rooms as the floor surface means the cutaway shows the plan --
    which is the only reason to cut a model open in the first place."""
    sc = Scene(cam)
    m = project.massing
    x0, y0, x1, y1 = m.footprint().bbox()
    pad = max(x1 - x0, y1 - y0) * 0.22
    sc.quad([(x0 - pad, y0 - pad, -0.05), (x1 + pad, y0 - pad, -0.05),
             (x1 + pad, y1 + pad, -0.05), (x0 - pad, y1 + pad, -0.05)], GROUNDC)

    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def removed(px, py):
        return cutaway and px > cx and py > cy

    for i, lv in enumerate(m.levels):
        fp = project.floorplans[i]
        for r in fp.rooms:
            c = r.centroid
            if removed(*c):
                continue
            sc.quad([(px, py, lv.ffl) for (px, py) in r.ring],
                    _rgb(r.fill), cull=False)
            for k in range(len(r.ring)):
                a, b = r.ring[k], r.ring[(k + 1) % len(r.ring)]
                sc.quad([(a[0], a[1], lv.ffl), (b[0], b[1], lv.ffl),
                         (b[0], b[1], lv.ffl - 0.30), (a[0], a[1], lv.ffl - 0.30)],
                        SLABC, cull=True)

    mesh = m.mesh()
    for fi in mesh.f:
        pts = [mesh.v[k] for k in fi]
        pcx = sum(p[0] for p in pts) / len(pts)
        pcy = sum(p[1] for p in pts) / len(pts)
        if removed(pcx, pcy):
            continue
        z = sum(p[2] for p in pts) / len(pts)
        roof_z = getattr(m, "top", m.height)
        sc.quad(pts, ROOFC if z >= roof_z - 0.05 else WALL)
    return sc


def _exploded(project, cam, lift=None):
    """Levels pulled apart, so every plan is visible at once."""
    sc = Scene(cam)
    m = project.massing
    lift = lift or max(m.height * 0.55, 6.0)
    for i, lv in enumerate(m.levels):
        z = i * lift
        fp = project.floorplans[i]
        for r in fp.rooms:
            sc.quad([(px, py, z) for (px, py) in r.ring], _rgb(r.fill), cull=False)
            for k in range(len(r.ring)):
                a, b = r.ring[k], r.ring[(k + 1) % len(r.ring)]
                sc.quad([(a[0], a[1], z), (b[0], b[1], z),
                         (b[0], b[1], z - 0.35), (a[0], a[1], z - 0.35)],
                        SLABC, cull=True)
    return sc, lift


def axo_sheet(project, out, number="A-800", paper="A1"):
    P = project.info
    s = Sheet(number, "Axonometric and Assembly", "Not to scale", paper,
              "Solid view and exploded levels", P,
              ["Generated from the same model as the drawings."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    m = project.massing
    bx = m.footprint().bbox()
    span = max(bx[2] - bx[0], bx[3] - bx[1], m.height) * 2.0

    k = min((x1 - x0) * 0.44, (y1 - y0) * 0.52) / max(span * 0.5, 1.0)
    cam = Cam(az=-122.0, el=28.0, scale=k, cx=x0 + (x1 - x0) * 0.30,
              cy=y0 + (y1 - y0) * 0.44)
    _scene(project, cam, cutaway=False).emit(s)
    s.text(x0 + 12, y1 - 42, "AXONOMETRIC", 5.0, "start", INK, "700", spacing=0.8)
    s.text(x0 + 12, y1 - 35, "From the south-west, 28° above the horizon",
           2.4, "start", GREY)

    k2 = min((x1 - x0) * 0.30, (y1 - y0) * 0.34) / max(span * 0.5, 1.0)
    cam2 = Cam(az=-122.0, el=28.0, scale=k2, cx=x0 + (x1 - x0) * 0.79,
               cy=y0 + (y1 - y0) * 0.46)
    sc2, lift = _exploded(project, cam2)
    sc2.emit(s)
    for i, lv in enumerate(m.levels):
        px, py = cam2.p((bx[2], bx[3], i * lift))
        s.line(px, py, x1 - 96, py, w="dim", color=GREY)
        s.circle(px, py, 0.55, w=None, fill=GREY)
        s.text(x1 - 93, py + 0.8, "%s · %s m² · %d rooms"
               % (lv.name, _sp(lv.area), len(project.floorplans[i].rooms)),
               2.2, "start", INK)
    s.text(x1 - (x1 - x0) * 0.34, y1 - 42, "EXPLODED LEVELS", 4.2, "start",
           INK, "700", spacing=0.8)

    A.notes_block(s, x0 + 12, y0 + 16, "AT A GLANCE", [
        "%d storeys" % len(m.levels),
        "%s m² gross internal" % _sp(m.gia()),
        "%.1f m to roof" % m.height,
        "%s m² footprint" % _sp(m.footprint().area),
        "%d rooms" % sum(len(f.rooms) for f in project.floorplans),
    ])
    return s.save(out)


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------
def site_sheet(project, out, number="A-010", paper="A1"):
    m = project.massing
    plate = m.footprint()
    x0, y0, x1, y1 = plate.bbox()
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    site_w, site_h = w + 70.0, h + 70.0
    boundary = G.rectangle(site_w, site_h, cx, cy)

    P = project.info
    s = Sheet(number, "Site Plan", "1 : %d", paper,
              "Site datum +0.000", P,
              ["Boundary indicative pending survey.",
               "Levels to be confirmed by topographical survey."])
    ax0, ay0, ax1, ay1 = s.area()
    bb = (cx - site_w / 2 - 6, cy - site_h / 2 - 6,
          cx + site_w / 2 + 6, cy + site_h / 2 + 6)
    scale = fit_scale(bb, ax1 - ax0, ay1 - ay0, margin_mm=28.0)
    s.scale_text = "1 : %d" % scale
    s.frame()
    v = View(s, scale, (ax0 + ax1) / 2.0 - cx * 1000.0 / scale,
             (ay0 + ay1) / 2.0 + cy * 1000.0 / scale)

    s.path(ring_path(v, boundary), w=None, fill=s.pattern("grass"))
    s.path(ring_path(v, boundary), w="heavy", color=GREEN, dash="12,4")

    az = math.radians(project.brief.entrance_azimuth)
    ex, ey = math.cos(az), math.sin(az)
    approach = [(cx + ex * (max(w, h) / 2 + 4) - ey * 6, cy + ey * (max(w, h) / 2 + 4) + ex * 6),
                (cx + ex * (max(w, h) / 2 + 4) + ey * 6, cy + ey * (max(w, h) / 2 + 4) - ex * 6),
                (cx + ex * (max(site_w, site_h) / 2) + ey * 9,
                 cy + ey * (max(site_w, site_h) / 2) - ex * 9),
                (cx + ex * (max(site_w, site_h) / 2) - ey * 9,
                 cy + ey * (max(site_w, site_h) / 2) + ex * 9)]
    s.path(d_poly(v, approach, True), w="thin", color=GREY, fill=s.pattern("paving"))

    ring = G.offset_ring(plate.outer, 9.0)
    s.path(ring_path(v, ring), w=None, fill="#eceae6")
    s.path(ring_path(v, ring), w="thin", color=GREY)
    s.path(ring_path(v, G.offset_ring(plate.outer, 4.0)), w="thin", color=GREY)

    bays = 0
    park = G.offset_ring(plate.outer, 13.0)
    per = G.perimeter(park)
    n = int(per // 5.4)
    cum = [0.0]
    for i in range(len(park)):
        cum.append(cum[-1] + math.dist(park[i], park[(i + 1) % len(park)]))
    for kk in range(n):
        t = cum[-1] * kk / n
        for j in range(len(cum) - 1):
            if cum[j] <= t <= cum[j + 1]:
                seg = cum[j + 1] - cum[j] or 1.0
                u = (t - cum[j]) / seg
                a, b = park[j], park[(j + 1) % len(park)]
                nx, ny = G._edge_normal(a, b)
                px = a[0] + (b[0] - a[0]) * u
                py = a[1] + (b[1] - a[1]) * u
                s.line(*v.p(px, py), *v.p(px + nx * 4.8, py + ny * 4.8),
                       w="fine", color="#a9a6a0")
                bays += 1
                break

    for r in (plate,):
        s.path(region_path(v, r), w=None, fill="#dfe5ea", rule="evenodd")
        s.path(region_path(v, r), w="outline", color=INK, fill="none", rule="evenodd")

    for i in range(26):
        a = 2 * math.pi * i / 26
        rr = max(site_w, site_h) * 0.40
        px, py = cx + math.cos(a) * rr, cy + math.sin(a) * rr
        if not G.point_in_ring((px, py), G.offset_ring(plate.outer, 16.0)):
            xx, yy = v.p(px, py)
            s.circle(xx, yy, max(1.4, v.mm(3.2)), w="hatch", color="#8fae86",
                     fill="#e4eede")

    A.dim_linear(s, v, (cx - site_w / 2, cy - site_h / 2),
                 (cx + site_w / 2, cy - site_h / 2), -14.0)
    A.dim_linear(s, v, (cx - site_w / 2, cy - site_h / 2),
                 (cx - site_w / 2, cy + site_h / 2), 14.0)
    A.dim_linear(s, v, (x0, y0), (x1, y0), -8.0)

    x, y = v.p(cx, cy + max(w, h) / 2 + 3)
    A.north_arrow(s, ax1 - 26, ay0 + 28)
    A.scale_bar(s, v, ax0 + 8, ay1 - 26, _bar_len(scale), 4,
                label="SCALE 1:%d" % scale)
    A.notes_block(s, ax0 + 8, ay1 - 84, "SITE", [
        "Site area: %s m²" % _sp(site_w * site_h),
        "Building footprint: %s m²" % _sp(plate.area),
        "Site coverage: %.1f %%" % (100.0 * plate.area / (site_w * site_h)),
        "Parking: %d bays" % bays,
        "Perimeter road: 5 000 wide, fire appliance access",
        "Approach from the %s" % _compass(project.brief.entrance_azimuth),
    ])
    return s.save(out)


def _compass(az):
    return {0: "east", 90: "north", 180: "west", 270: "south"}.get(
        int(az) % 360, "%d°" % az)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
def schedule_sheet(project, out, number="A-700", paper="A1"):
    P = project.info
    s = Sheet(number, "Area Schedule and Accommodation", "—", paper,
              "Computed from the model", P,
              ["Areas measured to the internal face of the enclosing wall."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    m = project.massing

    col = x0 + 16
    s.text(col, y0 + 20, "AREA BY LEVEL", 3.4, "start", INK, "700", spacing=1.2)
    s.line(col, y0 + 24, col + 250, y0 + 24, w="med", color=INK)
    yy = y0 + 32
    for lab in (("LEVEL", 0), ("FFL", 62), ("ROOMS", 104), ("CIRC m²", 150),
                ("GIA m²", 250)):
        s.text(col + lab[1], yy, lab[0], 2.0, "start" if lab[1] < 150 else "end",
               GREY, "600", spacing=0.7)
    yy += 6.0
    s.line(col, yy - 2.6, col + 250, yy - 2.6, w="hatch", color=LIGHT)
    for i, lv in enumerate(m.levels):
        fp = project.floorplans[i]
        s.text(col, yy, lv.name, 2.4, "start", INK)
        s.text(col + 62, yy, "%+.3f" % lv.ffl, 2.4, "start", GREY)
        s.text(col + 104, yy, str(len(fp.rooms)), 2.4, "start", GREY)
        s.text(col + 150, yy, _sp(fp.circulation_area),
               2.4, "end", GREY)
        s.text(col + 250, yy, _sp(lv.area), 2.4, "end", INK, "600")
        yy += 6.4
    s.line(col, yy - 2.2, col + 250, yy - 2.2, w="thin", color=INK)
    s.text(col, yy + 2, "GROSS INTERNAL AREA", 2.6, "start", INK, "700")
    s.text(col + 250, yy + 2, _sp(m.gia()), 3.2, "end", INK, "700")
    yy += 16

    agg = {}
    for fp in project.floorplans:
        for k, val in fp.by_category().items():
            agg[k] = agg.get(k, 0.0) + val
    circ_total = sum(f.circulation_area for f in project.floorplans)
    agg["circ"] = agg.get("circ", 0.0) + circ_total
    s.text(col, yy, "AREA BY USE", 3.4, "start", INK, "700", spacing=1.2)
    s.line(col, yy + 4, col + 250, yy + 4, w="med", color=INK)
    yy += 12
    # a degenerate plate has rooms of no area, and a bar chart scaled to the
    # largest of nothing divides by zero
    mx = max(agg.values(), default=0.0) or 1.0
    total = sum(agg.values()) or 1.0
    for k, val in sorted(agg.items(), key=lambda kv: -kv[1]):
        fill, stroke, label = L.CATEGORY.get(k, ("#eee", "#999", k))
        s.text(col, yy, label, 2.4, "start", INK)
        s.rect(col + 96, yy - 3.0, 88.0 * val / mx, 3.8, w="fine",
               color=stroke, fill=fill)
        s.text(col + 214, yy, _sp(val), 2.4, "end", INK)
        s.text(col + 250, yy, "%.0f%%" % (100 * val / total), 2.4, "end", GREY)
        yy += 6.6

    col2 = x0 + 296
    svc = [SV.for_floor(f) for f in project.floorplans]
    tot = {}
    for lst in svc:
        for k, val in SV.totals(lst).items():
            tot[k] = tot.get(k, 0) + val
    st = SV.structure(project, 0)
    fd = SV.foundations(project)
    esc = SV.escape(project.floorplans[0])
    rf = SV.roof(project)

    blocks = [
        ("BUILDING", [
            ("Storeys", str(len(m.levels))),
            ("Gross internal area", "%s m²" % _sp(m.gia())),
            ("Footprint", "%s m²" % _sp(m.footprint().area)),
            ("Height to roof", "%.2f m" % m.height),
            ("Floor to floor", "%.2f m" % m.levels[0].to_ffl),
            ("Rooms", str(sum(len(f.rooms) for f in project.floorplans))),
        ]),
        ("STRUCTURE", [
            ("Grid", "%d x %d" % (int(st["spacing"][0] * 1000),
                                  int(st["spacing"][1] * 1000))),
            ("Columns per level", str(len(st["columns"]))),
            ("Column load", "%d kN" % st["column_load_kn"]),
            ("Column size", "%d mm square" % st["column_size_mm"]),
            ("Slab / beams", "%d / %d mm" % (st["slab_depth_mm"],
                                             st["beam_depth_mm"])),
            ("Foundations", "%d pads at %.1f m" % (len(fd["pads"]), fd["pad_m"])),
        ]),
        ("SERVICES", [
            ("Design occupancy", "%d people" % tot.get("occupants", 0)),
            ("Luminaires", str(tot.get("luminaires", 0))),
            ("Lighting load", "%.1f kW" % tot.get("lighting_load_kw", 0)),
            ("Small power", "%.1f kW" % tot.get("small_power_kw", 0)),
            ("Fresh air", "%s l/s" % _sp(tot.get("fresh_air_lps", 0))),
            ("Sprinkler heads", str(tot.get("sprinklers", 0))),
            ("Roof outlets", str(len(rf["outlets"]))),
        ]),
        ("COMPLIANCE", [
            ("Worst travel distance", "%.1f m" % esc.worst),
            ("Travel limit", "%.0f m" % esc.limit),
            ("Escape status", "within limit" if esc.compliant else "EXCEEDS"),
            ("Protected stairs", str(len(SV.risers(project.floorplans[0])))),
            ("Accessible WC", "one per core"),
        ]),
    ]
    yy2 = y0 + 20
    for title, rows in blocks:
        s.text(col2, yy2, title, 3.4, "start", INK, "700", spacing=1.2)
        s.line(col2, yy2 + 4, col2 + 250, yy2 + 4, w="med", color=INK)
        yy2 += 12
        for k, val in rows:
            s.text(col2, yy2, k, 2.4, "start", GREY)
            s.text(col2 + 250, yy2, val, 2.5, "end", INK, "600")
            s.line(col2, yy2 + 2.0, col2 + 250, yy2 + 2.0, w="hatch", color=LIGHT)
            yy2 += 6.6
        yy2 += 10
    return s.save(out)


# ---------------------------------------------------------------------------
def cover_sheet(project, register, out, number="A-000", paper="A1"):
    P = project.info
    m = project.massing
    s = Sheet(number, "Cover Sheet and Drawing Register", "—", paper,
              P.get("subtitle", ""), P)
    s.frame()
    x0, y0, x1, y1 = s.area()

    s.text(x0 + 14, y0 + 40, P.get("name", "PROJECT"), 26.0, "start", INK,
           "700", spacing=3.2)
    s.text(x0 + 14, y0 + 54, P.get("subtitle", ""), 4.6, "start", GREY)
    s.line(x0 + 14, y0 + 62, x0 + 300, y0 + 62, w="med", color=INK)

    facts = [("Storeys", str(len(m.levels))),
             ("Gross internal area", "%s m²" % _sp(m.gia())),
             ("Footprint", "%s m²" % _sp(m.footprint().area)),
             ("Height to roof", "%.2f m" % m.height),
             ("Rooms", str(sum(len(f.rooms) for f in project.floorplans))),
             ("Sheets in this set", str(len(register)))]
    yy = y0 + 78
    for k, val in facts:
        s.text(x0 + 14, yy, k.upper(), 2.1, "start", GREY, "600", spacing=0.7)
        s.text(x0 + 130, yy, val, 3.6, "start", INK, "600")
        s.line(x0 + 14, yy + 3.4, x0 + 210, yy + 3.4, w="hatch", color=LIGHT)
        yy += 10.5

    bx = m.footprint().bbox()
    span = max(bx[2] - bx[0], bx[3] - bx[1], m.height) * 2.4
    k = min(230.0, 150.0) / max(span * 0.5, 1.0)
    cam = Cam(az=-122.0, el=27.0, scale=k, cx=x1 - 200, cy=y0 + 150)
    _scene(project, cam, cutaway=False).emit(s)

    ry = y0 + 216
    s.text(x0 + 14, ry, "DRAWING REGISTER", 3.0, "start", GREY, "700", spacing=1.4)
    s.line(x0 + 14, ry + 3.6, x1 - 14, ry + 3.6, w="med", color=INK)
    ry += 10
    half = (len(register) + 1) // 2
    for ci, chunk in enumerate((register[:half], register[half:])):
        bxx = x0 + 14 + ci * 306
        for dx, lab in ((0, "NUMBER"), (54, "TITLE"), (232, "SCALE")):
            s.text(bxx + dx, ry, lab, 2.0, "start", GREY, "600", spacing=0.7)
        s.line(bxx, ry + 2.4, bxx + 292, ry + 2.4, w="hatch", color=LIGHT)
        yy2 = ry + 8.0
        for (num, title, scale) in chunk:
            s.text(bxx, yy2, "%s-%s" % (P.get("number", ""), num), 2.3,
                   "start", INK, "600")
            s.text(bxx + 54, yy2, title, 2.3, "start", INK)
            s.text(bxx + 232, yy2, scale, 2.3, "start", GREY)
            yy2 += 5.8
    s.text(x0 + 14, y1 - 14, "Every sheet in this set is generated from one "
           "model; change a dimension and the whole set redraws.", 2.4,
           "start", GREY, italic=True)
    return s.save(out)


# ---------------------------------------------------------------------------
# Door and window schedule
# ---------------------------------------------------------------------------
def _table(s, x, y, width, cols, rows, title, note=None):
    """A ruled schedule table. cols = [(label, dx, anchor), ...]."""
    s.text(x, y, title, 3.4, "start", INK, "700", spacing=1.2)
    s.line(x, y + 4, x + width, y + 4, w="med", color=INK)
    yy = y + 12
    for (lab, dx, anc) in cols:
        s.text(x + dx, yy, lab, 2.0, anc, GREY, "600", spacing=0.7)
    yy += 5.6
    s.line(x, yy - 2.6, x + width, yy - 2.6, w="hatch", color=LIGHT)
    for row in rows:
        for (cell, (lab, dx, anc)) in zip(row, cols):
            bold = "600" if lab in ("MARK", "No.") else "400"
            s.text(x + dx, yy, cell, 2.4, anc,
                   INK if bold == "600" else GREY, bold)
        s.line(x, yy + 2.2, x + width, yy + 2.2, w="hatch", color=LIGHT)
        yy += 6.6
    if note:
        s.text(x, yy + 3, note, 2.1, "start", GREY, italic=True)
        yy += 7
    return yy


def _dim_mm(s, x1, y1, x2, y2, label, size=1.9):
    """A dimension drawn straight in sheet millimetres (for type elevations)."""
    s.line(x1, y1, x2, y2, w="fine", color=GREY)
    t = 1.1
    if abs(y2 - y1) < 0.01:
        s.line(x1, y1 - t, x1, y1 + t, w="fine", color=GREY)
        s.line(x2, y2 - t, x2, y2 + t, w="fine", color=GREY)
        s.text((x1 + x2) / 2, y1 - 1.6, label, size, "middle", GREY)
    else:
        s.line(x1 - t, y1, x1 + t, y1, w="fine", color=GREY)
        s.line(x2 - t, y2, x2 + t, y2, w="fine", color=GREY)
        s.text(x1 - 1.6, (y1 + y2) / 2, label, size, "end", GREY)


GLYPH_K = 0.034      # sheet mm per mm of opening (about 1:30)

IRONMONGERY = [
    ("IS1", "D1", "1½ pr hinges, lever latch, indicator where WC"),
    ("IS2", "D2", "2 pr hinges per leaf, lever latch, flush bolts"),
    ("IS3", "D3", "1½ pr fire hinges, overhead closer, intumescent set"),
    ("IS4", "D4", "Fire hinges, closers, panic hardware, coordinator"),
    ("IS5", "D5", "Sliding gear, break-out leaves, sensor and safety beam"),
]


def _door_glyph(s, x, y, w_mm, h_mm, double, k=GLYPH_K):
    """An elevation of the leaf at a common scale (about 1:30)."""
    w, h = w_mm * k, h_mm * k
    s.rect(x, y - h, w, h, w="thin", color=INK, fill="#f4f2ee")
    if double:
        s.line(x + w / 2, y - h, x + w / 2, y, w="fine", color=GREY)
        for cx in (x + w * 0.40, x + w * 0.60):
            s.circle(cx, y - h * 0.45, 1.1, w="fine", color=INK, fill=INK)
    else:
        s.rect(x + w * 0.12, y - h * 0.90, w * 0.76, h * 0.78, w="fine",
               color="#c3c0bb")
        s.circle(x + w * 0.84, y - h * 0.45, 1.1, w="fine", color=INK, fill=INK)
    s.line(x - 2, y, x + w + 2, y, w="med", color=INK)
    _dim_mm(s, x, y + 6, x + w, y + 6, "%d" % w_mm)
    _dim_mm(s, x - 6, y, x - 6, y - h, "%d" % h_mm)


def _window_glyph(s, x, y, w_mm, h_mm, curtain, k=GLYPH_K):
    w, h = w_mm * k, h_mm * k
    s.rect(x, y - h, w, h, w="thin", color=INK, fill="#e9f0f4")
    s.rect(x + 1.2, y - h + 1.2, max(w - 2.4, 0.4), max(h - 2.4, 0.4),
           w="fine", color="#9fb6c4")
    if curtain:
        s.line(x, y - h * 0.72, x + w, y - h * 0.72, w="fine", color=GREY)
        s.text(x + w / 2, y - h * 0.86, "transom", 1.6, "middle", GREY)
    else:
        s.line(x + w / 2, y - h, x + w / 2, y, w="fine", color=GREY)
        s.line(x + w * 0.52, y - h * 0.5, x + w * 0.92, y - h * 0.5, w="fine",
               color=GREY, dash="2,1.4")
    s.line(x - 2, y, x + w + 2, y, w="med", color=INK)
    _dim_mm(s, x, y + 6, x + w, y + 6, "%d" % w_mm)
    _dim_mm(s, x - 6, y, x - 6, y - h, "%d" % h_mm)


def _matrix(s, x, y, width, title, keys, rows, note=None):
    """A mark-by-something count matrix with row and column totals."""
    s.text(x, y, title, 3.0, "start", GREY, "700", spacing=1.4)
    s.line(x, y + 3.6, x + width, y + 3.6, w="med", color=INK)
    yy = y + 11
    n = len(keys)
    span = width - 60.0
    step = span / max(n, 1)
    s.text(x, yy, "MARK", 2.0, "start", GREY, "600", spacing=0.7)
    for j, k in enumerate(keys):
        s.text(x + 46 + step * (j + 0.5), yy, k.upper(), 2.0, "middle", GREY,
               "600", spacing=0.7)
    s.text(x + width, yy, "TOTAL", 2.0, "end", GREY, "600", spacing=0.7)
    yy += 5.6
    s.line(x, yy - 2.6, x + width, yy - 2.6, w="hatch", color=LIGHT)
    col_tot = [0] * n
    for (mark, counts) in rows:
        s.text(x, yy, mark, 2.4, "start", INK, "600")
        for j, k in enumerate(keys):
            c = counts.get(k, 0)
            col_tot[j] += c
            s.text(x + 46 + step * (j + 0.5), yy, str(c) if c else "–", 2.4,
                   "middle", INK if c else LIGHT)
        s.text(x + width, yy, str(sum(counts.values())), 2.4, "end", INK, "600")
        s.line(x, yy + 2.2, x + width, yy + 2.2, w="hatch", color=LIGHT)
        yy += 6.4
    s.line(x, yy - 2.2, x + width, yy - 2.2, w="thin", color=INK)
    s.text(x, yy + 2.4, "TOTAL", 2.4, "start", INK, "700")
    for j in range(n):
        s.text(x + 46 + step * (j + 0.5), yy + 2.4, str(col_tot[j]), 2.4,
               "middle", INK, "700")
    s.text(x + width, yy + 2.4, str(sum(col_tot)), 2.6, "end", INK, "700")
    yy += 10
    if note:
        s.text(x, yy, note, 2.1, "start", GREY, italic=True)
        yy += 6
    return yy


def _glyph_row(s, x, top, width, items, draw_one):
    """Lay type elevations across the column, shrunk to fit on one row."""
    if not items:
        return top
    n = len(items)
    gap = 26.0 if n <= 4 else 16.0
    total = sum(it["width_mm"] for it in items)
    k = min(GLYPH_K, (width - 22.0 - gap * (n - 1)) / max(total, 1.0))
    k = max(k, 0.012)
    base = top + max(it["height_mm"] for it in items) * k + 4.0
    gx = x + 12
    for it in items:
        draw_one(s, gx, base, it, k)
        gx += max(it["width_mm"] * k, 26.0) + gap
    return base + 32.0


def _door_key_plan(s, project, i, x, y, w_mm, h_mm, title):
    """A small plan with every door marked, so the schedule can be located."""
    from . import openings as OP
    lv = project.massing.levels[i]
    fp = project.floorplans[i]
    bx = lv.plate.bbox()
    scale = fit_scale(bx, w_mm, h_mm, margin_mm=14.0)
    mx, my = (bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0
    v = View(s, scale, x + w_mm / 2.0 - mx * 1000.0 / scale,
             y + h_mm / 2.0 + my * 1000.0 / scale)
    s.text(x, y - 6, title, 3.0, "start", GREY, "700", spacing=1.4)
    s.line(x, y - 2.4, x + w_mm, y - 2.4, w="med", color=INK)
    for r in fp.rooms:
        s.path(ring_path(v, r.ring), w="fine", color="#cfd3d6", fill="#fbfbfa")
    for c in fp.circulation:
        s.path(region_path(v, c), w="fine", color="#d8d2c4", fill="#f2ede1",
               rule="evenodd")
    s.path(ring_path(v, lv.plate.outer), w="med", color=INK)
    for hole in lv.plate.holes:
        s.path(ring_path(v, hole), w="med", color=INK)
    placed = []
    for d in OP.doors(project, i):
        px, py = v.p(*d.point)
        s.circle(px, py, 1.5, w="fine", color=RED, fill="#ffffff")
        best = None
        for (dx, dy, anc) in ((3.4, -1.4, "start"), (-3.4, -1.4, "end"),
                              (3.4, 3.2, "start"), (-3.4, 3.2, "end"),
                              (0.0, -4.4, "middle"), (0.0, 5.6, "middle")):
            lx, ly = px + dx, py + dy
            if any(abs(ox - lx) < 7.0 and abs(oy - ly) < 3.0
                   for (ox, oy) in placed):
                continue
            best = (lx, ly, anc)
            break
        if best is None:
            continue                       # too crowded to letter legibly
        placed.append(best[:2])
        s.text(best[0], best[1], d.mark, 2.0, best[2], RED, "600")
    s.text(x, y + h_mm + 4, "Scale 1:%d.  Every door on this level is marked; "
           "the schedule counts them across the building." % scale,
           2.1, "start", GREY, italic=True)


def _bay_setting_out(s, project, x, y, w_mm, h_mm, title):
    """One structural bay of curtain walling, dimensioned for setting out."""
    from . import openings as OP
    from .draw import facade_bays
    bays = facade_bays(project, 270.0)
    span = (bays[1] - bays[0]) if len(bays) > 1 else project.brief.room_width
    m = project.massing
    sh = m.levels[0].to_ffl
    clear = span - 2 * OP.REVEAL
    n, mod = OP._split(clear)

    k = min((w_mm - 40.0) / max(span, 0.1), (h_mm - 30.0) / max(sh, 0.1))
    ox, oy = x + 24.0, y + h_mm - 18.0            # model origin: bay left, FFL

    def P(mx_, mz):
        return (ox + mx_ * k, oy - mz * k)

    s.text(x, y - 6, title, 3.0, "start", GREY, "700", spacing=1.4)
    s.line(x, y - 2.4, x + w_mm, y - 2.4, w="med", color=INK)

    s.rect(*P(0.0, sh), span * k, sh * k, w="fine", color="#e4e0d8",
           fill="#faf9f6")
    for z, lab in ((0.0, "FFL"), (sh, "SOFFIT OVER")):
        a, b = P(-0.5, z), P(span + 0.5, z)
        s.line(a[0], a[1], b[0], b[1], w="med", color=INK)
        s.text(b[0] + 2, b[1] + 1, lab, 1.9, "start", GREY, "600")
    for mx_ in (0.0, span):                       # mullion on the grid
        a, b = P(mx_, -0.4), P(mx_, sh + 0.4)
        s.line(a[0], a[1], b[0], b[1], w="grid", color=BLUE, dash="6,2,1,2")

    z0, z1 = OP.SILL, sh - OP.HEAD_GAP
    gl = P(OP.REVEAL, z1)
    s.rect(gl[0], gl[1], clear * k, (z1 - z0) * k, w="thin", color=INK,
           fill="#e9f0f4")
    for j in range(1, n):
        a, b = P(OP.REVEAL + mod * j, z1), P(OP.REVEAL + mod * j, z0)
        s.line(a[0], a[1], b[0], b[1], w="thin", color=INK)
    sp_a, sp_b = P(OP.REVEAL, z0), P(OP.REVEAL, 0.0)
    s.rect(sp_a[0], sp_a[1], clear * k, (z0 - 0.0) * k, w="fine", color=GREY,
           fill="#dfdcd6")
    s.text((sp_a[0] + sp_a[0] + clear * k) / 2.0, sp_a[1] + (z0 * k) / 2.0 + 1,
           "SPANDREL", 1.9, "middle", GREY, "600", spacing=0.6)
    hd_a = P(OP.REVEAL, sh)
    s.rect(hd_a[0], hd_a[1], clear * k, OP.HEAD_GAP * k, w="fine", color=GREY,
           fill="#dfdcd6")

    a, b = P(0.0, 0.0), P(span, 0.0)
    _dim_mm(s, a[0], a[1] + 12, b[0], b[1] + 12, "%d structural bay"
            % int(round(span * 1000)))
    a, b = P(OP.REVEAL, 0.0), P(span - OP.REVEAL, 0.0)
    _dim_mm(s, a[0], a[1] + 6, b[0], b[1] + 6,
            "%d x %d modules" % (n, int(round(mod * 1000))))
    a, b = P(0.0, 0.0), P(0.0, sh)
    _dim_mm(s, a[0] - 8, a[1], b[0] - 8, b[1], "%d floor to floor"
            % int(round(sh * 1000)))
    a, b = P(0.0, 0.0), P(0.0, OP.SILL)
    _dim_mm(s, a[0] - 16, a[1], b[0] - 16, b[1], "%d sill"
            % int(round(OP.SILL * 1000)))
    s.text(x, y + h_mm + 4, "Reveal %d mm each side. Mullions sit on the "
           "structural grid; transom at mid height of the vision panel."
           % int(OP.REVEAL * 1000), 2.1, "start", GREY, italic=True)


def door_window_sheet(project, out, number="A-710", paper="A1"):
    from . import openings as OP
    P = project.info
    s = Sheet(number, "Door and Window Schedule", "—", paper,
              "Counted from the model", P,
              ["Sizes are structural openings; frames to be site measured.",
               "Fire ratings to BS 476 Part 22 / EN 1634-1.",
               "All fire doors to carry intumescent and smoke seals.",
               "Type elevations at 1:30; counts taken from the floor plans."])
    s.frame()
    x0, y0, x1, y1 = s.area()

    doors = OP.door_schedule(project)
    wins = OP.windows(project)
    tot = OP.totals(project)
    W = 268.0
    col = x0 + 16
    col2 = x0 + 300

    # ---- doors, left half ------------------------------------------------
    cols = [("MARK", 0, "start"), ("DESCRIPTION", 22, "start"),
            ("W x H mm", 150, "start"), ("FIRE", 196, "start"),
            ("LOCATION", 226, "start"), ("No.", W, "end")]
    rows = [(d["mark"], d["description"],
             "%d x %d" % (d["width_mm"], d["height_mm"]),
             d["fire"], d["use"], str(d["count"])) for d in doors]
    yy = _table(s, col, y0 + 20, W, cols, rows, "DOOR SCHEDULE")
    s.line(col, yy - 4.4, col + W, yy - 4.4, w="thin", color=INK)
    s.text(col, yy, "TOTAL DOORS", 2.6, "start", INK, "700")
    s.text(col + W, yy, str(tot["doors"]), 3.0, "end", INK, "700")
    yy += 18

    levels = [lv.name for lv in project.massing.levels]
    yy = _matrix(s, col, yy, W, "DOORS BY LEVEL", levels,
                 OP.door_matrix(project),
                 "Each stair core carries one FD60S pair and one FD30S "
                 "single at every level.")
    yy += 10

    s.text(col, yy, "IRONMONGERY SETS", 3.0, "start", GREY, "700", spacing=1.4)
    s.line(col, yy + 3.6, col + W, yy + 3.6, w="med", color=INK)
    yy += 11
    marks = set(d["mark"] for d in doors)
    for (iset, mark, desc) in IRONMONGERY:
        if mark not in marks:
            continue
        s.text(col, yy, iset, 2.4, "start", INK, "600")
        s.text(col + 24, yy, mark, 2.4, "start", GREY, "600")
        s.text(col + 46, yy, desc, 2.4, "start", GREY)
        s.line(col, yy + 2.2, col + W, yy + 2.2, w="hatch", color=LIGHT)
        yy += 6.4
    yy += 16

    s.text(col, yy, "DOOR TYPES", 3.0, "start", GREY, "700", spacing=1.4)
    s.line(col, yy + 3.6, col + W, yy + 3.6, w="med", color=INK)
    yy += 22

    def _one_door(sh, gx, base, d, k):
        _door_glyph(sh, gx, base, d["width_mm"], d["height_mm"],
                    d["width_mm"] > 1200, k)
        sh.text(gx, base + 12, d["mark"], 3.0, "start", INK, "700")
        sh.text(gx, base + 17, d["description"][:26], 2.0, "start", GREY)
        sh.text(gx, base + 21.5,
                d["fire"] if d["fire"] != "—" else "no rating", 2.0, "start",
                GREY)
        sh.text(gx, base + 26, "%d no." % d["count"], 2.0, "start", INK, "600")

    yy = _glyph_row(s, col, yy, W, doors, _one_door)

    # ---- windows, right half ---------------------------------------------
    cols2 = [("MARK", 0, "start"), ("TYPE", 22, "start"),
             ("W x H mm", 132, "start"), ("GLAZING", 178, "start"),
             ("No.", W, "end")]
    rows2 = [(w["mark"], w["type"], "%d x %d" % (w["width_mm"], w["height_mm"]),
              w["glazing"], str(w["count"])) for w in wins]
    yy2 = _table(s, col2, y0 + 20, W, cols2, rows2, "WINDOW SCHEDULE")
    s.line(col2, yy2 - 4.4, col2 + W, yy2 - 4.4, w="thin", color=INK)
    s.text(col2, yy2, "TOTAL UNITS", 2.6, "start", INK, "700")
    s.text(col2 + W, yy2, str(tot["windows"]), 3.0, "end", INK, "700")
    yy2 += 8
    s.text(col2, yy2, "GLAZED AREA", 2.6, "start", INK, "700")
    s.text(col2 + W, yy2, "%s m²" % _sp(tot["glazed_area_m2"]), 3.0, "end",
           INK, "700")
    yy2 += 18

    faces = [k for k in ("North", "East", "South", "West")
             if any(k in c for (_, c) in OP.window_matrix(project))]
    yy2 = _matrix(s, col2, yy2, W, "UNITS BY ELEVATION", faces,
                  OP.window_matrix(project),
                  "Wide bays are glazed as curtain walling and counted by "
                  "module, not by bay.")
    yy2 += 10

    facade = G.perimeter(project.massing.footprint().outer) * project.massing.height
    gia = project.massing.gia()
    perf = [("Glazing U-value", "1.4 W/m²K whole unit"),
            ("Centre pane Ug", "1.1 W/m²K, argon filled"),
            ("Solar factor g", "0.38, body-tinted outer pane"),
            ("Frame", "Thermally broken aluminium, PPC finish"),
            ("Acoustic", "Rw 38 dB to the glazed line"),
            ("Facade area", "%s m²" % _sp(facade)),
            ("Glazed ratio of facade", "%.1f %%"
             % (100.0 * tot["glazed_area_m2"] / max(facade, 1.0))),
            ("Glazed area to GIA", "%.1f %%" % (100.0 * tot["glazed_area_m2"]
                                                / max(gia, 1.0)))]
    s.text(col2, yy2, "GLAZING PERFORMANCE", 3.0, "start", GREY, "700",
           spacing=1.4)
    s.line(col2, yy2 + 3.6, col2 + W, yy2 + 3.6, w="med", color=INK)
    yy2 += 11
    for k, val in perf:
        s.text(col2, yy2, k, 2.4, "start", GREY)
        s.text(col2 + W, yy2, val, 2.4, "end", INK, "600")
        s.line(col2, yy2 + 2.2, col2 + W, yy2 + 2.2, w="hatch", color=LIGHT)
        yy2 += 6.4
    yy2 += 16

    s.text(col2, yy2, "WINDOW TYPES", 3.0, "start", GREY, "700", spacing=1.4)
    s.line(col2, yy2 + 3.6, col2 + W, yy2 + 3.6, w="med", color=INK)
    yy2 += 22

    def _one_window(sh, gx, base, w, k):
        _window_glyph(sh, gx, base, w["width_mm"], w["height_mm"],
                      w["mark"].startswith("CW"), k)
        sh.text(gx, base + 12, w["mark"], 3.0, "start", INK, "700")
        sh.text(gx, base + 17, w["type"][:26], 2.0, "start", GREY)
        sh.text(gx, base + 21.5, w["note"][:30], 2.0, "start", GREY)
        sh.text(gx, base + 26, "%d no." % w["count"], 2.0, "start", INK, "600")

    yy2 = _glyph_row(s, col2, yy2, W, wins, _one_window)

    # ---- key plan across the foot, bay setting-out above it --------------
    full = col2 + W - col
    band_top = max(yy, yy2) + 24
    band_h = y1 - 30 - band_top
    if band_h > 66:
        key_w = full * 0.60
        _door_key_plan(s, project, 0, col, band_top, key_w, band_h,
                       "DOOR KEY PLAN — %s" % project.massing.levels[0].name)
        bx_ = col + key_w + 30
        _bay_setting_out(s, project, bx_, band_top, full - key_w - 30, band_h,
                         "TYPICAL FACADE BAY — SETTING OUT")

    s.text(x0 + 16, y1 - 14, "Door positions are taken from the floor plans; "
           "window counts from the structural bays of each elevation. Change "
           "the grid and this schedule recounts itself.", 2.4, "start", GREY,
           italic=True)
    return s.save(out)
