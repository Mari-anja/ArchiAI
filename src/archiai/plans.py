"""Floor plans, roof plan and site plan."""

import math
from .svgkit import (Sheet, View, d_arc, d_ring, d_annulus, d_poly, d_poly_mm,
                     INK, GREY, LIGHT, BLUE, RED, GREEN, f, DASH_HID, DASH_ABOVE, polar)
from . import annot as A
from . import params as P
from . import program as PG

SCALE = 150
CX, CY = 335.0, 297.0        # plan centre on the A1 sheet, mm

ENCLOSED = ("core", "plant", "event", "meet", "amenity")
OPENINGS_00_OUT = [(263.0, 277.0), (84.0, 96.0)]
OPENINGS_00_IN  = [(264.0, 276.0), (84.0, 96.0)]


# ---------------------------------------------------------------------------
def _sheet(number, title, subtitle, notes=None):
    return Sheet(number, title, "1 : %d" % SCALE, "A1", subtitle, P.PROJECT, notes)


def _gaps_to_spans(gaps, t0=0.0, t1=360.0):
    """Complement of a list of angular gaps, as drawable spans."""
    gs = sorted((max(t0, a), min(t1, b)) for a, b in gaps if b > t0 and a < t1)
    spans, cur = [], t0
    for a, b in gs:
        if a > cur:
            spans.append((cur, a))
        cur = max(cur, b)
    if cur < t1:
        spans.append((cur, t1))
    return spans


def _wall_band(s, v, r0, r1, gaps=(), fill=None, w="cut", color=INK):
    fill = fill or s.pattern("concrete")
    for (a, b) in _gaps_to_spans(list(gaps)):
        s.path(d_ring(v, r0, r1, a, b), w=w, color=color, fill=fill)


def _door_arc(s, v, r, t_c, width=1.8, out=True, leaf=True):
    """Door opening in a circumferential wall, with swing."""
    half = math.degrees(width / 2.0 / r)
    a, b = t_c - half, t_c + half
    p1, p2 = v.pol(r, a), v.pol(r, b)
    s.line(p1[0], p1[1], p1[0], p1[1], w="fine")
    if not leaf:
        return
    d = v.mm(width)
    sgn = 1 if out else -1
    hx, hy = v.pol(r, a)
    ang = -t_c
    # leaf drawn as a straight jamb + quarter-circle swing, kept simple at 1:200
    ex, ey = v.pol(r + sgn * width, a)
    s.line(hx, hy, ex, ey, w="fine", color=INK)
    s.path("M %s %s A %s %s 0 0 %d %s %s" % (
        f(ex), f(ey), f(d), f(d), 1 if out else 0, f(p2[0]), f(p2[1])),
        w="fine", color=GREY)


def _radial_wall(s, v, t, r0, r1, w="med", color=INK, dash=None):
    a, b = v.pol(r0, t), v.pol(r1, t)
    s.line(a[0], a[1], b[0], b[1], w=w, color=color, dash=dash)


# ---------------------------------------------------------------------------
def _courtyard(s, v, detail=True):
    r = P.R_IN_00
    if not detail:
        s.circle(*v.p(0, 0), v.mm(r), w=None, fill="#f4f6f2")
        A.text_polar(s, v, 12.4, 300, "COURTYARD BELOW", 3.0, "tangent",
                     color="#8fa889", weight="600", spacing=1.6)
        return
    s.circle(*v.p(0, 0), v.mm(r), w=None, fill=s.pattern("grass"))
    # ring path and lawn
    s.path(d_arc(v, 18.6, 0, 360), w="fine", color="#8fae88", fill=s.pattern("paving"))
    s.path(d_arc(v, 15.4, 0, 360), w="fine", color="#8fae88", fill=s.pattern("grass"))
    # reflecting pool at the centre
    s.circle(*v.p(0, 0), v.mm(7.2), w="fine", color="#88b2c9", fill=s.pattern("water"))
    # radial paths aligned with the entrance and gateway
    for t in (90, 270, 0, 180):
        a, b = v.pol(15.4, t), v.pol(P.R_IN_00, t)
        s.line(a[0], a[1], b[0], b[1], w="fine", color="#9db894")
    # trees
    for i in range(16):
        t = 11.25 + i * 22.5
        rr = 20.4 if i % 2 == 0 else 17.0
        x, y = v.pol(rr, t)
        s.circle(x, y, v.mm(2.6), w="fine", color="#7fa478", fill="#dbe8d5")
        s.circle(x, y, 0.5, w=None, fill="#5f8557")
    A.text_polar(s, v, 11.0, 315, "COURTYARD", 3.4, "tangent", color="#4d7a46",
                 weight="700", spacing=1.4)
    A.text_polar(s, v, 11.0, 313, "", 2.0)
    x, y = v.pol(11.6, 300)
    s.text(x, y, "1 633 m²", 2.4, "middle", "#6b8f64", "500", rot=A.rot_tangent(300))


