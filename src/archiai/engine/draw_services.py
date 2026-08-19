"""Roof, ceiling and electrical sheets.

Each is drawn on the same PlanBase at the same scale and position as the
architectural plan, so the set overlays. Quantities come from services.py, so
what is drawn and what is scheduled cannot disagree."""

import math
from ..svgkit import (View, d_poly, d_poly_mm, INK, GREY, LIGHT, BLUE, RED,
                      GREEN, f, DASH_HID)
from .. import annot as A
from . import geom2d as G
from . import services as SV
from .draw import PlanBase, ring_path, region_path, _bar_len

AMBER = "#b8791f"
VIOLET = "#6b4fa0"
TEAL = "#1d7a76"


# ---------------------------------------------------------------------------
# Symbols. Sized in metres so they scale with the drawing.
# ---------------------------------------------------------------------------
def _sq(s, v, p, size, w="fine", color=INK, fill="none", rot=0.0):
    h = size / 2.0
    pts = [(-h, -h), (h, -h), (h, h), (-h, h)]
    if rot:
        a = math.radians(rot)
        c, sn = math.cos(a), math.sin(a)
        pts = [(x * c - y * sn, x * sn + y * c) for (x, y) in pts]
    s.path(d_poly(v, [(p[0] + x, p[1] + y) for (x, y) in pts], True),
           w=w, color=color, fill=fill)


def luminaire(s, v, p, size=0.6, emergency=False):
    _sq(s, v, p, size, w="fine", color=AMBER, fill="#fdf3e0")
    a, b = v.p(p[0] - size / 2, p[1]), v.p(p[0] + size / 2, p[1])
    s.line(a[0], a[1], b[0], b[1], w="fine", color=AMBER)
    if emergency:
        x, y = v.p(*p)
        s.circle(x, y, max(0.7, v.mm(size) * 0.30), w="fine", color=RED, fill="#ffffff")


def diffuser(s, v, p, size=0.45, extract=False):
    _sq(s, v, p, size, w="fine", color=TEAL, fill="#e6f2f1")
    h = size / 2.0
    a, b = v.p(p[0] - h, p[1] - h), v.p(p[0] + h, p[1] + h)
    s.line(a[0], a[1], b[0], b[1], w="fine", color=TEAL)
    if not extract:
        c, d = v.p(p[0] - h, p[1] + h), v.p(p[0] + h, p[1] - h)
        s.line(c[0], c[1], d[0], d[1], w="fine", color=TEAL)


def sprinkler(s, v, p, r=0.22):
    x, y = v.p(*p)
    s.circle(x, y, max(0.55, v.mm(r)), w="fine", color=BLUE, fill="#ffffff")
    s.circle(x, y, max(0.2, v.mm(r) * 0.4), w=None, fill=BLUE)


def detector(s, v, p, r=0.32):
    x, y = v.p(*p)
    s.circle(x, y, max(0.75, v.mm(r)), w="fine", color=RED, fill="#ffffff")
    s.text(x, y + 0.7, "S", 1.7, "middle", RED, "700")


def socket(s, v, p, n, size=0.36):
    """Twin socket: the conventional half-round against the wall."""
    x, y = v.p(*p)
    ang = math.degrees(math.atan2(-n[1], n[0]))
    rr = max(0.8, v.mm(size))
    s.path("M %s %s A %s %s 0 0 1 %s %s Z" % (
        f(x - rr * math.cos(math.radians(ang + 90))),
        f(y + rr * math.sin(math.radians(ang + 90))), f(rr), f(rr),
        f(x - rr * math.cos(math.radians(ang - 90))),
        f(y + rr * math.sin(math.radians(ang - 90)))),
        w="fine", color=VIOLET, fill="#f1ecf7")
    ex = x + math.cos(math.radians(ang)) * rr * 1.5
    ey = y - math.sin(math.radians(ang)) * rr * 1.5
    s.line(x, y, ex, ey, w="fine", color=VIOLET)


def floor_box(s, v, p, size=0.4):
    _sq(s, v, p, size, w="fine", color=VIOLET, fill="#ede7f5")
    x, y = v.p(*p)
    s.circle(x, y, max(0.3, v.mm(size) * 0.22), w=None, fill=VIOLET)


