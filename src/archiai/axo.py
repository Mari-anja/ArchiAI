"""Axonometric drawings.

A very small painter's-algorithm renderer: quads are generated from the same
parametric surface as everything else, back faces are culled, the rest are
sorted by depth and shaded by their normal.  No libraries, no ray tracing --
just enough to make an honest cutaway.
"""

import math
from .svgkit import Sheet, INK, GREY, LIGHT, BLUE, RED, f, d_poly_mm
from . import annot as A
from . import params as P
from . import program as PG


# ---------------------------------------------------------------------------
class Cam:
    def __init__(self, az=-125.0, el=26.0, scale=1.0, cx=0.0, cy=0.0):
        a, e = math.radians(az), math.radians(el)
        self.right = (-math.sin(a), math.cos(a), 0.0)
        self.up = (-math.cos(a) * math.sin(e), -math.sin(a) * math.sin(e), math.cos(e))
        self.dir = (math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))
        self.k, self.cx, self.cy = scale, cx, cy

    def p(self, v):
        x = v[0] * self.right[0] + v[1] * self.right[1] + v[2] * self.right[2]
        y = v[0] * self.up[0] + v[1] * self.up[1] + v[2] * self.up[2]
        return (self.cx + x * self.k, self.cy - y * self.k)

    def depth(self, v):
        return v[0] * self.dir[0] + v[1] * self.dir[1] + v[2] * self.dir[2]


LIGHT_DIR = (-0.36, -0.52, 0.77)


def _newell(pts):
    nx = ny = nz = 0.0
    m = len(pts)
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


def _norm(a):
    m = math.sqrt(sum(c * c for c in a)) or 1.0
    return (a[0] / m, a[1] / m, a[2] / m)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _shade(base, n):
    lit = max(0.0, sum(n[i] * LIGHT_DIR[i] for i in range(3)))
    t = 0.42 + 0.58 * lit
    r = int(base[0] * t + 255 * (1 - t) * 0.06)
    g = int(base[1] * t + 255 * (1 - t) * 0.06)
    b = int(base[2] * t + 255 * (1 - t) * 0.06)
    return "#%02x%02x%02x" % (min(255, r), min(255, g), min(255, b))


class Scene:
    def __init__(self, cam):
        self.cam = cam
        self.faces = []          # (depth, points2d, fill, stroke, width)

    def quad(self, pts, base, stroke=None, w="hatch", cull=True, flat=None):
        # Newell's method over every vertex. Taking the cross product of the
        # first three points fails whenever they are nearly collinear, which is
        # exactly what happens on a polygon traced round a curve -- the normal
        # comes out as noise and the face shades almost black.
        n = _norm(_newell(pts))
        if cull and sum(n[i] * self.cam.dir[i] for i in range(3)) <= 0.02:
            return
        d = sum(self.cam.depth(p) for p in pts) / len(pts)
        fill = flat if flat else _shade(base, n)
        self.faces.append((d, [self.cam.p(p) for p in pts], fill, stroke, w))

    def line3(self, a, b, color=INK, w="fine", bias=0.0):
        d = (self.cam.depth(a) + self.cam.depth(b)) / 2.0 + bias
        self.faces.append((d, [self.cam.p(a), self.cam.p(b)], None, color, w))

    def emit(self, sheet):
        for (d, pts, fill, stroke, w) in sorted(self.faces, key=lambda t: t[0]):
            if fill is None:
                sheet.line(pts[0][0], pts[0][1], pts[1][0], pts[1][1], w=w, color=stroke)
            else:
                sheet.path(d_poly_mm(pts, True), w=(w if stroke else None),
                           color=stroke or INK, fill=fill)


# ---------------------------------------------------------------------------
def surf(theta, phi, rad=None):
    rad = P.TUBE_R if rad is None else rad
    t, p = math.radians(theta), math.radians(phi)
    rho = P.MAJOR_R + rad * math.cos(p)
    return (rho * math.cos(t), rho * math.sin(t), P.TUBE_Z + rad * math.sin(p))


GLASS = (150, 176, 198)
CROWNC = (176, 180, 176)
PV = (52, 62, 74)
SLAB = (206, 200, 190)
GROUND = (214, 222, 205)
COURT = (196, 214, 186)


