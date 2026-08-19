"""Assemble a single-file project page: the live model plus the whole drawing set."""

import base64, math, os
from . import params as P
from . import program as PG
from . import viewer
from .sheets import REGISTER

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "assets", "page.html")


def _data_uri(path):
    with open(path, "rb") as fh:
        return "data:image/svg+xml;base64," + base64.b64encode(fh.read()).decode("ascii")


def _sheets(drawings_dir):
    out = []
    for (num, title, scale, size) in REGISTER:
        path = os.path.join(drawings_dir, "%s-%s.svg" % (P.PROJECT["number"], num))
        if not os.path.exists(path):
            continue
        out.append({"id": "%s-%s" % (P.PROJECT["number"], num), "title": title,
                    "scale": scale, "src": _data_uri(path)})
    return out


# ---------------------------------------------------------------------------
def section_diagram():
    """The generating section, drawn to the page's own colour tokens."""
    K, OX, OY = 16.6, 192.0, 236.0          # px per metre, origin of z = 0
    W, H = 384.0, 300.0

    def p(x, z):
        return (OX + x * K, OY - z * K)

    def tube(phi, r=P.TUBE_R):
        a = math.radians(phi)
        return (r * math.cos(a), P.TUBE_Z + r * math.sin(a))

    def arc(p0, p1, r=P.TUBE_R, n=90):
        pts = [p(*tube(p0 + (p1 - p0) * i / n, r)) for i in range(n + 1)]
        return "M " + " L ".join("%.2f %.2f" % q for q in pts)

    o = ['<svg viewBox="0 0 %g %g" role="img" aria-label="Generating section of the torus">'
         % (W, H)]
    A = o.append

    # ghost of the whole generating circle, including the part below ground
    cx, cy = p(0, P.TUBE_Z)
    A('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="none" stroke="var(--rule)" '
      'stroke-width="1" stroke-dasharray="3 3"/>' % (cx, cy, P.TUBE_R * K))
    # ground
    A('<line x1="14" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--ink)" stroke-width="1.6"/>'
      % (OY, W - 14, OY))
    for i in range(26):
        x = 16 + i * 14
        A('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--faint)" '
          'stroke-width=".7"/>' % (x, OY, x - 5, OY + 6))
    # the shell itself
    A('<path d="%s" fill="var(--accent-soft)" stroke="none" opacity=".65"/>'
      % (arc(P.PHI_SPRING_OUT, P.PHI_SPRING_IN) + " Z"))
    A('<path d="%s" fill="none" stroke="var(--ink)" stroke-width="2.4" '
      'stroke-linecap="round"/>' % arc(P.PHI_SPRING_OUT, P.PHI_SPRING_IN))
    # the two plates
    for z, lab in ((P.FFL_00, "+0.000"), (P.FFL_01, "+4.200")):
        a, b = p(-P.HALF_CHORD_00, z), p(P.HALF_CHORD_00, z)
        A('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--ink)" '
          'stroke-width="2.4"/>' % (a[0], a[1], b[0], b[1]))
        A('<text x="%.2f" y="%.2f" font-family="var(--mono),monospace" font-size="9" '
          'fill="var(--faint)" text-anchor="start">%s</text>' % (b[0] + 7, b[1] + 3, lab))
    # tube axis
    A('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--accent)" '
      'stroke-width=".9" stroke-dasharray="7 3 2 3"/>' % (p(-8.6, P.TUBE_Z)[0],
      p(0, P.TUBE_Z)[1], p(8.6, P.TUBE_Z)[0], p(0, P.TUBE_Z)[1]))
    A('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--accent)" '
      'stroke-width=".9" stroke-dasharray="7 3 2 3"/>' % (cx, p(0, -0.9)[1], cx,
      p(0, 10.6)[1]))
    A('<circle cx="%.2f" cy="%.2f" r="2.4" fill="var(--accent)"/>' % (cx, cy))

    # section angles
    for phi, lab, dx, dy, anchor in ((0.0, "φ 0°", 9, -6, "start"),
                                     (90.0, "φ 90°", 0, -8, "middle"),
                                     (180.0, "φ 180°", -9, 4, "end")):
        q = p(*tube(phi))
        A('<circle cx="%.2f" cy="%.2f" r="2.1" fill="var(--accent)"/>' % q)
        A('<text x="%.2f" y="%.2f" font-family="var(--mono),monospace" font-size="9.5" '
          'fill="var(--accent)" text-anchor="%s">%s</text>' % (q[0] + dx, q[1] + dy,
                                                               anchor, lab))
    for phi, lab, anchor, dx in ((P.PHI_SPRING_OUT, "φ −16.26°", "start", 8),
                                 (P.PHI_SPRING_IN, "φ 196.26°", "end", -8)):
        q = p(*tube(phi))
        A('<circle cx="%.2f" cy="%.2f" r="2.1" fill="var(--mark)"/>' % q)
        A('<text x="%.2f" y="%.2f" font-family="var(--mono),monospace" font-size="9" '
          'fill="var(--mark)" text-anchor="%s">%s</text>' % (q[0] + dx, q[1] + 13,
                                                             anchor, lab))

    # figured dimensions
    def dim_h(x0, x1, z, off, txt):
        a, b = p(x0, z), p(x1, z)
        y = a[1] + off
        A('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--graphite)" '
          'stroke-width=".8"/>' % (a[0], y, b[0], y))
        for q in (a, b):
            A('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--graphite)" '
              'stroke-width=".8"/>' % (q[0], y - 3.4, q[0], y + 3.4))
        A('<text x="%.2f" y="%.2f" font-family="var(--mono),monospace" font-size="9.5" '
          'fill="var(--graphite)" text-anchor="middle">%s</text>'
          % ((a[0] + b[0]) / 2, y - 5, txt))

    dim_h(-P.HALF_CHORD_00, P.HALF_CHORD_00, 0, 30, "14 400")
    a, b = p(-8.4, 0), p(-8.4, P.Z_APEX)
    A('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--graphite)" '
      'stroke-width=".8"/>' % (a[0], a[1], b[0], b[1]))
    for q in (a, b):
        A('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="var(--graphite)" '
          'stroke-width=".8"/>' % (q[0] - 3.4, q[1], q[0] + 3.4, q[1]))
    A('<text x="%.2f" y="%.2f" font-family="var(--mono),monospace" font-size="9.5" '
      'fill="var(--graphite)" text-anchor="middle" transform="rotate(-90 %.2f %.2f)">'
      '9 600</text>' % (a[0] - 6, (a[1] + b[1]) / 2, a[0] - 6, (a[1] + b[1]) / 2))
    A('<text x="%.2f" y="%.2f" font-family="var(--mono),monospace" font-size="9" '
      'fill="var(--accent)" text-anchor="middle">R 7 500 · axis at R 30 000, +2.100</text>'
      % (cx, p(0, 11.5)[1]))
    A("</svg>")
    return "".join(o)


# ---------------------------------------------------------------------------
def write(path, drawings_dir="output/drawings"):
    with open(TEMPLATE) as fh:
        html = fh.read()
    with open(os.path.join(HERE, "assets", "viewer.html")) as fh:
        vsrc = fh.read()
    i = vsrc.index("<script>")
    script = vsrc[i:vsrc.index("</script>", i) + len("</script>")]
    script = script.replace("__PARAMS__", __import__("json").dumps(
        viewer.params(), separators=(",", ":")))

    sheets = _sheets(drawings_dir)
    html = html.replace("__SECTION_SVG__", section_diagram())
    html = html.replace("__SHEETS__", __import__("json").dumps(sheets, separators=(",", ":")))
    html = html.replace("__VIEWER_SCRIPT__", script)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(html)
    return path