def _shell_cut(s, v, level):
    ri, ro = P.cut_radii(level)
    si, so = P.slab_edges(level)
    poche = s.pattern("concrete")
    gaps_out = OPENINGS_00_OUT if level == 0 else []
    gaps_in = OPENINGS_00_IN if level == 0 else []

    if level == 1:
        # restricted-headroom zone: shell curving down to meet the slab
        s.path(d_annulus(v, ro, so), w=None, fill="#f2f0ec")
        s.path(d_annulus(v, si, ri), w=None, fill="#f2f0ec")
        s.path(d_arc(v, so, 0, 360), w="fine", color=GREY, dash=DASH_HID)
        s.path(d_arc(v, si, 0, 360), w="fine", color=GREY, dash=DASH_HID)

    _wall_band(s, v, ro - P.ENV_T, ro, gaps_out, fill=poche)
    _wall_band(s, v, ri, ri + P.ENV_T, gaps_in, fill=poche)

    if level == 0:
        # slab edge sits inboard of the cut -- the tube is still leaning out
        s.path(d_arc(v, so, 0, 360), w="fine", color=GREY, dash=DASH_HID)
        s.path(d_arc(v, si, 0, 360), w="fine", color=GREY, dash=DASH_HID)


def _rooms(s, v, level):
    rooms = PG.ROOMS_00 if level == 0 else PG.ROOMS_01
    # loop circulation
    s.path(d_annulus(v, P.R_IN_00, P.R_LOOP), w=None, fill=PG.CATEGORY["circ"][0])
    for r in rooms:
        if r.cat == "ext":
            s.path(d_ring(v, P.R_IN_00, r.r1, r.t0, r.t1), w=None, fill="#f4f2ec")
            continue
        s.path(d_ring(v, r.r0, r.r1, r.t0, r.t1), w=None, fill=r.fill)
    # void hatch
    for r in rooms:
        if r.cat == "void":
            s.path(d_ring(v, r.r0, r.r1, r.t0, r.t1), w="med", color=GREY,
                   fill="#ffffff")
            n = 9
            for i in range(n + 1):
                t = r.t0 + (r.t1 - r.t0) * i / n
                a, b = v.pol(r.r0, t), v.pol(r.r1, t)
                s.line(a[0], a[1], b[0], b[1], w="hatch", color=LIGHT)

    # partitions
    for i, r in enumerate(rooms):
        nxt = rooms[(i + 1) % len(rooms)]
        if r.cat in ENCLOSED or nxt.cat in ENCLOSED or r.cat == "void" or nxt.cat == "void":
            _radial_wall(s, v, r.t1, min(r.r0, nxt.r0), P.R_OUT_00)
        if r.cat in ENCLOSED:
            span = _gaps_to_spans([(r.tm - math.degrees(1.1 / P.R_LOOP),
                                    r.tm + math.degrees(1.1 / P.R_LOOP))], r.t0, r.t1)
            for (a, b) in span:
                s.path(d_arc(v, P.R_LOOP, a, b), w="med", color=INK)
            _door_arc(s, v, P.R_LOOP, r.tm, 2.2, out=False)

    # loop edge to courtyard glazing is the shell itself; mark the loop line
    s.path(d_arc(v, P.R_LOOP, 0, 360), w="hatch", color=LIGHT, dash="2,2")


