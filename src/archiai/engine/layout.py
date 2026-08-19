"""Turning a floor plate into rooms.

The strategy is the one most real offices use and the one the torus set uses:
a daylight band around every edge that has a window, a circulation spine
between the bands, and cores punched into the band at intervals set by escape
distance. It is not clever, but it is defensible on any plate, and it gives a
plan a human can argue with rather than a blob.
"""

import math
from . import geom2d as G

CATEGORY = {
    "work":    ("#eef2f7", "#a8bacd", "Workplace"),
    "meet":    ("#f4efe7", "#c9b79a", "Meeting & collaboration"),
    "amenity": ("#f2f6ee", "#a9c19b", "Amenity & wellbeing"),
    "core":    ("#dcdcdc", "#8f8f8f", "Cores & vertical circulation"),
    "plant":   ("#e6e6e1", "#9c9c92", "Plant & back of house"),
    "circ":    ("#f8f8f6", "#c5c5bd", "Primary circulation"),
    "recep":   ("#e9eef4", "#93a8c0", "Entrance & reception"),
    "void":    ("#ffffff", "#b9b9b9", "Void / open to below"),
}


class Room:
    __slots__ = ("code", "name", "ring", "cat", "sub")

    def __init__(self, code, name, ring, cat="work", sub=None):
        self.code, self.name, self.ring, self.cat, self.sub = code, name, ring, cat, sub

    @property
    def area(self):
        return G.area(self.ring)

    @property
    def centroid(self):
        return G.centroid(self.ring)

    @property
    def fill(self):
        return CATEGORY[self.cat][0]

    @property
    def stroke(self):
        return CATEGORY[self.cat][1]

    def __repr__(self):
        return "<%s %s %.0f m2>" % (self.code, self.name, self.area)


class Floorplan:
    def __init__(self, level, rooms, circulation, plate):
        self.level, self.rooms, self.circulation, self.plate = level, rooms, circulation, plate

    @property
    def gia(self):
        return self.plate.area

    def by_category(self):
        agg = {}
        for r in self.rooms:
            agg[r.cat] = agg.get(r.cat, 0.0) + r.area
        return agg

    def __repr__(self):
        return "<Floorplan %s: %d rooms, %.0f m2>" % (self.level.name, len(self.rooms), self.gia)


class Brief:
    """What the user asked for, normalised."""

    def __init__(self, use="office", daylight_depth=7.5, corridor_w=2.4,
                 room_width=7.2, core_spacing=40.0, core_w=9.0, core_depth=None,
                 wall_t=0.35, entrance_azimuth=270.0, name="Untitled",
                 desk_area=8.0):
        self.use = use
        self.daylight_depth = daylight_depth
        self.corridor_w = corridor_w
        self.room_width = room_width
        self.core_spacing = core_spacing
        self.core_w = core_w
        self.core_depth = core_depth or daylight_depth
        self.wall_t = wall_t
        self.entrance_azimuth = entrance_azimuth
        self.name = name
        self.desk_area = desk_area


# ---------------------------------------------------------------------------
# Cutting a band into rooms.
#
# The naive way is to walk both edges of the band in proportional arc length,
# which is fine on a straight run and produces wedges at every corner, because
# the inner edge of a corner is much shorter than the outer one. Instead each
# division on the reference edge is projected across the band along its own
# normal, so the party wall is always perpendicular to the facade.
# ---------------------------------------------------------------------------
def ray_ring_hit(p, d, ring):
    """First hit of the ray p + t*d (t > 0) on a closed ring.

    Returns (point, edge_index, s_along_edge, t) or None."""
    best = None
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-12:
            continue
        rx, ry = a[0] - p[0], a[1] - p[1]
        t = (rx * ey - ry * ex) / den
        s = (rx * d[1] - ry * d[0]) / den
        if t > 1e-7 and -1e-9 <= s <= 1 + 1e-9:
            if best is None or t < best[3]:
                best = ((p[0] + d[0] * t, p[1] + d[1] * t), i, min(max(s, 0.0), 1.0), t)
    return best