def data_outlet(s, v, p, n, size=0.34):
    x, y = v.p(*p)
    r = max(0.8, v.mm(size))
    ang = math.atan2(-n[1], n[0])
    pts = [(x + math.cos(ang) * r, y - math.sin(ang) * r),
           (x + math.cos(ang + 2.4) * r, y - math.sin(ang + 2.4) * r),
           (x + math.cos(ang - 2.4) * r, y - math.sin(ang - 2.4) * r)]
    s.path(d_poly_mm(pts, True), w="fine", color=TEAL, fill="#dff0ef")


def board(s, v, p, label, w_m=1.6, h_m=0.5):
    _sq(s, v, p, max(w_m, h_m), w="med", color=VIOLET, fill=VIOLET)
    x, y = v.p(*p)
    s.text(x, y + 0.9, label, 2.2, "middle", "#ffffff", "700")


def rw_outlet(s, v, p, r=0.35):
    x, y = v.p(*p)
    rr = max(1.0, v.mm(r))
    s.circle(x, y, rr, w="med", color=BLUE, fill="#eaf2f8")
    s.line(x - rr, y, x + rr, y, w="fine", color=BLUE)
    s.line(x, y - rr, x, y + rr, w="fine", color=BLUE)


def fall_arrow(s, v, frm, to, label="1:80"):
    a, b = v.p(*frm), v.p(*to)
    s.line(a[0], a[1], b[0], b[1], w="fine", color=BLUE)
    ang = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))
    A._arrow(s, b[0], b[1], ang, BLUE, L=2.2, w=0.8)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    rot = -ang
    while rot > 90:
        rot -= 180
    while rot <= -90:
        rot += 180
    s.text(mx, my - 1.0, label, 1.9, "middle", BLUE, rot=rot, halo="#ffffff")


# ---------------------------------------------------------------------------
def roof_sheet(project, out, number="A-140", paper="A1"):
    i = len(project.massing.levels) - 1
    rf = SV.roof(project)
    pb = PlanBase(project, i, number, "Roof Plan",
                  "Top of parapet +%.3f" % (project.massing.height + 1.1),
                  ["Falls %s, minimum." % rf["falls"],
                   "Membrane laid to falls on tapered insulation.",
                   "All outlets fitted with leaf guards."], paper)
    s, v = pb.sheet, pb.view
    plate = rf["plate"]

    s.path(region_path(v, plate), w=None, fill="#f0efec", rule="evenodd")
    s.path(region_path(v, plate), w="cut", color=INK, fill="none", rule="evenodd")
    inner = plate.offset(0.30)
    s.path(region_path(v, inner), w="fine", color=GREY, fill="none", rule="evenodd")

    # walkway ring
    walk = plate.offset(2.2)
    s.path(region_path(v, walk), w="fine", color="#9aa0a6", fill="none",
           dash="5,3", rule="evenodd")

    for o in rf["outlets"]:
        c = G.centroid(plate.outer)
        d = math.dist(o, c) or 1.0
        frm = (o[0] + (c[0] - o[0]) / d * 5.5, o[1] + (c[1] - o[1]) / d * 5.5)
        fall_arrow(s, v, frm, o)
        rw_outlet(s, v, o)

    s.path(ring_path(v, rf["plant"]), w="med", color=INK, fill=s.pattern("steel"))
    pc = G.centroid(rf["plant"])
    x, y = v.p(*pc)
    s.text(x, y - 1.2, "PLANT ENCLOSURE", 2.4, "middle", INK, "700", halo="#ffffff")
    s.text(x, y + 2.0, "%.0f m²  ·  louvred, 2 400 high" % rf["plant_area_m2"],
           2.0, "middle", GREY, halo="#ffffff")

    for (p, name) in SV.risers(pb.floorplan):
        _sq(s, v, p, 1.4, w="med", color=INK, fill="#ffffff")
        x, y = v.p(*p)
        s.text(x, y + 0.8, "AOV", 1.9, "middle", INK, "700")

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "dot", "stroke": BLUE, "fill": "#eaf2f8",
             "label": "Rainwater outlet, %d no." % len(rf["outlets"])},
            {"kind": "line", "stroke": BLUE, "w": "fine", "label": "Direction of fall"},
            {"kind": "fill", "fill": "#d7dbe0", "stroke": INK, "label": "Plant enclosure"},
            {"kind": "line", "stroke": "#9aa0a6", "dash": "5,3", "w": "fine",
             "label": "Maintenance walkway, 1 200 wide"},
            {"kind": "fill", "fill": "#ffffff", "stroke": INK,
             "label": "Automatic opening vent over each core"},
        ],
        notes_title="ROOF",
        notes=["Roof area: %s m²" % _sp(rf["area_m2"]),
               "Outlets: %d at %.0f m centres" % (len(rf["outlets"]), 14.0),
               "Plant enclosure: %s m²" % _sp(rf["plant_area_m2"]),
               "Parapet: 1 100 above finished roof level",
               "Fall: %s" % rf["falls"]])
    return s.save(out)


