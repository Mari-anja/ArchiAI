"""The drawing set as one PDF, written with nothing but the standard library.

An architect issues a PDF, not fifty-five separate files. This turns the
sheets the engine already draws into one document at true paper size, with
the geometry still vector and the text still text, so it can be printed at
A1, zoomed into without going soft, and searched for a drawing number.

It is not a general SVG converter. It reads exactly the subset this engine
emits -- lines, paths, rectangles, circles, text, clipped groups and the hatch
patterns -- which is small enough to handle honestly and to keep honest.
"""

import math
import re
import zlib
import xml.etree.ElementTree as ET

MM = 72.0 / 25.4                       # PDF points per millimetre
SVG_NS = "{http://www.w3.org/2000/svg}"


# ---------------------------------------------------------------------------
# Font metrics: enough of Helvetica to place text where the SVG puts it
# ---------------------------------------------------------------------------
_HELV = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584")
_HELV_B = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584")

# the handful of characters beyond ASCII that the sheets actually use
_EXTRA = {"°": (400, 400), "²": (333, 333), "³": (333, 333),
          "½": (834, 889), "·": (278, 278), "×": (584, 584),
          "—": (1000, 1000), "–": (556, 556), "’": (222, 278),
          "é": (556, 556), "±": (584, 584)}


def _widths(bold):
    table = [int(v) for v in (_HELV_B if bold else _HELV).split()]
    out = {chr(32 + i): w for i, w in enumerate(table)}
    for ch, pair in _EXTRA.items():
        out[ch] = pair[1] if bold else pair[0]
    return out


W_REG, W_BOLD = _widths(False), _widths(True)


def text_width(s, size, bold=False, spacing=0.0):
    table = W_BOLD if bold else W_REG
    total = sum(table.get(ch, 556) for ch in s) / 1000.0 * size
    return total + spacing * len(s)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _f(v):
    return ("%.4f" % v).rstrip("0").rstrip(".") or "0"


def _num(v, default=0.0):
    if v is None:
        return default
    try:
        return float(str(v).strip().replace("mm", "").replace("px", ""))
    except ValueError:
        return default


def colour(value):
    """'#rrggbb' -> (r, g, b) in 0..1. 'none' -> None. 'url(#x)' -> ('P', x)."""
    if not value or value == "none":
        return None
    v = value.strip()
    if v.startswith("url(#"):
        return ("P", v[5:].rstrip(")"))
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (0.0, 0.0, 0.0)


def _rgb(c, stroke):
    return "%s %s %s %s" % (_f(c[0]), _f(c[1]), _f(c[2]), "RG" if stroke else "rg")


# ---------------------------------------------------------------------------
# Path data
# ---------------------------------------------------------------------------
_TOKENS = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def _arc(x0, y0, rx, ry, phi_deg, large, sweep, x1, y1):
    """An SVG elliptical arc as cubic Beziers, which is all PDF understands."""
    if rx == 0 or ry == 0 or (abs(x1 - x0) < 1e-12 and abs(y1 - y0) < 1e-12):
        return [("L", x1, y1)]
    phi = math.radians(phi_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x0 - x1) / 2.0, (y0 - y1) / 2.0
    x1p = cos_p * dx2 + sin_p * dy2
    y1p = -sin_p * dx2 + cos_p * dy2
    rx, ry = abs(rx), abs(ry)
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(num / den, 0.0)) if den else 0.0
    if large == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x0 + x1) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (y0 + y1) / 2.0

    def angle(ux, uy, vx, vy):
        d = math.hypot(ux, uy) * math.hypot(vx, vy)
        if d == 0:
            return 0.0
        c = max(-1.0, min(1.0, (ux * vx + uy * vy) / d))
        a = math.acos(c)
        return -a if ux * vy - uy * vx < 0 else a

    th0 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dth > 0:
        dth -= 2 * math.pi
    elif sweep and dth < 0:
        dth += 2 * math.pi

    segs = max(1, int(math.ceil(abs(dth) / (math.pi / 2))))
    out = []
    step = dth / segs
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    th = th0
    for _ in range(segs):
        c0, s0 = math.cos(th), math.sin(th)
        c1, s1 = math.cos(th + step), math.sin(th + step)

        def pt(c, s):
            return (cos_p * rx * c - sin_p * ry * s + cx,
                    sin_p * rx * c + cos_p * ry * s + cy)

        p1 = pt(c0, s0)
        p2 = pt(c1, s1)
        d1 = (cos_p * rx * -s0 - sin_p * ry * c0,
              sin_p * rx * -s0 + cos_p * ry * c0)
        d2 = (cos_p * rx * -s1 - sin_p * ry * c1,
              sin_p * rx * -s1 + cos_p * ry * c1)
        out.append(("C", p1[0] + k * d1[0], p1[1] + k * d1[1],
                    p2[0] - k * d2[0], p2[1] - k * d2[1], p2[0], p2[1]))
        th += step
    return out


