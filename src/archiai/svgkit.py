"""
A small drafting kit that writes ISO-style architectural sheets as plain SVG.

Units on the sheet are millimetres (the SVG viewBox is the paper size), so a
0.35 stroke really is a 0.35 mm pen.  Model space is metres; a `View` maps
metres onto the sheet at a stated scale.
"""

import math, os

# ---------------------------------------------------------------------------
# Paper, pens, type
# ---------------------------------------------------------------------------
PAPER = {
    "A0": (1189.0, 841.0), "A1": (841.0, 594.0), "A2": (594.0, 420.0),
    "A3": (420.0, 297.0),  "A4": (297.0, 210.0),
}

# ISO 128 pen weights, in mm
LW = {
    "grid":   0.13, "dim":  0.13, "hatch": 0.13, "fine": 0.18,
    "thin":   0.25, "med":  0.35, "heavy": 0.50, "cut":  0.70, "outline": 1.00,
}

INK   = "#111111"
GREY  = "#8a8a8a"
LIGHT = "#c9c9c9"
BLUE  = "#1c5fa8"     # grid, levels, references
RED   = "#b3261e"     # section marks, fire strategy
GREEN = "#2f6b3f"     # landscape
FONT  = "'Helvetica Neue',Helvetica,Arial,sans-serif"

DASH_GRID  = "6,2,1,2"
DASH_HID   = "3,2"
DASH_ABOVE = "8,3"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def f(v):
    """Trim floats so the SVG stays readable and small."""
    return ("%.3f" % v).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


