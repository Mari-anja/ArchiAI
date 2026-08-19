"""Construction details at 1:10 and the wall section at 1:50.

These are the drawings that say how the building is actually made. Every
layer is taken from `buildup`, which in turn is sized from the model, so a
change to the wall thickness or the slab depth redraws the detail instead of
leaving it to be corrected by hand.

Local coordinates: u runs horizontally, zero at the outer face of the wall
and positive into the building; z runs vertically from whatever datum the
panel is centred on. That way one set of build-ups serves every detail.
"""

import math
from ..svgkit import (Sheet, View, d_poly, d_poly_mm, INK, GREY, LIGHT, BLUE,
                      RED, GREEN, f, DASH_HID)
from .. import annot as A
from . import buildup as BU
from . import services as SV
from . import openings as OP


def _sheet(project, number, title, sub, scale_text, notes=None):
    return Sheet(number, title, scale_text, "A1", sub, project.info, notes)


# ---------------------------------------------------------------------------
# Drawing primitives in (u, z)
# ---------------------------------------------------------------------------
def rect(s, v, u0, z0, u1, z1, w="fine", color=GREY, fill="none", dash=None):
    s.path(d_poly(v, [(u0, z0), (u1, z0), (u1, z1), (u0, z1)], True),
           w=w, color=color, fill=fill, dash=dash)


def _paint(s, layer):
    return s.pattern(layer.pattern) if layer.pattern else (layer.fill or "none")


def vstack(s, v, layers, u0, z0, z1, sign=1):
    """A wall build-up: layers stacked along u, running between two heights."""
    out, u = [], u0
    for l in layers:
        t = l.t / 1000.0 * sign
        rect(s, v, u, z0, u + t, z1, w=l.line,
             color=INK if l.line == "cut" else GREY, fill=_paint(s, l))
        out.append((u + t / 2.0, l))
        u += t
    return out


def hstack(s, v, layers, z0, u0, u1, sign=-1):
    """A floor or roof build-up: layers stacked along z, running between two
    horizontal limits. sign -1 goes downward from the datum."""
    out, z = [], z0
    for l in layers:
        t = l.t / 1000.0 * sign
        rect(s, v, u0, z, u1, z + t, w=l.line,
             color=INK if l.line == "cut" else GREY, fill=_paint(s, l))
        out.append((z + t / 2.0, l))
        z += t
    return out


def earth(s, v, u0, z0, u1, z1):
    rect(s, v, u0, z0, u1, z1, w=None, fill=s.pattern("earth"))


def ground_line(s, v, u0, u1, z):
    a, b = v.p(u0, z), v.p(u1, z)
    s.line(a[0], a[1], b[0], b[1], w="med", color=INK)
    n = 9
    for i in range(n):
        x = a[0] + (b[0] - a[0]) * (i + 0.5) / n
        s.line(x, a[1] + 0.6, x - 1.6, a[1] + 2.4, w="fine", color=GREY)