def path_ops(d):
    """SVG path data to PDF path construction operators."""
    toks = [(m.group(1), m.group(2)) for m in _TOKENS.finditer(d or "")]
    out, i = [], 0
    cx = cy = sx = sy = 0.0
    cmd = None
    prev_c = None

    def nxt():
        nonlocal i
        v = float(toks[i][1])
        i += 1
        return v

    while i < len(toks):
        if toks[i][0]:
            cmd = toks[i][0]
            i += 1
            if cmd in "Zz":
                out.append("h")
                cx, cy = sx, sy
                continue
        if i >= len(toks) or cmd is None:
            break
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            x, y = nxt(), nxt()
            if rel:
                x, y = cx + x, cy + y
            out.append("%s %s m" % (_f(x), _f(y)))
            cx = sx = x
            cy = sy = y
            cmd = "l" if rel else "L"
        elif c == "L":
            x, y = nxt(), nxt()
            if rel:
                x, y = cx + x, cy + y
            out.append("%s %s l" % (_f(x), _f(y)))
            cx, cy = x, y
        elif c == "H":
            x = nxt()
            x = cx + x if rel else x
            out.append("%s %s l" % (_f(x), _f(cy)))
            cx = x
        elif c == "V":
            y = nxt()
            y = cy + y if rel else y
            out.append("%s %s l" % (_f(cx), _f(y)))
            cy = y
        elif c in ("C", "S"):
            if c == "C":
                x1, y1 = nxt(), nxt()
            else:
                x1, y1 = ((2 * cx - prev_c[0], 2 * cy - prev_c[1])
                          if prev_c else (cx, cy))
            x2, y2 = nxt(), nxt()
            x, y = nxt(), nxt()
            if rel:
                if c == "C":
                    x1, y1 = cx + x1, cy + y1
                x2, y2 = cx + x2, cy + y2
                x, y = cx + x, cy + y
            out.append("%s %s %s %s %s %s c" % (_f(x1), _f(y1), _f(x2), _f(y2),
                                                _f(x), _f(y)))
            prev_c = (x2, y2)
            cx, cy = x, y
            continue
        elif c in ("Q", "T"):
            if c == "Q":
                qx, qy = nxt(), nxt()
            else:
                qx, qy = ((2 * cx - prev_c[0], 2 * cy - prev_c[1])
                          if prev_c else (cx, cy))
            x, y = nxt(), nxt()
            if rel:
                if c == "Q":
                    qx, qy = cx + qx, cy + qy
                x, y = cx + x, cy + y
            out.append("%s %s %s %s %s %s c"
                       % (_f(cx + 2.0 / 3 * (qx - cx)), _f(cy + 2.0 / 3 * (qy - cy)),
                          _f(x + 2.0 / 3 * (qx - x)), _f(y + 2.0 / 3 * (qy - y)),
                          _f(x), _f(y)))
            prev_c = (qx, qy)
            cx, cy = x, y
            continue
        elif c == "A":
            rx, ry, rot = nxt(), nxt(), nxt()
            large, sweep = int(nxt()), int(nxt())
            x, y = nxt(), nxt()
            if rel:
                x, y = cx + x, cy + y
            for seg in _arc(cx, cy, rx, ry, rot, large, sweep, x, y):
                if seg[0] == "L":
                    out.append("%s %s l" % (_f(seg[1]), _f(seg[2])))
                else:
                    out.append("%s %s %s %s %s %s c"
                               % tuple(_f(v) for v in seg[1:]))
            cx, cy = x, y
        else:
            i += 1
            continue
        prev_c = None
    return out


# ---------------------------------------------------------------------------
# SVG element -> PDF content
# ---------------------------------------------------------------------------
FONTS = {(False, False): "F1", (True, False): "F2",
         (False, True): "F3", (True, True): "F4"}
