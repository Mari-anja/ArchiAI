"""Typical bay section (1:50) and envelope details (1:10)."""

import math
from .svgkit import (Sheet, View, d_poly, d_poly_mm, d_arc, INK, GREY, LIGHT,
                     BLUE, RED, GREEN, f, DASH_HID)
from . import annot as A
from . import params as P
from . import program as PG


def _sheet(number, title, sub, scale_text, notes=None):
    return Sheet(number, title, scale_text, "A1", sub, P.PROJECT, notes)


# ---------------------------------------------------------------------------
# Local tube coordinates: u = radius - MAJOR_R, z = height above FFL 00
# ---------------------------------------------------------------------------
def tp(phi, rad=None):
    rad = P.TUBE_R if rad is None else rad
    a = math.radians(phi)
    return (rad * math.cos(a), P.TUBE_Z + rad * math.sin(a))


def profile(rad, p0=None, p1=None, n=140):
    p0 = P.PHI_SPRING_OUT if p0 is None else p0
    p1 = P.PHI_SPRING_IN if p1 is None else p1
    return [tp(p0 + (p1 - p0) * i / n, rad) for i in range(n + 1)]


def callout(s, x, y, tag, sheet_ref, r=5.0, color=RED):
    s.circle(x, y, r, w="med", color=color, fill="#ffffff")
    s.line(x - r, y, x + r, y, w="fine", color=color)
    s.text(x, y - 1.2, tag, 3.0, "middle", color, "700")
    s.text(x, y + 3.6, sheet_ref, 2.2, "middle", color, "500")