def _focus_rooms(s, v):
    for (a0, a1, r0, r1) in PG.focus_rooms():
        s.path(d_ring(v, r0, r1, a0, a1), w="med", color=INK, fill="#faf7f2")
        _door_arc(s, v, r0, (a0 + a1) / 2.0, 0.9, out=False)


def _cores(s, v, level):
    for (cid, t_c, half) in P.CORES:
        for (name, a0, a1, r0, r1, cat) in PG.core_parts(t_c, half):
            s.path(d_ring(v, r0, r1, a0, a1), w="thin", color=GREY,
                   fill=PG.CATEGORY[cat][0])
        # stair: treads across the angular span
        a0, a1 = t_c - half, t_c - 0.4
        n = 13
        for i in range(1, n):
            t = a0 + (a1 - a0) * i / n
            p, q = v.pol(28.4, t), v.pol(32.2, t)
            s.line(p[0], p[1], q[0], q[1], w="fine", color=INK)
        mid = (a0 + a1) / 2.0
        p, q = v.pol(30.3, a0 + 0.6), v.pol(30.3, a1 - 0.6)
        s.line(p[0], p[1], q[0], q[1], w="thin", color=INK)
        A.text_polar(s, v, 30.3, mid, "UP" if level == 0 else "DN", 1.9, "tangent",
                     color=INK, weight="600")
        # lifts
        a0, a1 = t_c + 0.4, t_c + half
        for k in range(2):
            b0 = a0 + (a1 - a0) * k / 2.0
            b1 = a0 + (a1 - a0) * (k + 1) / 2.0
            s.path(d_ring(v, 28.4, 31.0, b0 + 0.3, b1 - 0.3), w="thin", color=INK,
                   fill="#eceff2")
            c = v.pol(29.7, (b0 + b1) / 2.0)
            d = v.mm(1.0)
            s.line(c[0] - d, c[1] - d, c[0] + d, c[1] + d, w="fine", color=GREY)
            s.line(c[0] - d, c[1] + d, c[0] + d, c[1] - d, w="fine", color=GREY)
        # WC fixtures, indicated
        for side, sgn in ((t_c - half / 2.0, -1), (t_c + half / 2.0, 1)):
            for j in range(4):
                t = side + (j - 1.5) * 1.5
                x, y = v.pol(33.2 + (j % 2) * 1.6, t)
                s.circle(x, y, v.mm(0.28), w="fine", color=GREY, fill="#ffffff")
        A.text_polar(s, v, 27.2, t_c, "CORE %s" % cid, 2.6, "tangent",
                     color=INK, weight="700", spacing=0.6)


def _columns(s, v, level):
    rr = v.mm(P.COL_DIA / 2.0) * 1.35
    for i in range(P.RADIAL_DIV):
        t = i * P.RADIAL_STEP
        for r in P.COL_RADII:
            x, y = v.pol(r, t)
            s.circle(x, y, rr, w="fine", color=INK, fill=INK)


def _desks(s, v, level):
    polys, n = PG.desks(level)
    for pts in polys:
        s.path(d_poly(v, pts, True), w="hatch", color="#8896a6", fill="#e3e9f0")
    return n


def _grid(s, v, r_bub=40.6):
    labels = [P.grid_label(i) for i in range(P.RADIAL_DIV)]
    thetas = [i * P.RADIAL_STEP for i in range(P.RADIAL_DIV)]
    A.radial_grid(s, v, thetas, 20.6, P.R_OUT_00, labels, bubble_at=r_bub)
    A.ring_grid(s, v, P.RING_GRID, P.RING_LABELS, t_label=0.0, bubble_r=3.4)


def _levels_and_marks(s, v, level):
    for (t0, t1), tag in ((P.SEC_AA, "A"), (P.SEC_BB, "B")):
        p1, p2 = v.pol(38.6, t0), v.pol(38.6, t1)
        A.section_mark(s, p1, p2, tag)
    x, y = v.pol(P.R_OUT_00 + 1.4, P.DET_THETA)
    A.elev_mark(s, x, y, "C", P.DET_THETA)
    z = P.FFL_00 if level == 0 else P.FFL_01
    x, y = v.pol(30.6, 249)
    A.level_tag(s, x, y, z, "FFL")