FONT_NAMES = {"F1": "Helvetica", "F2": "Helvetica-Bold",
              "F3": "Helvetica-Oblique", "F4": "Helvetica-BoldOblique"}
CAPS = {"butt": 0, "round": 1, "square": 2}
JOINS = {"miter": 0, "round": 1, "bevel": 2}


def _tag(el):
    return el.tag.replace(SVG_NS, "")


def _esc(s):
    out = []
    for ch in s:
        try:
            b = ch.encode("cp1252")
        except UnicodeEncodeError:
            b = b"?"
        for byte in b:
            c = chr(byte)
            out.append("\\" + c if c in "()\\" else c)
    return "".join(out)


def _gradient(el):
    """A linear gradient's ends and stops, in whatever units it declares."""
    stops = []
    for s in el:
        if _tag(s) != "stop":
            continue
        c = colour(s.get("stop-color", "#000000")) or (0, 0, 0)
        stops.append((_num(s.get("offset"), 0.0), c))
    stops.sort(key=lambda kv: kv[0])
    return {"x1": _num(el.get("x1"), 0.0), "y1": _num(el.get("y1"), 0.0),
            "x2": _num(el.get("x2"), 1.0), "y2": _num(el.get("y2"), 0.0),
            "bbox_units": el.get("gradientUnits", "objectBoundingBox")
            == "objectBoundingBox",
            "stops": stops or [(0.0, (0, 0, 0)), (1.0, (1, 1, 1))]}


def _ops_bbox(ops):
    """A rough bounding box straight off the path operators."""
    xs, ys = [], []
    for op in ops:
        parts = op.split()
        if parts and parts[-1] == "re" and len(parts) >= 5:
            x, y, w, h = (float(v) for v in parts[:4])
            xs += [x, x + w]
            ys += [y, y + h]
            continue
        nums = [float(v) for v in parts[:-1] if _NUMERIC.match(v)]
        xs += nums[0::2]
        ys += nums[1::2]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


_NUMERIC = re.compile(r"^-?\d*\.?\d+$")