# ---------------------------------------------------------------------------
class Panel:
    """One numbered detail: a clipped window with a key list beneath it."""
    W, H = 300.0, 208.0

    def __init__(self, sheet, x, y, tag, title, scale=10, u_c=0.0, z_c=0.0,
                 note=None):
        self.s, self.x, self.y = sheet, x, y
        self.tag, self.title, self.scale, self.note = tag, title, scale, note
        self.v = View(sheet, scale, x + self.W / 2.0 - u_c * 1000.0 / scale,
                      y + self.H / 2.0 + z_c * 1000.0 / scale)
        self.keys = []
        sheet.rect(x, y, self.W, self.H, w="fine", color=LIGHT, fill="#ffffff")
        sheet.add('<g %s>' % sheet.clip("det-%s" % tag, d_poly_mm(
            [(x, y), (x + self.W, y), (x + self.W, y + self.H), (x, y + self.H)],
            True)))

    def key(self, u, z, text, lead=None):
        """A numbered balloon on the drawing, and its line in the key."""
        self.keys.append(text)
        n = len(self.keys)
        px, py = self.v.p(u, z)
        if lead:
            lx, ly = self.v.p(*lead)
            self.s.line(px, py, lx, ly, w="fine", color=INK)
            px, py = lx, ly
        self.s.circle(px, py, 3.0, w="fine", color=INK, fill="#ffffff")
        self.s.text(px, py + 1.0, str(n), 2.2, "middle", INK, "700")

    def column(self, u_bal, z_top, dz):
        """A tidy vertical column of balloons with leaders back to the layers.

        Returns place(u, z, text); each call drops the next balloon one step
        down the column, so a ten layer build-up letters itself without the
        numbers piling up on the boundary lines."""
        state = [z_top]

        def place(u, z, text):
            self.key(u, z, text, lead=(u_bal, state[0]))
            state[0] -= dz
        return place

    def close(self):
        s = self.s
        s.add("</g>")
        s.rect(self.x, self.y, self.W, self.H, w="fine", color=GREY)
        s.circle(self.x + 10, self.y + 10, 5.4, w="med", color=RED,
                 fill="#ffffff")
        s.text(self.x + 10, self.y + 11.6, self.tag, 3.4, "middle", RED, "700")
        yy = self.y + self.H + 8
        s.text(self.x, yy, self.title, 3.2, "start", INK, "700", spacing=0.6)
        s.text(self.x + self.W, yy, "1 : %d" % self.scale, 2.6, "end", GREY)
        s.line(self.x, yy + 2.6, self.x + self.W, yy + 2.6, w="med", color=INK)
        yy += 8.6
        half = (len(self.keys) + 1) // 2
        for ci in range(2):
            chunk = self.keys[ci * half:(ci + 1) * half]
            cx = self.x + ci * (self.W / 2.0 + 4)
            ky = yy
            for i, text in enumerate(chunk, ci * half + 1):
                s.circle(cx + 2.4, ky - 0.8, 2.4, w="fine", color=INK)
                s.text(cx + 2.4, ky + 0.1, str(i), 1.9, "middle", INK, "700")
                s.text(cx + 7.4, ky, text, 2.15, "start", GREY)
                ky += 5.2
        if self.note:
            s.text(self.x, yy + half * 5.2 + 3, self.note, 2.1, "start", GREY,
                   italic=True)
        return yy + half * 5.2 + 8


# ---------------------------------------------------------------------------
# The four envelope details
# ---------------------------------------------------------------------------
def _detail_ground(s, project, x, y, tag="1"):
    """Where the wall meets the ground: footing, slab edge, damp proofing."""
    wall = BU.external_wall(project)
    grd = BU.ground_floor(project)
    fd = SV.foundations(project)
    t = project.brief.wall_t
    depth = sum(l.t for l in grd) / 1000.0
    d = Panel(s, x, y, tag, "FOUNDATION AND GROUND FLOOR JUNCTION",
              u_c=0.50, z_c=-0.41,
              note="Footing width follows the bearing pressure on S-010; "
                   "depth to the engineer's frost and shrinkage line.")
    v = d.v
    ext = -0.20                                   # external ground level
    foot_top = -(depth + 0.06)
    foot_bot = foot_top - 0.70
    fw = max(min(fd["pad_m"] * 0.32, 1.30), t + 0.40)

    # everything below ground, then the concrete, then the build-ups over it
    earth(s, v, -1.60, ext, 2.60, -2.20)
    rect(s, v, t / 2.0 - fw / 2.0, foot_top, t / 2.0 + fw / 2.0, foot_bot,
         w="cut", color=INK, fill=s.pattern("concrete"))
    rect(s, v, t / 2.0 - fw / 2.0 - 0.05, foot_bot, t / 2.0 + fw / 2.0 + 0.05,
         foot_bot - 0.05, w="fine", color=GREY, fill=s.pattern("screed"))
    rect(s, v, 0.0, ext + 0.02, t, foot_top, w="cut", color=INK,
         fill=s.pattern("concrete"))

    floor = hstack(s, v, grd, 0.0, t, 2.60)
    wall_l = vstack(s, v, wall, 0.0, 0.62, ext + 0.02)

    ground_line(s, v, -1.60, 0.0, ext)
    rect(s, v, -1.60, ext, -0.40, ext - 0.06, w="med", color=INK,
         fill=s.pattern("paving"))
    rect(s, v, -0.38, ext + 0.005, -0.04, ext - 0.46, w="fine", color=GREY,
         fill=s.pattern("gravel"))
    px, py = v.p(-0.21, ext - 0.30)
    s.circle(px, py, v.mm(0.055), w="med", color=INK, fill="#eaf0f4")

    # damp proof course through the inner leaf, lapped down to the membrane
    a, b = v.p(0.03, 0.09), v.p(t, 0.09)
    s.line(a[0], a[1], b[0], b[1], w="cut", color="#3b4148")
    rect(s, v, 0.030, ext + 0.02, 0.075, 0.09, w="fine", color=GREY,
         fill="#dfe3e6")

    left = d.column(-0.58, 0.56, 0.076)
    for (uc, l) in wall_l:
        left(uc, 0.34, l.name)
    left(0.052, ext + 0.30, "Insulated cavity closer at the base of the cavity")
    left(-0.21, ext - 0.30, "Perimeter land drain in a filtered trench")
    left(-0.95, ext - 0.03, "External paving falling away from the building")

    right = d.column(1.62, -0.02, 0.076)
    for (zc, l) in floor:
        right(1.28, zc, l.name)
    right(t / 2.0, 0.09, "Damp proof course lapped to the membrane")
    right(t / 2.0, (foot_top + foot_bot) / 2.0,
          "Mass concrete strip footing, %d mm wide" % round(fw * 1000))

    A.dim_linear(s, v, (0.0, 0.60), (t, 0.60), -7, "%d" % round(t * 1000),
                 size=2.1)
    A.dim_linear(s, v, (t / 2.0 - fw / 2.0, foot_bot),
                 (t / 2.0 + fw / 2.0, foot_bot), 8, "%d" % round(fw * 1000),
                 size=2.1)
    A.dim_linear(s, v, (2.28, 0.0), (2.28, -depth), -7, "%d" % round(depth * 1000),
                 size=2.1)
    return d.close()


