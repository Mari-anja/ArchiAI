"""The one abstraction the whole engine turns on.

Every drawing this system produces asks a building only a handful of questions.
Answer them and you get plans, sections, elevations, a mesh and schedules for
free -- whatever shape the building is.

    plate(i)        the floor plate at a level        -> plans, areas, framing
    cut(z)          solid material at a height        -> plan cut lines
    mesh()          the envelope as triangles         -> 3D, renders
    section(...)    generic, from mesh + plates       -> sections
    silhouette(...) generic, from mesh                -> elevations

A typology only has to implement the first three. The last two have working
generic implementations here, which a typology may override when it can do
better analytically -- as `Revolve` does, because a plane through the axis of a
solid of revolution cuts it in exact profile curves rather than sampled ones.
"""

import math
from . import geom2d as G


# ---------------------------------------------------------------------------
class Level:
    __slots__ = ("index", "name", "ffl", "to_ffl", "plate", "slab_t", "_band")

    def __init__(self, index, name, ffl, to_ffl, plate, slab_t=0.30):
        self.index, self.name = index, name
        self.ffl, self.to_ffl = ffl, to_ffl
        self.plate, self.slab_t = plate, slab_t
        self._band = None

    def band(self, t):
        """The wall band of this plate, worked out once.

        Cutting the building at a height is the single most asked question in
        the whole engine -- every plan, every section sample, every point on a
        swept wall -- and the answer for a given level never changes. Working
        it out afresh each time makes a mitred offset of every ring, which is
        what turned a tall building from linear into quadratic."""
        if self._band is None or self._band[0] != t:
            self._band = (t, self.plate.band(t))
        return self._band[1]

    @property
    def area(self):
        return self.plate.area

    def __repr__(self):
        return "<Level %s FFL %+.3f  %.0f m2>" % (self.name, self.ffl, self.area)


class Zone:
    """A band of the envelope, addressed the way the typology addresses it."""
    __slots__ = ("code", "kind", "lo", "hi", "note")

    def __init__(self, code, kind, lo, hi, note=""):
        self.code, self.kind, self.lo, self.hi, self.note = code, kind, lo, hi, note


# ---------------------------------------------------------------------------
class Mesh:
    __slots__ = ("v", "f", "groups", "_bounds")

    def __init__(self):
        self.v, self.f, self.groups = [], [], {}
        self._bounds = None

    def add(self, verts, group="shell"):
        i0 = len(self.v)
        self.v.extend(verts)
        self._bounds = None
        return list(range(i0, len(self.v)))

    def face(self, idx, group="shell"):
        self.f.append(tuple(idx))
        self.groups.setdefault(group, []).append(len(self.f) - 1)

    def quad(self, a, b, c, d, group="shell"):
        i = self.add([a, b, c, d])
        self.face(i, group)

    def tris(self):
        for fi in self.f:
            for k in range(1, len(fi) - 1):
                yield (self.v[fi[0]], self.v[fi[k]], self.v[fi[k + 1]])

    @property
    def n_faces(self):
        return len(self.f)

    def bounds(self):
        # Scanning every vertex is cheap once and ruinous eight thousand times,
        # which is how often a swept drawing asks a building how tall it is.
        if self._bounds is None:
            xs = [p[0] for p in self.v]; ys = [p[1] for p in self.v]; zs = [p[2] for p in self.v]
            self._bounds = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        return self._bounds

    # -- slicing -----------------------------------------------------------
    def slice_plane(self, point, normal):
        """Segments where the mesh crosses a plane. Returns 3D segments."""
        nx, ny, nz = normal
        px, py, pz = point
        segs = []
        for tri in self.tris():
            d = [(v[0] - px) * nx + (v[1] - py) * ny + (v[2] - pz) * nz for v in tri]
            pts = []
            for i in range(3):
                j = (i + 1) % 3
                if (d[i] > 0) != (d[j] > 0):
                    t = d[i] / (d[i] - d[j])
                    pts.append(tuple(tri[i][k] + (tri[j][k] - tri[i][k]) * t for k in range(3)))
                elif abs(d[i]) < 1e-12:
                    pts.append(tri[i])
            if len(pts) >= 2:
                segs.append((pts[0], pts[1]))
        return segs

    def slice_horizontal(self, z):
        segs = self.slice_plane((0, 0, z), (0, 0, 1))
        return [((a[0], a[1]), (b[0], b[1])) for (a, b) in segs]

    # -- silhouette --------------------------------------------------------
    def silhouette_edges(self, view_dir):
        """Edges where facing flips, plus open boundary edges."""
        edge = {}
        for fi in self.f:
            n = _face_normal([self.v[i] for i in fi])
            facing = (n[0] * view_dir[0] + n[1] * view_dir[1] + n[2] * view_dir[2]) > 0
            for k in range(len(fi)):
                a, b = fi[k], fi[(k + 1) % len(fi)]
                key = (a, b) if a < b else (b, a)
                edge.setdefault(key, []).append(facing)
        out = []
        for (a, b), facings in edge.items():
            if len(facings) == 1 or (True in facings and False in facings):
                out.append((self.v[a], self.v[b]))
        return out