def _annotation(s, v, level, desk_count):
    x0, y0, x1, y1 = s.area()
    A.north_arrow(s, x1 - 26, y0 + 28)
    A.scale_bar(s, v, x0 + 8, y1 - 26, 20, 4, label="SCALE 1:%d" % SCALE)
    A.key_plan(s, x1 - 26, y1 - 44, 15,
               highlight=[(0, 360)], label="LEVEL %02d" % level)

    items = []
    seen = []
    rooms = PG.ROOMS_00 if level == 0 else PG.ROOMS_01
    for r in rooms:
        if r.cat not in seen:
            seen.append(r.cat)
    for c in seen:
        fillc, strokec, lab = PG.CATEGORY[c]
        items.append({"kind": "fill", "fill": fillc, "stroke": strokec, "label": lab})
    items.append({"kind": "line", "stroke": BLUE, "dash": "6,2,1,2", "w": "grid",
                  "label": "Structural grid"})
    items.append({"kind": "line", "stroke": GREY, "dash": DASH_HID, "w": "fine",
                  "label": "Slab edge / shell springing"})
    if level == 1:
        items.append({"kind": "fill", "fill": "#f2f0ec", "stroke": "#b8b4ac",
                      "label": "Restricted headroom (under 2 100)"})
    A.legend(s, x0 + 8, y0 + 18, items)

    notes = [
        "Building set out from the centre of the torus;",
        "all radii to structural face unless noted.",
        "Radial grid R01-R36 at 10.00° centres.",
        "Ring grid C1-C5 at 3 600 centres.",
        "Plan cut at %d above FFL." % round(P.CUT_ABOVE_FFL * 1000),
        "Loop circulation 3 200 wide, courtyard side.",
        "",
        "Workstations shown this level: %d" % desk_count,
        "GIA this level: %s m²" % ("{:,.0f}".format(PG.gia(level)).replace(",", " ")),
    ]
    A.notes_block(s, x0 + 8, y1 - 84, "GENERAL NOTES", notes)


# ---------------------------------------------------------------------------
def level_plan(level, out):
    titles = {0: "Level 00 — Ground Floor Plan", 1: "Level 01 — First Floor Plan"}
    subs = {0: "FFL +0.000 (42.600 AOD)", 1: "FFL +4.200"}
    s = _sheet("A-1%02d" % level, titles[level], subs[level],
               notes=["Read with A-300 and A-301 sections.",
                      "Refer to A-600 for framing."])
    s.frame()
    v = View(s, SCALE, CX, CY)

    _courtyard(s, v, detail=(level == 0))
    _rooms(s, v, level)
    if level == 1:
        _focus_rooms(s, v)
    _cores(s, v, level)
    n = _desks(s, v, level)
    _shell_cut(s, v, level)
    _columns(s, v, level)
    _grid(s, v)

    # room tags
    rooms = PG.ROOMS_00 if level == 0 else PG.ROOMS_01
    for r in rooms:
        if r.cat == "core":
            continue
        rr = 33.2
        arc = math.radians(r.t1 - r.t0) * rr
        mode = "tangent" if arc >= 13.0 else "radial"
        A.room_tag(s, v, rr, r.tm, r.name, "%.0f" % r.area, sub=r.sub,
                   size=2.8 if arc >= 18 else (2.4 if arc >= 13 else 2.1), mode=mode)

    # dimensions
    A.dim_radial_chain(s, v, [P.R_IN_00] + P.COL_RADII + [P.R_OUT_00],
                       180.0, offset=0.0, total=True, size=2.4)
    A.dim_linear(s, v, polar(P.R_IN_00, 200.0), polar(P.R_LOOP, 200.0), 0.0, size=2.2)
    A.dim_diameter(s, v, P.R_OUT_00, 135.0, size=3.0, frac=0.80)
    A.dim_diameter(s, v, P.R_IN_00, 45.0, size=3.0, frac=0.70)
    A.dim_angular(s, v, 38.9, 0, 10, "10.00°")

    _levels_and_marks(s, v, level)
    _annotation(s, v, level, n)
    return s.save(out)


