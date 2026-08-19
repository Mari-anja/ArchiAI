"""Sections.  A plane through the axis of a torus cuts it in two true circles,
which is what makes these drawings worth looking at."""

import math
from .svgkit import (Sheet, View, d_poly, d_poly_mm, d_arc, INK, GREY, LIGHT,
                     BLUE, RED, GREEN, f, DASH_HID, DASH_ABOVE)
from . import annot as A
from . import params as P
from . import program as PG

SCALE = 150


def _sheet(number, title, sub, scale_text=None, paper="A1", notes=None):
    return Sheet(number, title, scale_text or ("1 : %d" % SCALE), paper, sub,
                 P.PROJECT, notes)


# ---------------------------------------------------------------------------
# Profiles in the section plane.  x is the signed distance from the building
# centre; z is height above FFL 00.
# ---------------------------------------------------------------------------
def tube_face(sign, radius, phi0=None, phi1=None, n=160):
    phi0 = P.PHI_SPRING_OUT if phi0 is None else phi0
    phi1 = P.PHI_SPRING_IN if phi1 is None else phi1
    pts = []
    for i in range(n + 1):
        phi = math.radians(phi0 + (phi1 - phi0) * i / n)
        pts.append((sign * (P.MAJOR_R + radius * math.cos(phi)),
                    P.TUBE_Z + radius * math.sin(phi)))
    return pts


def tube_cut_path(v, sign):
    """Closed path of the cut envelope: outer circle, inner circle, ground caps."""
    outer = tube_face(sign, P.TUBE_R)
    inner = tube_face(sign, P.TUBE_R - P.ENV_T)
    return d_poly(v, outer + list(reversed(inner)), True)


def x_opening(z):
    """Half-width of the clear courtyard opening at height z, in the section plane."""
    return P.MAJOR_R - P.half_chord(z)


def courtyard_clip(v):
    pts = []
    n = 60
    for i in range(n + 1):
        z = P.Z_APEX * i / n
        pts.append((x_opening(z), z))
    for i in range(n, -1, -1):
        z = P.Z_APEX * i / n
        pts.append((-x_opening(z), z))
    return d_poly(v, pts, True)


# ---------------------------------------------------------------------------
def _ground(s, v, half=45.0, depth=1.8):
    s.path(d_poly(v, [(-half, 0), (half, 0), (half, -depth), (-half, -depth)], True),
           w=None, fill=s.pattern("earth"))
    a, b = v.p(-half, 0), v.p(half, 0)
    s.line(a[0], a[1], b[0], b[1], w="cut", color=INK)


def _far_side(s, v, name):
    """The courtyard elevation of the far half of the ring, seen through the
    opening.  Clipped to the opening so it never runs over the cut tubes."""
    clip = s.clip(name, courtyard_clip(v))
    s.add("<g %s>" % clip)
    s.path(d_poly(v, [(-34, 0), (34, 0), (34, 10.4), (-34, 10.4)], True),
           w=None, fill="#fcfcfb")

    def far_profile(th_deg, phi0, phi1, n=40):
        th = math.radians(th_deg)
        pts = []
        for i in range(n + 1):
            phi = math.radians(phi0 + (phi1 - phi0) * i / n)
            rho = P.MAJOR_R + P.TUBE_R * math.cos(phi)
            pts.append((rho * math.sin(th), P.TUBE_Z + P.TUBE_R * math.sin(phi)))
        return pts

    # tonal wash over the far courtyard facade
    face = far_profile(-90, 90.0, P.PHI_SPRING_IN) + \
           list(reversed(far_profile(90, 90.0, P.PHI_SPRING_IN)))
    s.path(d_poly(v, [(-30, P.Z_APEX), (30, P.Z_APEX), (30, 0), (-30, 0)], True),
           w=None, fill="#f4f5f3")

    # horizontal lines: crown, Level 01 slab, springing
    for phi, wgt, col in ((90.0, "thin", "#8d939a"),
                          (P.PHI_L01_IN, "fine", "#9aa0a6"),
                          (118.0, "hatch", "#c2c6c9")):
        rho = P.MAJOR_R + P.TUBE_R * math.cos(math.radians(phi))
        z = P.TUBE_Z + P.TUBE_R * math.sin(math.radians(phi))
        a, b = v.p(-rho, z), v.p(rho, z)
        s.line(a[0], a[1], b[0], b[1], w=wgt, color=col)

    # mullions on the far courtyard facade, at 5 degree plan centres
    for k in range(-18, 19):
        pts = far_profile(k * 5.0, 118.0, P.PHI_SPRING_IN)
        s.path(d_poly(v, pts), w="hatch", color="#aeb4ba")
    # and the upper glazing above Level 01
    for k in range(-18, 19):
        pts = far_profile(k * 5.0, 90.0, 118.0)
        s.path(d_poly(v, pts), w="hatch", color="#cdd2d6")

    for x in (-14.0, -6.5, 3.0, 11.0, 17.5):
        _figure(s, v, x, 0.0, 0.62)
    for x, r in ((-19.0, 3.1), (-10.5, 2.7), (8.0, 3.0), (18.0, 2.6)):
        _tree(s, v, x, r)
    a, b = v.p(-7.2, 0.12), v.p(7.2, 0.12)
    s.line(a[0], a[1], b[0], b[1], w="fine", color="#8fb6cb")
    s.add("</g>")