def _detail_floor_edge(s, project, x, y, tag="2"):
    """Where a floor plate meets the facade."""
    wall = BU.external_wall(project)
    flr = BU.upper_floor(project)
    t = project.brief.wall_t
    raised = (flr[0].t + flr[1].t) / 1000.0
    slab = flr[2].t / 1000.0
    void = flr[3].t / 1000.0
    ceil = flr[4].t / 1000.0
    z_slab = -raised
    z_soff = z_slab - slab
    z_ceil = z_soff - void - ceil
    z_head = -OP.HEAD_GAP                      # head of the glazing below
    z_sill = OP.SILL                           # sill of the glazing above
    d = Panel(s, x, y, tag, "INTERMEDIATE FLOOR EDGE AND SPANDREL",
              u_c=0.62, z_c=-0.30,
              note="A cavity barrier at every floor holds the compartment "
                   "line at the facade.")
    v = d.v

    vstack(s, v, wall, 0.0, 1.10, -1.10)
    floor = hstack(s, v, flr, 0.0, t, 2.40)

    # slab runs through the inner leaf and stops at the cavity
    u_cav = (wall[0].t + wall[1].t) / 1000.0
    rect(s, v, u_cav, z_slab, t, z_soff, w="cut", color=INK,
         fill=s.pattern("concrete"))

    # spandrel: panel outside, insulated back pan and cavity barrier inside
    rect(s, v, 0.0, z_sill, wall[0].t / 1000.0, z_head, w="med", color=INK,
         fill="#c9ccd0")
    rect(s, v, wall[0].t / 1000.0, z_sill - 0.02, 0.115, z_head + 0.02,
         w="fine", color=GREY, fill=s.pattern("insul"))
    rect(s, v, 0.075, z_slab + 0.02, u_cav, z_soff - 0.02, w="fine",
         color=RED, fill="#f6e2de")

    # transoms top and bottom of the spandrel, glazing beyond
    for z in (z_sill, z_head):
        rect(s, v, 0.0, z + 0.03, 0.075, z - 0.03, w="med", color=INK,
             fill="#b7bcc2")
    rect(s, v, 0.012, z_head - 0.06, 0.036, -1.05, w="thin", color=INK,
         fill="#e9f0f4")

    # perimeter trench in the raised floor
    rect(s, v, t + 0.03, 0.0, t + 0.34, z_slab, w="fine", color=GREY,
         fill="#eef2f4")

    left = d.column(-0.50, 0.62, 0.092)
    left(0.02, (z_sill + z_head) / 2.0, "Curtain wall spandrel panel")
    left(0.09, (z_sill + z_head) / 2.0 - 0.20, "Insulated back pan")
    left(0.037, z_head - 0.35, "Double glazed vision panel below")
    left(0.09, z_head + 0.10, "Cavity closer returning the insulation to "
                              "the transom")

    right = d.column(1.62, 0.38, 0.092)
    right(0.10, (z_slab + z_soff) / 2.0,
          "Cavity barrier and fire stop at the slab edge")
    right(t * 0.7, (z_slab + z_soff) / 2.0,
          "Reinforced slab, %d mm, bearing on the inner leaf" % round(flr[2].t))
    for (zc, l) in floor:
        right(1.30, zc, l.name)
    right(t + 0.18, z_slab / 2.0, "Perimeter trench for heating and power")

    A.dim_linear(s, v, (t + 0.95, z_slab), (t + 0.95, z_soff), -7,
                 "%d" % round(flr[2].t), size=2.1)
    A.dim_linear(s, v, (t + 0.95, z_soff), (t + 0.95, z_ceil), -7,
                 "%d" % round(void + ceil and (void + ceil) * 1000), size=2.1)
    A.dim_linear(s, v, (-0.20, z_head), (-0.20, 0.30), 0,
                 "spandrel %d overall" % round((z_sill - z_head) * 1000),
                 size=2.1)
    return d.close()


