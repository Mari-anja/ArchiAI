"""Cover sheet, drawing register and area schedule."""

import math
from .svgkit import (Sheet, View, d_arc, d_annulus, d_poly_mm, INK, GREY, LIGHT,
                     BLUE, RED, GREEN, f)
from . import annot as A
from . import params as P
from . import program as PG
from . import axo

REGISTER = [
    ("A-000", "Cover Sheet and Drawing Register", "—",              "A1"),
    ("A-010", "Site Plan",                        "1:500",          "A1"),
    ("A-100", "Level 00 — Ground Floor Plan",     "1:150",          "A1"),
    ("A-101", "Level 01 — First Floor Plan",      "1:150",          "A1"),
    ("A-102", "Roof Plan",                        "1:150",          "A1"),
    ("A-200", "Elevations — South and East",      "1:150",          "A1"),
    ("A-201", "Elevations — North and West",      "1:150",          "A1"),
    ("A-202", "Developed Elevations",             "1:200",          "A1"),
    ("A-300", "Sections A-A and B-B",             "1:150",          "A1"),
    ("A-301", "Typical Bay — Radial Section",     "1:50",           "A1"),
    ("A-500", "Envelope Details",                 "1:10",           "A1"),
    ("A-600", "Level 01 Framing Plan",            "1:150",          "A1"),
    ("A-700", "Area Schedule and Accommodation",  "—",              "A1"),
    ("A-800", "Axonometric and Assembly",         "1:300 / 1:620",  "A1"),
]

MODEL_FILES = [
    ("torus-office.obj",  "Wavefront mesh, 17 named groups, metres"),
    ("torus-office.mtl",  "Material library for the mesh"),
    ("torus-office.scad", "Parametric OpenSCAD source"),
    ("viewer.html",       "Self-contained WebGL viewer"),
]


# ---------------------------------------------------------------------------
def cover_sheet(out):
    s = Sheet("A-000", "Cover Sheet and Drawing Register", "—", "A1",
              "Stage 3 spatial coordination issue", P.PROJECT)
    s.frame()
    x0, y0, x1, y1 = s.area()

    s.text(x0 + 14, y0 + 44, "TORUS", 34.0, "start", INK, "700", spacing=6.0)
    s.text(x0 + 14, y0 + 58, "A two-storey office pavilion on a circular clearing",
           5.0, "start", GREY, "400")
    s.line(x0 + 14, y0 + 66, x0 + 300, y0 + 66, w="med", color=INK)

    facts = [
        ("Overall diameter",        "75 000"),
        ("Courtyard diameter",      "45 000"),
        ("Height to shell apex",    "9 600"),
        ("Floor plate depth",       "14 400"),
        ("Gross internal area",     "%s m²" % _sp(PG.gia(0) + PG.gia(1))),
        ("Workstations shown",      "%d" % (PG.desks(0)[1] + PG.desks(1)[1])),
        ("Developed envelope",      "5 244 m²"),
        ("Hoop ribs",               "36 at 10.00°"),
    ]
    yy = y0 + 84
    for k, val in facts:
        s.text(x0 + 14, yy, k.upper(), 2.1, "start", GREY, "600", spacing=0.7)
        s.text(x0 + 120, yy, val, 3.6, "start", INK, "600")
        s.line(x0 + 14, yy + 3.4, x0 + 200, yy + 3.4, w="hatch", color=LIGHT)
        yy += 11.0

    # hero
    axo.cutaway(s, 452.0, 232.0, 1000.0 / 460.0)
    s.text(330.0, 350.0, "Cutaway axonometric from the south-west", 2.4, "start", GREY)

    # register
    ry = 384.0
    s.text(x0 + 14, ry, "DRAWING REGISTER", 3.0, "start", GREY, "700", spacing=1.4)
    s.line(x0 + 14, ry + 3.6, x1 - 14, ry + 3.6, w="med", color=INK)
    ry += 10.0
    cols = [(0, "NUMBER"), (50, "TITLE"), (222, "SCALE @ A1"), (272, "SIZE")]
    half = (len(REGISTER) + 1) // 2
    for ci, chunk in enumerate((REGISTER[:half], REGISTER[half:])):
        bx = x0 + 14 + ci * 306
        for dx, lab in cols:
            s.text(bx + dx, ry, lab, 2.0, "start", GREY, "600", spacing=0.7)
        s.line(bx, ry + 2.4, bx + 296, ry + 2.4, w="hatch", color=LIGHT)
        yy2 = ry + 8.0
        for (num, title, scale, size) in chunk:
            s.text(bx + 0,   yy2, "%s-%s" % (P.PROJECT["number"], num), 2.3, "start", INK, "600")
            s.text(bx + 50,  yy2, title, 2.3, "start", INK)
            s.text(bx + 222, yy2, scale, 2.3, "start", GREY)
            s.text(bx + 272, yy2, size, 2.3, "start", GREY)
            yy2 += 6.4

    my = ry + 8.0 + 7 * 6.4 + 14.0
    s.text(x0 + 14, my, "MODEL AND SOURCE", 3.0, "start", GREY, "700", spacing=1.4)
    s.line(x0 + 14, my + 3.6, x1 - 14, my + 3.6, w="med", color=INK)
    my += 10.0
    for (name, desc) in MODEL_FILES:
        s.text(x0 + 14, my, name, 2.4, "start", INK, "600")
        s.text(x0 + 14 + 90, my, desc, 2.4, "start", GREY)
        my += 6.0

    s.text(x0 + 14, y1 - 14, "Every drawing in this set is generated from one "
           "parametric model; change a dimension and the whole set regenerates.",
           2.4, "start", GREY, italic=True)
    A.north_arrow(s, x1 - 30, y0 + 30)
    return s.save(out)