# ---------------------------------------------------------------------------
# Sheet
# ---------------------------------------------------------------------------
class Sheet:
    TB_W = 180.0          # title block strip width
    MARGIN = 10.0

    def __init__(self, number, title, scale_text, paper="A1", subtitle="",
                 project=None, notes=None):
        self.w, self.h = PAPER[paper]
        self.paper = paper
        self.number, self.title, self.subtitle = number, title, subtitle
        self.scale_text = scale_text
        self.project = project or {}
        self.notes = notes or []
        self.body = []
        self.defs = []
        self._pat = set()

    # -- raw emit ----------------------------------------------------------
    def add(self, s):
        self.body.append(s)
        return self

    # -- geometry primitives (sheet mm) ------------------------------------
    def line(self, x1, y1, x2, y2, w="thin", color=INK, dash=None, cap="round", op=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        o = ' stroke-opacity="%s"' % f(op) if op is not None else ""
        self.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s" '
                 'stroke-linecap="%s"%s%s/>' % (f(x1), f(y1), f(x2), f(y2), color,
                                                f(LW.get(w, w)), cap, d, o))

    def path(self, d, w="thin", color=INK, fill="none", dash=None, op=None,
             cap="round", join="round", rule=None):
        da = ' stroke-dasharray="%s"' % dash if dash else ""
        o = ' fill-opacity="%s"' % f(op) if op is not None else ""
        fr = ' fill-rule="%s"' % rule if rule else ""
        sw = "" if w is None else ' stroke="%s" stroke-width="%s" stroke-linecap="%s" stroke-linejoin="%s"' % (
            color, f(LW.get(w, w)), cap, join)
        self.add('<path d="%s" fill="%s"%s%s%s%s/>' % (d, fill, o, fr, sw, da))

    def circle(self, cx, cy, r, w="thin", color=INK, fill="none", dash=None):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        sw = "" if w is None else ' stroke="%s" stroke-width="%s"' % (color, f(LW.get(w, w)))
        self.add('<circle cx="%s" cy="%s" r="%s" fill="%s"%s%s/>' % (
            f(cx), f(cy), f(r), fill, sw, d))

    def rect(self, x, y, w_, h_, w="thin", color=INK, fill="none", dash=None, rx=0):
        d = ' stroke-dasharray="%s"' % dash if dash else ""
        sw = "" if w is None else ' stroke="%s" stroke-width="%s"' % (color, f(LW.get(w, w)))
        r = ' rx="%s"' % f(rx) if rx else ""
        self.add('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"%s%s%s/>' % (
            f(x), f(y), f(w_), f(h_), fill, sw, d, r))

    def text(self, x, y, s, size=2.5, anchor="start", color=INK, weight="400",
             rot=None, spacing=None, family=FONT, italic=False, baseline=None,
             halo=None):
        tr = ' transform="rotate(%s %s %s)"' % (f(rot), f(x), f(y)) if rot else ""
        ls = ' letter-spacing="%s"' % f(spacing) if spacing else ""
        it = ' font-style="italic"' if italic else ""
        bl = ' dominant-baseline="%s"' % baseline if baseline else ""
        hl = ""
        if halo:
            hl = (' stroke="%s" stroke-width="%s" paint-order="stroke" '
                  'stroke-linejoin="round"' % (halo if isinstance(halo, str) else "#ffffff",
                                               f(size * 0.34)))
        self.add('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s" '
                 'font-weight="%s" text-anchor="%s"%s%s%s%s%s>%s</text>' % (
                     f(x), f(y), family, f(size), color, weight, anchor, tr, ls, it, bl,
                     hl, esc(s)))

    def textbox(self, x, y, lines, size=2.2, lead=1.45, anchor="start", color=INK, weight="400"):
        for i, ln in enumerate(lines):
            self.text(x, y + i * size * lead, ln, size, anchor, color, weight)

    def group(self, attrs=""):
        return _Group(self, attrs)

    def grid_pattern(self, name, size_mm, stroke="#c8ccd0", width=0.1, bg="none"):
        """A square grid at a given sheet size -- ceiling modules, paving, mesh."""
        if name not in self._pat:
            self._pat.add(name)
            rect = ('<rect width="%s" height="%s" fill="%s"/>' % (f(size_mm), f(size_mm), bg)) \
                if bg != "none" else ""
            self.defs.append(
                '<pattern id="%s" width="%s" height="%s" patternUnits="userSpaceOnUse">'
                '%s<path d="M0 0 H%s M0 0 V%s" stroke="%s" stroke-width="%s" fill="none"/>'
                '</pattern>' % (name, f(size_mm), f(size_mm), rect,
                                f(size_mm), f(size_mm), stroke, f(width)))
        return "url(#%s)" % name

    def clip(self, name, d):
        """Register a clip path from SVG path data and return its selector."""
        if name not in self._pat:
            self._pat.add(name)
            self.defs.append('<clipPath id="%s"><path d="%s"/></clipPath>' % (name, d))
        return "clip-path=\"url(#%s)\"" % name

    # -- hatch patterns ----------------------------------------------------
    def pattern(self, name):
        """Register (once) and return the url() for a named hatch pattern."""
        if name not in self._pat:
            self._pat.add(name)
            self.defs.append(_PATTERNS[name])
        return "url(#%s)" % name

    # -- output ------------------------------------------------------------
    def frame(self):
        m, W, H = self.MARGIN, self.w, self.h
        self.rect(0, 0, W, H, w=None, fill="#ffffff")
        self.rect(m, m, W - 2 * m, H - 2 * m, w="med", color=INK)
        self._titleblock()

    def _titleblock(self):
        m, W, H = self.MARGIN, self.w, self.h
        x0 = W - m - self.TB_W
        y0, y1 = m, H - m
        tw = self.TB_W
        self.line(x0, y0, x0, y1, w="med")
        P = self.project

        # -- studio identity
        cy = y0 + 8
        self.text(x0 + 8, cy + 4, "ARCHI", 8.5, color=INK, weight="700", spacing=1.2)
        self.text(x0 + 8 + 30.5, cy + 4, "AI", 8.5, color=BLUE, weight="700", spacing=1.2)
        self.text(x0 + 8, cy + 10.5, "DESIGN STUDIO", 2.4, color=GREY, weight="500", spacing=1.8)
        self.line(x0, y0 + 24, W - m, y0 + 24, w="thin")

        def field(y, label, value, size=3.0, weight="500", color=INK, lead=5.2):
            self.text(x0 + 8, y, label, 2.0, color=GREY, weight="600", spacing=0.9)
            if isinstance(value, str):
                value = [value]
            for i, v in enumerate(value):
                self.text(x0 + 8, y + 4.4 + i * lead, v, size, color=color, weight=weight)
            return y + 4.4 + max(1, len(value)) * lead

        y = y0 + 32
        y = field(y, "PROJECT", [P.get("name", ""), P.get("subtitle", "")], 5.5, "600") + 3
        self.line(x0, y - 4, W - m, y - 4, w="thin", color=LIGHT)
        y = field(y, "CLIENT", P.get("client", ""), 3.0) + 3
        self.line(x0, y - 4, W - m, y - 4, w="thin", color=LIGHT)
        ttl = _wrap(self.title, 24)
        y = field(y, "DRAWING TITLE", ttl, 4.6, "600") + 3
        if self.subtitle:
            self.text(x0 + 8, y - 2, self.subtitle, 2.4, color=GREY, weight="400")
            y += 3
        self.line(x0, y - 4, W - m, y - 4, w="thin", color=LIGHT)

        # -- notes
        if self.notes:
            self.text(x0 + 8, y, "NOTES", 2.0, color=GREY, weight="600", spacing=0.9)
            yy = y + 4.4
            for n in self.notes:
                for ln in _wrap(n, 40):
                    self.text(x0 + 8, yy, ln, 2.1, color=INK)
                    yy += 3.0
                yy += 1.0
            y = yy + 2
            self.line(x0, y - 4, W - m, y - 4, w="thin", color=LIGHT)

        # -- bottom data block
        by = y1 - 46
        self.line(x0, by, W - m, by, w="thin")
        cw = tw / 3.0
        cells = [("SCALE @ %s" % self.paper, self.scale_text),
                 ("STATUS", P.get("status", "").split("/")[0].strip()),
                 ("DATE", P.get("date", ""))]
        for i, (lab, val) in enumerate(cells):
            cx = x0 + i * cw
            if i:
                self.line(cx, by, cx, by + 14, w="thin", color=LIGHT)
            self.text(cx + 5, by + 5, lab, 1.9, color=GREY, weight="600", spacing=0.7)
            self.text(cx + 5, by + 10.5, val, 3.0, weight="500")
        self.line(x0, by + 14, W - m, by + 14, w="thin", color=LIGHT)

        self.text(x0 + 5, by + 21, "DRAWING NUMBER", 1.9, color=GREY, weight="600", spacing=0.7)
        self.text(x0 + 5, by + 31, "%s-%s" % (P.get("number", ""), self.number), 7.0, weight="700")
        self.text(W - m - 5, by + 31, "REV %s" % P.get("rev", ""), 4.4, anchor="end",
                  weight="600", color=BLUE)
        self.line(x0, by + 36, W - m, by + 36, w="thin", color=LIGHT)
        self.text(x0 + 5, by + 42, "Do not scale from this drawing. Figured dimensions govern.",
                  1.85, color=GREY)

    def save(self, path):
        defs = ""
        if self.defs:
            defs = "<defs>%s</defs>" % "".join(self.defs)
        out = ('<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
               'width="%smm" height="%smm" viewBox="0 0 %s %s">%s%s</svg>' % (
                   f(self.w), f(self.h), f(self.w), f(self.h), defs, "".join(self.body)))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(out)
        return path

    # -- drawing-area helpers ---------------------------------------------
    def area(self):
        """(x0, y0, x1, y1) of the usable drawing area, inside the title block."""
        m = self.MARGIN
        return (m, m, self.w - m - self.TB_W, self.h - m)

    def area_centre(self):
        x0, y0, x1, y1 = self.area()
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