def _sp(v):
    return "{:,.0f}".format(v).replace(",", " ")


# ---------------------------------------------------------------------------
def rcp_sheet(project, i, out, number=None, paper="A1"):
    number = number or "A-15%d" % i
    pb = PlanBase(project, i, number,
                  "%s — Reflected Ceiling Plan" % project.massing.levels[i].name,
                  "Viewed from below · soffit +%.3f above FFL"
                  % (project.massing.levels[i].to_ffl - 0.65),
                  ["Ceiling grid set out from the core; cut tiles to the "
                   "perimeter.",
                   "Coordinate with structure before ordering."], paper)
    s, v = pb.sheet, pb.view
    fp = pb.floorplan
    svc = SV.for_floor(fp)
    tot = SV.totals(svc)

    module = 0.6 * 1000.0 / pb.scale
    ceil_fill = s.grid_pattern("ceil", module, stroke="#cfd6dc", width=0.08)

    for rs in svc:
        r = rs.room
        if rs.ceiling == "grid":
            s.path(ring_path(v, r.ring), w="fine", color="#b9bec4", fill="#fbfcfd")
            s.path(ring_path(v, r.ring), w=None, fill=ceil_fill)
        elif rs.ceiling == "plaster":
            s.path(ring_path(v, r.ring), w="fine", color="#b9bec4", fill="#f2f2ef")
        else:
            s.path(ring_path(v, r.ring), w="fine", color="#b9bec4", fill="#ffffff")

    pb.walls()
    for rs in svc:
        for p in rs.luminaires:
            luminaire(s, v, p)
        for p in rs.supply:
            diffuser(s, v, p)
        for p in rs.extract:
            diffuser(s, v, p, extract=True)
        for p in rs.sprinklers:
            sprinkler(s, v, p)
        for p in rs.detectors:
            detector(s, v, p)

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "fill", "fill": "#fdf3e0", "stroke": AMBER,
             "label": "600 x 600 LED panel, 36 W"},
            {"kind": "fill", "fill": "#e6f2f1", "stroke": TEAL,
             "label": "Supply / extract diffuser"},
            {"kind": "dot", "stroke": BLUE, "fill": "#ffffff", "label": "Sprinkler head"},
            {"kind": "dot", "stroke": RED, "fill": "#ffffff", "label": "Smoke detector"},
            {"kind": "fill", "fill": "#fbfcfd", "stroke": "#cfd6dc",
             "label": "600 exposed grid ceiling"},
            {"kind": "fill", "fill": "#f2f2ef", "stroke": "#b9bec4",
             "label": "Plasterboard, skim and paint"},
        ],
        notes_title="CEILINGS",
        notes=["Luminaires: %d" % tot["luminaires"],
               "Diffusers: %d supply" % tot["supply_terminals"],
               "Sprinkler heads: %d at %.0f m² max coverage"
               % (tot["sprinklers"], SV.SPRINKLER_COVERAGE),
               "Smoke detectors: %d" % tot["detectors"],
               "Grid module: 600 x 600",
               "Soffit height: 2 700 above FFL"])
    return s.save(out)