# ---------------------------------------------------------------------------
# ROOF PLAN
# ---------------------------------------------------------------------------
def _rho(phi):
    return P.MAJOR_R + P.TUBE_R * math.cos(math.radians(phi))


def roof_plan(out):
    s = _sheet("A-102", "Roof Plan", "Shell crown, photovoltaic array and rainwater",
               notes=["Seen from above only the upper half of the",
                      "shell is visible; the overhanging flanks are",
                      "shown dashed."])
    s.frame()
    v = View(s, SCALE, CX, CY)

    _courtyard(s, v, detail=True)

    # visible upper surface, banded by section angle
    bands = [(0.0, 16.26, "#e4eaf0"), (16.26, 62.0, "#dde5ec"), (62.0, 90.0, "#cfd6da"),
             (90.0, 118.0, "#d6dcdf"), (118.0, 163.74, "#dde5ec"), (163.74, 180.0, "#e4eaf0")]
    for (p0, p1, col) in bands:
        s.path(d_annulus(v, _rho(p1), _rho(p0)), w=None, fill=col)
    for phi in (0.0, 16.26, 62.0, 90.0, 118.0, 163.74, 180.0):
        s.path(d_arc(v, _rho(phi), 0, 360), w="fine", color="#8d939a")

    # hidden springing / gutter lines
    for r in (P.R_OUT_00, P.R_IN_00):
        s.path(d_arc(v, r, 0, 360), w="fine", color=GREY, dash=DASH_HID)

    # photovoltaic array, phi 64 to 88
    r_pv0, r_pv1 = _rho(88.0), _rho(64.0)
    s.path(d_annulus(v, r_pv0, r_pv1), w=None, fill="#4a5560")
    n = 144
    for i in range(n):
        t = i * 360.0 / n
        a, b = v.pol(r_pv0, t), v.pol(r_pv1, t)
        s.line(a[0], a[1], b[0], b[1], w="hatch", color="#7d8791")
    for rr in (30.9, 31.8, 32.6):
        s.path(d_arc(v, rr, 0, 360), w="hatch", color="#7d8791")

    # rooflight slots in the inner crown
    for i in range(8):
        t0 = i * 45.0 + 8.0
        s.path(d_ring(v, 27.2, 29.4, t0, t0 + 29.0), w="med", color=INK, fill="#eaf2f7")
        A.text_polar(s, v, 28.3, t0 + 14.5, "ROOFLIGHT", 1.9, "tangent", color="#5c6a76")

    # maintenance walkway on the apex
    s.path(d_annulus(v, 29.4, 30.6), w="fine", color="#9aa0a6", fill="#f0f0ee")
    A.text_polar(s, v, 30.0, 200, "MAINTENANCE WALKWAY  1200 WIDE", 2.0, "tangent",
                 color=GREY, weight="600")

    # rainwater outlets on both gutters
    for i in range(36):
        t = i * 10.0 + 5.0
        for r in (P.R_OUT_00 - 0.5, P.R_IN_00 + 0.5):
            x, y = v.pol(r, t)
            s.circle(x, y, 0.9, w="fine", color=BLUE, fill="#ffffff")

    _grid(s, v)
    A.dim_diameter(s, v, P.R_MAX, 135.0, size=3.0, frac=0.80)
    A.dim_diameter(s, v, P.MAJOR_R, 45.0, text="Ø60000  APEX", size=3.0, frac=0.74)
    A.dim_radial_chain(s, v, [_rho(180.0), _rho(118.0), P.MAJOR_R, _rho(62.0), _rho(0.0)],
                       180.0, size=2.3, total=True)

    x0, y0, x1, y1 = s.area()
    A.north_arrow(s, x1 - 26, y0 + 28)
    A.scale_bar(s, v, x0 + 8, y1 - 26, 20, 4, label="SCALE 1:%d" % SCALE)
    A.legend(s, x0 + 8, y0 + 18, [
        {"kind": "fill", "fill": "#4a5560", "stroke": "#4a5560",
         "label": "Photovoltaic laminate, phi 64°-88°"},
        {"kind": "fill", "fill": "#eaf2f7", "stroke": INK, "label": "Rooflight slot, 8 no."},
        {"kind": "fill", "fill": "#cfd6da", "stroke": "#8d939a",
         "label": "Standing-seam aluminium crown"},
        {"kind": "fill", "fill": "#dde5ec", "stroke": "#8d939a",
         "label": "Curved insulating glass"},
        {"kind": "dot", "stroke": BLUE, "label": "Rainwater outlet, 72 no."},
        {"kind": "line", "stroke": GREY, "dash": DASH_HID, "w": "fine",
         "label": "Springing line / gutter below"},
    ])
    A.notes_block(s, x0 + 8, y1 - 92, "RAINWATER", [
        "The shell drains to two continuous ring gutters",
        "at the springing lines. Outlets at 10° centres",
        "discharge to an attenuation tank beneath the",
        "courtyard; harvested water serves irrigation",
        "and WC flushing.",
        "",
        "Roof area (developed): %s m²" % "{:,.0f}".format(_shell_area()).replace(",", " "),
        "PV array area: %s m²" % "{:,.0f}".format(_shell_area(64.0, 88.0)).replace(",", " "),
    ])
    return s.save(out)