class _Group:
    def __init__(self, sheet, attrs):
        self.s, self.a = sheet, attrs
    def __enter__(self):
        self.s.add("<g %s>" % self.a); return self.s
    def __exit__(self, *a):
        self.s.add("</g>")


def _wrap(s, n):
    words, lines, cur = str(s).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if len(t) > n and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------------------------------------------------------------------------
# Hatch / fill patterns
# ---------------------------------------------------------------------------
_PATTERNS = {
    "concrete": '<pattern id="concrete" width="2.2" height="2.2" patternUnits="userSpaceOnUse" '
                'patternTransform="rotate(45)"><rect width="2.2" height="2.2" fill="#e9e9e6"/>'
                '<line x1="0" y1="0" x2="0" y2="2.2" stroke="#9a9a95" stroke-width="0.12"/></pattern>',
    "insul":    '<pattern id="insul" width="3" height="3" patternUnits="userSpaceOnUse">'
                '<rect width="3" height="3" fill="#fdf6e3"/>'
                '<path d="M0 1.5 Q0.75 0 1.5 1.5 T3 1.5" fill="none" stroke="#c8b98a" stroke-width="0.13"/></pattern>',
    "screed":   '<pattern id="screed" width="1.4" height="1.4" patternUnits="userSpaceOnUse">'
                '<rect width="1.4" height="1.4" fill="#f2f2ef"/>'
                '<circle cx="0.7" cy="0.7" r="0.09" fill="#a5a59e"/></pattern>',
    "earth":    '<pattern id="earth" width="3.2" height="3.2" patternUnits="userSpaceOnUse" '
                'patternTransform="rotate(30)"><rect width="3.2" height="3.2" fill="#efeae2"/>'
                '<line x1="0" y1="0" x2="0" y2="3.2" stroke="#bcae99" stroke-width="0.12"/>'
                '<line x1="1.6" y1="0" x2="1.6" y2="3.2" stroke="#d8cfc0" stroke-width="0.1"/></pattern>',
    "steel":    '<pattern id="steel" width="1.1" height="1.1" patternUnits="userSpaceOnUse" '
                'patternTransform="rotate(45)"><rect width="1.1" height="1.1" fill="#d7dbe0"/>'
                '<line x1="0" y1="0" x2="0" y2="1.1" stroke="#6d7581" stroke-width="0.16"/></pattern>',
    "grass":    '<pattern id="grass" width="4" height="4" patternUnits="userSpaceOnUse">'
                '<rect width="4" height="4" fill="#eef3ea"/>'
                '<path d="M1 3 l0.5 -1 M2 3.4 l0.4 -0.9 M3 2.8 l0.5 -1" stroke="#9dbb96" '
                'stroke-width="0.14" fill="none"/></pattern>',
    "water":    '<pattern id="water" width="4" height="3" patternUnits="userSpaceOnUse">'
                '<rect width="4" height="3" fill="#e8f1f6"/>'
                '<path d="M0 1.5 Q1 0.7 2 1.5 T4 1.5" fill="none" stroke="#9dc2d8" stroke-width="0.15"/></pattern>',
    "paving":   '<pattern id="paving" width="6" height="6" patternUnits="userSpaceOnUse">'
                '<rect width="6" height="6" fill="#f4f3f0"/>'
                '<path d="M0 0 H6 M0 0 V6" stroke="#dcd9d2" stroke-width="0.13"/></pattern>',
}


