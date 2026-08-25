"""Boolean operations on polygons: union, difference, intersection.

Without these an engine can only ever build one primitive at a time, which is
why every building it made was a box, or a box with a hole, or a cylinder. A
composition -- two bars shifted and crossed, a mass with a wedge carved out of
it, a slab that steps as it rises -- is exactly a boolean of volumes, taken
one floor at a time.

The method is split-and-classify: every edge of each polygon is cut wherever
the other polygon touches it, so each resulting fragment lies wholly inside
the other, wholly outside it, or along its boundary. Each operation is then
just a choice of which fragments to keep. It is quadratic, which for a floor
plate of a few hundred edges is nothing, and in exchange it is simple enough
to be checked rather than believed.

Buildings are full of exact coincidences -- two blocks flush against each
other share a whole edge, a wing meets a slab precisely at a corner -- so
fragments lying along a shared boundary are classified by which way each
polygon runs there, rather than by nudging a test point and hoping.

Everything is exact rather than sampled, because the output is a drawing at
1:50 where a wall that wobbles by a millimetre is a wall drawn wrong.
"""

import math

EPS = 1e-9
TOL = 1e-7

UNION = "union"
INTERSECTION = "intersection"
DIFFERENCE = "difference"

IN, OUT, ON_SAME, ON_OPPOSITE = "in", "out", "on+", "on-"