class Converter:
    """One SVG document into one PDF page's content stream."""

    # a picture that is not a drawing sheet gets a page it sits comfortably on
    FIT_MM = (420.0, 297.0)

    def __init__(self, svg, page_mm=None):
        root = ET.fromstring(svg)
        w_attr = root.get("width") or "841mm"
        self.width = _num(w_attr, 841.0)
        self.height = _num(root.get("height"), 594.0)
        vb = (root.get("viewBox") or "").split()
        if len(vb) == 4:
            self.width = _num(vb[2], self.width)
            self.height = _num(vb[3], self.height)
        if page_mm:
            page_w, page_h = page_mm
        elif "mm" in str(w_attr):
            page_w, page_h = self.width, self.height      # user units are mm
        else:
            aspect = self.width / max(self.height, 1e-6)
            fw, fh = self.FIT_MM
            page_w, page_h = ((fw, fw / aspect) if aspect >= fw / fh
                              else (fh * aspect, fh))
        self.page_w, self.page_h = page_w, page_h
        self.scale = (page_w * MM) / max(self.width, 1e-6)
        self.patterns, self.clips, self.gradients = {}, {}, {}
        for defs in root.iter(SVG_NS + "defs"):
            for el in defs:
                t = _tag(el)
                if t == "pattern":
                    self.patterns[el.get("id")] = el
                elif t == "linearGradient":
                    self.gradients[el.get("id")] = _gradient(el)
                elif t == "clipPath":
                    kid = next(iter(el), None)
                    if kid is not None:
                        self.clips[el.get("id")] = kid.get("d", "")
        self.used = {}                 # tiling pattern id -> resource name
        self.shadings = {}             # resource name -> shading spec
        self.gs = {}                   # (fill_op, stroke_op) -> resource name
        self.fonts = set()
        self.ops = []
        self._walk(root)

    # -- resources ---------------------------------------------------------
    def _pattern_name(self, pid):
        if pid not in self.used:
            self.used[pid] = "Pt%d" % (len(self.used) + 1)
        return self.used[pid]

    def _paint_ref(self, pid, ops):
        """The resource name for a url(#...) fill, or None if it is unknown.

        A dangling reference makes a PDF that will not open, so anything the
        document does not actually define falls back to a flat colour."""
        if pid in self.patterns:
            return self._pattern_name(pid)
        grad = self.gradients.get(pid)
        if not grad:
            return None
        box = _ops_bbox(ops)
        if not box:
            return None
        x0, y0, x1, y1 = box
        if grad["bbox_units"]:
            gx1 = x0 + grad["x1"] * (x1 - x0)
            gy1 = y0 + grad["y1"] * (y1 - y0)
            gx2 = x0 + grad["x2"] * (x1 - x0)
            gy2 = y0 + grad["y2"] * (y1 - y0)
        else:
            gx1, gy1, gx2, gy2 = grad["x1"], grad["y1"], grad["x2"], grad["y2"]
        name = "Sh%d" % (len(self.shadings) + 1)
        self.shadings[name] = {
            "coords": (gx1, gy1, gx2, gy2), "stops": grad["stops"],
            "matrix": [self.scale, 0.0, 0.0, -self.scale, 0.0,
                       self.page_h * MM]}
        return name

    def _gs_name(self, ca, CA):
        key = (round(ca, 3), round(CA, 3))
        if key not in self.gs:
            self.gs[key] = "GS%d" % (len(self.gs) + 1)
        return self.gs[key]

    # -- walking -----------------------------------------------------------
    def _walk(self, el):
        for kid in el:
            t = _tag(kid)
            if t == "defs":
                continue
            if t == "g":
                clip = kid.get("clip-path", "")
                cid = clip[5:].rstrip(")") if clip.startswith("url(#") else None
                self.ops.append("q")
                if cid and cid in self.clips:
                    self.ops.extend(path_ops(self.clips[cid]))
                    self.ops.append("W n")
                self._walk(kid)
                self.ops.append("Q")
            elif t == "line":
                self._shape(kid, ["%s %s m" % (_f(_num(kid.get("x1"))),
                                               _f(_num(kid.get("y1")))),
                                  "%s %s l" % (_f(_num(kid.get("x2"))),
                                               _f(_num(kid.get("y2"))))])
            elif t == "rect":
                self._shape(kid, self._rect_ops(kid))
            elif t == "circle":
                self._shape(kid, self._circle_ops(_num(kid.get("cx")),
                                                  _num(kid.get("cy")),
                                                  _num(kid.get("r"))))
            elif t == "path":
                self._shape(kid, path_ops(kid.get("d")))
            elif t == "text":
                self._text(kid)
            else:
                self._walk(kid)

    def _rect_ops(self, el):
        x, y = _num(el.get("x")), _num(el.get("y"))
        w, h = _num(el.get("width")), _num(el.get("height"))
        r = _num(el.get("rx"))
        if r <= 0:
            return ["%s %s %s %s re" % (_f(x), _f(y), _f(w), _f(h))]
        r = min(r, w / 2.0, h / 2.0)
        k = r * 0.5523
        return ["%s %s m" % (_f(x + r), _f(y)),
                "%s %s l" % (_f(x + w - r), _f(y)),
                "%s %s %s %s %s %s c" % (_f(x + w - r + k), _f(y), _f(x + w),
                                         _f(y + r - k), _f(x + w), _f(y + r)),
                "%s %s l" % (_f(x + w), _f(y + h - r)),
                "%s %s %s %s %s %s c" % (_f(x + w), _f(y + h - r + k),
                                         _f(x + w - r + k), _f(y + h),
                                         _f(x + w - r), _f(y + h)),
                "%s %s l" % (_f(x + r), _f(y + h)),
                "%s %s %s %s %s %s c" % (_f(x + r - k), _f(y + h), _f(x),
                                         _f(y + h - r + k), _f(x), _f(y + h - r)),
                "%s %s l" % (_f(x), _f(y + r)),
                "%s %s %s %s %s %s c" % (_f(x), _f(y + r - k), _f(x + r - k),
                                         _f(y), _f(x + r), _f(y)),
                "h"]

    @staticmethod
    def _circle_ops(cx, cy, r):
        k = r * 0.5523
        return ["%s %s m" % (_f(cx + r), _f(cy)),
                "%s %s %s %s %s %s c" % (_f(cx + r), _f(cy + k), _f(cx + k),
                                         _f(cy + r), _f(cx), _f(cy + r)),
                "%s %s %s %s %s %s c" % (_f(cx - k), _f(cy + r), _f(cx - r),
                                         _f(cy + k), _f(cx - r), _f(cy)),
                "%s %s %s %s %s %s c" % (_f(cx - r), _f(cy - k), _f(cx - k),
                                         _f(cy - r), _f(cx), _f(cy - r)),
                "%s %s %s %s %s %s c" % (_f(cx + k), _f(cy - r), _f(cx + r),
                                         _f(cy - k), _f(cx + r), _f(cy)),
                "h"]

    # -- painting ----------------------------------------------------------
    def _shape(self, el, ops):
        if not ops:
            return
        fill = colour(el.get("fill", "none"))
        stroke = colour(el.get("stroke"))
        if stroke is not None and not el.get("stroke-width"):
            stroke = None
        if fill is None and stroke is None:
            return
        self.ops.append("q")
        fo = _num(el.get("fill-opacity"), 1.0)
        so = _num(el.get("stroke-opacity"), 1.0)
        if fo < 1.0 or so < 1.0:
            self.ops.append("/%s gs" % self._gs_name(fo, so))
        if isinstance(fill, tuple) and fill and fill[0] == "P":
            name = self._paint_ref(fill[1], ops)
            if name:
                self.ops.append("/Pattern cs /%s scn" % name)
            else:
                self.ops.append(_rgb((0.85, 0.85, 0.85), False))
        elif fill is not None:
            self.ops.append(_rgb(fill, False))
        if stroke is not None:
            self.ops.append(_rgb(stroke, True))
            self.ops.append("%s w" % _f(max(_num(el.get("stroke-width"), 0.2), 0.01)))
            self.ops.append("%d J" % CAPS.get(el.get("stroke-linecap", "butt"), 0))
            self.ops.append("%d j" % JOINS.get(el.get("stroke-linejoin", "miter"), 0))
            dash = el.get("stroke-dasharray")
            if dash and dash != "none":
                nums = [_f(_num(v)) for v in re.split(r"[,\s]+", dash.strip()) if v]
                self.ops.append("[%s] 0 d" % " ".join(nums))
        self.ops.extend(ops)
        even = el.get("fill-rule") == "evenodd"
        if fill is not None and stroke is not None:
            self.ops.append("B*" if even else "B")
        elif fill is not None:
            self.ops.append("f*" if even else "f")
        else:
            self.ops.append("S")
        self.ops.append("Q")

    # -- text --------------------------------------------------------------
    def _text(self, el):
        s = "".join(el.itertext())
        if not s:
            return
        size = _num(el.get("font-size"), 2.5)
        weight = el.get("font-weight", "400")
        bold = weight in ("600", "700", "800", "900", "bold")
        italic = el.get("font-style") == "italic"
        name = FONTS[(bold, italic)]
        self.fonts.add(name)
        spacing = _num(el.get("letter-spacing"), 0.0)
        x, y = _num(el.get("x")), _num(el.get("y"))
        w = text_width(s, size, bold, spacing)
        anchor = el.get("text-anchor", "start")
        if anchor == "middle":
            x -= w / 2.0
        elif anchor == "end":
            x -= w
        base = el.get("dominant-baseline")
        if base in ("middle", "central"):
            y += size * 0.36
        elif base == "hanging":
            y += size * 0.72

        self.ops.append("q")
        rot = el.get("transform", "")
        m = re.match(r"rotate\(\s*(-?[\d.]+)[,\s]+(-?[\d.]+)[,\s]+(-?[\d.]+)\s*\)", rot)
        if m:
            a = math.radians(float(m.group(1)))
            px, py = float(m.group(2)), float(m.group(3))
            ca, sa = math.cos(a), math.sin(a)
            self.ops.append("%s %s %s %s %s %s cm" % (
                _f(ca), _f(sa), _f(-sa), _f(ca),
                _f(px - (px * ca - py * sa)), _f(py - (px * sa + py * ca))))

        halo = colour(el.get("stroke"))
        fill = colour(el.get("fill")) or (0, 0, 0)
        body = "BT /%s %s Tf %s Tc 1 0 0 -1 %s %s Tm (%s) Tj ET" % (
            name, _f(size), _f(spacing), _f(x), _f(y), _esc(s))
        if halo is not None and el.get("paint-order") == "stroke":
            self.ops.append(_rgb(halo, True))
            self.ops.append("%s w 1 j" % _f(_num(el.get("stroke-width"), size * 0.34)))
            self.ops.append(body.replace("Tf", "Tf 1 Tr", 1))
        self.ops.append(_rgb(fill, False))
        self.ops.append(body.replace("Tf", "Tf 0 Tr", 1))
        self.ops.append("Q")

    # -- output ------------------------------------------------------------
    def content(self):
        head = "q %s 0 0 %s 0 %s cm" % (_f(self.scale), _f(-self.scale),
                                        _f(self.page_h * MM))
        return ("%s\n%s\nQ" % (head, "\n".join(self.ops))).encode("latin-1",
                                                                  "replace")

    def pattern_streams(self):
        """Each hatch as a PDF tiling pattern, converted the same way."""
        out = []
        for pid, name in self.used.items():
            el = self.patterns.get(pid)
            if el is None:
                continue
            w = _num(el.get("width"), 4.0)
            h = _num(el.get("height"), 4.0)
            sub = Converter._blank(self)
            sub._walk(el)
            ang = 0.0
            m = re.search(r"rotate\(\s*(-?[\d.]+)", el.get("patternTransform", ""))
            if m:
                ang = math.radians(float(m.group(1)))
            c, s = math.cos(ang), math.sin(ang)
            k = self.scale
            matrix = [c * k, -s * k, -s * k, -c * k, 0.0, self.page_h * MM]
            out.append({"name": name, "bbox": (0, 0, w, h), "step": (w, h),
                        "matrix": matrix,
                        "content": "\n".join(sub.ops).encode("latin-1", "replace"),
                        "fonts": sub.fonts})
        return out

    @classmethod
    def _blank(cls, like):
        obj = cls.__new__(cls)
        obj.width, obj.height = like.width, like.height
        obj.page_w, obj.page_h, obj.scale = like.page_w, like.page_h, like.scale
        obj.patterns, obj.clips, obj.used, obj.gs = {}, {}, {}, {}
        obj.fonts, obj.ops = set(), []
        return obj