def _detail_parapet(s, project, x, y, tag="3"):
    """Where the wall passes the roof."""
    wall = BU.external_wall(project)
    rf = BU.roof(project)
    t = project.brief.wall_t
    up = 0.72
    d = Panel(s, x, y, tag, "PARAPET AND ROOF EDGE", u_c=0.62, z_c=0.05,
              note="Waterproofing dressed 150 mm above the finished roof "
                   "surface, minimum.")
    v = d.v
    deck = -(rf[0].t + rf[1].t + rf[2].t + rf[3].t) / 1000.0    # top of slab
    soff = deck - rf[4].t / 1000.0

    wall_l = vstack(s, v, wall, 0.0, soff, -1.10)
    roof_l = hstack(s, v, rf, 0.0, t, 2.40)

    # the wall carries on past the roof as an insulated upstand
    rect(s, v, 0.0, up, t, soff, w="cut", color=INK, fill=s.pattern("block"))
    rect(s, v, wall[0].t / 1000.0, up - 0.05, 0.165, deck, w="fine",
         color=GREY, fill=s.pattern("insul"))

    # membrane turned up the inside face and over the top of the upstand
    s.path(d_poly(v, [(t + 0.9, 0.0), (0.20, 0.0), (0.20, up - 0.03),
                      (0.0, up - 0.03)]), w="med", color="#3b4148")

    rect(s, v, -0.06, up + 0.09, t + 0.06, up - 0.03, w="med", color=INK,
         fill="#c3c6ca")
    rect(s, v, -0.06, up - 0.03, -0.03, up - 0.07, w="fine", color=GREY,
         fill="#c3c6ca")

    a, b = v.p(t + 0.45, 0.055), v.p(t + 1.55, 0.069)
    s.line(a[0], a[1], b[0], b[1], w="fine", color=BLUE, dash="4,2")
    s.text((a[0] + b[0]) / 2.0, a[1] - 2.4, "FALL 1:80", 2.0, "middle", BLUE,
           "600")

    left = d.column(-0.50, up + 0.02, 0.092)
    left(t / 2.0, up + 0.03, "Pressed metal coping with a drip both sides")
    left(0.10, up - 0.30, "Insulated parapet upstand, continuous with the wall")
    left(0.20, 0.24, "Waterproofing dressed up and over the upstand")
    for (uc, l) in wall_l:
        left(uc, -0.70, l.name)

    right = d.column(1.62, -0.04, 0.092)
    for (zc, l) in roof_l:
        right(1.30, zc, l.name)
    right(t / 2.0, (up + soff) / 2.0, "Inner leaf carried up to the coping")

    A.dim_linear(s, v, (-0.22, 0.0), (-0.22, up + 0.09), 0,
                 "%d" % round((up + 0.09) * 1000), size=2.1)
    A.dim_linear(s, v, (t + 0.95, 0.0), (t + 0.95, soff), -7,
                 "%d" % round(-soff * 1000), size=2.1)
    return d.close()


