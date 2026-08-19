"""Elevations.

Seen from any horizontal direction the torus reads as a wide, low arch: the
crown projects to a straight line at +9.600 between x = ±30 000, and the flanks
follow the true circular profile of the tube.  Because the building is a solid
of revolution, the four cardinal elevations differ only in their openings --
so the developed (unrolled) elevations on A-202 carry most of the information.
"""

import math
from .svgkit import (Sheet, View, d_poly, d_poly_mm, INK, GREY, LIGHT, BLUE,
                     RED, GREEN, f, DASH_HID)
from . import annot as A
from . import params as P
from . import program as PG

SCALE = 150
GLASS = "#e8eef3"
GLASS_D = "#d5dfe8"
CROWN = "#dfe1e0"
PVCOL = "#4a5560"


def _sheet(number, title, sub, scale_text=None, notes=None):
    return Sheet(number, title, scale_text or ("1 : %d" % SCALE), "A1", sub,
                 P.PROJECT, notes)


def rho(phi_deg):
    return P.MAJOR_R + P.TUBE_R * math.cos(math.radians(phi_deg))


def zed(phi_deg):
    return P.TUBE_Z + P.TUBE_R * math.sin(math.radians(phi_deg))


def sx(theta, phi, av):
    return rho(phi) * math.sin(math.radians(theta - av))


def visible(theta, av):
    return math.cos(math.radians(theta - av)) > -1e-9


def meridian(theta, av, phi0, phi1, n=48):
    """One plan angle, drawn through a range of section angle."""
    return [(sx(theta, phi0 + (phi1 - phi0) * i / n, av),
             zed(phi0 + (phi1 - phi0) * i / n)) for i in range(n + 1)]


def silhouette(n=64):
    pts = []
    for i in range(n + 1):
        phi = P.PHI_SPRING_OUT + (90.0 - P.PHI_SPRING_OUT) * i / n
        pts.append((-rho(phi), zed(phi)))
    for i in range(n, -1, -1):
        phi = P.PHI_SPRING_OUT + (90.0 - P.PHI_SPRING_OUT) * i / n
        pts.append((rho(phi), zed(phi)))
    return pts


# ---------------------------------------------------------------------------
def _ground(s, v, half=44.0, depth=1.6):
    s.path(d_poly(v, [(-half, 0), (half, 0), (half, -depth), (-half, -depth)], True),
           w=None, fill=s.pattern("earth"))
    a, b = v.p(-half, 0), v.p(half, 0)
    s.line(a[0], a[1], b[0], b[1], w="cut", color=INK)


def _opening(s, v, av, t0, t1, phi0, phi1, label=None):
    """A hole cut through the shell, drawn between two meridians."""
    if not (visible((t0 + t1) / 2.0, av)):
        return
    t0 = max(t0, av - 89.5)
    t1 = min(t1, av + 89.5)
    if t1 <= t0:
        return
    pts = meridian(t0, av, phi0, phi1) + list(reversed(meridian(t1, av, phi0, phi1)))
    s.path(d_poly(v, pts, True), w="med", color=INK, fill="#f0efec")
    # reveal
    inner = meridian(t0 + (t1 - t0) * 0.12, av, phi0, phi1) + \
        list(reversed(meridian(t1 - (t1 - t0) * 0.12, av, phi0, phi1)))
    s.path(d_poly(v, inner, True), w="fine", color=GREY, fill="#e2e0dc")
    if label:
        xm = (sx((t0 + t1) / 2.0, phi0, av))
        x, y = v.p(xm, zed(phi0) + (zed(phi1) - zed(phi0)) * 0.45)
        s.text(x, y, label, 2.1, "middle", GREY, "600", halo="#f0efec")