def _sp(v):
    return "{:,.0f}".format(v).replace(",", " ")


# ---------------------------------------------------------------------------
def schedule_sheet(out):
    s = Sheet("A-700", "Area Schedule and Accommodation", "—", "A1",
              "Areas computed from the parametric model", P.PROJECT,
              ["Areas are net internal to the sector",
               "boundaries shown on A-100 and A-101."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    COL_W, ROW = 206.0, 6.4

    def table(bx, by, title, rooms, level):
        s.text(bx, by, title, 3.4, "start", INK, "700", spacing=1.2)
        s.line(bx, by + 4.0, bx + COL_W, by + 4.0, w="med", color=INK)
        yy = by + 11.0
        for dx, lab in ((0, "CODE"), (26, "SPACE"), (146, "SECTOR"), (COL_W, "AREA m²")):
            s.text(bx + dx, yy, lab, 2.0, "start" if dx < COL_W else "end", GREY,
                   "600", spacing=0.7)
        s.line(bx, yy + 2.6, bx + COL_W, yy + 2.6, w="hatch", color=LIGHT)
        yy += 8.4
        for r in rooms:
            s.rect(bx - 5.0, yy - 2.6, 3.2, 3.2, w=None, fill=r.fill)
            s.text(bx + 0,   yy, r.code, 2.4, "start", GREY)
            s.text(bx + 26,  yy, r.name, 2.4, "start", INK)
            s.text(bx + 146, yy, "%g–%g°" % (r.t0, r.t1), 2.2, "start", GREY)
            s.text(bx + COL_W, yy, _sp(r.area), 2.4, "end", INK)
            yy += ROW
        loop = math.pi * (P.R_LOOP ** 2 - P.R_IN_00 ** 2)
        s.rect(bx - 5.0, yy - 2.6, 3.2, 3.2, w=None, fill=PG.CATEGORY["circ"][0])
        s.text(bx + 26, yy, "Courtyard loop circulation", 2.4, "start", INK)
        s.text(bx + COL_W, yy, _sp(loop), 2.4, "end", INK)
        yy += ROW + 1.0
        s.line(bx, yy - 3.4, bx + COL_W, yy - 3.4, w="thin", color=INK)
        s.text(bx + 26, yy, "GROSS INTERNAL AREA", 2.6, "start", INK, "700")
        s.text(bx + COL_W, yy, _sp(PG.gia(level)), 3.0, "end", INK, "700")
        return yy + 12.0

    cx1, cx2, cx3 = x0 + 18, x0 + 248, x0 + 478
    y_a = table(cx1, y0 + 18, "LEVEL 00  ·  FFL +0.000", PG.schedule(0), 0)
    y_b = table(cx2, y0 + 18, "LEVEL 01  ·  FFL +4.200", PG.schedule(1), 1)

    # ---- key metrics, under Level 00 -----------------------------------
    desks = PG.desks(0)[1] + PG.desks(1)[1]
    gia = PG.gia(0) + PG.gia(1)
    footprint = math.pi * (P.R_OUT_00 ** 2 - P.R_IN_00 ** 2)
    site = math.pi * P.SITE_R ** 2
    metrics = [
        ("Gross internal area", "%s m²" % _sp(gia)),
        ("Level 00 / Level 01", "%s / %s m²" % (_sp(PG.gia(0)), _sp(PG.gia(1)))),
        ("Building footprint", "%s m²" % _sp(footprint)),
        ("Courtyard", "%s m²" % _sp(math.pi * P.R_IN_00 ** 2)),
        ("Site area", "%s m²" % _sp(site)),
        ("Site coverage", "%.1f %%" % (100.0 * footprint / site)),
        ("Workstations drawn", "%d" % desks),
        ("Area per workstation", "%.1f m²" % (gia / desks)),
        ("Design occupancy at 1:8", "%d people" % round(gia / 8.0)),
        ("Focus and meeting cells", "%d on Level 01" % len(PG.focus_rooms())),
        ("Developed envelope", "5 244 m²"),
        ("Wall-to-floor ratio", "%.2f" % (5244.0 / gia)),
        ("Facade length, outer", "%.1f m" % (2 * math.pi * P.R_MAX)),
        ("Facade length, courtyard", "%.1f m" % (2 * math.pi * P.R_MIN)),
        ("Max distance to daylight", "7 200"),
        ("Max travel to a protected stair", "23.6 m"),
    ]
    s.text(cx1, y_a, "KEY METRICS", 3.4, "start", INK, "700", spacing=1.2)
    s.line(cx1, y_a + 4.0, cx1 + COL_W, y_a + 4.0, w="med", color=INK)
    yy = y_a + 12.0
    for k, v in metrics:
        s.text(cx1, yy, k, 2.4, "start", GREY)
        s.text(cx1 + COL_W, yy, v, 2.6, "end", INK, "600")
        s.line(cx1, yy + 2.0, cx1 + COL_W, yy + 2.0, w="hatch", color=LIGHT)
        yy += 7.0

    # ---- area by category, under Level 01 -------------------------------
    s.text(cx2, y_b, "AREA BY CATEGORY", 3.4, "start", INK, "700", spacing=1.2)
    s.line(cx2, y_b + 4.0, cx2 + COL_W, y_b + 4.0, w="med", color=INK)
    agg = {}
    for lv in (0, 1):
        for k, v in PG.by_category(lv).items():
            agg[k] = agg.get(k, 0.0) + v
    agg["circ"] = agg.get("circ", 0.0) + 2 * math.pi * (P.R_LOOP ** 2 - P.R_IN_00 ** 2)
    agg.pop("void", None)
    agg.pop("ext", None)
    mx = max(agg.values())
    yy = y_b + 13.0
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1]):
        fill, stroke, label = PG.CATEGORY[k]
        s.text(cx2, yy, label, 2.4, "start", INK)
        s.rect(cx2 + 78, yy - 3.0, 88.0 * v / mx, 3.8, w="fine", color=stroke, fill=fill)
        s.text(cx2 + COL_W, yy, _sp(v), 2.4, "end", INK)
        yy += 7.0
    yy += 10.0

    # ---- accommodation standards ---------------------------------------
    s.text(cx2, yy, "SPACE STANDARDS APPLIED", 3.4, "start", INK, "700", spacing=1.2)
    s.line(cx2, yy + 4.0, cx2 + COL_W, yy + 4.0, w="med", color=INK)
    yy += 12.0
    for k, v in [
            ("Workstation", "1 600 x 800, benched 3 x 2"),
            ("Desk row pitch", "3 000 including 1 400 aisle"),
            ("Focus room", "3 600 x 2 800 nominal"),
            ("Meeting room, 8 person", "24 m²"),
            ("Circulation loop", "3 200 clear"),
            ("Ceiling height, Level 00", "3 550 clear"),
            ("Ceiling height, Level 01", "2 100 to 5 400, curved soffit"),
            ("Raised floor", "150 with 350 services above"),
            ("Occupancy density", "1 : 8 m² for services design"),
            ("Cycle spaces", "180 in the northern gateway"),
    ]:
        s.text(cx2, yy, k, 2.4, "start", GREY)
        s.text(cx2 + COL_W, yy, v, 2.4, "end", INK, "600")
        s.line(cx2, yy + 2.0, cx2 + COL_W, yy + 2.0, w="hatch", color=LIGHT)
        yy += 7.0

    # ---- narrative column ----------------------------------------------
    yy = y0 + 18
    yy = A.notes_block(s, cx3, yy, "FIRE STRATEGY", [
        "Purpose group 3, offices. Two storeys with the top",
        "storey at +4.200, so no firefighting shaft is",
        "required; each of the four cores carries a protected",
        "escape stair 1 400 wide discharging directly to",
        "open air at the perimeter.",
        "",
        "The ring plan gives every occupant two directions of",
        "travel along the courtyard loop. Maximum travel to a",
        "protected stair is 23.6 m, against a 45 m limit where",
        "escape is possible in more than one direction.",
        "",
        "Occupancy 657 at 1:8. Stair capacity 4 x 1 400 gives",
        "4 x 220 = 880 persons, so the building clears on",
        "three stairs with the fourth discounted.",
        "",
        "Each core and the plant zone is a 60 minute",
        "compartment. Shell steelwork is intumescent coated",
        "to 60 minutes. The undercroft at the northern",
        "gateway is treated as external.",
        "",
        "Fire appliance access is provided around the whole",
        "perimeter road; dry riser inlets at each core are",
        "all within 45 m of hardstanding.",
    ], size=2.35, lead=3.6) + 10.0
    yy = A.notes_block(s, cx3, yy, "ACCESSIBILITY", [
        "Level threshold at every entrance: the external",
        "ground plane and FFL 00 share one datum all round,",
        "so there is no ramp anywhere on the approach.",
        "",
        "Two 13-person lifts in each core, 1 100 x 2 100.",
        "An accessible WC in every core, eight in total.",
        "",
        "The courtyard loop is level and 3 200 wide with",
        "seating at not more than 50 m centres, so no",
        "journey inside the building exceeds that between",
        "rests.",
        "",
        "Refuge space at each stair lobby: two wheelchair",
        "spaces per core with two-way communication.",
    ], size=2.35, lead=3.6) + 10.0
    A.notes_block(s, cx3, yy, "ENERGY AND SERVICES", [
        "Ground-source heat pumps on a 48-borehole field",
        "under the courtyard, 140 m deep, seasonal COP 4.1.",
        "",
        "628 m² of photovoltaic laminate integrated into the",
        "crown standing seam between phi 64° and 88°,",
        "estimated 118 MWh a year.",
        "",
        "Mixed-mode ventilation. The 14 400 plate is open to",
        "both facades, so cross ventilation reaches the whole",
        "floor; actuated vents at both springing lines drive",
        "night purge through the curved soffit.",
        "",
        "Rainwater from the two ring gutters is attenuated",
        "under the courtyard and reused for irrigation and",
        "WC flushing.",
        "",
        "Target 55 kWh/m²/yr including small power.",
    ], size=2.35, lead=3.6)
    return s.save(out)