def _tree(s, v, x, r, z=0.0):
    trunk_h = r * 0.85
    a, b = v.p(x, z), v.p(x, z + trunk_h)
    s.line(a[0], a[1], b[0], b[1], w="fine", color="#7d8a72")
    cx, cy = v.p(x, z + trunk_h + r * 0.75)
    s.circle(cx, cy, v.mm(r * 0.95), w="fine", color="#8fae86", fill="#eaf1e6")


def _figure(s, v, x, z, scale=1.0):
    h = 1.75 * scale
    cx, cy = v.p(x, z + h)
    s.circle(cx, cy + v.mm(h * 0.06), v.mm(h * 0.075), w=None, fill="#6f7681")
    pts = [(x - 0.20 * scale, z), (x - 0.20 * scale, z + h * 0.86),
           (x + 0.20 * scale, z + h * 0.86), (x + 0.20 * scale, z)]
    s.path(d_poly(v, pts, True), w=None, fill="#6f7681", op=0.85)


def _slabs(s, v, theta_pair, show_rooms=True):
    poche = s.pattern("concrete")
    for sign, theta in ((-1, theta_pair[0]), (1, theta_pair[1])):
        r0, r1 = P.R_IN_00, P.R_OUT_00
        # ground bearing slab
        s.path(d_poly(v, [(sign * r0, 0), (sign * r1, 0),
                          (sign * r1, -0.35), (sign * r0, -0.35)], True),
               w="cut", color=INK, fill=poche)
        # Level 01 slab, omitted where the plan shows a void or an undercroft
        rm0 = PG.room_at(0, theta)
        rm1 = PG.room_at(1, theta)
        if rm1 is None or rm1.cat != "void":
            s.path(d_poly(v, [(sign * r0, P.FFL_01), (sign * r1, P.FFL_01),
                              (sign * r1, P.FFL_01 - P.SLAB_T),
                              (sign * r0, P.FFL_01 - P.SLAB_T)], True),
                   w="cut", color=INK, fill=poche)
        else:
            # edge of the void, shown beyond
            for rr in (r0, r1):
                a, b = v.p(sign * rr, P.FFL_01), v.p(sign * rr, P.FFL_01 - P.SLAB_T)
                s.line(a[0], a[1], b[0], b[1], w="fine", color=GREY, dash=DASH_HID)
        if show_rooms:
            _room_labels(s, v, sign, rm0, rm1)


def _room_labels(s, v, sign, rm0, rm1):
    xc = sign * ((P.R_IN_00 + P.R_OUT_00) / 2.0)
    if rm0 is not None:
        x, y = v.p(xc, 1.4)
        s.text(x, y, rm0.name.upper(), 2.3, "middle", INK, "600", halo="#ffffff")
        x, y = v.p(xc, 0.85)
        s.text(x, y, "%s   FFL +0.000" % rm0.code, 1.9, "middle", GREY, halo="#ffffff")
    if rm1 is not None:
        x, y = v.p(xc, P.FFL_01 + 1.5)
        s.text(x, y, rm1.name.upper(), 2.3, "middle", INK, "600", halo="#ffffff")
        x, y = v.p(xc, P.FFL_01 + 0.95)
        s.text(x, y, "%s   FFL +4.200" % rm1.code, 1.9, "middle", GREY, halo="#ffffff")


def _structure(s, v, theta_pair):
    """Hoop ribs and columns seen beyond the cut plane."""
    for sign in (-1, 1):
        pts = tube_face(sign, P.TUBE_R - P.ENV_T - P.RIB_DIA / 2.0)
        s.path(d_poly(v, pts), w="fine", color="#8d939a", dash=DASH_HID)
        for rr in P.COL_RADII:
            a, b = v.p(sign * rr, 0), v.p(sign * rr, P.FFL_01 - P.SLAB_T)
            s.line(a[0], a[1], b[0], b[1], w="med", color=INK)
            a, b = v.p(sign * rr, P.FFL_01), v.p(sign * rr, P.FFL_01 + 1.6)
            s.line(a[0], a[1], b[0], b[1], w="fine", color=GREY, dash=DASH_HID)
        # suspended ceiling / services zone under the Level 01 slab
        a, b = v.p(sign * P.R_IN_00, P.FFL_01 - P.SLAB_T - P.CEIL_ZONE), \
               v.p(sign * P.R_OUT_00, P.FFL_01 - P.SLAB_T - P.CEIL_ZONE)
        s.line(a[0], a[1], b[0], b[1], w="fine", color=GREY, dash="4,2")