# ---------------------------------------------------------------------------
# View: model metres -> sheet millimetres
# ---------------------------------------------------------------------------
class View:
    def __init__(self, sheet, scale, ox, oy, rot=0.0):
        """`scale` is the denominator: 200 means 1:200."""
        self.s = sheet
        self.scale = float(scale)
        self.k = 1000.0 / self.scale      # mm on sheet per metre of model
        self.ox, self.oy = ox, oy
        self.rot = math.radians(rot)

    def mm(self, metres):
        return metres * self.k

    def m(self, mm_):
        return mm_ / self.k

    def p(self, x, y):
        if self.rot:
            c, s = math.cos(self.rot), math.sin(self.rot)
            x, y = x * c - y * s, x * s + y * c
        return (self.ox + x * self.k, self.oy - y * self.k)

    # -- polar convenience -------------------------------------------------
    def pol(self, r, t_deg):
        a = math.radians(t_deg)
        return self.p(r * math.cos(a), r * math.sin(a))


def polar(r, t_deg):
    a = math.radians(t_deg)
    return (r * math.cos(a), r * math.sin(a))


# ---------------------------------------------------------------------------
# Path builders (model space -> SVG path data)
# ---------------------------------------------------------------------------
def d_arc(v, r, t0, t1, move=True):
    """Arc of radius r (metres) from t0 to t1 degrees, about the model origin."""
    seg, out = [], []
    span = t1 - t0
    n = max(1, int(math.ceil(abs(span) / 90.0)))
    step = span / n
    x, y = v.pol(r, t0)
    if move:
        out.append("M %s %s" % (f(x), f(y)))
    rr = v.mm(r)
    for i in range(n):
        a1 = t0 + step * (i + 1)
        x, y = v.pol(r, a1)
        # SVG y is inverted relative to model y, so CCW in model = sweep 0
        sweep = 0 if step > 0 else 1
        large = 1 if abs(step) > 180 else 0
        out.append("A %s %s 0 %d %d %s %s" % (f(rr), f(rr), large, sweep, f(x), f(y)))
    return " ".join(out)


def d_ring(v, r0, r1, t0, t1):
    """Closed annular sector."""
    p0 = v.pol(r1, t0)
    d = ["M %s %s" % (f(p0[0]), f(p0[1]))]
    d.append(d_arc(v, r1, t0, t1, move=False))
    p1 = v.pol(r0, t1)
    d.append("L %s %s" % (f(p1[0]), f(p1[1])))
    d.append(d_arc(v, r0, t1, t0, move=False))
    d.append("Z")
    return " ".join(d)


def d_annulus(v, r0, r1):
    """Closed full annulus using the even-odd/nonzero trick (two circles)."""
    def circ(r, cw):
        rr = v.mm(r)
        x0, y0 = v.pol(r, 0)
        x1, y1 = v.pol(r, 180)
        s = 1 if cw else 0
        return "M %s %s A %s %s 0 1 %d %s %s A %s %s 0 1 %d %s %s Z" % (
            f(x0), f(y0), f(rr), f(rr), s, f(x1), f(y1), f(rr), f(rr), s, f(x0), f(y0))
    return circ(r1, False) + " " + circ(r0, True)


def d_poly(v, pts, close=False):
    out = []
    for i, (x, y) in enumerate(pts):
        px, py = v.p(x, y)
        out.append(("M" if i == 0 else "L") + " %s %s" % (f(px), f(py)))
    if close:
        out.append("Z")
    return " ".join(out)


def d_poly_mm(pts, close=False):
    out = []
    for i, (x, y) in enumerate(pts):
        out.append(("M" if i == 0 else "L") + " %s %s" % (f(x), f(y)))
    if close:
        out.append("Z")
    return " ".join(out)