# ---------------------------------------------------------------------------
def power_sheet(project, i, out, number=None, paper="A1"):
    number = number or "E-10%d" % i
    pb = PlanBase(project, i, number,
                  "%s — Small Power and Data" % project.massing.levels[i].name,
                  "Coordination layout · not a designed installation",
                  ["Final circuit design by the electrical engineer.",
                   "Socket heights 450 above FFL unless noted.",
                   "All containment to be earthed and continuous."], paper)
    s, v = pb.sheet, pb.view
    fp = pb.floorplan
    svc = SV.for_floor(fp)
    tot = SV.totals(svc)

    pb.furniture_ghost()
    pb.walls()

    for route in SV.containment(fp):
        s.path(ring_path(v, route), w="med", color=VIOLET, dash="9,3")

    for rs in svc:
        for (p, n) in rs.sockets:
            socket(s, v, p, n)
        for (p, n) in rs.data:
            data_outlet(s, v, p, n)
        for p in rs.floor_boxes:
            floor_box(s, v, p)

    for (p, name) in SV.risers(fp):
        board(s, v, p, "DB")

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "fill", "fill": "#f1ecf7", "stroke": VIOLET,
             "label": "Twin switched socket, 450 AFFL"},
            {"kind": "fill", "fill": "#ede7f5", "stroke": VIOLET,
             "label": "Floor box, 4 power + 2 data"},
            {"kind": "fill", "fill": "#dff0ef", "stroke": TEAL,
             "label": "Data outlet, 2 x RJ45"},
            {"kind": "fill", "fill": VIOLET, "stroke": VIOLET,
             "label": "Distribution board in core"},
            {"kind": "line", "stroke": VIOLET, "dash": "9,3", "w": "med",
             "label": "Primary containment route"},
        ],
        notes_title="ELECTRICAL LOAD",
        notes=["Sockets: %d twin" % tot["sockets"],
               "Floor boxes: %d" % tot["floor_boxes"],
               "Occupancy: %d people" % tot["occupants"],
               "Small power: %.1f kW at 200 W/person" % tot["small_power_kw"],
               "Lighting: %.1f kW" % tot["lighting_load_kw"],
               "Distribution: one board per core, %d total"
               % len(SV.risers(fp))])
    return s.save(out)


# ---------------------------------------------------------------------------
def lighting_sheet(project, i, out, number=None, paper="A1"):
    number = number or "E-20%d" % i
    pb = PlanBase(project, i, number,
                  "%s — Lighting and Emergency Lighting"
                  % project.massing.levels[i].name,
                  "Lumen method · maintained illuminance at working plane",
                  ["Luminaire count from the lumen method: "
                   "n = E x A / (F x UF x MF).",
                   "UF 0.70, MF 0.90, 4 800 lm luminaire.",
                   "Emergency luminaires on a 3 hour non-maintained supply."],
                  paper)
    s, v = pb.sheet, pb.view
    fp = pb.floorplan
    svc = SV.for_floor(fp)
    tot = SV.totals(svc)

    pb.furniture_ghost()
    pb.walls()

    em_total = 0
    for zi, rs in enumerate(svc):
        r = rs.room
        for k, p in enumerate(rs.luminaires):
            em = (r.cat in ("circ", "core")) or (k % 5 == 0)
            luminaire(s, v, p, emergency=em)
            em_total += 1 if em else 0
        if r.area > 24 and rs.lux:
            cx, cy = v.p(*r.centroid)
            s.text(cx, cy - 1.4, "%d lx" % rs.lux, 2.0, "middle", AMBER, "700",
                   halo="#ffffff")
            s.text(cx, cy + 1.4, "Z%02d · %d no." % (zi + 1, len(rs.luminaires)),
                   1.9, "middle", GREY, halo="#ffffff")

    for (p, name) in SV.risers(fp):
        board(s, v, p, "LB")

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "fill", "fill": "#fdf3e0", "stroke": AMBER,
             "label": "600 x 600 LED panel, 4 800 lm"},
            {"kind": "dot", "stroke": RED, "fill": "#ffffff",
             "label": "Emergency luminaire, 3 hour"},
            {"kind": "fill", "fill": VIOLET, "stroke": VIOLET,
             "label": "Lighting board in core"},
        ],
        notes_title="LIGHTING",
        notes=["Luminaires: %d" % tot["luminaires"],
               "Emergency: %d (%.0f%%)" % (em_total,
                                           100.0 * em_total / max(1, tot["luminaires"])),
               "Connected load: %.1f kW" % tot["lighting_load_kw"],
               "Load density: %.1f W/m²"
               % (tot["lighting_load_kw"] * 1000.0 / max(1.0, pb.level.area)),
               "Office 500 lx · circulation 150 lx",
               "Switching: presence detection per zone"])
    return s.save(out)