def _section_grid(s, v, ztop=10.9):
    for i, r in enumerate(P.RING_GRID):
        for sign in (-1, 1):
            x = sign * r
            a, b = v.p(x, -0.9), v.p(x, ztop - 0.55)
            s.line(a[0], a[1], b[0], b[1], w="grid", color=BLUE, dash="6,2,1,2")
            cx, cy = v.p(x, ztop)
            s.circle(cx, cy, 3.4, w="grid", color=BLUE, fill="#ffffff")
            s.text(cx, cy + 0.75, P.RING_LABELS[i], 2.1, "middle", BLUE, "600")


def _envelope(s, v):
    poche = s.pattern("concrete")
    for sign in (-1, 1):
        s.path(tube_cut_path(v, sign), w="cut", color=INK, fill=poche)
        # glazing zones marked on the inner face
        for (code, p0, p1, kind, desc) in P.ENVELOPE:
            if kind != "glazing":
                continue
            pts = tube_face(sign, P.TUBE_R - P.ENV_T * 0.5, p0, p1, 40)
            s.path(d_poly(v, pts), w="med", color="#4c7fae")


def _levels(s, v, x_tag):
    for z, lab in ((P.FFL_00, "LEVEL 00  FFL"), (P.FFL_01, "LEVEL 01  FFL"),
                   (P.Z_APEX, "SHELL APEX")):
        x, y = v.p(x_tag, z)
        A.level_tag(s, x, y, z, lab)


def _height_dims(s, v, x):
    A.dim_linear(s, v, (x, 0), (x, P.FFL_01), -6.0)
    A.dim_linear(s, v, (x, P.FFL_01), (x, P.Z_APEX), -6.0)
    A.dim_linear(s, v, (x, 0), (x, P.Z_APEX), -16.0)


def _plan_dims(s, v, y=0.0):
    A.dim_linear(s, v, (-P.R_OUT_00, y), (-P.R_IN_00, y), -18.0)
    A.dim_linear(s, v, (-P.R_IN_00, y), (P.R_IN_00, y), -18.0)
    A.dim_linear(s, v, (P.R_IN_00, y), (P.R_OUT_00, y), -18.0)
    A.dim_linear(s, v, (-P.R_MAX, y), (P.R_MAX, y), -26.0, text="75000  OVERALL")


# ---------------------------------------------------------------------------
def _one_section(s, cx, base_y, theta_pair, tag, caption):
    v = View(s, SCALE, cx, base_y)
    _ground(s, v)
    _far_side(s, v, "court-%s" % tag)
    _slabs(s, v, theta_pair)
    _structure(s, v, theta_pair)
    _envelope(s, v)
    for x in (-30.0, 30.0):
        _figure(s, v, x - 4.2, 0.0)
        _figure(s, v, x + 3.0, P.FFL_01)
    _section_grid(s, v)
    _levels(s, v, P.R_MAX + 1.2)
    _height_dims(s, v, -P.R_MAX - 1.0)
    _plan_dims(s, v)
    # title under the drawing
    s.text(cx - v.mm(P.R_MAX), base_y + 34, "SECTION %s-%s" % (tag, tag), 5.2,
           "start", INK, "700", spacing=0.8)
    s.text(cx - v.mm(P.R_MAX) + 46, base_y + 34, "1 : %d" % SCALE, 3.2, "start", GREY)
    s.text(cx - v.mm(P.R_MAX), base_y + 40, caption, 2.4, "start", GREY)
    return v


def sections_sheet(out):
    s = _sheet("A-300", "Sections A-A and B-B", "Cut on the axis of the torus",
               notes=["Section planes are set midway between radial",
                      "gridlines; see A-100 for their location."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    cx = (x0 + x1) / 2.0 + 6
    _one_section(s, cx, 206.0, P.SEC_AA, "A",
                 "Through the service gateway (left) and the entrance hall (right)")
    _one_section(s, cx, 432.0, P.SEC_BB, "B",
                 "Through Town Square East (left) and the auditorium (right)")
    A.scale_bar(s, View(s, SCALE, 0, 0), x0 + 8, y1 - 24, 20, 4,
                label="SCALE 1:%d" % SCALE)
    A.notes_block(s, x0 + 8, y0 + 16, "SECTION NOTES", [
        "A plane through the axis of a torus cuts it in two",
        "true circles of radius 7 500, centred at ±30 000",
        "and +2.100. The ground plane truncates them at the",
        "level of the ground-floor slab, so the shell springs",
        "directly from the paving on two concentric circles",
        "at radius 22 800 and 37 200.",
        "",
        "Both floor plates are chords of that circle placed",
        "symmetrically about its axis, which is why they are",
        "identical 14 400 wide annuli.",
    ])
    return s.save(out)