def _shell_area(p0=None, p1=None):
    """Surface area of a band of the torus:  A = 2*pi*R * r * dphi  +  2*pi*r^2*(sin p1 - sin p0)"""
    p0 = P.PHI_SPRING_OUT if p0 is None else p0
    p1 = P.PHI_SPRING_IN if p1 is None else p1
    a0, a1 = math.radians(p0), math.radians(p1)
    return (2 * math.pi * P.MAJOR_R * P.TUBE_R * (a1 - a0)
            + 2 * math.pi * P.TUBE_R ** 2 * (math.sin(a1) - math.sin(a0)))


# ---------------------------------------------------------------------------
# SITE PLAN
# ---------------------------------------------------------------------------
def site_plan(out):
    SC = 500
    s = Sheet("A-010", "Site Plan", "1 : %d" % SC, "A1",
              "Site datum +0.000 = 42.600 AOD", P.PROJECT,
              ["Levels shown are AOD.",
               "Refer to landscape package for planting."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    v = View(s, SC, (x0 + x1) / 2.0, (y0 + y1) / 2.0)

    # site
    s.circle(*v.p(0, 0), v.mm(P.SITE_R), w=None, fill=s.pattern("grass"))
    s.circle(*v.p(0, 0), v.mm(P.SITE_R), w="heavy", color=GREEN, dash="12,4")

    # perimeter service and fire road
    s.path(d_annulus(v, P.RING_ROAD_R - 3.5, P.RING_ROAD_R + 3.5), w=None, fill="#eceae6")
    for r in (P.RING_ROAD_R - 3.5, P.RING_ROAD_R + 3.5):
        s.path(d_arc(v, r, 0, 360), w="thin", color=GREY)
    s.path(d_arc(v, P.RING_ROAD_R, 0, 360), w="hatch", color="#b9b6b0", dash="8,4")

    # southern approach and forecourt
    s.path(d_ring(v, P.R_OUT_00, P.SITE_R, 264.0, 276.0), w=None, fill=s.pattern("paving"))
    s.path(d_ring(v, P.R_OUT_00, P.RING_ROAD_R + 8.0, 250.0, 290.0), w=None,
           fill=s.pattern("paving"))
    s.path(d_ring(v, P.R_OUT_00, P.RING_ROAD_R + 8.0, 250.0, 290.0), w="thin", color=GREY)

    # northern service yard
    s.path(d_ring(v, P.R_OUT_00, P.RING_ROAD_R + 4.0, 78.0, 102.0), w=None,
           fill="#eceae6")
    s.path(d_ring(v, P.R_OUT_00, P.RING_ROAD_R + 4.0, 78.0, 102.0), w="thin", color=GREY)

    # parking bays along the outside of the ring road
    for i in range(64):
        t = i * 360.0 / 64 + 2.8
        if 244 < t < 296 or 74 < t < 106:
            continue
        s.path(d_ring(v, P.RING_ROAD_R + 3.5, P.RING_ROAD_R + 8.5, t, t + 3.4),
               w="hatch", color="#a9a6a0", fill="#f4f3f0")

    # the building, simplified
    s.path(d_annulus(v, P.R_IN_00, P.R_MAX), w=None, fill="#dfe5ea")
    s.path(d_arc(v, P.R_MAX, 0, 360), w="heavy", color=INK)
    s.path(d_arc(v, P.R_IN_00, 0, 360), w="heavy", color=INK)
    s.path(d_arc(v, P.MAJOR_R, 0, 360), w="fine", color="#93a2ad", dash=DASH_HID)
    s.circle(*v.p(0, 0), v.mm(P.R_IN_00), w=None, fill=s.pattern("grass"))
    s.circle(*v.p(0, 0), v.mm(7.2), w="fine", color="#88b2c9", fill=s.pattern("water"))
    for (a0, a1) in ((263, 277), (84, 96)):
        s.path(d_ring(v, P.R_IN_00, P.R_OUT_00, a0, a1), w="med", color=INK,
               fill=s.pattern("paving"))

    # trees
    for ring, count, rad in ((66.0, 40, 3.4), (80.0, 48, 3.0), (96.0, 56, 3.6)):
        for i in range(count):
            t = i * 360.0 / count + (ring % 7)
            if 250 < t < 290 and ring < 90:
                continue
            x, y = v.pol(ring, t)
            s.circle(x, y, v.mm(rad), w="hatch", color="#8fae86", fill="#e4eede")

    # annotation
    A.text_polar(s, v, 46.0, 270, "PRINCIPAL APPROACH", 2.6, "radial", color=INK, weight="600")
    A.text_polar(s, v, 46.0, 90, "SERVICE YARD", 2.6, "radial", color=INK, weight="600")
    A.text_polar(s, v, P.RING_ROAD_R, 200, "PERIMETER FIRE AND SERVICE ROAD  7000 WIDE",
                 2.3, "tangent", color=GREY, weight="600")
    A.text_polar(s, v, 106.0, 45, "SITE BOUNDARY", 2.6, "tangent", color=GREEN, weight="700")
    A.text_polar(s, v, 30.0, 315, "TORUS", 4.4, "tangent", color=INK, weight="700", spacing=2.0)

    A.dim_diameter(s, v, P.R_MAX, 150.0, size=3.0, frac=0.86)
    A.text_polar(s, v, P.RING_ROAD_R + 10.5, 138, "Ø104 000  RING ROAD CENTRELINE",
                 2.4, "tangent", color=GREY, weight="600")
    A.text_polar(s, v, P.SITE_R - 5.0, 225, "Ø236 000  SITE BOUNDARY",
                 2.4, "tangent", color=GREEN, weight="600")

    for t, lvl in ((20, 42.60), (140, 42.35), (250, 42.85), (330, 42.45)):
        x, y = v.pol(72.0, t)
        s.circle(x, y, 1.0, w=None, fill=INK)
        s.text(x + 2.4, y + 1.0, "%.2f" % lvl, 2.1, "start", INK, "500", halo="#ffffff")

    A.north_arrow(s, x1 - 26, y0 + 28)
    A.scale_bar(s, v, x0 + 8, y1 - 26, 50, 5, label="SCALE 1:500")
    A.notes_block(s, x0 + 8, y0 + 16, "SITE STRATEGY", [
        "The building is set at the centre of a circular",
        "clearing, addressed from the south. Vehicles are",
        "held at a perimeter ring road with 268 spaces;",
        "the inner 52 m radius is pedestrian only.",
        "",
        "Fire appliance access is provided around the",
        "whole perimeter, within 45 m of every dry riser",
        "inlet. The courtyard is reached through the",
        "northern gateway (3 550 clear) and the entrance.",
        "",
        "A ground-source borefield sits beneath the",
        "courtyard: 48 boreholes at 140 m deep.",
    ])
    return s.save(out)
