"""A building as a composition of volumes, rather than a shape off a menu.

The engine used to hold eleven plan shapes -- bar, courtyard, L, tower, circle
and a few polygons -- and every building anyone asked for had to be one of
them. That is why everything came back a box. No amount of understanding a
brief helps if the only thing that can be built is a box.

Here a building is a list of volumes. Each one has a footprint, a place, a
rotation, and the range of heights it occupies; each either adds to the mass
or is carved out of it; and each can turn or grow as it rises. A floor plate
is then just those volumes evaluated at that height and booleaned together,
which is a thing the engine can do exactly.

Two crossed bars, a slab with a wedge cut out of it, a tower that twists, a
podium with a thinner tower rising off-centre from it, a block split by a
canyon -- all of them are three or four lines of this, and none of them were
expressible at all before.
"""

import math

from . import clip as CL
from . import geom2d as G


ADD, CUT = "add", "cut"

SHAPES = ("box", "cylinder", "polygon", "wedge", "outline")


def _rotate(pts, deg, about=(0.0, 0.0)):
    if not deg:
        return list(pts)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    ox, oy = about
    return [(ox + (x - ox) * c - (y - oy) * s,
             oy + (x - ox) * s + (y - oy) * c) for (x, y) in pts]


def _scaled(pts, k, about):
    if abs(k - 1.0) < 1e-12:
        return list(pts)
    ox, oy = about
    return [(ox + (x - ox) * k, oy + (y - oy) * k) for (x, y) in pts]


class Volume:
    """One piece of the building, and the heights over which it exists."""

    __slots__ = ("shape", "width", "depth", "sides", "x", "y", "rotation",
                 "base", "top", "twist", "taper", "op", "outline", "name")

    def __init__(self, shape="box", width=40.0, depth=24.0, sides=6, x=0.0,
                 y=0.0, rotation=0.0, base=0.0, top=None, twist=0.0,
                 taper=0.0, op=ADD, outline=None, name=""):
        self.shape = shape if shape in SHAPES else "box"
        self.width = max(0.5, float(width))
        self.depth = max(0.5, float(depth))
        self.sides = max(3, min(96, int(sides)))
        self.x, self.y = float(x), float(y)
        self.rotation = float(rotation)
        self.base = float(base)
        self.top = None if top is None else float(top)
        self.twist = float(twist)          # degrees per metre of height
        self.taper = float(taper)          # fraction of size gained per metre
        self.op = CUT if op == CUT else ADD
        self.outline = [tuple(p) for p in outline] if outline else None
        self.name = name or self.shape

    # -- the footprint of this volume, before it is placed ------------------
    def _base_ring(self):
        if self.shape == "outline" and self.outline and len(self.outline) >= 3:
            return list(self.outline)
        w, d = self.width, self.depth
        if self.shape == "cylinder":
            n = 72
            return [(w / 2.0 * math.cos(2 * math.pi * i / n),
                     d / 2.0 * math.sin(2 * math.pi * i / n)) for i in range(n)]
        if self.shape == "polygon":
            n = self.sides
            return [(w / 2.0 * math.cos(math.pi / 2 + 2 * math.pi * i / n),
                     d / 2.0 * math.sin(math.pi / 2 + 2 * math.pi * i / n))
                    for i in range(n)]
        if self.shape == "wedge":
            return [(-w / 2.0, -d / 2.0), (w / 2.0, -d / 2.0), (-w / 2.0, d / 2.0)]
        return [(-w / 2.0, -d / 2.0), (w / 2.0, -d / 2.0),
                (w / 2.0, d / 2.0), (-w / 2.0, d / 2.0)]

    def spans(self, z, tol=1e-6):
        if z < self.base - tol:
            return False
        return self.top is None or z < self.top - tol

    def at(self, z):
        """This volume's outline at height z, in world coordinates."""
        ring = self._base_ring()
        rise = max(0.0, z - self.base)
        k = 1.0 + self.taper * rise
        if k < 0.02:
            return None
        ring = _scaled(ring, k, (0.0, 0.0))
        ring = _rotate(ring, self.rotation + self.twist * rise)
        ring = [(x + self.x, y + self.y) for (x, y) in ring]
        return ring if len(ring) >= 3 else None

    def describe(self):
        bits = ["%s %.0f x %.0f m" % (self.shape, self.width, self.depth)]
        if self.x or self.y:
            bits.append("at %+.0f, %+.0f" % (self.x, self.y))
        if self.rotation:
            bits.append("turned %.0f deg" % self.rotation)
        if self.twist:
            bits.append("twisting %.1f deg/m" % self.twist)
        if self.taper:
            bits.append("%s %.0f%% per metre"
                        % ("growing" if self.taper > 0 else "shrinking",
                           abs(self.taper) * 100))
        span = "from %.1f m" % self.base
        span += (" to %.1f m" % self.top) if self.top is not None else " up"
        bits.append(span)
        return ("cut out: " if self.op == CUT else "") + ", ".join(bits)


class Form:
    """The whole composition: volumes added and carved, in order."""

    def __init__(self, volumes=None, name=""):
        self.volumes = list(volumes or [])
        self.name = name

    def add(self, *v):
        self.volumes.extend(v)
        return self

    @property
    def height(self):
        top = 0.0
        for v in self.volumes:
            if v.op != ADD:
                continue
            top = max(top, v.top if v.top is not None else v.base)
        return top

    def rings_at(self, z):
        """Every ring of the plan at height z: outlines first, then holes."""
        solid = []
        for v in self.volumes:
            if v.op != ADD or not v.spans(z):
                continue
            r = v.at(z)
            if r:
                solid = CL.union(solid, [r]) if solid else [r]
        if not solid:
            return []
        for v in self.volumes:
            if v.op != CUT or not v.spans(z):
                continue
            r = v.at(z)
            if r:
                solid = CL.difference(solid, [r])
                if not solid:
                    return []
        return solid

    def region_at(self, z):
        """The plan at height z as a Region, or None where there is nothing.

        A composition can come apart into separate pieces at some height -- two
        towers off one podium, above the podium. The engine plans one plate per
        level, so the largest piece is the plate and the rest are reported
        rather than silently kept or silently dropped."""
        rings = self.rings_at(z)
        if not rings:
            return None
        outers = [r for r in rings if CL.signed_area(r) > 0]
        holes = [r for r in rings if CL.signed_area(r) <= 0]
        if not outers:
            return None
        outers.sort(key=lambda r: -abs(CL.signed_area(r)))
        keep = outers[0]
        mine = [h for h in holes if CL._nested_in(h, keep)]
        return G.Region(keep, mine)

    def pieces_at(self, z):
        """How many separate pieces the plan is in at this height."""
        return sum(1 for r in self.rings_at(z) if CL.signed_area(r) > 0)

    def describe(self):
        return [v.describe() for v in self.volumes]