def _shell(sc, t0, t1, dt=3.0, dphi=4.0):
    phis = []
    p = P.PHI_SPRING_OUT
    while p < P.PHI_SPRING_IN - 1e-6:
        phis.append((p, min(p + dphi, P.PHI_SPRING_IN)))
        p += dphi
    t = t0
    while t < t1 - 1e-6:
        ta, tb = t, min(t + dt, t1)
        for (pa, pb) in phis:
            mid = (pa + pb) / 2.0
            if 64.0 <= mid <= 88.0:
                base = PV
            elif 62.0 <= mid <= 118.0:
                base = CROWNC
            else:
                base = GLASS
            sc.quad([surf(ta, pa), surf(tb, pa), surf(tb, pb), surf(ta, pb)], base)
        t += dt


def _cut_face(sc, theta, flip=False):
    """The sectioned face of the shell and the slabs at a cut plane."""
    pts_o, pts_i = [], []
    n = 60
    for i in range(n + 1):
        phi = P.PHI_SPRING_OUT + (P.PHI_SPRING_IN - P.PHI_SPRING_OUT) * i / n
        pts_o.append(surf(theta, phi, P.TUBE_R))
        pts_i.append(surf(theta, phi, P.TUBE_R - P.ENV_T))
    for i in range(n):
        sc.quad([pts_o[i], pts_o[i + 1], pts_i[i + 1], pts_i[i]], (120, 120, 118),
                cull=False, flat="#8f8f8c")
    t = math.radians(theta)
    for z, th in ((P.FFL_00, 0.35), (P.FFL_01, P.SLAB_T)):
        a = (P.R_IN_00 * math.cos(t), P.R_IN_00 * math.sin(t), z)
        b = (P.R_OUT_00 * math.cos(t), P.R_OUT_00 * math.sin(t), z)
        c = (P.R_OUT_00 * math.cos(t), P.R_OUT_00 * math.sin(t), z - th)
        d = (P.R_IN_00 * math.cos(t), P.R_IN_00 * math.sin(t), z - th)
        sc.quad([a, b, c, d], (140, 134, 126), cull=False, flat="#9b948b")


def _slab(sc, z, t0, t1, dt=3.0, r0=None, r1=None):
    r0 = P.R_IN_00 if r0 is None else r0
    r1 = P.R_OUT_00 if r1 is None else r1
    t = t0
    while t < t1 - 1e-6:
        ta, tb = t, min(t + dt, t1)
        pa, pb = math.radians(ta), math.radians(tb)
        sc.quad([(r0 * math.cos(pa), r0 * math.sin(pa), z),
                 (r1 * math.cos(pa), r1 * math.sin(pa), z),
                 (r1 * math.cos(pb), r1 * math.sin(pb), z),
                 (r0 * math.cos(pb), r0 * math.sin(pb), z)], SLAB)
        t += dt


def _disc(sc, z, r, base, t0=0.0, t1=360.0, r0=0.0, dt=6.0):
    t = t0
    while t < t1 - 1e-6:
        ta, tb = t, min(t + dt, t1)
        pa, pb = math.radians(ta), math.radians(tb)
        sc.quad([(r0 * math.cos(pa), r0 * math.sin(pa), z),
                 (r * math.cos(pa), r * math.sin(pa), z),
                 (r * math.cos(pb), r * math.sin(pb), z),
                 (r0 * math.cos(pb), r0 * math.sin(pb), z)], base)
        t += dt


def _columns(sc, t0, t1):
    for i in range(P.RADIAL_DIV):
        th = i * P.RADIAL_STEP
        if not (t0 <= th <= t1):
            continue
        for r in P.COL_RADII:
            t = math.radians(th)
            x, y = r * math.cos(t), r * math.sin(t)
            for (z0, z1) in ((0.0, P.FFL_01 - P.SLAB_T), (P.FFL_01, P.FFL_01 + 3.6)):
                sc.line3((x, y, z0), (x, y, z1), color=INK, w="med", bias=1.5)


def _ribs(sc, t0, t1, step=10.0, color="#5d6672", w="fine", bias=0.0, rad=None):
    rad = P.TUBE_R - P.ENV_T - 0.25 if rad is None else rad
    th = 0.0
    while th <= 360.0:
        if t0 <= th <= t1:
            prev = None
            for i in range(61):
                phi = P.PHI_SPRING_OUT + (P.PHI_SPRING_IN - P.PHI_SPRING_OUT) * i / 60
                cur = surf(th, phi, rad)
                if prev:
                    sc.line3(prev, cur, color=color, w=w, bias=bias)
                prev = cur
        th += step


