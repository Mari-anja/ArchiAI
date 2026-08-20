"""Plane geometry for building footprints.

Everything downstream works on closed polylines ("rings"). Curves are sampled,
because the output is sampled anyway: SVG paths, meshes and area take-offs all
end up as line segments. A `Region` is one outer ring plus any number of holes.
"""

import math

TOL = 1e-7


# ---------------------------------------------------------------------------
# Rings
# ---------------------------------------------------------------------------
def signed_area(ring):
    a = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def area(ring):
    return abs(signed_area(ring))


def is_ccw(ring):
    return signed_area(ring) > 0


def ccw(ring):
    return ring if is_ccw(ring) else ring[::-1]


def cw(ring):
    return ring[::-1] if is_ccw(ring) else ring


def perimeter(ring, closed=True):
    n = len(ring)
    m = n if closed else n - 1
    return sum(math.dist(ring[i], ring[(i + 1) % n]) for i in range(m))


def centroid(ring):
    a = signed_area(ring)
    if abs(a) < TOL:
        n = max(1, len(ring))
        return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)
    cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return (cx / (6 * a), cy / (6 * a))


def bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_ring(p, ring):
    x, y = p
    inside = False
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xi > x:
                inside = not inside
    return inside


def dedupe(ring, tol=1e-6):
    out = []
    for p in ring:
        if not out or math.dist(p, out[-1]) > tol:
            out.append(p)
    while len(out) > 1 and math.dist(out[0], out[-1]) <= tol:
        out.pop()
    return out