def _face_normal(pts):
    n = [0.0, 0.0, 0.0]
    m = len(pts)
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    l = math.sqrt(sum(c * c for c in n)) or 1.0
    return (n[0] / l, n[1] / l, n[2] / l)


# ---------------------------------------------------------------------------
class SectionResult:
    """A vertical cut, in the section plane's own 2D frame: u across, v up."""

    def __init__(self):
        self.cut = []        # closed polygons of material
        self.slabs = []      # (u0, u1, z_top, thickness) per level
        self.beyond = []     # (z, lo, hi) extent of everything past the cut
        self.levels = []     # (name, ffl)


def _trace(run):
    """Turn a run of stable interval counts into closed polygons."""
    if len(run) < 2:
        return []
    k = len(run[0][1])
    out = []
    for j in range(k):
        left = [(ivs[j][0], z) for (z, ivs) in run]
        right = [(ivs[j][1], z) for (z, ivs) in run]
        poly = left + right[::-1]
        if len(poly) >= 3:
            out.append((poly, True))
    return out


class Elevation2D:
    def __init__(self):
        self.outline = []    # silhouette polylines, (x, z)
        self.joints = []     # horizontal joint lines from envelope zones
        self.verticals = []  # meridian / mullion lines
        self.openings = []


# ---------------------------------------------------------------------------
class Massing:
    """Base typology. Implement plate/cut/mesh; the rest comes free."""

    name = "massing"

    def __init__(self, levels, zones=None):
        self.levels = levels
        self.zones = zones or []
        self._mesh = None

    # -- required ----------------------------------------------------------
    def plate(self, i):
        return self.levels[i].plate

    def cut(self, z):
        raise NotImplementedError

    def build_mesh(self):
        raise NotImplementedError

    def mesh(self):
        if self._mesh is None:
            self._mesh = self.build_mesh()
        return self._mesh

    # -- derived -----------------------------------------------------------
    @property
    def height(self):
        return self.mesh().bounds()[5]

    def footprint(self):
        return self.levels[0].plate

    def gia(self):
        return sum(l.area for l in self.levels)

    def bands_at(self, z):
        """cut(z) normalised to a list of Bands."""
        c = self.cut(z)
        return list(c) if isinstance(c, (list, tuple)) else [c]

    def solid_intervals(self, z, p0, u):
        """Where a horizontal line through the solid at height z is material."""
        out = []
        for b in self.bands_at(z):
            outer = G.region_line_intervals(b.outer, p0, u)
            inner = G.region_line_intervals(b.inner, p0, u)
            out += G.subtract_intervals(outer, inner)
        return sorted(out)

    def extent_at(self, z, axis):
        """Projected width of the building at height z, along a screen axis."""
        lo = hi = None
        for b in self.bands_at(z):
            for ring in b.outer.rings:
                for (x, y) in ring:
                    s = x * axis[0] + y * axis[1]
                    lo = s if lo is None else min(lo, s)
                    hi = s if hi is None else max(hi, s)
        return (lo, hi)

    def section(self, p0, direction, steps=200, z0=0.0, z1=None):
        """Vertical cut, built by sampling the solid rather than slicing a mesh.

        Sampling works for every typology: straight walls come out as clean
        rectangles and a swept profile comes out as its true curve, without the
        section code needing to know which it is looking at."""
        dx, dy = direction
        l = math.hypot(dx, dy) or 1.0
        u = (dx / l, dy / l)
        z1 = self.height if z1 is None else z1
        res = SectionResult()

        samples = []
        for i in range(steps + 1):
            z = z0 + (z1 - z0) * i / steps
            samples.append((z, self.solid_intervals(z, p0, u)))

        # group runs where the number of material intervals is stable, then
        # trace each one up its left edge and back down its right
        run = []
        for (z, ivs) in samples:
            if run and len(ivs) != len(run[-1][1]):
                res.cut += _trace(run)
                run = []
            run.append((z, ivs))
        res.cut += _trace(run)

        for lv in self.levels:
            for (t0, t1) in G.region_line_intervals(lv.plate, p0, u):
                res.slabs.append((t0, t1, lv.ffl, lv.slab_t))
            res.levels.append((lv.name, lv.ffl))

        axis = u
        for i in range(steps + 1):
            z = z0 + (z1 - z0) * i / steps
            lo, hi = self.extent_at(z, axis)
            if lo is not None:
                res.beyond.append((z, lo, hi))
        return res

    def silhouette(self, azimuth, steps=200, z0=0.0, z1=None):
        """Orthographic elevation: the projected extent of the solid at every
        height, which is exactly the outline however the building is shaped."""
        a = math.radians(azimuth)
        right = (-math.sin(a), math.cos(a))
        z1 = self.height if z1 is None else z1
        el = Elevation2D()
        left, rightside = [], []
        for i in range(steps + 1):
            z = z0 + (z1 - z0) * i / steps
            lo, hi = self.extent_at(z, right)
            if lo is None:
                continue
            left.append((lo, z))
            rightside.append((hi, z))
        el.outline = [(left + rightside[::-1], True)] if left else []
        for z in self.joint_heights():
            lo, hi = self.extent_at(max(z - 1e-4, 0.0), right)
            if lo is not None:
                el.joints.append((z, [([(lo, z), (hi, z)], False)]))
        return el

    def joint_heights(self):
        return [lv.ffl for lv in self.levels if lv.ffl > 1e-6]

    def __repr__(self):
        return "<%s %d levels, %.0f m2 GIA, %.2f m tall>" % (
            self.name, len(self.levels), self.gia(), self.height)