def _detail_jamb(s, project, x, y, tag="4"):
    """A plan cut where the glazing meets the solid wall."""
    wall = BU.external_wall(project)
    t = project.brief.wall_t
    d = Panel(s, x, y, tag, "CURTAIN WALL JAMB — PLAN", scale=2, u_c=t / 2.0,
              z_c=0.0,
              note="Cut on plan, outside to the left. z runs along the facade.")
    v = d.v
    u_cav = (wall[0].t + wall[1].t) / 1000.0

    # solid wall above the mullion centreline, glazing below it
    vstack(s, v, wall, 0.0, 0.21, 0.038)
    rect(s, v, 0.0, 0.038, 0.075, -0.038, w="med", color=INK, fill="#b7bcc2")
    rect(s, v, 0.014, -0.038, 0.042, -0.21, w="thin", color=INK, fill="#e9f0f4")
    rect(s, v, wall[0].t / 1000.0, 0.038, 0.145, -0.030, w="fine", color=GREY,
         fill=s.pattern("insul"))
    rect(s, v, 0.145, 0.038, t, -0.030, w="cut", color=INK,
         fill=s.pattern("block"))
    rect(s, v, t - 0.015, 0.038, t, -0.075, w="fine", color=GREY,
         fill=s.pattern("plaster"))
    for z in (0.038, -0.038):
        px, py = v.p(0.007, z)
        s.circle(px, py, v.mm(0.009), w="fine", color=RED, fill="#f6dcd8")

    up = d.column(-0.100, 0.190, 0.029)
    up(0.02, 0.12, wall[0].name)
    up(0.065, 0.12, wall[1].name)
    up(u_cav + 0.03, 0.005, "Insulated cavity closer keeping the line of "
                            "insulation")
    up(0.24, 0.005, "Structural inner leaf returning to the mullion")

    dn = up
    dn(0.037, -0.14, "Double glazed unit in a capped aluminium mullion")
    dn(t - 0.008, -0.055, "Plasterboard reveal on metal furring")
    dn(0.007, -0.038, "Gun applied sealant on a backing rod, both faces")
    dn(0.007, 0.038, "Air and vapour seal taped back to the inner leaf")

    A.dim_linear(s, v, (0.0, 0.175), (t, 0.175), -7, "%d" % round(t * 1000),
                 size=2.1)
    A.dim_linear(s, v, (0.0, -0.038), (0.0, -0.21), -8, "glazed", size=2.1)
    return d.close()


# ---------------------------------------------------------------------------
def details_sheet(project, out, number="A-500", paper="A1"):
    s = _sheet(project, number, "Envelope Details",
               "Ground, floor edge, parapet and jamb", "1 : 10",
               ["Dimensions in millimetres.",
                "Detail locations are keyed on the wall section, A-400.",
                "Build-ups are sized from the model and listed on A-400."])
    s.frame()
    x0, y0, x1, y1 = s.area()
    gap = (x1 - x0 - 2 * Panel.W) / 3.0
    cx = [x0 + gap, x0 + gap * 2 + Panel.W]
    top = y0 + 12
    row2 = top + Panel.H + 78
    _detail_ground(s, project, cx[0], top, "1")
    _detail_floor_edge(s, project, cx[1], top, "2")
    _detail_parapet(s, project, cx[0], row2, "3")
    _detail_jamb(s, project, cx[1], row2, "4")
    return s.save(out)


# ---------------------------------------------------------------------------
# The wall section that the details hang off
# ---------------------------------------------------------------------------
def _figure(s, v, u, z, h=1.75):
    """A person, for scale."""
    hx, hy = v.p(u, z + h)
    s.circle(hx, hy + v.mm(0.11), v.mm(0.11), w="fine", color=GREY)
    a, b = v.p(u, z + h - 0.22), v.p(u, z + 0.72)
    s.line(a[0], a[1], b[0], b[1], w="fine", color=GREY)
    for du in (-0.17, 0.17):
        c = v.p(u + du, z)
        s.line(b[0], b[1], c[0], c[1], w="fine", color=GREY)
    for du in (-0.22, 0.22):
        c = v.p(u + du, z + 0.90)
        s.line(a[0], a[1] + v.mm(0.16), c[0], c[1], w="fine", color=GREY)


def _callout(s, x, y, tag, sheet_ref, r=5.2):
    s.circle(x, y, r, w="med", color=RED, fill="#ffffff")
    s.line(x - r, y, x + r, y, w="fine", color=RED)
    s.text(x, y - 1.0, tag, 3.0, "middle", RED, "700")
    s.text(x, y + 3.6, sheet_ref, 2.1, "middle", RED, "500")