# ---------------------------------------------------------------------------
def _desks_3d(sc, level, z, t0, t1):
    polys, _ = PG.desks(level)
    for pts in polys:
        tm = math.degrees(math.atan2(sum(p[1] for p in pts) / 4.0,
                                     sum(p[0] for p in pts) / 4.0)) % 360.0
        if not (t0 <= tm <= t1):
            continue
        sc.quad([(x, y, z + 0.74) for (x, y) in pts], (176, 168, 156), cull=False)


def _cores_3d(sc, z0, z1, t0, t1):
    for (cid, tc, half) in P.CORES:
        if not (t0 <= tc <= t1):
            continue
        for a, b in ((tc - half, tc - half), (tc + half, tc + half)):
            pass
        for aa in (tc - half, tc + half):
            t = math.radians(aa)
            p0 = (P.CORE_R0 * math.cos(t), P.CORE_R0 * math.sin(t), z0)
            p1 = (P.CORE_R1 * math.cos(t), P.CORE_R1 * math.sin(t), z0)
            sc.quad([p0, p1, (p1[0], p1[1], z1), (p0[0], p0[1], z1)],
                    (168, 168, 164), cull=False)


def cutaway(sheet, cx, cy, scale, cut0=266.0, cut1=360.0, ribs=True):
    cam = Cam(az=-122.0, el=27.0, scale=scale, cx=cx, cy=cy)
    sc = Scene(cam)
    _disc(sc, -0.02, P.SITE_R * 0.42, GROUND, r0=0.0, dt=7.5)
    _disc(sc, 0.0, P.R_IN_00, COURT, r0=0.0, dt=7.5)
    _slab(sc, P.FFL_00, 0.0, 360.0)
    _desks_3d(sc, 0, P.FFL_00, cut0 - 4.0, 360.0)
    _cores_3d(sc, P.FFL_00, P.FFL_01 + 3.4, cut0 - 100.0, 360.0)
    _columns(sc, cut0 - 100.0, 360.0)
    _slab(sc, P.FFL_01, 0.0, cut0)
    _desks_3d(sc, 1, P.FFL_01, cut0 - 4.0, 360.0)
    if ribs:
        _ribs(sc, cut0 - 92.0, cut1, step=10.0, bias=0.6)
    _shell(sc, 0.0, cut0)
    _cut_face(sc, cut0)
    _cut_face(sc, 0.0)
    sc.emit(sheet)
    return cam