# ---------------------------------------------------------------------------
# Fire strategy
# ---------------------------------------------------------------------------
def fire_sheet(project, i, out, number=None, paper="A1"):
    number = number or "FS-10%d" % i
    fp_level = project.massing.levels[i]
    pb = PlanBase(project, i, number,
                  "%s — Fire Strategy" % fp_level.name,
                  "Escape routes and travel distances",
                  ["Travel distance measured as direct line x %.2f, the "
                   "concept-stage allowance for routing." % SV.ROUTE_FACTOR,
                   "To be confirmed by the fire engineer against walked routes.",
                   "Limit %.0f m where escape is possible in more than one "
                   "direction." % SV.ESCAPE_LIMIT_TWO_WAY], paper)
    s, v = pb.sheet, pb.view
    fp = pb.floorplan
    esc = SV.escape(fp)

    pb.furniture_ghost()
    for r in fp.rooms:
        if r.cat in ("core", "plant"):
            s.path(ring_path(v, r.ring), w="med", color=RED, fill="#fbeceb")
    pb.walls()

    for route in esc.routes:
        a, b = v.p(*route["from"]), v.p(*route["to"])
        over = route["travel_m"] > esc.limit
        col = RED if over else "#2f7a4f"
        s.line(a[0], a[1], b[0], b[1], w="med" if over else "thin", color=col,
               dash="7,3")
        ang = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))
        A._arrow(s, b[0], b[1], ang, col, L=2.4, w=0.9)

    worst = sorted(esc.routes, key=lambda r: -r["travel_m"])[:6]
    for route in worst:
        a, b = v.p(*route["from"]), v.p(*route["to"])
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        s.text(mx, my - 1.2, "%.1f m" % route["travel_m"], 2.2, "middle",
               RED if route["travel_m"] > esc.limit else "#2f7a4f", "700",
               halo="#ffffff")

    for (p, name) in SV.risers(fp):
        x, y = v.p(*p)
        s.circle(x, y, 4.6, w="med", color=RED, fill="#ffffff")
        s.text(x, y + 1.2, "EXIT", 2.0, "middle", RED, "700")

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "fill", "fill": "#fbeceb", "stroke": RED,
             "label": "60 minute compartment (core, plant)"},
            {"kind": "line", "stroke": "#2f7a4f", "dash": "7,3", "w": "thin",
             "label": "Escape route within limit"},
            {"kind": "line", "stroke": RED, "dash": "7,3", "w": "med",
             "label": "Escape route exceeding limit"},
            {"kind": "dot", "stroke": RED, "fill": "#ffffff",
             "label": "Protected stair / final exit"},
        ],
        notes_title="FIRE",
        notes=["Worst travel: %.1f m (%s)" % (esc.worst, esc.worst_room or "-"),
               "Limit: %.0f m, two directions" % esc.limit,
               "Status: %s" % ("within limit" if esc.compliant else "EXCEEDS LIMIT"),
               "Protected stairs: %d" % len(SV.risers(fp)),
               "Occupancy: %d at design density" % SV.totals(SV.for_floor(fp))["occupants"],
               "Sprinklers throughout; detection to all areas"])
    return s.save(out)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------