# ---------------------------------------------------------------------------
# The file itself
# ---------------------------------------------------------------------------
class Document:
    """A minimal PDF writer: numbered objects, a cross-reference table, done."""

    def __init__(self, compress=True):
        self.objects = [None]                 # 1-based
        self.compress = compress

    def add(self, body):
        self.objects.append(body if isinstance(body, bytes)
                            else body.encode("latin-1", "replace"))
        return len(self.objects) - 1

    def reserve(self):
        self.objects.append(None)
        return len(self.objects) - 1

    def put(self, ref, body):
        self.objects[ref] = body if isinstance(body, bytes) \
            else body.encode("latin-1", "replace")

    def stream(self, data, extra=""):
        if self.compress:
            data = zlib.compress(data, 6)
            extra += " /Filter /FlateDecode"
        head = "<< /Length %d%s >>\nstream\n" % (len(data), extra)
        return self.add(head.encode("latin-1") + data + b"\nendstream")

    def render(self, root_ref, info_ref=None):
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * len(self.objects)
        for i in range(1, len(self.objects)):
            offsets[i] = len(out)
            out += ("%d 0 obj\n" % i).encode("latin-1")
            out += self.objects[i] or b"<< >>"
            out += b"\nendobj\n"
        start = len(out)
        out += ("xref\n0 %d\n" % len(self.objects)).encode("latin-1")
        out += b"0000000000 65535 f \n"
        for i in range(1, len(self.objects)):
            out += ("%010d 00000 n \n" % offsets[i]).encode("latin-1")
        trailer = "trailer\n<< /Size %d /Root %d 0 R" % (len(self.objects), root_ref)
        if info_ref:
            trailer += " /Info %d 0 R" % info_ref
        out += (trailer + " >>\nstartxref\n%d\n%%%%EOF\n" % start).encode("latin-1")
        return bytes(out)