def resample(ring, max_seg, closed=True):
    """Subdivide so no segment is longer than `max_seg`."""
    out = []
    n = len(ring)
    m = n if closed else n - 1
    for i in range(m):
        a, b = ring[i], ring[(i + 1) % n]
        out.append(a)
        d = math.dist(a, b)
        k = int(d // max_seg)
        for j in range(1, k + 1):
            t = j * max_seg / d
            if t < 1 - 1e-9:
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    if not closed:
        out.append(ring[-1])
    return out


def rotate(ring, deg, about=(0.0, 0.0)):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    ox, oy = about
    return [((x - ox) * c - (y - oy) * s + ox, (x - ox) * s + (y - oy) * c + oy)
            for (x, y) in ring]


def translate(ring, dx, dy):
    return [(x + dx, y + dy) for (x, y) in ring]


def scale(ring, k, about=(0.0, 0.0)):
    ox, oy = about
    return [(ox + (x - ox) * k, oy + (y - oy) * k) for (x, y) in ring]


# ---------------------------------------------------------------------------
# Offsetting.  Mitred, with a spike clamp -- enough for building footprints,
# which are not adversarial input.
# ---------------------------------------------------------------------------
def offset_ring(ring, d, miter_limit=4.0):
    """Offset a closed ring by `d`, positive outward for a CCW ring."""
    r = dedupe(ring)
    n = len(r)
    if n < 3 or abs(d) < TOL:
        return list(r)
    if not is_ccw(r):
        r = r[::-1]
        d = -d
        flip = True
    else:
        flip = False

    out = []
    for i in range(n):
        p_prev, p, p_next = r[i - 1], r[i], r[(i + 1) % n]
        n1 = _edge_normal(p_prev, p)
        n2 = _edge_normal(p, p_next)
        bx, by = n1[0] + n2[0], n1[1] + n2[1]
        bl = math.hypot(bx, by)
        if bl < 1e-9:
            out.append((p[0] + n1[0] * d, p[1] + n1[1] * d))
            continue
        bx, by = bx / bl, by / bl
        cos_half = bx * n1[0] + by * n1[1]
        scale_ = 1.0 / max(cos_half, 1.0 / miter_limit)
        out.append((p[0] + bx * d * scale_, p[1] + by * d * scale_))
    out = dedupe(out)
    return out[::-1] if flip else out


def _edge_normal(a, b):
    """Outward normal of edge a->b for a CCW ring."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l = math.hypot(dx, dy) or 1.0
    return (dy / l, -dx / l)


# ---------------------------------------------------------------------------
# Region: outer ring plus holes
# ---------------------------------------------------------------------------
class Region:
    __slots__ = ("outer", "holes")

    def __init__(self, outer, holes=None):
        self.outer = ccw(dedupe(list(outer)))
        self.holes = [cw(dedupe(list(h))) for h in (holes or [])]

    @property
    def area(self):
        return area(self.outer) - sum(area(h) for h in self.holes)

    @property
    def rings(self):
        return [self.outer] + self.holes

    def contains(self, p):
        if not point_in_ring(p, self.outer):
            return False
        return not any(point_in_ring(p, h) for h in self.holes)

    def offset(self, d):
        """Inward-positive shrink of the usable area: outer in, holes out."""
        return Region(offset_ring(self.outer, -d),
                      [offset_ring(h, -d) for h in self.holes])

    def band(self, t):
        """The wall band of thickness t inside the region boundary."""
        return Band(self, self.offset(t))

    def bbox(self):
        return bbox(self.outer)

    def resample(self, max_seg):
        return Region(resample(self.outer, max_seg),
                      [resample(h, max_seg) for h in self.holes])

    def __repr__(self):
        return "<Region %.1f m2, %d holes>" % (self.area, len(self.holes))


class Band:
    """The material between an outer region and an inner one -- a wall in plan."""
    __slots__ = ("outer", "inner")

    def __init__(self, outer, inner):
        self.outer, self.inner = outer, inner

    @property
    def area(self):
        return self.outer.area - self.inner.area

    @property
    def rings(self):
        return self.outer.rings + [r[::-1] for r in self.inner.rings]


# ---------------------------------------------------------------------------
# Ready-made footprints
# ---------------------------------------------------------------------------
def rectangle(w, h, cx=0.0, cy=0.0):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
            (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def circle(r, n=96, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * i / n),
             cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def regular_polygon(sides, r, cx=0.0, cy=0.0, phase=0.0):
    return [(cx + r * math.cos(math.radians(phase) + 2 * math.pi * i / sides),
             cy + r * math.sin(math.radians(phase) + 2 * math.pi * i / sides))
            for i in range(sides)]


def rounded_rect(w, h, radius, n=12, cx=0.0, cy=0.0):
    r = min(radius, w / 2, h / 2)
    pts = []
    corners = [(cx + w / 2 - r, cy + h / 2 - r, 0), (cx - w / 2 + r, cy + h / 2 - r, 90),
               (cx - w / 2 + r, cy - h / 2 + r, 180), (cx + w / 2 - r, cy - h / 2 + r, 270)]
    for (px, py, a0) in corners:
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((px + r * math.cos(a), py + r * math.sin(a)))
    return dedupe(pts)


def l_shape(w, h, cut_w, cut_h, cx=0.0, cy=0.0):
    x0, y0 = cx - w / 2, cy - h / 2
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h - cut_h),
            (x0 + w - cut_w, y0 + h - cut_h), (x0 + w - cut_w, y0 + h), (x0, y0 + h)]


# ---------------------------------------------------------------------------
# Chaining loose segments back into polylines -- used by mesh slicing
# ---------------------------------------------------------------------------
def chain_segments(segs, tol=1e-5):
    """Join (a, b) segments end to end. Returns [(points, closed), ...]."""
    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    ends = {}
    for i, (a, b) in enumerate(segs):
        ends.setdefault(key(a), []).append((i, 0))
        ends.setdefault(key(b), []).append((i, 1))

    used = [False] * len(segs)
    out = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        chain = [segs[i][0], segs[i][1]]
        # walk forward, then backward
        for direction in (1, 0):
            while True:
                tip = chain[-1] if direction else chain[0]
                nxt = None
                for (j, side) in ends.get(key(tip), ()):
                    if used[j]:
                        continue
                    nxt = (j, side)
                    break
                if nxt is None:
                    break
                j, side = nxt
                used[j] = True
                other = segs[j][1 - side]
                if direction:
                    chain.append(other)
                else:
                    chain.insert(0, other)
        closed = len(chain) > 2 and math.dist(chain[0], chain[-1]) <= tol * 10
        if closed:
            chain.pop()
        out.append((dedupe(chain), closed))
    return out


# ---------------------------------------------------------------------------
# Line / region intersection -- how a vertical section plane meets a floor plate
# ---------------------------------------------------------------------------
def ring_line_params(ring, p0, d):
    """Parameters t where the infinite line p0 + t*d crosses a closed ring."""
    ts = []
    n = len(ring)
    dx, dy = d
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        rx, ry = a[0] - p0[0], a[1] - p0[1]
        u = (rx * ey - ry * ex) / den          # along the line
        s = (rx * dy - ry * dx) / den          # along the edge
        if -1e-9 <= s < 1 - 1e-9:
            ts.append(u)
    return ts


def region_line_intervals(region, p0, d):
    """Intervals of the line that lie inside the region, as (t0, t1) pairs."""
    ts = []
    for ring in region.rings:
        ts += ring_line_params(ring, p0, d)
    ts.sort()
    out = []
    for i in range(0, len(ts) - 1, 2):
        if ts[i + 1] - ts[i] > 1e-9:
            out.append((ts[i], ts[i + 1]))
    return out


def subtract_intervals(a, b):
    """a minus b, both lists of (t0, t1)."""
    out = []
    for (s, e) in a:
        pieces = [(s, e)]
        for (bs, be) in b:
            nxt = []
            for (ps, pe) in pieces:
                if be <= ps or bs >= pe:
                    nxt.append((ps, pe))
                    continue
                if bs > ps:
                    nxt.append((ps, bs))
                if be < pe:
                    nxt.append((be, pe))
            pieces = nxt
        out += [(s2, e2) for (s2, e2) in pieces if e2 - s2 > 1e-9]
    return out

# ---------------------------------------------------------------------------
# Is this outline buildable?
# ---------------------------------------------------------------------------
def _segments_cross(a, b, c, d):
    def side(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)
    d1, d2 = side(c, d, a), side(c, d, b)
    d3, d4 = side(a, b, c), side(a, b, d)
    return d1 != d2 and d3 != d4


def self_intersects(ring, limit=400):
    """Does the outline cross itself? A shape drawn with a mouse often does."""
    n = len(ring)
    if n < 4 or n > limit:
        return False
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue                      # they share the closing vertex
            c, d = ring[j], ring[(j + 1) % n]
            if _segments_cross(a, b, c, d):
                return True
    return False


def problems(region, min_area=25.0, max_area=None, min_width=3.0):
    """Everything wrong with an outline, in sentences someone can act on.

    Drawn and traced outlines arrive from a mouse or a photograph, so they
    come with the faults a mouse and a photograph produce: shapes that cross
    themselves, courtyards that are not inside the building, slivers nothing
    fits in. Saying so is better than drawing nonsense from them."""
    out = []
    outer = dedupe(list(region.outer))
    if len(outer) < 3:
        return ["the outline needs at least three separate corners"]
    a = area(outer)
    if a < 1e-6:
        return ["the outline encloses no area; it may double back on itself"]
    if self_intersects(outer):
        out.append("the outline crosses itself; each corner should join the "
                   "next without the edges overlapping")
    if a < min_area:
        out.append("the outline encloses only %.1f m²; it is probably drawn in "
                   "the wrong units" % a)
    if max_area and a > max_area:
        out.append("the outline encloses %s m², which is above the limit of "
                   "%s m²" % (_thousands(a), _thousands(max_area)))
    for i, h in enumerate(region.holes, 1):
        hh = dedupe(list(h))
        if len(hh) < 3:
            out.append("courtyard %d needs at least three corners" % i)
            continue
        if not all(point_in_ring(p, outer) for p in hh):
            out.append("courtyard %d is not inside the outline" % i)
        elif area(hh) >= a * 0.92:
            out.append("courtyard %d leaves almost no building around it" % i)
    for i in range(len(region.holes)):
        for j in range(i + 1, len(region.holes)):
            if any(point_in_ring(p, region.holes[i]) for p in region.holes[j]):
                out.append("courtyards %d and %d overlap" % (i + 1, j + 1))
                break
    if not out and min_width and not fits_inside(region, min_width / 2.0):
        # nothing fits in a shape thinner than a room, and a plan of it is a
        # drawing of a line
        out.append("the outline is under %.0f m across; a room will not fit "
                   "inside it" % min_width)
    return out


def fits_inside(region, d):
    """Is there anything left after pulling the boundary in by d?

    Asking the shrunk shape for its area is not enough: a mitred offset past
    the middle of a thin shape turns it inside out, and an inside out polygon
    reports a cheerful positive area. Containment is not enough either --
    flip a thin rectangle about its own centre line and every corner is still
    inside where it started.

    What does change is the direction the boundary runs. An offset that had
    room to move keeps its winding; one that has passed through the middle and
    come out the other side reverses it. So the test is the sign."""
    if d <= 0:
        return True
    outer = offset_ring(ccw(dedupe(list(region.outer))), -d)
    if len(outer) < 3 or signed_area(outer) <= 1e-6:
        return False
    for h in region.holes:
        grown = offset_ring(cw(dedupe(list(h))), -d)
        if len(grown) < 3 or signed_area(grown) >= -1e-6:
            return False                      # the courtyard turned inside out
        if not all(point_in_ring(p, outer) for p in grown):
            return False                      # or ate the building around it
    return True


def _thousands(v):
    return "{:,.0f}".format(v).replace(",", " ")


def convex_hull(ring):
    """The smallest convex outline containing every corner, anticlockwise."""
    pts = sorted(set((round(x, 9), round(y, 9)) for (x, y) in ring))
    if len(pts) < 3:
        return list(pts)

    def half(seq):
        out = []
        for q in seq:
            while len(out) >= 2:
                (ax, ay), (bx, by) = out[-2], out[-1]
                if (bx - ax) * (q[1] - ay) - (by - ay) * (q[0] - ax) <= 0:
                    out.pop()
                else:
                    break
            out.append(q)
        return out[:-1]

    return half(pts) + half(pts[::-1])


def solidity(ring):
    """Area as a fraction of its convex hull: 1 for a box, less for a comb.

    A shape read out of a photograph that has gone wrong is not merely
    complicated, it is riddled — this is how that shows up as a number."""
    hull = convex_hull(ring)
    if len(hull) < 3:
        return 0.0
    h = abs(signed_area(hull))
    return abs(signed_area(ring)) / h if h > 1e-12 else 0.0


def raggedness(ring):
    """Perimeter measured in units of the shape's own size.

    Four for a square, five for a shaky freehand circle, eight for a deep
    comb, and well into the teens for something that is not a drawing."""
    a = abs(signed_area(ring))
    if a <= 1e-12:
        return 1e9
    return perimeter(ring) / math.sqrt(a)