def framing_sheet(project, i, out, number=None, paper="A1"):
    number = number or "S-1%02d" % i
    st = SV.structure(project, i)
    pb = PlanBase(project, i, number,
                  "%s — Framing Plan" % project.massing.levels[i].name,
                  "Concrete flat slab on a %s x %s grid"
                  % (int(st["spacing"][0] * 1000), int(st["spacing"][1] * 1000)),
                  ["Sizes are for coordination. Design by the engineer.",
                   "Slab %d mm; beams %d mm deep."
                   % (st["slab_depth_mm"], st["beam_depth_mm"])], paper)
    s, v = pb.sheet, pb.view
    plate = pb.level.plate
    g = pb.grid

    s.path(region_path(v, plate), w=None, fill="#fbfbfa", rule="evenodd")
    s.path(region_path(v, plate), w="heavy", color=INK, fill="none", rule="evenodd")

    cols = st["columns"]
    colset = set((round(x, 3), round(y, 3)) for (x, y) in cols)
    xs = sorted(set(round(x, 3) for (x, y) in cols))
    ys = sorted(set(round(y, 3) for (x, y) in cols))

    def beam(a, b, primary=True):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        if not plate.contains(mid):
            return
        p, q = v.p(*a), v.p(*b)
        s.line(p[0], p[1], q[0], q[1], w="med" if primary else "thin",
               color=INK if primary else "#5c6a76")

    for y in ys:
        row = [x for x in xs if (round(x, 3), round(y, 3)) in colset]
        for a, b in zip(row, row[1:]):
            beam((a, y), (b, y), True)
    for x in xs:
        col = [y for y in ys if (round(x, 3), round(y, 3)) in colset]
        for a, b in zip(col, col[1:]):
            beam((x, a), (x, b), True)
            beam((x + (xs[1] - xs[0]) / 2.0 if len(xs) > 1 else x, a),
                 (x + (xs[1] - xs[0]) / 2.0 if len(xs) > 1 else x, b), False)

    dia = st["column_size_mm"] / 1000.0
    for (x, y) in cols:
        _sq(s, v, (x, y), dia, w="med", color=INK, fill=INK)

    for r in pb.floorplan.rooms:
        if r.cat == "core":
            s.path(ring_path(v, r.ring), w="heavy", color=INK, fill=s.pattern("steel"))
            cx, cy = v.p(*r.centroid)
            s.text(cx, cy + 0.8, "SHEAR CORE", 2.0, "middle", INK, "700",
                   halo="#ffffff")

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "fill", "fill": INK, "stroke": INK,
             "label": "Column %d x %d" % (st["column_size_mm"], st["column_size_mm"])},
            {"kind": "line", "stroke": INK, "w": "med", "label": "Primary beam"},
            {"kind": "line", "stroke": "#5c6a76", "w": "thin", "label": "Secondary beam"},
            {"kind": "fill", "fill": "#d7dbe0", "stroke": INK,
             "label": "Shear core, in-situ walls"},
        ],
        notes_title="STRUCTURE",
        notes=["Grid: %d x %d" % (int(st["spacing"][0] * 1000),
                                  int(st["spacing"][1] * 1000)),
               "Columns this level: %d" % len(cols),
               "Tributary area: %.0f m²" % st["tributary_m2"],
               "Design UDL: %.1f kN/m² (%.1f dead + %.1f live)"
               % (st["udl_kpa"], SV.DEAD_KPA, SV.LIVE_KPA),
               "Column load: %d kN over %d storeys"
               % (st["column_load_kn"], st["storeys_above"]),
               "Slab %d, beams %d deep" % (st["slab_depth_mm"], st["beam_depth_mm"])])
    return s.save(out)