# ---------------------------------------------------------------------------
VOID_BAND_MIN = 9.0     # metres of building that must remain around a void


def _open_void(plate, grow, band_min):
    """`plate` with its holes opened by `grow`, or None if that leaves no room."""
    if grow <= 0.0:
        return plate
    out = []
    for h in plate.holes:
        r = G.offset_ring(h, -grow)
        if len(r) < 3 or G.signed_area(r) >= 0:      # turned itself inside out
            return None
        out.append(r)
    if not out:
        return None
    opened = G.Region(plate.outer, out)
    # what is left has to be wide enough to be a building, not a rim
    if opened.area < plate.area * 0.16:
        return None
    # fits_inside pulls the outer in and pushes the hole out at the same
    # time, so it closes the band between them by twice the distance given.
    for r in out:
        if not G.fits_inside(G.Region(plate.outer, [r]), band_min / 2.0):
            return None
    return opened


class Support:
    """One thing standing on the ground: a column, or a core coming down."""
    __slots__ = ("kind", "region", "centre", "size", "material")

    def __init__(self, kind, region, centre, size, material="concrete"):
        self.kind, self.region, self.centre = kind, region, centre
        self.size, self.material = size, material

    def __repr__(self):
        return "<%s %.0f mm at %.1f, %.1f>" % (self.kind, self.size * 1000,
                                               self.centre[0], self.centre[1])


def _shaft(m, ring, z0, z1, group):
    r = G.resample(ring, 2.0)
    n = len(r)
    for k in range(n):
        a, b = r[k], r[(k + 1) % n]
        m.quad((a[0], a[1], z0), (b[0], b[1], z0),
               (b[0], b[1], z1), (a[0], a[1], z1), group)