def _pdf_string(s):
    return "(%s)" % _esc(s or "")


def write(svgs, out_path, title=None, author=None, subject=None):
    """A list of SVG documents (strings or paths) as one PDF.

    Page size follows each sheet, so an A1 set prints at A1 and a stray A3
    stays A3."""
    doc = Document()
    font_refs = {}
    for name, base in FONT_NAMES.items():
        font_refs[name] = doc.add(
            "<< /Type /Font /Subtype /Type1 /BaseFont /%s "
            "/Encoding /WinAnsiEncoding >>" % base)

    pages_ref = doc.reserve()
    page_refs = []
    for item in svgs:
        svg = item
        if not str(item).lstrip().startswith("<"):
            with open(item) as fh:
                svg = fh.read()
        conv = Converter(svg)
        content_ref = doc.stream(conv.content())

        pat_refs = {}
        for pat in conv.pattern_streams():
            res = "<< /ProcSet [/PDF] >>"
            if pat["fonts"]:
                res = "<< /ProcSet [/PDF /Text] /Font << %s >> >>" % " ".join(
                    "/%s %d 0 R" % (n, font_refs[n]) for n in sorted(pat["fonts"]))
            data = pat["content"]
            if doc.compress:
                data = zlib.compress(data, 6)
            head = ("<< /Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 "
                    "/BBox [0 0 %s %s] /XStep %s /YStep %s /Resources %s "
                    "/Matrix [%s] /Length %d /Filter /FlateDecode >>\nstream\n"
                    % (_f(pat["bbox"][2]), _f(pat["bbox"][3]),
                       _f(pat["step"][0]), _f(pat["step"][1]), res,
                       " ".join(_f(v) for v in pat["matrix"]), len(data)))
            pat_refs[pat["name"]] = doc.add(
                head.encode("latin-1") + data + b"\nendstream")

        for name, sh in conv.shadings.items():
            stops = sh["stops"]
            if len(stops) == 2:
                fn = ("<< /FunctionType 2 /Domain [0 1] /C0 [%s] /C1 [%s] /N 1 >>"
                      % (" ".join(_f(v) for v in stops[0][1]),
                         " ".join(_f(v) for v in stops[1][1])))
            else:
                subs, bounds, encode = [], [], []
                for i in range(len(stops) - 1):
                    subs.append("<< /FunctionType 2 /Domain [0 1] /C0 [%s] "
                                "/C1 [%s] /N 1 >>"
                                % (" ".join(_f(v) for v in stops[i][1]),
                                   " ".join(_f(v) for v in stops[i + 1][1])))
                    encode.append("0 1")
                    if i:
                        bounds.append(_f(stops[i][0]))
                fn = ("<< /FunctionType 3 /Domain [0 1] /Functions [%s] "
                      "/Bounds [%s] /Encode [%s] >>"
                      % (" ".join(subs), " ".join(bounds), " ".join(encode)))
            pat_refs[name] = doc.add(
                "<< /Type /Pattern /PatternType 2 /Matrix [%s] /Shading "
                "<< /ShadingType 2 /ColorSpace /DeviceRGB /Coords [%s] "
                "/Function %s /Extend [true true] >> >>"
                % (" ".join(_f(v) for v in sh["matrix"]),
                   " ".join(_f(v) for v in sh["coords"]), fn))

        gs_refs = {}
        for (ca, CA), name in conv.gs.items():
            gs_refs[name] = doc.add(
                "<< /Type /ExtGState /ca %s /CA %s >>" % (_f(ca), _f(CA)))

        res = ["/ProcSet [/PDF /Text]"]
        used_fonts = conv.fonts | {f for p in conv.pattern_streams()
                                   for f in p["fonts"]}
        if used_fonts or True:
            res.append("/Font << %s >>" % " ".join(
                "/%s %d 0 R" % (n, font_refs[n]) for n in sorted(FONT_NAMES)))
        if pat_refs:
            res.append("/Pattern << %s >>" % " ".join(
                "/%s %d 0 R" % (n, r) for n, r in sorted(pat_refs.items())))
        if gs_refs:
            res.append("/ExtGState << %s >>" % " ".join(
                "/%s %d 0 R" % (n, r) for n, r in sorted(gs_refs.items())))

        page_refs.append(doc.add(
            "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %s %s] "
            "/Resources << %s >> /Contents %d 0 R >>"
            % (pages_ref, _f(conv.page_w * MM), _f(conv.page_h * MM),
               " ".join(res), content_ref)))

    doc.put(pages_ref, "<< /Type /Pages /Count %d /Kids [%s] >>"
            % (len(page_refs), " ".join("%d 0 R" % r for r in page_refs)))
    root = doc.add("<< /Type /Catalog /Pages %d 0 R /PageLayout /SinglePage >>"
                   % pages_ref)
    info = doc.add("<< /Title %s /Author %s /Subject %s /Producer (ArchiAI) >>"
                   % (_pdf_string(title or "Drawing set"),
                      _pdf_string(author or "ArchiAI"),
                      _pdf_string(subject or "")))
    data = doc.render(root, info)
    if hasattr(out_path, "write"):
        out_path.write(data)
        return out_path
    with open(out_path, "wb") as fh:
        fh.write(data)
    return out_path