def foundation_sheet(project, out, number="S-010", paper="A1"):
    fd = SV.foundations(project)
    pb = PlanBase(project, 0, number, "Foundation Plan",
                  "Pad footings on %d kPa allowable bearing" % fd["bearing_kpa"],
                  ["Founding level to be confirmed by ground investigation.",
                   "Pads sized on allowable bearing pressure only; "
                   "settlement not assessed."], paper)
    s, v = pb.sheet, pb.view
    plate = pb.level.plate

    s.path(region_path(v, plate), w="fine", color=GREY, fill="none",
           dash=DASH_HID, rule="evenodd")

    side = fd["pad_m"]
    for (x, y) in fd["pads"]:
        _sq(s, v, (x, y), side, w="med", color=INK, fill=s.pattern("concrete"))
        _sq(s, v, (x, y), side * 0.28, w="fine", color=GREY)

    for r in pb.floorplan.rooms:
        if r.cat == "core":
            ring = G.offset_ring(r.ring, fd["strip_width_m"])
            s.path(ring_path(v, ring), w="med", color=INK, fill=s.pattern("concrete"))
            s.path(ring_path(v, r.ring), w="fine", color=GREY)

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "fill", "fill": "#e9e9e6", "stroke": INK,
             "label": "Pad footing %.0f x %.0f x %.0f"
                      % (fd["pad_m"] * 1000, fd["pad_m"] * 1000, fd["depth_m"] * 1000)},
            {"kind": "fill", "fill": "#e9e9e6", "stroke": INK,
             "label": "Strip footing under core walls, %d wide"
                      % (fd["strip_width_m"] * 1000)},
            {"kind": "line", "stroke": GREY, "dash": DASH_HID, "w": "fine",
             "label": "Building line over"},
        ],
        notes_title="FOUNDATIONS",
        notes=["Pads: %d no." % len(fd["pads"]),
               "Pad size: %.1f x %.1f x %.1f m" % (fd["pad_m"], fd["pad_m"],
                                                   fd["depth_m"]),
               "Design load: %d kN per column" % fd["load_kn"],
               "Allowable bearing: %d kPa" % fd["bearing_kpa"],
               "Concrete: approx %.0f m³" % fd["concrete_m3"],
               "Blinding 50 mm; cover 75 mm to earth face"])
    return s.save(out)


# ---------------------------------------------------------------------------
# Mechanical and public health
# ---------------------------------------------------------------------------
def ventilation_sheet(project, i, out, number=None, paper="A1"):
    number = number or "M-10%d" % i
    pb = PlanBase(project, i, number,
                  "%s — Ventilation" % project.massing.levels[i].name,
                  "Fresh air at %.0f l/s per person" % SV.FRESH_AIR_LPS,
                  ["Air handling units in the roof plant enclosure.",
                   "Risers in each core; horizontal distribution above the "
                   "circulation ceiling.",
                   "Volumes are for coordination, not a designed system."], paper)
    s, v = pb.sheet, pb.view
    fp = pb.floorplan
    svc = SV.for_floor(fp)
    tot = SV.totals(svc)

    pb.furniture_ghost()
    pb.walls()

    for route in SV.containment(fp):
        s.path(ring_path(v, route), w="heavy", color=TEAL, dash="12,4")
        s.path(ring_path(v, route), w="fine", color="#bfe0de")

    for rs in svc:
        for p in rs.supply:
            diffuser(s, v, p)
        for p in rs.extract:
            diffuser(s, v, p, extract=True)
        if rs.airflow_lps:
            cx, cy = v.p(*rs.room.centroid)
            s.text(cx, cy + 2.2, "%d l/s" % rs.airflow_lps, 2.0, "middle", TEAL,
                   "700", halo="#ffffff")

    for (p, name) in SV.risers(fp):
        _sq(s, v, p, 2.0, w="med", color=TEAL, fill="#d6ecea")
        x, y = v.p(*p)
        s.text(x, y + 0.9, "RISER", 2.0, "middle", TEAL, "700")

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "fill", "fill": "#e6f2f1", "stroke": TEAL,
             "label": "Supply diffuser, %d l/s" % SV.TERMINAL_LPS},
            {"kind": "fill", "fill": "#e6f2f1", "stroke": TEAL,
             "label": "Extract grille"},
            {"kind": "line", "stroke": TEAL, "dash": "12,4", "w": "heavy",
             "label": "Primary duct route"},
            {"kind": "fill", "fill": "#d6ecea", "stroke": TEAL,
             "label": "Riser in core"},
        ],
        notes_title="VENTILATION",
        notes=["Occupancy: %d people" % tot["occupants"],
               "Fresh air: %s l/s total" % _sp(tot["fresh_air_lps"]),
               "Supply terminals: %d at %d l/s" % (tot["supply_terminals"],
                                                   SV.TERMINAL_LPS),
               "Air change rate: approx %.1f /h"
               % (tot["fresh_air_lps"] * 3.6 / max(1.0, pb.level.area * 2.7)),
               "Risers: one per core",
               "Heat recovery: 75%% efficient plate exchanger"])
    return s.save(out)


