"""Setting-out grids.

A grid knows three things: where its lines are, what they are called, and how
to dimension between them. Orthogonal buildings get letters and numbers;
buildings set out from a centre get radii and angles. The sheet code asks the
same questions of both.
"""

import math
from . import geom2d as G


def _alpha(i):
    """1 -> A, 26 -> Z, 27 -> AA. Skips I and O, as drawing offices do."""
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    out = ""
    i += 1
    while i > 0:
        i, r = divmod(i - 1, len(letters))
        out = letters[r] + out
    return out


class GridLine:
    __slots__ = ("label", "a", "b", "kind")

    def __init__(self, label, a, b, kind="line"):
        self.label, self.a, self.b, self.kind = label, a, b, kind


class Grid:
    def lines(self):
        raise NotImplementedError

    def dimension_runs(self):
        """[(label, [points along which to dimension]), ...]"""
        return []


class OrthoGrid(Grid):
    """Letters on one axis, numbers on the other -- the default for anything
    drawn as a footprint."""

    def __init__(self, bbox, spacing=7.2, margin=8.0, angle=0.0):
        x0, y0, x1, y1 = bbox
        self.bbox, self.margin, self.angle = bbox, margin, angle
        self.spacing = spacing
        self.xs = self._positions(x0, x1, spacing)
        self.ys = self._positions(y0, y1, spacing)

    @staticmethod
    def _positions(a, b, s):
        span = b - a
        n = max(1, int(round(span / s)))
        step = span / n
        return [a + step * i for i in range(n + 1)]

    @property
    def actual_spacing(self):
        return ((self.xs[1] - self.xs[0]) if len(self.xs) > 1 else 0.0,
                (self.ys[1] - self.ys[0]) if len(self.ys) > 1 else 0.0)

    def lines(self):
        x0, y0, x1, y1 = self.bbox
        m = self.margin
        out = []
        for i, x in enumerate(self.xs):
            out.append(GridLine(str(i + 1), (x, y0 - m), (x, y1 + m)))
        for j, y in enumerate(self.ys):
            out.append(GridLine(_alpha(j), (x0 - m, y), (x1 + m, y)))
        return out

    def dimension_runs(self):
        x0, y0, x1, y1 = self.bbox
        m = self.margin
        return [("x", [(x, y0 - m) for x in self.xs]),
                ("y", [(x0 - m, y) for y in self.ys])]

    def columns(self, region, inset=0.0):
        """Grid intersections that fall inside the plate."""
        out = []
        for x in self.xs:
            for y in self.ys:
                if region.contains((x, y)):
                    out.append((x, y))
        return out


class RadialGrid(Grid):
    """Radial spokes and concentric rings -- for buildings set out from a
    centre, which is what a solid of revolution always is."""

    def __init__(self, divisions=36, ring_radii=(), r_inner=0.0, r_outer=1.0,
                 margin=3.4, centre=(0.0, 0.0), prefix="R"):
        self.n, self.rings = divisions, list(ring_radii)
        self.r0, self.r1, self.margin = r_inner, r_outer, margin
        self.centre, self.prefix = centre, prefix

    @property
    def step(self):
        return 360.0 / self.n

    def lines(self):
        cx, cy = self.centre
        out = []
        for i in range(self.n):
            t = math.radians(i * self.step)
            out.append(GridLine("%s%02d" % (self.prefix, i + 1),
                                (cx + self.r0 * math.cos(t), cy + self.r0 * math.sin(t)),
                                (cx + (self.r1 + self.margin) * math.cos(t),
                                 cy + (self.r1 + self.margin) * math.sin(t))))
        for j, r in enumerate(self.rings):
            out.append(GridLine("C%d" % (j + 1), None, None, kind="ring"))
        return out

    def columns(self, radii, thetas=None):
        cx, cy = self.centre
        thetas = thetas or [i * self.step for i in range(self.n)]
        return [(cx + r * math.cos(math.radians(t)), cy + r * math.sin(math.radians(t)))
                for t in thetas for r in radii]

    def dimension_runs(self):
        return [("radial", [(r, 0.0) for r in self.rings])]


def choose(massing, spacing=7.2):
    """Pick the grid a typology deserves."""
    from .massing import Revolve
    if isinstance(massing, Revolve):
        b = massing.mesh().bounds()
        return RadialGrid(divisions=36, r_inner=0.0, r_outer=max(b[3], b[4]))
    return OrthoGrid(massing.footprint().bbox(), spacing)