def elevation(s, cx, base_y, av, tag, caption, scale=SCALE, openings=True):
    v = View(s, scale, cx, base_y)
    _ground(s, v)

    # body of the shell
    s.path(d_poly(v, silhouette(), True), w=None, fill=GLASS)
    # crown band, opaque
    crown = meridian(av - 89.5, av, 62.0, 118.0, 8)
    band = []
    for k in range(-36, 37):
        th = av + k * 2.5
        band.append((sx(th, 62.0, av), zed(62.0)))
    top = [(x, P.Z_APEX) for (x, _) in [(-30, 0), (30, 0)]]
    s.path(d_poly(v, band + [(30.0, P.Z_APEX), (-30.0, P.Z_APEX)], True),
           w=None, fill=CROWN)

    # meridian joint lines, 5 degree centres, front half only
    for k in range(-36, 37):
        th = av + k * 2.5
        if abs(k) * 2.5 > 89.5:
            continue
        wgt = "fine" if k % 4 == 0 else "hatch"
        col = "#9aa4ad" if k % 4 == 0 else "#c3ccd3"
        s.path(d_poly(v, meridian(th, av, P.PHI_SPRING_OUT, 118.0)), w=wgt, color=col)

    # horizontal joint lines: every circle on the shell projects to a straight line
    for phi, wgt, col, lab in (
            (P.PHI_SPRING_OUT, "med", INK, None),
            (0.0, "fine", "#8d939a", None),
            (P.PHI_L01_OUT, "med", "#5c6a76", "LEVEL 01"),
            (38.0, "hatch", "#b6bfc6", None),
            (62.0, "fine", "#8d939a", None),
            (90.0, "med", INK, None)):
        r = rho(phi)
        z = zed(phi)
        a, b = v.p(-r, z), v.p(r, z)
        s.line(a[0], a[1], b[0], b[1], w=wgt, color=col)

    # integrated PV on the outer face of the crown
    for k in range(-30, 31):
        th = av + k * 3.0
        if abs(k) * 3.0 > 88.0:
            continue
        pts = meridian(th, av, 64.0, 88.0, 10)
        s.path(d_poly(v, pts), w="hatch", color=PVCOL, op=None)

    if openings:
        _opening(s, v, av, 263.0, 277.0, P.PHI_SPRING_OUT, P.PHI_L01_OUT, "ENTRANCE")
        _opening(s, v, av, 84.0, 96.0, P.PHI_SPRING_OUT, P.PHI_L01_OUT, "GATEWAY")

    # outline last, heavy
    s.path(d_poly(v, silhouette(), True), w="outline", color=INK, fill="none")

    # scale figures and landscape
    for x in (-31.0, -20.0, 6.0, 15.0, 27.0):
        _fig(s, v, x)
    for x, r in ((-40.0, 4.2), (39.5, 3.8)):
        _tree(s, v, x, r)

    for z, lab in ((P.FFL_00, "LEVEL 00  FFL"), (P.FFL_01, "LEVEL 01  FFL"),
                   (P.Z_APEX, "SHELL APEX")):
        x, y = v.p(P.R_MAX + 1.4, z)
        A.level_tag(s, x, y, z, lab)
    A.dim_linear(s, v, (-P.R_MAX - 1.0, 0), (-P.R_MAX - 1.0, P.Z_APEX), -6.0)
    A.dim_linear(s, v, (-P.R_MAX, 0), (P.R_MAX, 0), -16.0, text="75000  OVERALL")

    s.text(cx - v.mm(P.R_MAX), base_y + 30, tag, 5.2, "start", INK, "700", spacing=0.8)
    s.text(cx - v.mm(P.R_MAX), base_y + 36, caption, 2.4, "start", GREY)
    return v


def _envelope_key(s, x, y):
    s.text(x, y, "ENVELOPE ZONES", 2.4, "start", GREY, "700", spacing=1.0)
    s.line(x, y + 2.6, x + 250, y + 2.6, w="thin", color=GREY)
    yy = y + 8.0
    cols = [(0, "ZONE"), (26, "phi FROM"), (56, "phi TO"), (84, "RADIUS"), (116, "BUILD-UP")]
    for dx, lab in cols:
        s.text(x + dx, yy, lab, 1.9, "start", GREY, "600", spacing=0.6)
    yy += 4.4
    s.line(x, yy - 2.8, x + 250, yy - 2.8, w="hatch", color=LIGHT)
    for (code, p0, p1, kind, desc) in P.ENVELOPE:
        s.rect(x, yy - 2.4, 3.2, 2.6, w="fine", color=GREY,
               fill=GLASS if kind == "glazing" else CROWN)
        s.text(x + 5, yy, code, 2.1, "start", INK, "600")
        s.text(x + 26, yy, "%.2f°" % p0, 2.1, "start", INK)
        s.text(x + 56, yy, "%.2f°" % p1, 2.1, "start", INK)
        s.text(x + 84, yy, "%d - %d" % (round(rho(p0) * 1000), round(rho(p1) * 1000)), 2.1,
               "start", INK)
        s.text(x + 116, yy, desc, 2.1, "start", GREY)
        yy += 5.2
    return yy