def piloti(footprint, spacing=8.4, size=0.40, inset=1.2, material="concrete",
           round_=True):
    """Columns on a grid, clipped to the footprint they hold up.

    A lifted building is only convincing if the thing holding it up is where
    the structure would really be, so they sit on the same grid the frame
    above uses and stop at the edge of the plate."""
    x0, y0, x1, y1 = footprint.bbox()
    inner = footprint.offset(-inset) if inset else footprint
    ring = inner.outer if len(inner.outer) >= 3 else footprint.outer
    nx = max(2, int(round((x1 - x0) / spacing)))
    ny = max(2, int(round((y1 - y0) / spacing)))
    out = []
    for i in range(nx + 1):
        for j in range(ny + 1):
            cx = x0 + (x1 - x0) * i / nx
            cy = y0 + (y1 - y0) * j / ny
            if not G.point_in_ring((cx, cy), ring):
                continue
            if any(G.point_in_ring((cx, cy), h) for h in footprint.holes):
                continue
            sec = (G.circle(size / 2.0, 16, cx, cy) if round_
                   else G.rectangle(size, size, cx, cy))
            out.append(Support("column", G.Region(sec), (cx, cy), size, material))
    return out


def core_supports(footprint, count=2, size=7.0):
    """Cores brought down to the earth, when only they touch it."""
    x0, y0, x1, y1 = footprint.bbox()
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    span = (x1 - x0)
    out = []
    for i in range(max(1, count)):
        off = (i - (count - 1) / 2.0) * min(span * 0.32, 26.0)
        p = (cx + off, cy)
        if not G.point_in_ring(p, footprint.outer):
            p = (cx + off, cy + (y1 - y0) * 0.28)
        out.append(Support("core", G.Region(G.rectangle(size, size, p[0], p[1])),
                           p, size, "concrete"))
    return out


class Extrusion(Massing):
    """A footprint pushed up, optionally with per-level setbacks.

    Covers the overwhelming majority of real briefs: slabs, courtyard blocks,
    L-plans, towers, anything the user draws."""

    name = "extrusion"

    def __init__(self, footprint, storeys=2, floor_to_floor=4.2, wall_t=0.35,
                 ground_ffl=0.0, setbacks=None, parapet=1.1, slab_t=0.30,
                 lift=0.0, columns=None, cores=None, void_growth=0.0):
        self.foot = footprint if isinstance(footprint, G.Region) else G.Region(footprint)
        self.wall_t, self.parapet, self.f2f = wall_t, parapet, floor_to_floor
        # A building can be held above an open ground plane. Everything above
        # the lift is unchanged; below it there is nothing but what carries it.
        self.lift = max(0.0, float(lift or 0.0))
        self.columns = list(columns or []) if self.lift else []
        self.cores = list(cores or []) if self.lift else []
        if self.lift and not self.columns:
            self.columns = piloti(self.foot)
        ground_ffl = ground_ffl + self.lift
        setbacks = setbacks or {}
        # A void that opens out as it rises: the outside stays monolithic
        # while the inside gets lighter floor by floor, which is a different
        # move from a setback and reads as one from the ground.
        self.void_growth = max(0.0, float(void_growth or 0.0))
        widest = None                  # the most open plate that still works
        levels = []
        for i in range(storeys):
            back = setbacks.get(i, 0.0)
            plate = self.foot.offset(back) if back else self.foot
            if self.void_growth and plate.holes:
                # The void grows until there is no building left to give, and
                # then it stops. It must never snap shut on the floor above.
                opened = _open_void(plate, self.void_growth * i, VOID_BAND_MIN)
                plate = opened or widest or plate
                widest = plate
            levels.append(Level(i, "Level %02d" % i, ground_ffl + i * floor_to_floor,
                                floor_to_floor, plate, slab_t))
        super().__init__(levels)
        self.top = levels[-1].ffl + floor_to_floor
        self.zones = [
            Zone("EX-GL", "glazing", ground_ffl, self.top, "Facade glazing"),
            Zone("EX-RF", "roof", self.top, self.top + parapet, "Roof and parapet"),
        ]
        if self.lift:
            self.zones.insert(0, Zone("EX-PI", "structure", 0.0, self.lift,
                                      "Open ground plane on columns"))

    def undercroft(self):
        """What stands on the ground when the building does not."""
        return [c.region for c in self.columns] + [c.region for c in self.cores]

    def cut(self, z):
        # Below the lift the plan is the columns and the cores, which is what
        # makes the ground floor read as open rather than as a missing storey.
        if self.lift and z < self.lift - 1e-9:
            bands = [G.Band(r, G.Region([])) for r in self.undercroft()]
            return bands or [self.levels[0].band(self.wall_t)]
        for lv in reversed(self.levels):
            if z >= lv.ffl - 1e-9:
                return lv.band(self.wall_t)
        return self.levels[0].band(self.wall_t)

    def build_mesh(self):
        m = Mesh()
        for c in self.columns + self.cores:
            _shaft(m, c.region.outer, 0.0, self.lift,
                   "column" if c in self.columns else "core")
        if self.lift:                       # the underside people stand beneath
            base = self.levels[0].plate
            m.face(m.add([(x, y, self.lift) for (x, y)
                          in G.resample(base.outer, 4.0)][::-1]), "soffit")
        for i, lv in enumerate(self.levels):
            z0 = lv.ffl
            z1 = (self.levels[i + 1].ffl if i + 1 < len(self.levels)
                  else self.top + self.parapet)
            for ring in lv.plate.rings:
                r = G.resample(ring, 3.0)
                n = len(r)
                for k in range(n):
                    a, b = r[k], r[(k + 1) % n]
                    m.quad((a[0], a[1], z0), (b[0], b[1], z0),
                           (b[0], b[1], z1), (a[0], a[1], z1), "wall")
        top = self.levels[-1].plate
        m.face(m.add([(x, y, self.top) for (x, y) in G.resample(top.outer, 4.0)]), "roof")
        return m

    def joint_heights(self):
        h = [lv.ffl for lv in self.levels if lv.ffl > 1e-6] + [self.top]
        return ([0.0, self.lift] + h) if self.lift else h


