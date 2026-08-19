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
    mx = max(agg.values()) if agg else 1.0
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
