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
                   cat="work", start_index=1, min_area=2.5, max_area=None):
    """Cut the band between two rings into rooms about `target_w` wide."""
    outer = G.resample(G.ccw(G.dedupe(outer)), max(0.5, target_w / 10.0))
    inner = G.resample(G.ccw(G.dedupe(inner)), max(0.5, target_w / 10.0))
    cum = _cum(outer)
    total = cum[-1]
    n = max(1, int(round(total / target_w)))
    band_area = abs(G.area(outer) - G.area(inner))
    cap = max_area if max_area else max(min_area * 2.0, 6.0 * band_area / n)

    # Which way across the band? For a perimeter band the far edge is inboard;
    # for a band around a courtyard it is outboard. Decide once, by sampling,
    # so a concave corner can never flip the direction mid-run.
    sign = _crossing_sign(outer, cum, inner)

    hits = []
    for i in range(n):
        p, nrm, _ = _point_and_normal(outer, cum, i / n)
        d = (nrm[0] * sign, nrm[1] * sign)
        hit = ray_ring_hit(p, d, inner)
        if hit is None:                          # try the other side
            hit = ray_ring_hit(p, (-d[0], -d[1]), inner)
        if hit is None:                          # corner: mitre into it
            hit = nearest_on_ring(p, inner)
        hits.append(hit)

    cum_i = _cum(inner)
    walk = _monotonic(cum_i, hits)
    walk.append(walk[0] + cum_i[-1])             # close the loop

    rooms, idx = [], start_index
    for i in range(n):
        outer_pts = ring_arc(outer, _pos_from_frac(outer, cum, i / n),
                             _pos_from_frac(outer, cum, (i + 1) / n), forward=True)
        if walk[i + 1] - walk[i] > 1e-6:
            inner_pts = ring_arc(inner, _pos_at_length(cum_i, walk[i + 1]),
                                 _pos_at_length(cum_i, walk[i]), forward=False)
        else:
            inner_pts = [_pos_point(inner, cum_i, walk[i])]
        ring = G.dedupe(outer_pts + inner_pts)
        if len(ring) >= 3 and min_area <= G.area(ring) <= cap:
            rooms.append(Room("%s.%02d" % (code_prefix, idx), name, G.ccw(ring), cat))
            idx += 1
    return rooms


def _pos_point(ring, cum, t):
    e, s = _pos_at_length(cum, t)
    return _at(ring, e, s)


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


def _pos_scalar(cum, edge, s):
    """(edge, s) -> arc length along the ring."""
    seg = cum[edge + 1] - cum[edge]
    return cum[edge] + seg * s


def _pos_at_length(cum, t):
    """Arc length -> (edge, s), wrapping."""
    total = cum[-1]
    t = t % total
    lo, hi = 0, len(cum) - 2
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid + 1] <= t:
            lo = mid + 1
        else:
            hi = mid
    seg = cum[lo + 1] - cum[lo] or 1.0
    return (lo, (t - cum[lo]) / seg)


def _monotonic(cum_inner, hits):
    """Force the projections to advance the same way round as the reference.

    Walking the outer edge one way must walk the inner edge the same way. At a
    corner the projection can land behind its predecessor, and a naive walk
    then traverses almost the whole ring backwards and returns a cell the size
    of the building. Any backward step is clamped to zero, which collapses that
    cell into the mitre triangle it should have been."""
    total = cum_inner[-1]
    out = [_pos_scalar(cum_inner, hits[0][1], hits[0][2])]
    for h in hits[1:]:
        raw = _pos_scalar(cum_inner, h[1], h[2])
        delta = (raw - out[-1]) % total
        if delta > total * 0.5:
            delta = 0.0
        out.append(out[-1] + delta)
    return out


def _pos_from_frac(ring, cum, frac):
    t = frac * cum[-1]
    for k in range(len(cum) - 1):
        if cum[k] <= t <= cum[k + 1]:
            seg = cum[k + 1] - cum[k] or 1.0
            return (k, (t - cum[k]) / seg)
    return (0, 0.0)


PUBLIC_FIRST = ("recep", "amenity", "meet", "work", "plant")
UPPER_FIRST = ("work", "meet", "amenity", "plant")


def programme_for_level(brief, level_index):
    """Order the schedule for this floor.

    On the ground floor the public rooms sit nearest the entrance and the
    plant goes furthest from it; upstairs the reception drops out and the
    floor is workspace-led. It is the ordering an architect would reach for
    without thinking about it, and it is the only thing standing between a
    plan with room names and a plan that is actually organised."""
    prog = list(getattr(brief, "accommodation", []) or [])
    if not prog:
        return []
    if level_index == 0:
        rank = PUBLIC_FIRST
    else:
        prog = [p for p in prog if p[2] != "recep"]
        rank = UPPER_FIRST
        total = sum(p[1] for p in prog) or 1.0
        prog = [(n, sh / total, c) for (n, sh, c) in prog]
    return sorted(prog, key=lambda p: rank.index(p[2]) if p[2] in rank else 99)


def assign_programme(rooms, brief, centre, level_index):
    """Walk the plan from the entrance and fill the schedule in order."""
    prog = programme_for_level(brief, level_index)
    if not prog:
        return
    free = [r for r in rooms if r.cat != "core"]
    if not free:
        return
    ent = math.radians(getattr(brief, "entrance_azimuth", 270.0))

    def sweep(r):
        cx, cy = r.centroid
        return (math.atan2(cy - centre[1], cx - centre[0]) - ent) % (2 * math.pi)

    free.sort(key=sweep)
    total = sum(r.area for r in free)
    i = 0
    for (name, share, cat) in prog:
        quota = total * share
        got = 0.0
        while i < len(free) and got < quota - 1e-9:
            r = free[i]
            r.name, r.cat = name, cat
            got += r.area
            i += 1
    fallback = prog[0]
    for r in free[i:]:
        r.name, r.cat = fallback[0], fallback[2]


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

    assign_programme(rooms, brief, G.centroid(plate.outer), level_index)

    circ = G.Region(core_ring.outer, core_ring.holes) if core_ring.outer else None
    return Floorplan(level, rooms, circ, plate)