def nearest_on_ring(p, ring):
    """Closest point on a ring, as (point, edge_index, s, distance).

    Used where a perpendicular projection misses: within a band's depth of a
    corner the far edge simply isn't opposite the facade any more, so the party
    wall mitres into the corner instead. That is how the bay gets drawn by
    hand, and it fills the corner rather than leaving it out of the schedule."""
    best = None
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        l2 = ex * ex + ey * ey
        t = 0.0 if l2 < 1e-15 else max(0.0, min(1.0, ((p[0] - a[0]) * ex +
                                                      (p[1] - a[1]) * ey) / l2))
        q = (a[0] + ex * t, a[1] + ey * t)
        d = math.dist(p, q)
        if best is None or d < best[3]:
            best = (q, i, t, d)
    return best


def ring_arc(ring, pos_a, pos_b, forward=True):
    """Points along a ring between two (edge_index, s) positions.

    A position (i, s) lies on the edge ring[i] -> ring[i+1]. Walking forward
    the first vertex passed is ring[i+1]; walking backward it is ring[i]."""
    n = len(ring)
    ia, sa = pos_a
    ib, sb = pos_b
    pa, pb = _at(ring, ia, sa), _at(ring, ib, sb)
    pts = [pa]
    if forward:
        if not (ia == ib and sb >= sa - 1e-12):
            i = (ia + 1) % n
            for _ in range(n):
                pts.append(ring[i])
                if i == ib:
                    break
                i = (i + 1) % n
    else:
        if not (ia == ib and sb <= sa + 1e-12):
            i = ia
            for _ in range(n):
                pts.append(ring[i])
                if i == (ib + 1) % n:
                    break
                i = (i - 1) % n
    pts.append(pb)
    return G.dedupe(pts)


def _at(ring, i, s):
    a, b = ring[i % len(ring)], ring[(i + 1) % len(ring)]
    return (a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s)


def _cum(ring):
    d = [0.0]
    n = len(ring)
    for i in range(n):
        d.append(d[-1] + math.dist(ring[i], ring[(i + 1) % n]))
    return d


def _point_and_normal(ring, cum, frac):
    """Point at a fraction of perimeter, plus the ring's outward normal there."""
    t = frac * cum[-1]
    n = len(ring)
    for k in range(n):
        if cum[k] <= t <= cum[k + 1]:
            seg = cum[k + 1] - cum[k] or 1.0
            u = (t - cum[k]) / seg
            a, b = ring[k], ring[(k + 1) % n]
            p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
            return p, G._edge_normal(a, b), k
    return ring[0], G._edge_normal(ring[0], ring[1]), 0


def subdivide_band(outer, inner, target_w, code_prefix="R", name="Workspace",
                   cat="work", start_index=1, min_area=6.0, max_area=None):
    """Cut the band between two rings into rooms about `target_w` wide."""
    outer = G.resample(G.ccw(G.dedupe(outer)), max(0.5, target_w / 10.0))
    inner = G.resample(G.ccw(G.dedupe(inner)), max(0.5, target_w / 10.0))
    cum = _cum(outer)
    total = cum[-1]
    n = max(1, int(round(total / target_w)))
    band_area = abs(G.area(outer) - G.area(inner))
    cap = max_area if max_area else max(min_area * 2.0, 3.0 * band_area / n)

    # Which way across the band? For a perimeter band the far edge is inboard;
    # for a band around a courtyard it is outboard. Decide once, by sampling,
    # so a concave corner can never flip the direction mid-run.
    sign = _crossing_sign(outer, cum, inner)

    cuts = []
    for i in range(n):
        frac = i / n
        p, nrm, _ = _point_and_normal(outer, cum, frac)
        d = (nrm[0] * sign, nrm[1] * sign)
        hit = ray_ring_hit(p, d, inner)
        if hit is None:
            hit = ray_ring_hit(p, (-d[0], -d[1]), inner)
        if hit is None:                          # corner: mitre into it
            hit = nearest_on_ring(p, inner)
        cuts.append((frac, p, hit))

    rooms, idx = [], start_index
    for i in range(n):
        f0, p0, h0 = cuts[i]
        f1, p1, h1 = cuts[(i + 1) % n]
        if h0 is None or h1 is None:
            continue
        outer_pts = ring_arc(outer, _pos_from_frac(outer, cum, f0),
                             _pos_from_frac(outer, cum, f1), forward=True)
        inner_pts = ring_arc(inner, (h1[1], h1[2]), (h0[1], h0[2]), forward=False)
        ring = G.dedupe(outer_pts + inner_pts)
        if len(ring) >= 3 and min_area <= G.area(ring) <= cap:
            rooms.append(Room("%s.%02d" % (code_prefix, idx), name, G.ccw(ring), cat))
            idx += 1
    return rooms