def swept_wall(s, v, layers, face, z0, z1, n=72):
    """The wall drawn along the real envelope profile, not as a straight line.

    The outer face is asked of the massing at every height, so a torus, a cone
    or a leaning slab shows its actual profile in the wall section, and a
    straight extrusion degenerates to the same flat band it always was."""
    zs = [z0 + (z1 - z0) * i / n for i in range(n + 1)]
    faces = [face(z) for z in zs]
    off = 0.0
    for l in layers:
        t = l.t / 1000.0
        outer = [(faces[i] - off, zs[i]) for i in range(len(zs))]
        inner = [(faces[i] - off - t, zs[i]) for i in range(len(zs) - 1, -1, -1)]
        s.path(d_poly(v, outer + inner, True),
               w=l.line, color=INK if l.line == "cut" else GREY,
               fill=(s.pattern(l.pattern) if l.pattern else (l.fill or "none")))
        off += t


def swept_band(s, v, face, z0, z1, off0, off1, n=32, **style):
    """A strip of facade -- glazing, a spandrel -- following the envelope."""
    zs = [z0 + (z1 - z0) * i / n for i in range(n + 1)]
    a = [(face(z) - off0, z) for z in zs]
    b = [(face(z) - off1, z) for z in reversed(zs)]
    s.path(d_poly(v, a + b, True), **style)


