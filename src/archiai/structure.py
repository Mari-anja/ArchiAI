"""Structural framing plan and member schedule."""

import math
from .svgkit import (Sheet, View, d_arc, d_ring, d_annulus, d_poly, INK, GREY,
                     LIGHT, BLUE, RED, f, DASH_HID)
from . import annot as A
from . import params as P
from . import program as PG

SCALE = 150
CX, CY = 322.0, 297.0


def framing_plan(out):
    s = Sheet("A-600", "Level 01 Framing Plan", "1 : %d" % SCALE, "A1",
              "Steel frame; shell ribs shown over", P.PROJECT,
              ["Sizes are for coordination only.",
               "Refer to the engineer's package for design."])
    s.frame()
    v = View(s, SCALE, CX, CY)

    s.circle(*v.p(0, 0), v.mm(P.R_IN_00), w=None, fill="#f7f8f6")
    s.path(d_annulus(v, P.R_IN_00, P.R_OUT_00), w=None, fill="#fbfbfa")

    # composite deck span direction, indicated
    for i in range(P.RADIAL_DIV * 2):
        t = i * P.SECONDARY_STEP + P.SECONDARY_STEP / 2.0
        a, b = v.pol(P.R_IN_00 + 0.4, t), v.pol(P.R_OUT_00 - 0.4, t)
        s.line(a[0], a[1], b[0], b[1], w="hatch", color="#cfd4d9", dash="1.5,1.5")

    # hoop ribs over, dashed
    for i in range(P.RADIAL_DIV):
        t = i * P.RADIAL_STEP
        a, b = v.pol(P.R_IN_00, t), v.pol(P.R_OUT_00, t)
        s.line(a[0], a[1], b[0], b[1], w="fine", color="#9aa0a6", dash=DASH_ABOVE
               if False else "8,3")

    # ring beams on the grid
    for i, r in enumerate(P.RING_GRID):
        wgt = "med" if r in P.COL_RADII else "thin"
        col = INK if r in P.COL_RADII else "#5c6a76"
        s.path(d_arc(v, r, 0, 360), w=wgt, color=col)

    # edge trimmers
    for r in (P.R_IN_00, P.R_OUT_00):
        s.path(d_arc(v, r, 0, 360), w="heavy", color=INK)

    # radial secondary beams at 5 degrees
    for i in range(P.RADIAL_DIV * 2):
        t = i * P.SECONDARY_STEP
        primary = (i % 2 == 0)
        a, b = v.pol(P.R_IN_00, t), v.pol(P.R_OUT_00, t)
        s.line(a[0], a[1], b[0], b[1], w="med" if primary else "thin",
               color=INK if primary else "#5c6a76")

    # columns
    for i in range(P.RADIAL_DIV):
        t = i * P.RADIAL_STEP
        for r in P.COL_RADII:
            x, y = v.pol(r, t)
            s.circle(x, y, v.mm(P.COL_DIA / 2.0) * 1.5, w="fine", color=INK, fill=INK)

    # core braced bays, highlighted
    for (cid, tc, half) in P.CORES:
        s.path(d_ring(v, 28.4, 32.2, tc - half, tc - 0.4), w="med", color=RED,
               fill="#fbeceb")
        for k in (0, 1):
            a = v.pol(28.4 if k == 0 else 32.2, tc - half)
            b = v.pol(32.2 if k == 0 else 28.4, tc - 0.4)
            s.line(a[0], a[1], b[0], b[1], w="med", color=RED)
        A.text_polar(s, v, 30.3, tc - half / 2.0, "BRACED BAY", 1.9, "tangent",
                     color=RED, weight="700")

    # openings framed out
    for (a0, a1, lab) in ((263.0, 277.0, "ENTRANCE"), (84.0, 96.0, "GATEWAY")):
        s.path(d_ring(v, P.R_IN_00, P.R_OUT_00, a0, a1), w="med", color=RED,
               fill="none", dash="6,3")

    # grid
    labels = [P.grid_label(i) for i in range(P.RADIAL_DIV)]
    thetas = [i * P.RADIAL_STEP for i in range(P.RADIAL_DIV)]
    A.radial_grid(s, v, thetas, 20.6, P.R_OUT_00, labels, bubble_at=40.6)
    A.ring_grid(s, v, P.RING_GRID, P.RING_LABELS, t_label=0.0, bubble_r=3.4)

    A.dim_radial_chain(s, v, [P.R_IN_00] + P.COL_RADII + [P.R_OUT_00], 180.0,
                       size=2.4, total=True)
    A.dim_angular(s, v, 38.9, 0, 5, "5.00°")

    x0, y0, x1, y1 = s.area()
    A.north_arrow(s, x1 - 26, y0 + 28)
    A.scale_bar(s, v, x0 + 8, y1 - 26, 20, 4, label="SCALE 1:%d" % SCALE)
    A.legend(s, x0 + 8, y0 + 18, [
        {"kind": "line", "stroke": INK, "w": "heavy", "label": "Edge trimmer, PFC 300"},
        {"kind": "line", "stroke": INK, "w": "med", "label": "Primary radial beam, UB 457x191"},
        {"kind": "line", "stroke": "#5c6a76", "w": "thin", "label": "Secondary radial beam, UB 305x165"},
        {"kind": "line", "stroke": INK, "w": "med", "label": "Ring beam on C2 / C4"},
        {"kind": "line", "stroke": "#9aa0a6", "w": "fine", "dash": "8,3", "label": "CHS 457x16 hoop rib over"},
        {"kind": "dot", "stroke": INK, "fill": INK, "label": "CHS 324x12.5 column"},
        {"kind": "fill", "fill": "#fbeceb", "stroke": RED, "label": "Braced bay"},
    ])
    _member_schedule(s, x0 + 8, y1 - 138)
    return s.save(out)


DASH_ABOVE = "8,3"


def _member_schedule(s, x, y):
    s.text(x, y, "MEMBER SCHEDULE", 2.4, "start", GREY, "700", spacing=1.0)
    s.line(x, y + 2.6, x + 128, y + 2.6, w="thin", color=GREY)
    rows = [
        ("MARK", "MEMBER", "NO."),
        ("SR-1", "CHS 457 x 16 hoop rib", "36"),
        ("SR-2", "CHS 219 x 10 purlin", "21 rings"),
        ("SC-1", "CHS 324 x 12.5 column", "72"),
        ("SB-1", "UB 457 x 191 radial primary", "72"),
        ("SB-2", "UB 305 x 165 radial secondary", "72"),
        ("SB-3", "Ring beam, UB 356 x 171", "5 rings"),
        ("SB-4", "PFC 300 edge trimmer", "2 rings"),
        ("F-1",  "RC ring beam 1 100 x 900", "2 rings"),
        ("F-2",  "600 CFA pile, 18 m", "148"),
    ]
    yy = y + 7.4
    for i, r in enumerate(rows):
        wt = "700" if i == 0 else "400"
        col = GREY if i == 0 else INK
        for dx, txt in zip((0, 22, 112), r):
            s.text(x + dx, yy, txt, 2.0, "start", col, wt)
        yy += 4.2
        if i == 0:
            s.line(x, yy - 2.8, x + 128, yy - 2.8, w="hatch", color=LIGHT)
    return yy