def drainage_sheet(project, out, number="P-100", paper="A1"):
    pb = PlanBase(project, 0, number, "Drainage — Below Ground",
                  "Foul and surface water, gravity to the site connection",
                  ["Invert levels and gradients to the drainage engineer.",
                   "Foul at 1:60 minimum; surface water at 1:100 minimum.",
                   "Rodding access at every change of direction."], paper)
    s, v = pb.sheet, pb.view
    fp = pb.floorplan
    plate = pb.level.plate
    rf = SV.roof(project)

    s.path(region_path(v, plate), w="fine", color=GREY, fill="#fbfbfa",
           dash=DASH_HID, rule="evenodd")

    cores = SV.risers(fp)
    cx, cy = G.centroid(plate.outer)
    x0, y0, x1, y1 = plate.bbox()
    connection = (cx, y0 - 8.0)

    for (p, name) in cores:
        a, b = v.p(*p), v.p(p[0], connection[1] + 4.0)
        s.line(a[0], a[1], b[0], b[1], w="heavy", color="#7a5230")
        c = v.p(p[0], connection[1] + 4.0)
        d = v.p(*connection)
        s.line(c[0], c[1], d[0], d[1], w="heavy", color="#7a5230")
        _sq(s, v, p, 1.6, w="med", color="#7a5230", fill="#f0e6dc")
        x, y = v.p(*p)
        s.text(x, y + 0.8, "SVP", 2.0, "middle", "#7a5230", "700")
        mp = (p[0], connection[1] + 4.0)
        xx, yy = v.p(*mp)
        s.circle(xx, yy, 2.4, w="med", color="#7a5230", fill="#ffffff")
        s.text(xx, yy + 0.8, "MH", 1.8, "middle", "#7a5230", "700")

    for o in rf["outlets"]:
        x, y = v.p(*o)
        s.circle(x, y, 1.6, w="fine", color=BLUE, fill="#eaf2f8")
        a, b = v.p(*o), v.p(o[0], connection[1] + 6.5)
        s.line(a[0], a[1], b[0], b[1], w="fine", color=BLUE, dash="4,3")

    xx, yy = v.p(*connection)
    s.circle(xx, yy, 4.2, w="cut", color="#7a5230", fill="#ffffff")
    s.text(xx, yy + 1.2, "CX", 2.4, "middle", "#7a5230", "700")
    s.text(xx, yy + 9.0, "SITE CONNECTION", 2.2, "middle", INK, "700")

    pb.gridlines()
    pb.finish(
        legend_items=[
            {"kind": "line", "stroke": "#7a5230", "w": "heavy",
             "label": "Foul drain, 150 dia"},
            {"kind": "line", "stroke": BLUE, "dash": "4,3", "w": "fine",
             "label": "Surface water, 110 dia"},
            {"kind": "fill", "fill": "#f0e6dc", "stroke": "#7a5230",
             "label": "Soil and vent pipe in core"},
            {"kind": "dot", "stroke": "#7a5230", "fill": "#ffffff",
             "label": "Manhole / rodding eye"},
        ],
        notes_title="DRAINAGE",
        notes=["Soil stacks: %d, one per core" % len(cores),
               "Rainwater outlets: %d" % len(rf["outlets"]),
               "Roof area drained: %s m²" % _sp(rf["area_m2"]),
               "Design rainfall: 75 mm/h",
               "Foul flow: %s l/s at %d people"
               % (_sp(max(1, SV.totals(SV.for_floor(fp))["occupants"] * 0.03)),
                  SV.totals(SV.for_floor(fp))["occupants"]),
               "Separate systems to the site connection"])
    return s.save(out)