# ---------------------------------------------------------------------------
def bay_section(out):
    SC = 50
    s = _sheet("A-301", "Typical Bay — Radial Section", "One 10° bay of the ring",
               "1 : 50",
               notes=["Typical away from cores and openings.",
                      "See A-500 for details 1, 2 and 3."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    cx, base = 250.0, 452.0
    v = View(s, SC, cx, base)
    poche = s.pattern("concrete")
    earth = s.pattern("earth")
    insul = s.pattern("insul")
    steel = s.pattern("steel")

    # ground and made-up levels
    s.path(d_poly(v, [(-9.6, 0), (9.6, 0), (9.6, -2.2), (-9.6, -2.2)], True),
           w=None, fill=earth)
    a, b = v.p(-9.6, 0), v.p(9.6, 0)
    s.line(a[0], a[1], b[0], b[1], w="med", color=INK)

    # shell: outer skin and inner lining
    outer = profile(P.TUBE_R)
    inner = profile(P.TUBE_R - P.ENV_T)
    s.path(d_poly(v, outer + list(reversed(inner)), True), w="cut", color=INK, fill=poche)
    ins = profile(P.TUBE_R - 0.06) + list(reversed(profile(P.TUBE_R - 0.28)))
    s.path(d_poly(v, ins, True), w=None, fill=insul, op=0.9)

    # hoop rib beyond the cut plane
    rib = profile(P.TUBE_R - P.ENV_T - P.RIB_DIA / 2.0)
    s.path(d_poly(v, rib), w="med", color="#6d7581", dash=DASH_HID)

    # floor plates
    for z in (P.FFL_00, P.FFL_01):
        u0, u1 = -P.HALF_CHORD_00, P.HALF_CHORD_00
        if z == P.FFL_00:
            s.path(d_poly(v, [(u0, 0), (u1, 0), (u1, -0.35), (u0, -0.35)], True),
                   w="cut", color=INK, fill=poche)
            s.path(d_poly(v, [(u0, -0.35), (u1, -0.35), (u1, -0.50), (u0, -0.50)], True),
                   w="fine", color=GREY, fill=insul)
        else:
            s.path(d_poly(v, [(u0, z), (u1, z), (u1, z - P.SLAB_T), (u0, z - P.SLAB_T)],
                          True), w="cut", color=INK, fill=poche)
            # raised access floor and suspended ceiling
            s.path(d_poly(v, [(u0, z + 0.15), (u1, z + 0.15), (u1, z), (u0, z)], True),
                   w="fine", color=GREY, fill="#f4f4f1")
            zc = z - P.SLAB_T - P.CEIL_ZONE
            s.path(d_poly(v, [(u0 + 0.4, zc), (u1 - 0.4, zc),
                              (u1 - 0.4, zc + 0.05), (u0 + 0.4, zc + 0.05)], True),
                   w="fine", color=GREY, fill="#efefec")

    # raised access floor at ground level
    s.path(d_poly(v, [(-P.HALF_CHORD_00, 0.15), (P.HALF_CHORD_00, 0.15),
                      (P.HALF_CHORD_00, 0), (-P.HALF_CHORD_00, 0)], True),
           w="fine", color=GREY, fill="#f4f4f1")

    # columns
    for u in (P.COL_RADII[0] - P.MAJOR_R, P.COL_RADII[1] - P.MAJOR_R):
        for (z0, z1) in ((0.15, P.FFL_01 - P.SLAB_T), (P.FFL_01 + 0.15, P.FFL_01 + 3.4)):
            s.path(d_poly(v, [(u - P.COL_DIA / 2, z0), (u + P.COL_DIA / 2, z0),
                              (u + P.COL_DIA / 2, z1), (u - P.COL_DIA / 2, z1)], True),
                   w="med", color=INK, fill=steel)
        # foundation
        s.path(d_poly(v, [(u - 0.9, -0.5), (u + 0.9, -0.5), (u + 0.9, -1.4), (u - 0.9, -1.4)],
                      True), w="med", color=INK, fill=poche)
        s.path(d_poly(v, [(u - 0.25, -1.4), (u + 0.25, -1.4), (u + 0.25, -2.2), (u - 0.25, -2.2)],
                      True), w="fine", color=GREY, fill=poche)

    # continuous ring foundations under the shell springings
    for u in (-P.HALF_CHORD_00, P.HALF_CHORD_00):
        s.path(d_poly(v, [(u - 0.55, -0.15), (u + 0.55, -0.15), (u + 0.55, -1.25),
                          (u - 0.55, -1.25)], True), w="cut", color=INK, fill=poche)

    # ground gutters at the springings
    for u, sgn in ((-P.HALF_CHORD_00, -1), (P.HALF_CHORD_00, 1)):
        gx = u + sgn * 0.42
        s.path(d_poly(v, [(gx - 0.18, 0.02), (gx + 0.18, 0.02), (gx + 0.18, -0.30),
                          (gx - 0.18, -0.30)], True), w="med", color=INK, fill="#eaf0f4")

    # occupants and furniture, for scale
    _fig(s, v, -4.2, 0.15)
    _fig(s, v, 2.6, 0.15)
    _fig(s, v, -1.4, P.FFL_01 + 0.15)
    _fig(s, v, 4.6, P.FFL_01 + 0.15)
    for u in (-5.4, -3.6, 2.6, 4.4):
        for z in (0.15, P.FFL_01 + 0.15):
            s.path(d_poly(v, [(u - 0.8, z + 0.72), (u + 0.8, z + 0.72),
                              (u + 0.8, z + 0.75), (u - 0.8, z + 0.75)], True),
                   w="fine", color=GREY, fill="#e3e9f0")
            for lu in (u - 0.72, u + 0.72):
                a, b = v.p(lu, z), v.p(lu, z + 0.72)
                s.line(a[0], a[1], b[0], b[1], w="fine", color=GREY)

    # headroom limit on Level 01
    for sgn in (-1, 1):
        uu = sgn * (P.R_OUT_01_USABLE - P.MAJOR_R)
        a, b = v.p(uu, P.FFL_01), v.p(uu, P.FFL_01 + P.CLEAR_HEIGHT_MIN)
        s.line(a[0], a[1], b[0], b[1], w="fine", color=RED, dash="3,2")
    x, y = v.p(P.R_OUT_01_USABLE - P.MAJOR_R + 0.1, P.FFL_01 + 1.05)
    s.text(x, y, "2100 HEADROOM LIMIT", 2.0, "start", RED, "600", rot=-90, halo="#ffffff")

    # dimensions and levels
    A.dim_linear(s, v, (-P.HALF_CHORD_00, 0), (P.COL_RADII[0] - P.MAJOR_R, 0), 26.0)
    A.dim_linear(s, v, (P.COL_RADII[0] - P.MAJOR_R, 0), (P.COL_RADII[1] - P.MAJOR_R, 0), 26.0)
    A.dim_linear(s, v, (P.COL_RADII[1] - P.MAJOR_R, 0), (P.HALF_CHORD_00, 0), 26.0)
    A.dim_linear(s, v, (-P.HALF_CHORD_00, 0), (P.HALF_CHORD_00, 0), 36.0)
    A.dim_linear(s, v, (-P.TUBE_R - 0.3, 0), (-P.TUBE_R - 0.3, P.FFL_01), -8.0)
    A.dim_linear(s, v, (-P.TUBE_R - 0.3, P.FFL_01), (-P.TUBE_R - 0.3, P.Z_APEX), -8.0)
    A.dim_linear(s, v, (-P.TUBE_R - 0.3, 0), (-P.TUBE_R - 0.3, P.Z_APEX), -18.0)
    for z, lab in ((P.FFL_00, "LEVEL 00"), (P.FFL_01, "LEVEL 01"), (P.Z_APEX, "APEX")):
        x, y = v.p(P.TUBE_R + 0.5, z)
        A.level_tag(s, x, y, z, lab)
    x, y = v.p(-P.HALF_CHORD_00 + 1.2, P.FFL_01 - P.SLAB_T - P.CEIL_ZONE - 0.15)
    s.text(x, y, "%d CLEAR" % round(P.CLEAR_L00 * 1000), 2.2, "start", INK, "600",
           halo="#ffffff")
    x, y = v.p(-0.8, P.FFL_01 + P.HEAD_L01_CROWN * 0.55)
    s.text(x, y, "%d CLEAR AT CROWN" % round((P.HEAD_L01_CROWN - 0.15) * 1000),
           2.2, "start", INK, "600", halo="#ffffff")

    # detail callouts
    callout(s, *v.p(P.HALF_CHORD_00 + 0.75, 0.55), "1", "A-500")
    callout(s, *v.p(P.HALF_CHORD_00 - 0.15, P.FFL_01 + 0.55), "2", "A-500")
    callout(s, *v.p(1.9, P.Z_APEX - 0.75), "3", "A-500")

    # centreline of the tube
    a, b = v.p(0, -2.6), v.p(0, P.Z_APEX + 1.2)
    s.line(a[0], a[1], b[0], b[1], w="grid", color=BLUE, dash="10,3,2,3")
    x, y = v.p(0, P.Z_APEX + 1.6)
    s.text(x, y, "C̲  TUBE  R 30 000", 2.2, "middle", BLUE, "600")

    s.text(cx - 150, base + 46, "TYPICAL BAY — RADIAL SECTION", 5.2, "start", INK,
           "700", spacing=0.8)
    s.text(cx - 150, base + 53, "Looking clockwise; typical between R01 and R36", 2.4,
           "start", GREY)

    # annotation column
    _bay_notes(s, 432.0, 236.0)
    A.scale_bar(s, v, x0 + 8, y1 - 24, 5, 5, label="SCALE 1:50")
    return s.save(out)


def _fig(s, v, x, z, scale=1.0):
    h = 1.75 * scale
    cx, cy = v.p(x, z + h)
    s.circle(cx, cy + v.mm(h * 0.06), v.mm(h * 0.075), w=None, fill="#6f7681")
    s.path(d_poly(v, [(x - 0.20, z), (x - 0.20, z + h * 0.86),
                      (x + 0.20, z + h * 0.86), (x + 0.20, z)], True),
           w=None, fill="#6f7681", op=0.85)


def _bay_notes(s, x, y):
    rows = [
        ("SHELL", [
            "Curved IGU: 8 mm toughened / 16 argon / 6.8 laminate",
            "low-e, Ug 1.1 W/m²K, g-value 0.28",
            "Radial aluminium mullions at 2.5° with thermal break",
            "Crown: 0.9 aluminium standing seam on 200 rigid",
            "insulation, U 0.13 W/m²K, on steel liner tray",
        ]),
        ("PRIMARY STRUCTURE", [
            "36 no. CHS 457 x 16 hoop ribs at 10° centres,",
            "arc length 27.82 m, springing at radius 22 800",
            "and 37 200 onto continuous ring foundations",
            "CHS 219 x 10 circumferential shell members",
            "Ring grid C2 and C4: CHS 324 x 12.5 columns",
        ]),
        ("FLOORS", [
            "130 mm lightweight concrete on 60 mm composite",
            "deck, 300 mm overall, on radial UB 457 x 191",
            "secondary beams at 5° centres",
            "150 mm raised access floor; 350 mm services and",
            "ceiling zone below the Level 01 slab",
        ]),
        ("SUBSTRUCTURE", [
            "600 mm CFA piles to columns; 1 100 x 900 continuous",
            "ring beam under each springing line",
            "200 mm RC ground bearing slab on 150 mm insulation",
        ]),
        ("ENVIRONMENT", [
            "Mixed mode: openable vents at both springing lines",
            "give cross ventilation across the 14.4 m plate",
            "The outward lean of the shell self-shades the",
            "Level 00 glazing; brise-soleil not required",
            "GSHP borefield beneath the courtyard",
        ]),
    ]
    yy = y
    for title, lines in rows:
        s.text(x, yy, title, 2.4, "start", GREY, "700", spacing=1.0)
        s.line(x, yy + 2.2, x + 190, yy + 2.2, w="hatch", color=LIGHT)
        yy += 6.4
        for ln in lines:
            s.text(x, yy, ln, 2.2, "start", INK)
            yy += 3.4
        yy += 5.0
    return yy


# ---------------------------------------------------------------------------
# 1:10 envelope details
# ---------------------------------------------------------------------------
class Panel:
    """One detail panel: a clipped drawing area with a numbered key beneath."""
    W, H_DWG = 200.0, 176.0

    def __init__(self, sheet, x, y, tag, title, z_origin=0.0, scale=10):
        self.s, self.x, self.y = sheet, x, y
        self.tag, self.title = tag, title
        self.v = View(sheet, scale, x + self.W / 2.0, y + self.H_DWG / 2.0 + z_origin * 1000.0 / scale)
        self.keys = []
        sheet.rect(x, y, self.W, self.H_DWG, w="fine", color=LIGHT, fill="#ffffff")
        sheet.add('<g %s>' % sheet.clip("det-%s" % tag, d_poly_mm(
            [(x, y), (x + self.W, y), (x + self.W, y + self.H_DWG), (x, y + self.H_DWG)], True)))

    def close(self):
        self.s.add("</g>")
        callout(self.s, self.x + 9, self.y + 9, self.tag, "")
        self.s.text(self.x, self.y + self.H_DWG + 7, self.title, 3.2, "start", INK,
                    "700", spacing=0.4)
        self.s.text(self.x, self.y + self.H_DWG + 12, "1 : 10", 2.3, "start", GREY)
        yy = self.y + self.H_DWG + 20
        for i, (u, z, txt) in enumerate(self.keys, 1):
            self.s.text(self.x + 1.4, yy + 1.6, str(i), 2.0, "middle", INK, "700")
            self.s.circle(self.x + 1.4, yy + 0.9, 2.6, w="fine", color=INK)
            self.s.text(self.x + 7, yy + 1.6, txt, 2.15, "start", INK)
            yy += 5.4
        return yy

    def key(self, u, z, txt):
        self.keys.append((u, z, txt))
        x, y = self.v.p(u, z)
        n = len(self.keys)
        self.s.circle(x, y, 2.6, w="fine", color=INK, fill="#ffffff")
        self.s.text(x, y + 0.75, str(n), 2.0, "middle", INK, "700")


def details_sheet(out):
    s = _sheet("A-500", "Envelope Details", "Springing, floor edge and crown",
               "1 : 10", notes=["Detail locations shown on A-301.",
                                "Dimensions in millimetres."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    poche = s.pattern("concrete")
    earth = s.pattern("earth")
    insul = s.pattern("insul")
    steel = s.pattern("steel")
    screed = s.pattern("screed")

    # ---- Detail 1: outer springing at ground level ---------------------
    d = Panel(s, 16.0, 34.0, "1", "OUTER SPRINGING AT GROUND LEVEL", z_origin=0.05)
    v = d.v
    s.path(d_poly(v, [(0.06, 0), (1.60, 0), (1.60, -1.60), (0.06, -1.60)], True),
           w=None, fill=earth)
    s.path(d_poly(v, [(0.06, 0), (1.60, 0), (1.60, -0.06), (0.06, -0.06)], True),
           w="med", color=INK, fill=screed)
    s.path(d_poly(v, [(-0.55, -0.15), (0.55, -0.15), (0.55, -1.60), (-0.55, -1.60)], True),
           w="cut", color=INK, fill=poche)
    s.path(d_poly(v, [(-1.60, 0), (-0.06, 0), (-0.06, -0.20), (-1.60, -0.20)], True),
           w="cut", color=INK, fill=poche)
    s.path(d_poly(v, [(-1.60, -0.20), (-0.06, -0.20), (-0.06, -0.35), (-1.60, -0.35)], True),
           w="fine", color=GREY, fill=insul)
    s.path(d_poly(v, [(-1.60, -0.35), (-0.06, -0.35), (-0.06, -1.60), (-1.60, -1.60)], True),
           w=None, fill=earth)
    # raised access floor
    s.path(d_poly(v, [(-1.60, 0.15), (-0.30, 0.15), (-0.30, 0.12), (-1.60, 0.12)], True),
           w="med", color=INK, fill="#ded9d2")
    for u in (-1.35, -1.00, -0.65):
        s.path(d_poly(v, [(u - 0.015, 0.12), (u + 0.015, 0.12), (u + 0.015, 0),
                          (u - 0.015, 0)], True), w="fine", color=GREY, fill="#eeeeea")
    # gutter
    s.path(d_poly(v, [(0.14, 0.02), (0.50, 0.02), (0.50, -0.30), (0.14, -0.30)], True),
           w="cut", color=INK, fill="#eaf0f4")
    for i in range(8):
        u = 0.16 + i * 0.048
        a, b = v.p(u, 0.02), v.p(u, -0.02)
        s.line(a[0], a[1], b[0], b[1], w="fine", color=GREY)
    # curved glazing rising from the base shoe
    a0, a1 = P.PHI_SPRING_OUT, P.PHI_SPRING_OUT + 22.0
    og = [(x - P.HALF_CHORD_00, z) for (x, z) in profile(P.TUBE_R, a0, a1, 30)]
    ig = [(x - P.HALF_CHORD_00, z) for (x, z) in profile(P.TUBE_R - 0.045, a0, a1, 30)]
    s.path(d_poly(v, og + list(reversed(ig)), True), w="med", color="#4c7fae", fill="#dfe9f1")
    s.path(d_poly(v, [(x - P.HALF_CHORD_00, z) for (x, z) in
                      profile(P.TUBE_R - 0.30, a0, a1, 30)]), w="med", color=INK)
    s.path(d_poly(v, [(-0.15, 0.02), (0.10, 0.02), (0.10, 0.30), (0.015, 0.30),
                      (0.015, 0.13), (-0.15, 0.13)], True), w="med", color=INK, fill=steel)
    s.path(d_poly(v, [(-0.15, 0.02), (0.015, 0.02), (0.015, -0.13), (-0.15, -0.13)], True),
           w="fine", color=GREY, fill=insul)
    d.key(0.02, 0.44, "Curved IGU, 8 / 16 argon / 6.8 laminate")
    d.key(-0.07, 0.09, "Aluminium base shoe with thermal break")
    d.key(0.32, -0.14, "Ring gutter 300 x 300, aluminium, grated")
    d.key(0.00, -0.60, "RC ring beam 1 100 x 900 on 600 CFA piles")
    d.key(-0.85, -0.27, "150 rigid insulation on DPM")
    d.key(-1.15, 0.06, "150 raised access floor on 200 RC slab")
    d.key(0.90, -0.03, "Granite setts on 150 sand-cement bed")
    d.close()

    # ---- Detail 2: Level 01 slab edge ----------------------------------
    d = Panel(s, 232.0, 34.0, "2", "LEVEL 01 SLAB EDGE AT THE SHELL", z_origin=P.FFL_01)
    v = d.v
    zz = P.FFL_01
    s.path(d_poly(v, [(-1.60, zz), (0.0, zz), (0.0, zz - 0.30), (-1.60, zz - 0.30)], True),
           w="cut", color=INK, fill=poche)
    for i in range(11):
        u = -1.58 + i * 0.145
        s.path(d_poly(v, [(u, zz - 0.24), (u + 0.07, zz - 0.30), (u + 0.075, zz - 0.24)],
                      True), w="fine", color=GREY, fill="#dcdcd8")
    s.path(d_poly(v, [(-1.60, zz + 0.15), (-0.22, zz + 0.15), (-0.22, zz + 0.12),
                      (-1.60, zz + 0.12)], True), w="med", color=INK, fill="#ded9d2")
    s.path(d_poly(v, [(-1.60, zz - 0.65), (-0.28, zz - 0.65), (-0.28, zz - 0.70),
                      (-1.60, zz - 0.70)], True), w="med", color=INK, fill="#efefec")
    a0, a1 = P.PHI_L01_OUT - 17.0, P.PHI_L01_OUT + 17.0
    og = [(x - P.HALF_CHORD_01, z) for (x, z) in profile(P.TUBE_R, a0, a1, 40)]
    ig = [(x - P.HALF_CHORD_01, z) for (x, z) in profile(P.TUBE_R - 0.045, a0, a1, 40)]
    s.path(d_poly(v, og + list(reversed(ig)), True), w="med", color="#4c7fae", fill="#dfe9f1")
    s.path(d_poly(v, [(x - P.HALF_CHORD_01, z) for (x, z) in
                      profile(P.TUBE_R - 0.30, a0, a1, 40)]), w="med", color=INK)
    s.path(d_poly(v, [(-0.30, zz), (-0.02, zz), (-0.02, zz - 0.42), (-0.30, zz - 0.42)],
                  True), w="med", color=INK, fill=steel)
    s.path(d_poly(v, [(-0.10, zz + 0.05), (0.05, zz + 0.05), (0.05, zz - 0.10),
                      (-0.10, zz - 0.10)], True), w="med", color=INK, fill=steel)
    d.key(-0.80, zz - 0.15, "130 lightweight concrete on 60 composite deck")
    d.key(-0.16, zz - 0.22, "PFC 300 edge trimmer welded to the rib")
    d.key(-0.02, zz - 0.03, "Transom with thermal break, bolted to trimmer")
    d.key(0.28, zz + 0.50, "Openable vent, actuated, for night purge")
    d.key(-0.90, zz - 0.67, "Perforated metal ceiling, 350 services zone")
    d.key(-1.20, zz + 0.135, "150 raised access floor")
    d.close()

    # ---- Detail 3: crown -----------------------------------------------
    d = Panel(s, 448.0, 34.0, "3", "CROWN WITH INTEGRATED PHOTOVOLTAIC",
              z_origin=P.Z_APEX - 0.22)
    v = d.v
    a0, a1 = 84.0, 96.0

    def band(r0, r1, fill, wgt="fine", col=GREY):
        a = profile(r0, a0, a1, 40)
        b = profile(r1, a0, a1, 40)
        s.path(d_poly(v, a + list(reversed(b)), True), w=wgt, color=col, fill=fill)

    band(P.TUBE_R, P.TUBE_R - 0.014, "#3f4a55", "med", INK)
    band(P.TUBE_R - 0.014, P.TUBE_R - 0.055, "#c8ccd0", "fine", GREY)
    band(P.TUBE_R - 0.055, P.TUBE_R - 0.255, insul, "fine", GREY)
    band(P.TUBE_R - 0.255, P.TUBE_R - 0.295, "#d7dbe0", "med", INK)
    band(P.TUBE_R - 0.325, P.TUBE_R - 0.360, "#efefec", "fine", GREY)
    for t in (86.0, 94.0):
        px, pz = tp(t, P.TUBE_R - 0.41)
        s.circle(*v.p(px, pz), v.mm(P.PURLIN_DIA / 2), w="med", color=INK, fill=steel)
    px, pz = tp(90.0, P.TUBE_R - 0.30)
    d.key(*tp(88.0, P.TUBE_R + 0.05), "PV laminate bonded to the standing seam")
    d.key(*tp(92.5, P.TUBE_R - 0.035), "0.9 aluminium standing seam, 400 bays")
    d.key(*tp(87.0, P.TUBE_R - 0.155), "200 rigid insulation, U 0.13 W/m²K")
    d.key(*tp(92.0, P.TUBE_R - 0.275), "Steel liner tray, vapour control layer")
    d.key(*tp(86.0, P.TUBE_R - 0.41), "CHS 219 x 10 circumferential purlin")
    d.key(*tp(94.5, P.TUBE_R - 0.343), "Perforated acoustic soffit lining")
    d.close()

    # ---- Detail 4: courtyard springing at ground level ------------------
    d = Panel(s, 16.0, 300.0, "4", "COURTYARD SPRINGING AT GROUND LEVEL", z_origin=0.05)
    v = d.v
    s.path(d_poly(v, [(-1.60, 0), (-0.06, 0), (-0.06, -1.60), (-1.60, -1.60)], True),
           w=None, fill=earth)
    s.path(d_poly(v, [(-1.60, 0.02), (-0.60, 0.02), (-0.60, -0.55), (-1.60, -0.55)], True),
           w="fine", color=GREY, fill="#eef3ea")
    s.path(d_poly(v, [(-0.60, 0), (-0.06, 0), (-0.06, -0.06), (-0.60, -0.06)], True),
           w="med", color=INK, fill=screed)
    s.path(d_poly(v, [(-0.55, -0.15), (0.55, -0.15), (0.55, -1.60), (-0.55, -1.60)], True),
           w="cut", color=INK, fill=poche)
    s.path(d_poly(v, [(0.06, 0), (1.60, 0), (1.60, -0.20), (0.06, -0.20)], True),
           w="cut", color=INK, fill=poche)
    s.path(d_poly(v, [(0.06, -0.20), (1.60, -0.20), (1.60, -0.35), (0.06, -0.35)], True),
           w="fine", color=GREY, fill=insul)
    s.path(d_poly(v, [(0.06, -0.35), (1.60, -0.35), (1.60, -1.60), (0.06, -1.60)], True),
           w=None, fill=earth)
    s.path(d_poly(v, [(0.30, 0.15), (1.60, 0.15), (1.60, 0.12), (0.30, 0.12)], True),
           w="med", color=INK, fill="#ded9d2")
    s.path(d_poly(v, [(-0.50, 0.02), (-0.14, 0.02), (-0.14, -0.30), (-0.50, -0.30)], True),
           w="cut", color=INK, fill="#eaf0f4")
    for i in range(8):
        u = -0.48 + i * 0.048
        a, b = v.p(u, 0.02), v.p(u, -0.02)
        s.line(a[0], a[1], b[0], b[1], w="fine", color=GREY)
    a0, a1 = P.PHI_SPRING_IN, P.PHI_SPRING_IN - 22.0
    og = [(x + P.HALF_CHORD_00, z) for (x, z) in profile(P.TUBE_R, a0, a1, 30)]
    ig = [(x + P.HALF_CHORD_00, z) for (x, z) in profile(P.TUBE_R - 0.045, a0, a1, 30)]
    s.path(d_poly(v, og + list(reversed(ig)), True), w="med", color="#4c7fae", fill="#dfe9f1")
    s.path(d_poly(v, [(x + P.HALF_CHORD_00, z) for (x, z) in
                      profile(P.TUBE_R - 0.30, a0, a1, 30)]), w="med", color=INK)
    s.path(d_poly(v, [(0.15, 0.02), (-0.10, 0.02), (-0.10, 0.30), (-0.015, 0.30),
                      (-0.015, 0.13), (0.15, 0.13)], True), w="med", color=INK, fill=steel)
    d.key(-0.02, 0.44, "Curved IGU with openable vent at every third bay")
    d.key(0.07, 0.09, "Base shoe with thermal break, level threshold")
    d.key(-0.32, -0.14, "Courtyard gutter 300 x 300 with leaf guard")
    d.key(0.00, -0.60, "RC ring beam 1 100 x 900 on 600 CFA piles")
    d.key(-1.05, -0.26, "Courtyard build-up: 550 growing medium on drainage")
    d.key(1.15, 0.06, "150 raised access floor on 200 RC slab")
    d.close()

    _perf_table(s, 232.0, 306.0)
    _fixing_note(s, 232.0, 386.0)
    A.scale_bar(s, View(s, 10, 0, 0), 232.0, 520.0, 1.0, 4, label="SCALE 1:10")
    return s.save(out)


def _fixing_note(s, x, y):
    s.text(x, y, "GENERAL DETAIL NOTES", 2.6, "start", GREY, "700", spacing=1.0)
    s.line(x, y + 3.0, x + 400, y + 3.0, w="thin", color=GREY)
    lines = [
        "Every glazing unit on the shell is cold-bent to a single radius of 7 500 about the",
        "tube axis; the panel is developable in one direction only, so no panel is doubly curved.",
        "Units repeat identically around the ring, giving 144 types per section band rather than",
        "144 x 36 unique panels.",
        "",
        "The shell is set out from the tube centreline at radius 30 000 and height +2.100.",
        "Section angle phi is measured from the outermost point of the tube, positive upwards.",
        "",
        "All steelwork galvanised and factory finished. Site welds to be tested to BS EN ISO 17637.",
        "Movement joints at radial gridlines R09, R18, R27 and R36 through the ground slab only;",
        "the shell is continuous and accommodates movement through its own curvature.",
        "",
        "Thermal bridging at every base shoe broken by a 30 mm structural thermal break pad;",
        "psi-value 0.08 W/m·K assumed in the fabric energy calculation.",
    ]
    yy = y + 8.0
    for ln in lines:
        s.text(x, yy, ln, 2.2, "start", INK)
        yy += 3.6
    return yy


def _perf_table(s, x, y):
    s.text(x, y, "ENVELOPE PERFORMANCE", 2.6, "start", GREY, "700", spacing=1.0)
    s.line(x, y + 3.0, x + 400, y + 3.0, w="thin", color=GREY)
    rows = [
        ("ELEMENT", "BUILD-UP", "U-VALUE", "AREA"),
        ("Curved glazing", "8 toughened / 16 argon / 6.8 laminate, low-e", "1.10 W/m²K", "3 690 m²"),
        ("Crown", "0.9 aluminium standing seam / 200 PIR / liner tray", "0.13 W/m²K", "1 554 m²"),
        ("Ground slab", "200 RC / 150 PIR / DPM / 150 blinding", "0.15 W/m²K", "2 714 m²"),
        ("Rooflights", "Triple glazed, argon filled, 8 no. slots", "1.30 W/m²K", "178 m²"),
        ("Air permeability", "Whole-building test at 50 Pa", "3.0 m³/h·m²", "—"),
    ]
    yy = y + 8.0
    for i, r in enumerate(rows):
        wt = "700" if i == 0 else "400"
        col = GREY if i == 0 else INK
        sz = 2.0 if i == 0 else 2.2
        for dx, txt in zip((0, 78, 268, 340), r):
            s.text(x + dx, yy, txt, sz, "start", col, wt, spacing=0.6 if i == 0 else None)
        yy += 5.0
        if i == 0:
            s.line(x, yy - 3.2, x + 400, yy - 3.2, w="hatch", color=LIGHT)
    return yy
