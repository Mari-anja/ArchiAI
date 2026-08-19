"""Turn a picture of a shape into a footprint the engine can build.

Someone sketches an outline on paper, photographs it, and drops it in. Or
they export a plan as an image. Either way what arrives is a grid of pixels,
and what the engine needs is a closed ring in metres.

The route is deterministic, not learned: threshold the ink, decide what is
inside it, walk the boundary, simplify it, and then straighten it — because a
hand-drawn rectangle should come out as a rectangle rather than as a wobble
with three hundred vertices. Nothing here calls a model, so the same picture
always gives the same building.
"""

import math
import struct
import zlib

from . import geom2d as G


# ---------------------------------------------------------------------------
# PNG in, luminance grid out
# ---------------------------------------------------------------------------
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _unfilter(raw, w, h, bpp, stride):
    out = bytearray(h * stride)
    prev = bytearray(stride)
    pos = 0
    for r in range(h):
        ft = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                c = prev[i - bpp] if i >= bpp else 0
                b = prev[i]
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif ft != 0:
            raise ValueError("unknown PNG filter %d" % ft)
        out[r * stride:(r + 1) * stride] = line
        prev = line
    return out


def read_png(data):
    """(width, height, rows) with rows of luminance 0.0 (ink) to 1.0 (paper).

    Enough of the format to read what a phone, a scanner or a browser canvas
    produces: 8 or 16 bit, greyscale, palette, RGB or RGBA, any filter.
    Transparency is composited onto white, so a cut-out sketch reads as ink
    on paper rather than ink on nothing."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, plte, trns, hdr = 8, [], None, None, None
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if kind == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IEND":
            break
    if not hdr:
        raise ValueError("PNG has no header")
    w, h, depth, ctype, comp, filt, interlace = hdr
    if interlace:
        raise ValueError("interlaced PNG is not supported; save it without Adam7")
    if depth not in (8, 16) or ctype not in CHANNELS:
        raise ValueError("unsupported PNG: %d bit, colour type %d" % (depth, ctype))
    if w * h > 40_000_000:
        raise ValueError("image is too large to trace")
    nch = CHANNELS[ctype]
    step = depth // 8
    bpp = max(1, nch * step)
    stride = w * bpp
    raw = zlib.decompress(b"".join(idat))
    flat = _unfilter(raw, w, h, bpp, stride)

    rows = []
    for r in range(h):
        base = r * stride
        row = [0.0] * w
        for c in range(w):
            o = base + c * bpp
            if ctype == 3:
                i = flat[o] * 3
                rr, gg, bb = plte[i], plte[i + 1], plte[i + 2]
                a = trns[flat[o]] if trns and flat[o] < len(trns) else 255
            elif ctype in (0, 4):
                rr = gg = bb = flat[o]
                a = flat[o + step * 1] if ctype == 4 else 255
            else:
                rr, gg, bb = flat[o], flat[o + step], flat[o + 2 * step]
                a = flat[o + 3 * step] if ctype == 6 else 255
            lum = (0.2126 * rr + 0.7152 * gg + 0.0722 * bb) / 255.0
            row[c] = lum * (a / 255.0) + (1.0 - a / 255.0)      # over white
        rows.append(row)
    return w, h, rows


def downsample(rows, longest=320):
    """Shrink to a workable size. Averaging also quiets pencil grain."""
    h = len(rows)
    w = len(rows[0]) if h else 0
    k = max(1, int(math.ceil(max(w, h) / float(longest))))
    if k == 1:
        return w, h, rows
    nw, nh = max(1, w // k), max(1, h // k)
    out = []
    for r in range(nh):
        line = [0.0] * nw
        for c in range(nw):
            s = n = 0.0
            for dr in range(k):
                rr = rows[r * k + dr]
                for dc in range(k):
                    s += rr[c * k + dc]
                    n += 1
            line[c] = s / n
        out.append(line)
    return nw, nh, out


# ---------------------------------------------------------------------------
# Ink, and what is inside it
# ---------------------------------------------------------------------------
def otsu(rows, bins=64):
    """The threshold that best separates ink from paper, chosen from the
    picture itself rather than guessed, so a faint pencil line and a bold
    marker both work."""
    hist = [0] * bins
    total = 0
    for row in rows:
        for v in row:
            hist[min(bins - 1, int(v * bins))] += 1
            total += 1
    if not total:
        return 0.5
    sum_all = sum(i * hist[i] for i in range(bins))
    best, cut, wb, sb = -1.0, bins // 2, 0, 0.0
    for i in range(bins):
        wb += hist[i]
        if wb == 0 or wb == total:
            continue
        sb += i * hist[i]
        mb = sb / wb
        mf = (sum_all - sb) / (total - wb)
        var = wb * (total - wb) * (mb - mf) ** 2
        if var > best:
            best, cut = var, i
    return (cut + 1) / float(bins)


def _components(mask, w, h, want):
    """Label 4-connected runs of cells equal to `want`. Returns (labels, sizes)."""
    labels = [[0] * w for _ in range(h)]
    sizes = [0]
    nxt = 0
    for r0 in range(h):
        for c0 in range(w):
            if mask[r0][c0] != want or labels[r0][c0]:
                continue
            nxt += 1
            n = 0
            stack = [(r0, c0)]
            labels[r0][c0] = nxt
            while stack:
                r, c = stack.pop()
                n += 1
                for (dr, dc) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < h and 0 <= cc < w and not labels[rr][cc] \
                            and mask[rr][cc] == want:
                        labels[rr][cc] = nxt
                        stack.append((rr, cc))
            sizes.append(n)
    return labels, sizes


def _parity(ink, w, r, c):
    """How many strokes lie between this cell and the edge of the picture.

    Odd means the cell is inside the outline; even means it is outside it, or
    inside a courtyard drawn within it."""
    runs, prev = 0, False
    for x in range(c):
        cur = ink[r][x]
        if cur and not prev:
            runs += 1
        prev = cur
    return runs & 1


def _is_filled(ink_n, enclosed_n):
    """Is the ink the shape, or only its outline?

    A filled blob has ink over nearly everything its boundary encloses; a
    pencil outline has ink over a thin fraction of it. Which one it is decides
    whether an enclosed white region is the inside of the building or a
    courtyard."""
    if enclosed_n <= 0:
        return True
    return ink_n / float(enclosed_n) > 0.45


def solid(rows, w, h, threshold=None, keep_hole_frac=0.012):
    """The filled shape the picture describes, as a boolean grid.

    An outline drawing and a filled one both work, and a courtyard survives
    either way: openings big enough to be courtyards are kept, while specks
    and the gaps in a shaky line are filled."""
    t = otsu(rows) if threshold is None else threshold
    ink = [[rows[r][c] < t for c in range(w)] for r in range(h)]
    ink_n = sum(1 for r in range(h) for c in range(w) if ink[r][c])
    if not ink_n:
        raise ValueError("the image has no dark marks to trace")

    labels, sizes = _components(ink, w, h, False)
    outside = set()
    for c in range(w):
        outside.add(labels[0][c])
        outside.add(labels[h - 1][c])
    for r in range(h):
        outside.add(labels[r][0])
        outside.add(labels[r][w - 1])

    # every cell the ink shuts off from the edge of the picture
    reps = {}
    enclosed_n = ink_n
    for r in range(h):
        for c in range(w):
            lb = labels[r][c]
            if ink[r][c] or lb in outside:
                continue
            enclosed_n += 1
            reps.setdefault(lb, []).append((r, c))

    filled = _is_filled(ink_n, enclosed_n)
    inside = set()
    if not filled:
        for lb, cells in reps.items():
            votes = 0
            picks = cells[::max(1, len(cells) // 5)][:5]
            for (r, c) in picks:
                votes += _parity(ink, w, r, c)
            if votes * 2 > len(picks):
                inside.add(lb)

    shape = [[ink[r][c] or (labels[r][c] in inside and not ink[r][c])
              for c in range(w)] for r in range(h)]

    lab, sz = _components(shape, w, h, True)
    if len(sz) < 2:
        raise ValueError("no shape found in the image")
    main = max(range(1, len(sz)), key=lambda i: sz[i])
    if sz[main] < 0.004 * w * h:
        raise ValueError("the largest shape covers less than half a percent "
                         "of the image; is the drawing too faint?")
    shape = [[lab[r][c] == main for c in range(w)] for r in range(h)]

    # what is left enclosed is a hole, if it is big enough to be a courtyard
    hl, hs = _components(shape, w, h, False)
    border = set()
    for c in range(w):
        border.add(hl[0][c])
        border.add(hl[h - 1][c])
    for r in range(h):
        border.add(hl[r][0])
        border.add(hl[r][w - 1])
    for r in range(h):
        for c in range(w):
            lb = hl[r][c]
            if not shape[r][c] and lb not in border \
                    and hs[lb] < keep_hole_frac * sz[main]:
                shape[r][c] = True
    return shape, hl, border


# ---------------------------------------------------------------------------
# Boundary
# ---------------------------------------------------------------------------
def boundary_loops(shape, w, h):
    """Closed rings around the shape, in lattice coordinates with y upward.

    Every cell face that has shape on one side and not on the other is one
    unit edge, directed so the shape lies to its left. Chained together those
    edges close exactly, which a pixel walk does not always manage."""
    edges = {}

    def add(a, b):
        edges.setdefault(a, []).append(b)

    for r in range(h):
        y1, y0 = h - r, h - r - 1
        row = shape[r]
        for c in range(w):
            if not row[c]:
                continue
            x0, x1 = c, c + 1
            if r == 0 or not shape[r - 1][c]:
                add((x1, y1), (x0, y1))
            if r == h - 1 or not shape[r + 1][c]:
                add((x0, y0), (x1, y0))
            if c == 0 or not row[c - 1]:
                add((x0, y1), (x0, y0))
            if c == w - 1 or not row[c + 1]:
                add((x1, y0), (x1, y1))

    loops = []
    while edges:
        start = next(iter(edges))
        ring = [start]
        cur = start
        while True:
            outs = edges.get(cur)
            if not outs:
                break
            nxt = outs.pop()
            if not outs:
                del edges[cur]
            if nxt == start:
                break
            ring.append(nxt)
            cur = nxt
        if len(ring) >= 4:
            loops.append([(float(x), float(y)) for (x, y) in ring])
    return loops


def rdp(ring, eps):
    """Drop the vertices that carry no information."""
    n = len(ring)
    if n < 4:
        return ring[:]
    # start from the two furthest-apart points so a closed ring has anchors
    i0 = 0
    i1 = max(range(n), key=lambda i: (ring[i][0] - ring[0][0]) ** 2
             + (ring[i][1] - ring[0][1]) ** 2)
    out = _rdp_open(ring[i0:i1 + 1], eps)[:-1] + \
        _rdp_open(ring[i1:] + [ring[i0]], eps)[:-1]
    return out


def _rdp_open(pts, eps):
    if len(pts) < 3:
        return pts[:]
    a, b = pts[0], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    worst, wi = -1.0, 0
    for i in range(1, len(pts) - 1):
        p = pts[i]
        if n < 1e-12:
            d = math.hypot(p[0] - a[0], p[1] - a[1])
        else:
            d = abs(dy * (p[0] - a[0]) - dx * (p[1] - a[1])) / n
        if d > worst:
            worst, wi = d, i
    if worst <= eps:
        return [a, b]
    return _rdp_open(pts[:wi + 1], eps)[:-1] + _rdp_open(pts[wi:], eps)


# ---------------------------------------------------------------------------
# Straightening
# ---------------------------------------------------------------------------
def dominant_angle(ring):
    """The angle the drawing is mostly built on, weighted by edge length."""
    bins = [0.0] * 90
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            continue
        deg = math.degrees(math.atan2(dy, dx)) % 90.0
        bins[int(deg) % 90] += L
    k = max(range(90), key=lambda i: bins[i] + 0.5 * (bins[i - 1] + bins[(i + 1) % 90]))
    tot = bins[k] + bins[k - 1] + bins[(k + 1) % 90]
    if tot < 1e-9:
        return 0.0
    centre = ((k - 1) * bins[k - 1] + k * bins[k] + (k + 1) * bins[(k + 1) % 90]) / tot
    return math.radians(centre % 90.0)


def regularise(ring, tol_deg=22.0, base=None):
    """Snap edges that are nearly on the grain of the drawing onto it.

    A hand-drawn rectangle arrives as four edges a few degrees out of true.
    Each edge close to the dominant axis is turned onto it exactly, and the
    corners are put back by intersecting the neighbouring lines. Edges that
    are genuinely off-axis -- a splayed wing, a curve -- are left alone."""
    n = len(ring)
    if n < 3:
        return ring[:]
    base = dominant_angle(ring) if base is None else base
    lines = []
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            lines.append(None)
            continue
        ang = math.atan2(dy, dx)
        rel = math.degrees(ang - base) % 90.0
        off = rel if rel <= 45.0 else rel - 90.0
        if abs(off) <= tol_deg:
            k = round(math.degrees(ang - base) / 90.0)
            ang = base + math.radians(90.0 * k)
            dx, dy = math.cos(ang), math.sin(ang)
        else:
            dx, dy = dx / L, dy / L
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        lines.append((mid, (dx, dy)))

    out = []
    for i in range(n):
        l0, l1 = lines[i - 1], lines[i]
        p = _cross(l0, l1)
        out.append(p if p else ring[i])
    return drop_collinear(_dedupe(out))


def _cross(l0, l1):
    if not l0 or not l1:
        return None
    (p0, d0), (p1, d1) = l0, l1
    den = d0[0] * d1[1] - d0[1] * d1[0]
    if abs(den) < 1e-6:
        return None
    t = ((p1[0] - p0[0]) * d1[1] - (p1[1] - p0[1]) * d1[0]) / den
    q = (p0[0] + d0[0] * t, p0[1] + d0[1] * t)
    if math.hypot(q[0] - p0[0], q[1] - p0[1]) > 4.0 * (
            math.hypot(p1[0] - p0[0], p1[1] - p0[1]) + 1.0):
        return None                       # a near-parallel pair flying off
    return q


def drop_collinear(ring, tol_deg=4.0):
    """Lose the vertices that only restate the line they sit on."""
    n = len(ring)
    if n < 4:
        return ring[:]
    out = []
    for i in range(n):
        a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
        d0 = math.atan2(b[1] - a[1], b[0] - a[0])
        d1 = math.atan2(c[1] - b[1], c[0] - b[0])
        turn = abs(math.degrees(d1 - d0) + 180.0) % 360.0 - 180.0
        if abs(turn) > tol_deg:
            out.append(b)
    return out if len(out) >= 3 else ring[:]


def _dedupe(ring, eps=1e-6):
    out = []
    for p in ring:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > eps:
            out.append(p)
    while len(out) > 3 and math.hypot(out[0][0] - out[-1][0],
                                      out[0][1] - out[-1][1]) <= eps:
        out.pop()
    return out


# ---------------------------------------------------------------------------
def footprint(rows, w=None, h=None, area_m2=None, width_m=None,
              simplify=0.010, straighten=22.0, longest=320):
    """A luminance grid in, a Region in metres out.

    Give either the floor area the plate should cover or its overall width;
    without a size the ring comes back in metres at one pixel to the metre,
    which is only useful for testing."""
    if w is None or h is None:
        h = len(rows)
        w = len(rows[0]) if h else 0
    w, h, rows = downsample(rows, longest)
    shape, hole_labels, border = solid(rows, w, h)
    loops = boundary_loops(shape, w, h)
    if not loops:
        raise ValueError("no closed outline could be traced")

    eps = simplify * max(w, h)
    rings = []
    for lp in loops:
        r = rdp(lp, eps)
        if len(r) >= 3:
            rings.append(r)
    if not rings:
        raise ValueError("the outline simplified away to nothing")

    outer = max(rings, key=lambda r: abs(G.signed_area(r)))
    base = dominant_angle(outer)
    outer = regularise(outer, straighten, base)
    if G.signed_area(outer) < 0:
        outer = outer[::-1]

    holes = []
    for r in rings:
        if r is None or len(r) < 3:
            continue
        if abs(G.signed_area(r)) >= abs(G.signed_area(outer)) * 0.98:
            continue
        if abs(G.signed_area(r)) < abs(G.signed_area(outer)) * 0.012:
            continue
        r = regularise(r, straighten, base)
        if len(r) < 3:
            continue
        if G.signed_area(r) > 0:
            r = r[::-1]
        holes.append(r)

    k = 1.0
    if width_m:
        bx = _bbox(outer)
        span = max(bx[2] - bx[0], bx[3] - bx[1])
        k = width_m / span if span > 1e-9 else 1.0
    elif area_m2:
        net = abs(G.signed_area(outer)) - sum(abs(G.signed_area(r)) for r in holes)
        k = math.sqrt(area_m2 / net) if net > 1e-9 else 1.0

    cx, cy = G.centroid(outer)
    def put(r):
        return [((x - cx) * k, (y - cy) * k) for (x, y) in r]
    return G.Region(put(outer), [put(r) for r in holes])


def _bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def from_png(data, **kw):
    w, h, rows = read_png(data)
    return footprint(rows, w, h, **kw)