def axo_sheet(out):
    s = Sheet("A-800", "Axonometric and Assembly", "1 : 300 and 1 : 620", "A1",
              "Cutaway from the south-west", P.PROJECT,
              ["Cut on radial gridlines R01 and R28.",
               "Generated from the same parametric model",
               "as the plans and sections."])
    s.frame()
    x0, y0, x1, y1 = s.area()

    cam = cutaway(s, 244.0, 318.0, 1000.0 / 300.0)
    s.text(60.0, 494.0, "CUTAWAY AXONOMETRIC", 5.2, "start", INK, "700", spacing=0.8)
    s.text(60.0, 501.0, "From the south-west, 27° above the horizon; a quarter of "
                        "the ring removed on R01 and R28.   1 : 300", 2.4, "start", GREY)

    # ---- exploded assembly, at a smaller scale -------------------------
    ex, ey, k = 540.0, 160.0, 1000.0 / 620.0
    layers = [
        ("Shell — 36 hoop ribs, 5 244 m² envelope", 68.0, "shell"),
        ("Level 01 — 2 714 m² plate at +4.200", 47.0, "l01"),
        ("Frame — 72 columns, radial beams at 5°", 30.0, "frame"),
        ("Level 00 — 2 714 m² plate at +0.000", 14.0, "l00"),
        ("Site and courtyard", -16.0, "site"),
    ]
    for (label, lift, kind) in layers:
        cam2 = Cam(az=-122.0, el=27.0, scale=k, cx=ex, cy=ey + 190.0)
        sc = Scene(cam2)
        off = lift

        def raise_(fn, *a, **kw):
            fn(*a, **kw)

        if kind == "shell":
            _shell_lift(sc, off)
        elif kind == "l01":
            _slab_lift(sc, P.FFL_01 + off)
        elif kind == "frame":
            _frame_lift(sc, off)
        elif kind == "l00":
            _slab_lift(sc, P.FFL_00 + off)
        else:
            _site_lift(sc, off)
        sc.emit(s)
        px, py = cam2.p((P.R_MAX * 0.55, P.R_MAX * 0.55, off))
        s.line(px, py, ex + 74, py, w="dim", color=GREY)
        s.circle(px, py, 0.55, w=None, fill=GREY)
        s.text(ex + 77, py + 0.8, label, 2.2, "start", INK)

    s.text(ex - 84, 494.0, "EXPLODED ASSEMBLY", 4.4, "start", INK, "700", spacing=0.8)
    s.text(ex - 84, 501.0, "1 : 620", 2.4, "start", GREY)

    A.notes_block(s, x0 + 8, y0 + 16, "THE PARTI", [
        "A circle of radius 7 500 swept around a vertical",
        "axis at 30 000 makes the whole building. The",
        "ground plane truncates the torus exactly at the",
        "ground-floor slab, so the shell springs from the",
        "paving without a plinth, leans out to its widest",
        "at +2.100, and returns to a crown at +9.600.",
        "",
        "Both floor plates are chords of the same circle,",
        "set symmetrically about its axis. They come out",
        "identical: 14 400 deep, daylit from the outer",
        "facade and from the courtyard, with no point on",
        "either plate more than 7 200 from a window.",
    ])
    return s.save(out)


def _shell_lift(sc, off):
    for (a, b) in ((0.0, 360.0),):
        t = a
        while t < b - 1e-6:
            ta, tb = t, min(t + 6.0, b)
            p = P.PHI_SPRING_OUT
            while p < P.PHI_SPRING_IN - 1e-6:
                pa, pb = p, min(p + 8.0, P.PHI_SPRING_IN)
                mid = (pa + pb) / 2.0
                base = PV if 64 <= mid <= 88 else (CROWNC if 62 <= mid <= 118 else GLASS)
                q = [surf(ta, pa), surf(tb, pa), surf(tb, pb), surf(ta, pb)]
                sc.quad([(x, y, z + off) for (x, y, z) in q], base)
                p += 8.0
            t += 6.0


def _slab_lift(sc, z):
    t = 0.0
    while t < 360.0 - 1e-6:
        ta, tb = t, t + 6.0
        pa, pb = math.radians(ta), math.radians(tb)
        r0, r1 = P.R_IN_00, P.R_OUT_00
        sc.quad([(r0 * math.cos(pa), r0 * math.sin(pa), z),
                 (r1 * math.cos(pa), r1 * math.sin(pa), z),
                 (r1 * math.cos(pb), r1 * math.sin(pb), z),
                 (r0 * math.cos(pb), r0 * math.sin(pb), z)], SLAB)
        t += 6.0


def _frame_lift(sc, off):
    for i in range(P.RADIAL_DIV):
        th = math.radians(i * P.RADIAL_STEP)
        for r in P.COL_RADII:
            x, y = r * math.cos(th), r * math.sin(th)
            sc.line3((x, y, off), (x, y, off + P.FFL_01), color=INK, w="fine")
    for r in P.COL_RADII:
        prev = None
        for i in range(73):
            t = math.radians(i * 5.0)
            cur = (r * math.cos(t), r * math.sin(t), off + P.FFL_01)
            if prev:
                sc.line3(prev, cur, color="#5d6672", w="hatch")
            prev = cur
    for i in range(P.RADIAL_DIV * 2):
        t = math.radians(i * P.SECONDARY_STEP)
        sc.line3((P.R_IN_00 * math.cos(t), P.R_IN_00 * math.sin(t), off + P.FFL_01),
                 (P.R_OUT_00 * math.cos(t), P.R_OUT_00 * math.sin(t), off + P.FFL_01),
                 color="#5d6672", w="hatch")


def _site_lift(sc, off):
    _disc(sc, off, P.SITE_R * 0.55, GROUND, r0=0.0, dt=10.0)
    _disc(sc, off + 0.02, P.R_IN_00, COURT, r0=0.0, dt=10.0)