# ---------------------------------------------------------------------------
class Revolve(Massing):
    """A closed profile in (radius, height) swept around the vertical axis.

    The torus is one instance of this; so are domes, cones, stepped rings and
    vaulted sheds. Because the profile is exact, sections through the axis are
    exact too -- this typology overrides the generic mesh slicing."""

    name = "revolve"

    def __init__(self, profile, plates, storeys_named=None, segments=144,
                 slab_t=0.30, floor_to_floor=None):
        """`profile` is a closed ring in (r, z) describing solid material.
        `plates` is [(ffl, Region), ...]."""
        self.profile = G.dedupe(list(profile))
        self.segments = segments
        levels = []
        for i, (ffl, plate) in enumerate(plates):
            name = (storeys_named[i] if storeys_named else "Level %02d" % i)
            f2f = floor_to_floor or (plates[i + 1][0] - ffl if i + 1 < len(plates) else 4.2)
            levels.append(Level(i, name, ffl, f2f, plate, slab_t))
        super().__init__(levels)

    # -- profile helpers ---------------------------------------------------
    def profile_radii(self, z):
        """Radii at which the profile crosses height z, sorted."""
        rs = []
        n = len(self.profile)
        for i in range(n):
            (r0, z0), (r1, z1) = self.profile[i], self.profile[(i + 1) % n]
            if (z0 > z) != (z1 > z):
                t = (z - z0) / (z1 - z0)
                rs.append(r0 + (r1 - r0) * t)
        return sorted(rs)

    def cut(self, z):
        """Annular bands of solid at height z."""
        rs = self.profile_radii(z)
        bands = []
        for i in range(0, len(rs) - 1, 2):
            ro, ri = rs[i + 1], rs[i]
            if ro - ri > 1e-6:
                bands.append(G.Band(G.Region(G.circle(ro, self.segments)),
                                    G.Region(G.circle(ri, self.segments))))
        return bands

    def build_mesh(self):
        m = Mesh()
        prof = G.resample(self.profile, 0.45)
        n, s = len(prof), self.segments
        for i in range(n):
            (r0, z0), (r1, z1) = prof[i], prof[(i + 1) % n]
            for k in range(s):
                a0, a1 = 2 * math.pi * k / s, 2 * math.pi * (k + 1) / s
                m.quad((r0 * math.cos(a0), r0 * math.sin(a0), z0),
                       (r0 * math.cos(a1), r0 * math.sin(a1), z0),
                       (r1 * math.cos(a1), r1 * math.sin(a1), z1),
                       (r1 * math.cos(a0), r1 * math.sin(a0), z1), "shell")
        return m