# ---------------------------------------------------------------------------
# Small geometry
# ---------------------------------------------------------------------------
def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _same(a, b, tol=TOL):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def signed_area(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        s += a[0] * b[1] - b[0] * a[1]
    return s / 2.0


def _on_segment(p, a, b, tol=TOL):
    """Is p on the segment a-b, within tolerance?"""
    if abs(_cross(a, b, p)) > tol * max(1.0, math.dist(a, b)):
        return False
    return (min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol and
            min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol)


def point_in_rings(p, rings, tol=TOL):
    """IN, OUT, or None when p sits exactly on a boundary.

    Even-odd across all rings, which is what makes an outline with holes in
    it behave: a point inside a hole is crossed twice and comes out outside."""
    for r in rings:
        n = len(r)
        for i in range(n):
            if _on_segment(p, r[i], r[(i + 1) % n], tol):
                return None
    inside = False
    x, y = p
    for r in rings:
        n = len(r)
        for i in range(n):
            ax, ay = r[i]
            bx, by = r[(i + 1) % n]
            if (ay > y) != (by > y):
                t = (y - ay) / (by - ay)
                if x < ax + t * (bx - ax):
                    inside = not inside
    return IN if inside else OUT


# ---------------------------------------------------------------------------
# Cutting every edge wherever the other polygon touches it
# ---------------------------------------------------------------------------
def _edges(rings):
    out = []
    for r in rings:
        n = len(r)
        for i in range(n):
            a, b = r[i], r[(i + 1) % n]
            if not _same(a, b):
                out.append((a, b))
    return out


def _crossings(a0, a1, b0, b1):
    """Every point of a0-a1 that also lies on b0-b1."""
    va = (a1[0] - a0[0], a1[1] - a0[1])
    vb = (b1[0] - b0[0], b1[1] - b0[1])
    d = va[0] * vb[1] - va[1] * vb[0]
    e = (b0[0] - a0[0], b0[1] - a0[1])
    if abs(d) > EPS:
        s = (e[0] * vb[1] - e[1] * vb[0]) / d
        t = (e[0] * va[1] - e[1] * va[0]) / d
        if -TOL <= s <= 1 + TOL and -TOL <= t <= 1 + TOL:
            s = min(1.0, max(0.0, s))
            return [(a0[0] + va[0] * s, a0[1] + va[1] * s)]
        return []
    # parallel; collinear only if b0 lies on the line through a
    if abs(e[0] * va[1] - e[1] * va[0]) > TOL * max(1.0, math.hypot(*va)):
        return []
    la = va[0] * va[0] + va[1] * va[1]
    if la < EPS:
        return []
    out = []
    for p in (b0, b1):
        t = ((p[0] - a0[0]) * va[0] + (p[1] - a0[1]) * va[1]) / la
        if -TOL <= t <= 1 + TOL:
            t = min(1.0, max(0.0, t))
            out.append((a0[0] + va[0] * t, a0[1] + va[1] * t))
    return out


def _split(edges, others):
    """Each edge cut wherever any edge of `others` touches it."""
    out = []
    for (a0, a1) in edges:
        cuts = []
        for (b0, b1) in others:
            cuts += _crossings(a0, a1, b0, b1)
        if not cuts:
            out.append((a0, a1))
            continue
        v = (a1[0] - a0[0], a1[1] - a0[1])
        l2 = v[0] * v[0] + v[1] * v[1]
        ts = [0.0, 1.0]
        for p in cuts:
            t = ((p[0] - a0[0]) * v[0] + (p[1] - a0[1]) * v[1]) / l2
            if TOL < t < 1.0 - TOL:
                ts.append(t)
        ts.sort()
        pts = [(a0[0] + v[0] * t, a0[1] + v[1] * t) for t in ts]
        for i in range(len(pts) - 1):
            if not _same(pts[i], pts[i + 1]):
                out.append((pts[i], pts[i + 1]))
    return out


def _classify(edge, rings):
    """Where a fragment sits relative to a polygon.

    A fragment is uncut, so its midpoint speaks for the whole of it: inside,
    outside, or -- where the two polygons touch along it -- running the same
    way round as the boundary it lies on, or the opposite way."""
    a, b = edge
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    where = point_in_rings(mid, rings)
    if where is not None:
        return where
    ev = (b[0] - a[0], b[1] - a[1])
    for r in rings:
        n = len(r)
        for i in range(n):
            c, d = r[i], r[(i + 1) % n]
            if _on_segment(mid, c, d):
                ov = (d[0] - c[0], d[1] - c[1])
                return (ON_SAME if ev[0] * ov[0] + ev[1] * ov[1] > 0
                        else ON_OPPOSITE)
    return OUT


# What each operation keeps, by which polygon a fragment came from and where
# it sits relative to the other. True means keep it but walked backwards,
# which is how a subtracted volume becomes a hole.
KEEP = {
    UNION: ({OUT: False, ON_SAME: False}, {OUT: False}),
    INTERSECTION: ({IN: False, ON_SAME: False}, {IN: False}),
    DIFFERENCE: ({OUT: False, ON_OPPOSITE: False}, {IN: True}),
}


def _fragments(a_rings, b_rings, op):
    ae = _split(_edges(a_rings), _edges(b_rings))
    be = _split(_edges(b_rings), _edges(a_rings))
    from_a, from_b = KEEP[op]
    out = []
    for edge in ae:
        w = _classify(edge, b_rings)
        if w in from_a:
            out.append(edge[::-1] if from_a[w] else edge)
    for edge in be:
        w = _classify(edge, a_rings)
        if w in from_b:
            out.append(edge[::-1] if from_b[w] else edge)
    return out


# ---------------------------------------------------------------------------
# Stitching fragments back into rings
# ---------------------------------------------------------------------------
def _key(p, q=1e6):
    return (round(p[0] * q), round(p[1] * q))


def _stitch(frags):
    """Walk directed fragments head to tail into closed rings.

    Where several fragments leave the same point -- which happens wherever the
    two outlines cross -- take the sharpest turn, so the walk hugs the
    boundary instead of cutting across the middle and swallowing a hole."""
    starts = {}
    for i, (a, b) in enumerate(frags):
        starts.setdefault(_key(a), []).append(i)
    used = [False] * len(frags)
    rings = []

    for seed in range(len(frags)):
        if used[seed]:
            continue
        ring = []
        i = seed
        guard = 0
        ok = True
        while True:
            guard += 1
            if guard > len(frags) + 4:
                ok = False
                break
            used[i] = True
            a, b = frags[i]
            ring.append(a)
            if _key(b) == _key(frags[seed][0]) and len(ring) >= 3:
                break
            cand = [j for j in starts.get(_key(b), ()) if not used[j]]
            if not cand:
                ok = False
                break
            if len(cand) == 1:
                i = cand[0]
            else:
                inc = math.atan2(b[1] - a[1], b[0] - a[0])

                def turn(j):
                    c, d = frags[j]
                    out = math.atan2(d[1] - c[1], d[0] - c[0])
                    return (out - inc + math.pi) % (2 * math.pi)

                i = max(cand, key=turn)
        if ok and len(ring) >= 3:
            rings.append(ring)
    return rings


def _tidy(rings):
    out = []
    for r in rings:
        clean = []
        for p in r:
            if not clean or not _same(p, clean[-1]):
                clean.append((float(p[0]), float(p[1])))
        while len(clean) > 1 and _same(clean[0], clean[-1]):
            clean.pop()
        i = 0
        while len(clean) > 3 and i < len(clean):
            a, b, c = clean[i - 1], clean[i], clean[(i + 1) % len(clean)]
            if abs(_cross(a, b, c)) < TOL * max(1.0, math.dist(a, c)):
                clean.pop(i)
            else:
                i += 1
        if len(clean) >= 3 and abs(signed_area(clean)) > 1e-6:
            out.append(clean)
    return out


def _nested_in(ring, other):
    """Is `ring` inside `other`?

    Rings coming out of a boolean never cross, so the question is settled by
    any single point of one against the other. It has to be a point ON the
    ring, not a point inside the area it encloses: an interior point of an
    outline can easily land inside the very hole it contains, which would
    make the outline look nested in its own hole."""
    n = len(ring)
    for i in range(n):
        for p in (ring[i], ((ring[i][0] + ring[(i + 1) % n][0]) / 2.0,
                            (ring[i][1] + ring[(i + 1) % n][1]) / 2.0)):
            w = point_in_rings(p, [other])
            if w is not None:                   # not sitting on its boundary
                return w == IN
    return False


def _orient(rings):
    """Outlines anticlockwise, whatever is enclosed by them clockwise."""
    out = []
    for i, r in enumerate(rings):
        depth = sum(1 for j, other in enumerate(rings)
                    if i != j and _nested_in(r, other))
        want_ccw = (depth % 2 == 0)
        out.append(r if (signed_area(r) > 0) == want_ccw else r[::-1])
    return out


# ---------------------------------------------------------------------------
def clip(subject, clip_poly, operation):
    """Boolean of two polygons, each a list of rings; returns a list of rings.

    Rings come back the way the rest of the engine wants them: outlines
    anticlockwise, holes clockwise."""
    subject = [list(r) for r in subject if len(r) >= 3]
    clip_poly = [list(r) for r in clip_poly if len(r) >= 3]
    if not subject:
        return _orient(_tidy(clip_poly)) if operation == UNION else []
    if not clip_poly:
        return [] if operation == INTERSECTION else _orient(_tidy(subject))
    return _orient(_tidy(_stitch(_fragments(subject, clip_poly, operation))))


def union(a, b):
    return clip(a, b, UNION)


def difference(a, b):
    return clip(a, b, DIFFERENCE)


def intersection(a, b):
    return clip(a, b, INTERSECTION)


def union_all(polys):
    out = []
    for p in polys:
        p = [list(r) for r in p if len(r) >= 3]
        out = union(out, p) if out else _orient(_tidy(p))
    return out