def _fig(s, v, x, z=0.0, scale=1.0):
    h = 1.75 * scale
    cx, cy = v.p(x, z + h)
    s.circle(cx, cy + v.mm(h * 0.06), v.mm(h * 0.075), w=None, fill="#6f7681")
    s.path(d_poly(v, [(x - 0.20, z), (x - 0.20, z + h * 0.86),
                      (x + 0.20, z + h * 0.86), (x + 0.20, z)], True),
           w=None, fill="#6f7681", op=0.85)


def _tree(s, v, x, r, z=0.0):
    a, b = v.p(x, z), v.p(x, z + r * 0.9)
    s.line(a[0], a[1], b[0], b[1], w="fine", color="#7d8a72")
    cx, cy = v.p(x, z + r * 0.9 + r * 0.8)
    s.circle(cx, cy, v.mm(r), w="fine", color="#8fae86", fill="#eaf1e6")


# ---------------------------------------------------------------------------
def elevations_sheet(out, which):
    pairs = {
        "A-200": [(270.0, "SOUTH ELEVATION", "Principal approach and main entrance"),
                  (0.0, "EAST ELEVATION", "Studio East and Cores A and D beyond")],
        "A-201": [(90.0, "NORTH ELEVATION", "Service gateway and loading"),
                  (180.0, "WEST ELEVATION", "Auditorium and Cores B and C beyond")],
    }[which]
    titles = {"A-200": "Elevations — South and East",
              "A-201": "Elevations — North and West"}
    s = _sheet(which, titles[which], "Orthographic; the shell is a solid of revolution",
               notes=["All four elevations share the same profile;",
                      "they differ only where the ring is cut through.",
                      "See A-202 for the developed facades."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    cx = (x0 + x1) / 2.0 + 6
    elevation(s, cx, 196.0, pairs[0][0], pairs[0][1], pairs[0][2])
    elevation(s, cx, 392.0, pairs[1][0], pairs[1][1], pairs[1][2])
    _envelope_key(s, x0 + 8, 452.0)
    A.scale_bar(s, View(s, SCALE, 0, 0), x0 + 8, y1 - 24, 20, 4,
                label="SCALE 1:%d" % SCALE)
    A.notes_block(s, x0 + 8, y0 + 16, "ENVELOPE", [
        "Curved insulating glass units on a radial",
        "steel mullion grid at 2.5° centres (1 636",
        "at the widest circle, 982 at the courtyard).",
        "",
        "Crown: insulated standing-seam aluminium",
        "with integrated photovoltaic laminate over",
        "the band phi 64° to 88°.",
        "",
        "The shell springs from a continuous ground",
        "gutter at radius 37 200 and 22 800.",
    ])
    return s.save(out)


# ---------------------------------------------------------------------------
# Developed (unrolled) elevations
# ---------------------------------------------------------------------------
def developed(s, cx, base_y, t0, t1, r_dev, phi0, phi1, scale, label, inner=False):
    """Unroll the shell about the building axis at reference radius r_dev."""
    v = View(s, scale, cx, base_y)
    L = math.radians(t1 - t0) * r_dev

    def X(theta):
        return math.radians(theta - (t0 + t1) / 2.0) * r_dev

    # body
    pts = [(X(t0), zed(phi0)), (X(t1), zed(phi0)), (X(t1), zed(phi1)), (X(t0), zed(phi1))]
    s.path(d_poly(v, pts, True), w=None, fill=GLASS)
    if not inner:
        s.path(d_poly(v, [(X(t0), zed(62.0)), (X(t1), zed(62.0)),
                          (X(t1), zed(phi1)), (X(t0), zed(phi1))], True),
               w=None, fill=CROWN)
    # meridians
    th = t0
    while th <= t1 + 1e-6:
        wgt, col = ("fine", "#9aa4ad") if abs(th % 10.0) < 1e-6 else ("hatch", "#c8d0d6")
        a, b = v.p(X(th), zed(phi0)), v.p(X(th), zed(phi1))
        s.line(a[0], a[1], b[0], b[1], w=wgt, color=col)
        th += 2.5 if not inner else 5.0
    # horizontals
    for phi, wgt, col in ((phi0, "med", INK), (P.PHI_L01_OUT if not inner else P.PHI_L01_IN,
                                               "med", "#5c6a76"),
                          (62.0 if not inner else 118.0, "fine", "#8d939a"),
                          (phi1, "med", INK)):
        a, b = v.p(X(t0), zed(phi)), v.p(X(t1), zed(phi))
        s.line(a[0], a[1], b[0], b[1], w=wgt, color=col)
    # programme markers
    for (cid, tc, half) in P.CORES:
        if t0 <= tc <= t1:
            s.path(d_poly(v, [(X(tc - half), zed(phi0)), (X(tc + half), zed(phi0)),
                              (X(tc + half), zed(phi1)), (X(tc - half), zed(phi1))], True),
                   w="fine", color=GREY, fill="#e6e6e2", op=0.75)
            x, y = v.p(X(tc), zed(phi0) + 1.2)
            s.text(x, y, "CORE %s" % cid, 2.2, "middle", INK, "700", halo="#ffffff")
    for (a0, a1, lab) in ((263.0, 277.0, "MAIN ENTRANCE"), (84.0, 96.0, "SERVICE GATEWAY")):
        if t0 <= (a0 + a1) / 2.0 <= t1:
            zz0, zz1 = zed(phi0), P.FFL_01
            s.path(d_poly(v, [(X(a0), zz0), (X(a1), zz0), (X(a1), zz1), (X(a0), zz1)], True),
                   w="med", color=INK, fill="#f0efec")
            x, y = v.p(X((a0 + a1) / 2.0), 2.0)
            s.text(x, y, lab, 2.0, "middle", INK, "600", halo="#f0efec")
    s.path(d_poly(v, pts, True), w="heavy", color=INK, fill="none")

    # grid ticks
    th = math.ceil(t0 / 10.0) * 10.0
    while th <= t1:
        i = int(round(th / P.RADIAL_STEP)) % P.RADIAL_DIV
        x, y = v.p(X(th), zed(phi0))
        s.circle(x, y + 6.0, 3.0, w="grid", color=BLUE, fill="#ffffff")
        s.text(x, y + 6.75, P.grid_label(i), 1.9, "middle", BLUE, "600")
        th += 20.0
    s.text(cx - v.mm(L / 2.0), base_y - v.mm(zed(phi1)) - 6.0, label, 3.4,
           "start", INK, "700", spacing=0.5)
    return v


def developed_sheet(out):
    s = _sheet("A-202", "Developed Elevations", "Outer and courtyard facades unrolled",
               "1 : 200", notes=["Unrolled at radius 37 500 (outer) and",
                                 "22 500 (courtyard). Heights are true;",
                                 "lengths are developed on those radii."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    cx = (x0 + x1) / 2.0
    developed(s, cx, 112.0, 0.0, 180.0, P.R_MAX, P.PHI_SPRING_OUT, 90.0, 200,
              "DEVELOPED OUTER ELEVATION   R01 – R19   (0° to 180°)   1:200")
    developed(s, cx, 214.0, 180.0, 360.0, P.R_MAX, P.PHI_SPRING_OUT, 90.0, 200,
              "DEVELOPED OUTER ELEVATION   R19 – R01   (180° to 360°)   1:200")
    developed(s, cx, 366.0, 0.0, 180.0, P.R_MIN, 90.0, P.PHI_SPRING_IN, 200,
              "DEVELOPED COURTYARD ELEVATION   R01 – R19   (0° to 180°)   1:200", inner=True)
    developed(s, cx, 468.0, 180.0, 360.0, P.R_MIN, 90.0, P.PHI_SPRING_IN, 200,
              "DEVELOPED COURTYARD ELEVATION   R19 – R01   (180° to 360°)   1:200", inner=True)
    A.scale_bar(s, View(s, 200, 0, 0), x0 + 8, y1 - 24, 40, 4, label="SCALE 1:200")
    A.notes_block(s, x0 + 8, y1 - 74, "DEVELOPED LENGTHS", [
        "Outer facade at R 37 500 : %s m" % ("%.1f" % (2 * math.pi * P.R_MAX)),
        "Courtyard facade at R 22 500 : %s m" % ("%.1f" % (2 * math.pi * P.R_MIN)),
        "Shell arc length per rib : %s m" % ("%.2f" % (
            math.radians(P.PHI_SPRING_IN - P.PHI_SPRING_OUT) * P.TUBE_R)),
    ])
    return s.save(out)