def _crossing_sign(outer, cum, inner, samples=7):
    """+1 if the far edge of the band lies outboard of the reference ring."""
    votes = 0.0
    for k in range(samples):
        p, nrm, _ = _point_and_normal(outer, cum, (k + 0.5) / samples)
        ts = {}
        for sg in (-1.0, 1.0):
            h = ray_ring_hit(p, (nrm[0] * sg, nrm[1] * sg), inner)
            if h:
                ts[sg] = h[3]
        if not ts:
            continue
        best = min(ts, key=ts.get)
        votes += best
    return 1.0 if votes > 0 else -1.0


def _pos_from_frac(ring, cum, frac):
    t = frac * cum[-1]
    for k in range(len(cum) - 1):
        if cum[k] <= t <= cum[k + 1]:
            seg = cum[k + 1] - cum[k] or 1.0
            return (k, (t - cum[k]) / seg)
    return (0, 0.0)


def allocate(level, brief, level_index=0):
    """Daylight bands + a circulation spine, with cores punched into the band."""
    plate = level.plate
    d, cw = brief.daylight_depth, brief.corridor_w
    rooms = []
    band_pairs = []

    inner_face = plate.offset(brief.wall_t)
    core_ring = inner_face.offset(d)                     # inboard edge of the outer band
    band_pairs.append((inner_face.outer, core_ring.outer, "outer"))
    for h_in, h_core in zip(inner_face.holes, core_ring.holes):
        band_pairs.append((h_in, h_core, "court"))

    prefix = "%02d" % level_index
    idx = 1
    outer_rooms = []
    for (o, i, which) in band_pairs:
        if G.area(o) < 4.0 or G.area(i) < 4.0:
            continue
        new = subdivide_band(o, i, brief.room_width,
                             code_prefix=prefix, start_index=idx,
                             name=("Workspace" if which == "outer" else "Studio"))
        rooms += new
        if which == "outer":
            outer_rooms = new
        idx += len(new)

    # Cores punched into the outer band, spaced by escape distance and placed
    # on the roomiest bays so they never land on a corner sliver.
    pool = outer_rooms or rooms
    if pool:
        n_cores = max(2, int(math.ceil(
            G.perimeter(inner_face.outer) / brief.core_spacing)))
        n_cores = min(n_cores, max(1, len(pool) // 3))
        step = len(pool) / float(n_cores)
        median = sorted(r.area for r in pool)[len(pool) // 2]
        placed = 0
        for c in range(n_cores):
            base = int(round(c * step)) % len(pool)
            pick = None
            for off in (0, 1, -1, 2, -2):
                cand = pool[(base + off) % len(pool)]
                if cand.cat == "work" and cand.area >= median * 0.8:
                    pick = cand
                    break
            if pick is None:
                continue
            pick.cat = "core"
            pick.name = "Core %s" % chr(ord("A") + placed)
            pick.code = "%s.C%d" % (prefix, placed + 1)
            placed += 1

    circ = G.Region(core_ring.outer, core_ring.holes) if core_ring.outer else None
    return Floorplan(level, rooms, circ, plate)