def wall_section_sheet(project, out, number="A-400", detail_sheet="A-500",
                       paper="A1"):
    """A slice through the facade from the footing to the coping.

    The facade position is read from the massing at every level, so a leaning
    or curved envelope shows as it is rather than as a straight line drawn for
    convenience."""
    m = project.massing
    wall = BU.external_wall(project)
    grd = BU.ground_floor(project)
    flr = BU.upper_floor(project)
    rf = BU.roof(project)
    t = project.brief.wall_t
    depth = 6.0                                   # how much plate to show

    s = _sheet(project, number, "Typical Wall Section",
               "Footing to coping through the facade", "1 : 50",
               ["Dimensions in millimetres unless noted.",
                "Details 1 to 4 are drawn on %s." % detail_sheet,
                "Build-ups are sized from the model."])
    s.frame()
    x0, y0, x1, y1 = s.area()

    top = m.height + 0.9
    bot = -2.2
    scale = 50
    while (top - bot) * 1000.0 / scale > (y1 - y0 - 76) and scale < 200:
        scale = {50: 100, 100: 200}[scale]
    s.scale_text = "1 : %d" % scale

    def face(z):
        return m.extent_at(min(max(z, 0.05), m.height - 0.05), (1.0, 0.0))[1]

    u0 = face(1.2)
    ox = x0 + 190.0
    oy = y0 + 34.0 + (top) * 1000.0 / scale
    v = View(s, scale, ox - u0 * 1000.0 / scale, oy)

    earth(s, v, u0 - depth - 0.6, -0.20, u0 + 1.9, bot)
    ground_line(s, v, u0 + 0.05, u0 + 1.9, -0.20)

    # ground floor slab and its footing
    hstack(s, v, grd, 0.0, u0 - depth, u0)
    fw = max(min(SV.foundations(project)["pad_m"] * 0.32, 1.30), t + 0.40)
    fz = -(sum(l.t for l in grd) / 1000.0 + 0.06)
    rect(s, v, u0 - t / 2.0 - fw / 2.0, fz, u0 - t / 2.0 + fw / 2.0, fz - 0.70,
         w="cut", color=INK, fill=s.pattern("concrete"))

    # every level: slab, raised floor, ceiling, glazing and spandrel
    for i, lv in enumerate(m.levels):
        uf = face(lv.ffl + 1.2)
        nxt = (m.levels[i + 1].ffl if i + 1 < len(m.levels) else m.height)
        if i:
            slab = flr[2].t / 1000.0
            zt = lv.ffl - (flr[0].t + flr[1].t) / 1000.0
            rect(s, v, uf - depth, zt, uf, zt - slab, w="cut", color=INK,
                 fill=s.pattern("concrete"))
            rect(s, v, uf - depth, lv.ffl, uf - t, zt, w="fine", color=GREY,
                 fill="#f6f5f2")
            zc = zt - slab - flr[3].t / 1000.0
            rect(s, v, uf - depth, zc, uf - t, zc - flr[4].t / 1000.0,
                 w="fine", color=GREY, fill="#efefec")
        # the wall itself, following the envelope between the two levels
        swept_wall(s, v, wall, face, lv.ffl - (0.35 if i else 0.20), nxt)
        # glazing and spandrel on the facade line
        zg0, zg1 = lv.ffl + OP.SILL, nxt - OP.HEAD_GAP
        if zg1 - zg0 > 0.5:
            swept_band(s, v, face, zg0, zg1, 0.010, 0.055, w="thin",
                       color=INK, fill="#e9f0f4")
        if zg0 - (lv.ffl - OP.HEAD_GAP) > 0.1:
            swept_band(s, v, face, lv.ffl - OP.HEAD_GAP, zg0, 0.004, 0.048,
                       w="fine", color=GREY, fill="#c9ccd0")
        A.level_tag(s, *v.p(uf - depth + 0.8, lv.ffl), lv.ffl, "FFL")
        _figure(s, v, uf - 2.4, lv.ffl + 0.15)

    # roof and parapet
    uf = face(m.height - 0.05)
    hstack(s, v, rf, m.height, uf - depth, uf)
    rect(s, v, uf - t, m.height + 0.72, uf, m.height - 0.30, w="cut",
         color=INK, fill=s.pattern("block"))
    rect(s, v, uf - t - 0.06, m.height + 0.81, uf + 0.06, m.height + 0.72,
         w="med", color=INK, fill="#c3c6ca")

    # dimensions: floor to floor, then overall
    chain = [(lv.ffl, lv.name) for lv in m.levels] + [(m.height, "Roof")]
    for k in range(len(chain) - 1):
        A.dim_linear(s, v, (u0 - depth - 0.30, chain[k][0]),
                     (u0 - depth - 0.30, chain[k + 1][0]), 0,
                     "%d" % round((chain[k + 1][0] - chain[k][0]) * 1000),
                     size=2.2)
    A.dim_linear(s, v, (u0 - depth - 0.30, 0.0), (u0 - depth - 0.30, m.height),
                 -14, "%d overall" % round(m.height * 1000), size=2.4)

    # detail callouts
    for (z, tag) in ((0.10, "1"), (m.levels[min(1, len(m.levels) - 1)].ffl, "2"),
                     (m.height, "3")):
        px, py = v.p(face(max(z, 0.1)) + 0.55, z)
        _callout(s, px, py, tag, detail_sheet)
        s.line(px - 5.2, py, px - 14, py, w="fine", color=RED)
    px, py = v.p(face(1.2) + 0.55, m.levels[0].ffl + OP.SILL + 0.6)
    _callout(s, px, py, "4", detail_sheet)

    # ---- the build-ups, written out ------------------------------------
    sm = BU.summary(project)
    cx = x0 + 300
    yy = y0 + 24
    s.text(cx, yy, "BUILD-UPS", 3.6, "start", INK, "700", spacing=1.4)
    s.line(cx, yy + 4, x1 - 12, yy + 4, w="med", color=INK)
    yy += 12
    for lab, k, kind in (("EXTERNAL WALL", "wall", "wall"),
                         ("ROOF", "roof", "roof"),
                         ("INTERMEDIATE FLOOR", "floor", None),
                         ("GROUND FLOOR", "ground", "floor")):
        e = sm[k]
        s.text(cx, yy, lab, 2.6, "start", INK, "700", spacing=0.8)
        s.text(x1 - 12, yy, "%d mm overall" % e["thickness_mm"], 2.4, "end",
               INK, "600")
        yy += 6.0
        for l in e["layers"]:
            s.text(cx + 4, yy, "%5d" % round(l.t), 2.3, "start", GREY, "600")
            s.text(cx + 24, yy, l.name, 2.3, "start", GREY)
            s.line(cx, yy + 2.0, x1 - 12, yy + 2.0, w="hatch", color=LIGHT)
            yy += 5.4
        if kind:
            s.text(cx + 4, yy + 1, "U-value", 2.4, "start", INK, "600")
            s.text(x1 - 12, yy + 1, "%.2f W/m²K" % e["u"], 2.6, "end", INK,
                   "700")
            yy += 7.0
        yy += 7.0

    if yy < y1 - 40:
        s.text(cx, yy, "PERFORMANCE NOTES", 3.0, "start", GREY, "700",
               spacing=1.4)
        s.line(cx, yy + 3.6, x1 - 12, yy + 3.6, w="med", color=INK)
        yy += 10
        for line in ("Insulation is continuous past every slab edge; the "
                     "cavity barrier holds the compartment line.",
                     "Air permeability is sealed at the inner leaf, taped to "
                     "the window frames at every jamb.",
                     "Waterproofing is dressed 150 mm above the finished roof "
                     "and returned under the coping.",
                     "The footing width follows the bearing pressure used on "
                     "the foundation plan."):
            s.textbox(cx + 4, yy, [line], 2.3, 1.5, color=GREY)
            yy += 9.0
    # ---- heights, and where the section is cut --------------------------
    lv0 = m.levels[0]
    zone = (flr[0].t + flr[1].t + flr[2].t + flr[3].t + flr[4].t) / 1000.0
    clear = lv0.to_ffl - zone
    rows = [("Floor to floor", "%d mm" % round(lv0.to_ffl * 1000)),
            ("Floor zone: raised floor, slab, services, ceiling",
             "%d mm" % round(zone * 1000)),
            ("Clear height, finished floor to ceiling",
             "%d mm" % round(clear * 1000)),
            ("Raised floor void", "%d mm" % round(flr[1].t)),
            ("Services zone above the ceiling", "%d mm" % round(flr[3].t)),
            ("Sill of the vision panel", "%d mm" % round(OP.SILL * 1000)),
            ("Head of the vision panel",
             "%d mm" % round((lv0.to_ffl - OP.HEAD_GAP) * 1000)),
            ("Vision panel height",
             "%d mm" % round((lv0.to_ffl - OP.HEAD_GAP - OP.SILL) * 1000)),
            ("Daylight opening as a share of the storey",
             "%.0f %%" % (100.0 * (lv0.to_ffl - OP.HEAD_GAP - OP.SILL)
                          / lv0.to_ffl)),
            ("Height to the top of the coping",
             "%d mm" % round((m.height + 0.81) * 1000))]
    if yy < y1 - 120:
        s.text(cx, yy, "HEIGHTS", 3.0, "start", GREY, "700", spacing=1.4)
        s.line(cx, yy + 3.6, x1 - 12, yy + 3.6, w="med", color=INK)
        yy += 10
        for k, val in rows:
            s.text(cx + 4, yy, k, 2.4, "start", GREY)
            s.text(x1 - 12, yy, val, 2.5, "end", INK, "600")
            s.line(cx, yy + 2.2, x1 - 12, yy + 2.2, w="hatch", color=LIGHT)
            yy += 6.4
        yy += 14

    band = y1 - 20 - yy
    if band > 60:
        from .draw import fit_scale, ring_path, region_path
        plate = m.levels[0].plate
        bx = plate.bbox()
        kw = x1 - 12 - cx
        ks = fit_scale(bx, kw, band, margin_mm=16.0)
        mx, my = (bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0
        kv = View(s, ks, cx + kw / 2.0 - mx * 1000.0 / ks,
                  yy + band / 2.0 + my * 1000.0 / ks)
        s.text(cx, yy - 6, "WHERE THE SECTION IS CUT", 3.0, "start", GREY,
               "700", spacing=1.4)
        s.line(cx, yy - 2.4, x1 - 12, yy - 2.4, w="med", color=INK)
        s.path(ring_path(kv, plate.outer), w="med", color=INK, fill="#f6f5f2")
        for hole in plate.holes:
            s.path(ring_path(kv, hole), w="med", color=INK, fill="#ffffff")
        reach = max((bx[2] - bx[0]) * 0.22, depth + 4.0)
        a, b = kv.p(u0 - reach, my), kv.p(u0 + 2.5, my)
        s.line(a[0], a[1], b[0], b[1], w="cut", color=RED, dash="10,3,2,3")
        s.circle(b[0], b[1], 3.2, w="med", color=RED, fill="#ffffff")
        s.text(b[0], b[1] + 1.1, "W", 2.4, "middle", RED, "700")
        s.text(cx, yy + band + 6, "Cut on the deepest facade; the section "
               "applies to every elevation unless noted.", 2.2, "start", GREY,
               italic=True)

    A.scale_bar(s, v, x0 + 10, y1 - 24, 5, 5, label="SCALE 1:%d" % scale)
    return s.save(out)
