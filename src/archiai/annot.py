"""Annotation conventions: dimensions, gridlines, tags, symbols, legends."""

import math
from .svgkit import (LW, INK, GREY, LIGHT, BLUE, RED, GREEN, FONT, f, d_arc,
                     d_poly_mm, DASH_GRID, polar)

TICK = 1.6          # length of the oblique dimension tick, mm


# ---------------------------------------------------------------------------
# Text orientation helpers
# ---------------------------------------------------------------------------
def rot_radial(theta):
    r = -theta
    while r > 90:  r -= 180
    while r <= -90: r += 180
    return r

def rot_tangent(theta):
    r = -theta - 90
    while r > 90:  r -= 180
    while r <= -90: r += 180
    return r

def text_polar(s, v, r, theta, txt, size=2.4, mode="tangent", anchor="middle",
               color=INK, weight="400", spacing=None):
    x, y = v.pol(r, theta)
    rot = rot_tangent(theta) if mode == "tangent" else (rot_radial(theta) if mode == "radial" else 0)
    s.text(x, y, txt, size, anchor, color, weight, rot=rot, spacing=spacing,
           baseline="middle", halo="#ffffff")


# ---------------------------------------------------------------------------
# Linear dimension (model coordinates)
# ---------------------------------------------------------------------------
def dim_linear(s, v, p1, p2, offset, text=None, size=2.2, color=INK,
               witness=True, gap=1.2, ext=1.5, above=1.3):
    """Dimension between two model points.  `offset` is in sheet mm, measured
    along the left-hand normal of the p1->p2 direction."""
    (x1, y1), (x2, y2) = v.p(*p1), v.p(*p2)
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return
    ux, uy = dx / L, dy / L
    nx, ny = uy, -ux                       # left normal, screen space
    ax, ay = x1 + nx * offset, y1 + ny * offset
    bx, by = x2 + nx * offset, y2 + ny * offset

    if witness:
        sgn = 1.0 if offset >= 0 else -1.0
        for (px, py), (qx, qy) in (((x1, y1), (ax, ay)), ((x2, y2), (bx, by))):
            s.line(px + nx * gap * sgn, py + ny * gap * sgn,
                   qx + nx * ext * sgn, qy + ny * ext * sgn, w="dim", color=color)

    s.line(ax, ay, bx, by, w="dim", color=color)
    tx, ty = (ux + nx) * TICK / 2.0, (uy + ny) * TICK / 2.0
    for (px, py) in ((ax, ay), (bx, by)):
        s.line(px - tx, py - ty, px + tx, py + ty, w="dim", color=color)

    if text is None:
        text = "%d" % round(math.dist(p1, p2) * 1000)
    rot = math.degrees(math.atan2(dy, dx))
    if rot > 90:
        rot -= 180
    elif rot <= -90:
        rot += 180
    rr = math.radians(rot)
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    s.text(mx + math.sin(rr) * above, my - math.cos(rr) * above,
           text, size, "middle", color, "500", rot=rot, halo="#ffffff")


def dim_chain(s, v, pts, offset, size=2.2, color=INK, total=False, total_off=7.0):
    for a, b in zip(pts, pts[1:]):
        dim_linear(s, v, a, b, offset, size=size, color=color)
    if total and len(pts) > 2:
        dim_linear(s, v, pts[0], pts[-1], offset + total_off, size=size, color=color)


def dim_radial_chain(s, v, radii, theta, offset=0.0, size=2.2, color=INK, total=True):
    """Chain of dimensions along a radial line -- the natural way to dimension
    a ring building."""
    pts = [polar(r, theta) for r in radii]
    dim_chain(s, v, pts, offset, size=size, color=color, total=total)


def dim_diameter(s, v, r, theta, text=None, size=2.6, color=INK, frac=0.72):
    """Diameter dimension across the plan.  `frac` slides the text along the
    line so several diameters on one drawing do not pile up at the centre."""
    a = v.pol(r, theta)
    b = v.pol(r, theta + 180)
    s.line(a[0], a[1], b[0], b[1], w="dim", color=color)
    for (px, py), sgn in ((a, 1), (b, -1)):
        ang = math.radians(-theta) + (0 if sgn > 0 else math.pi)
        _arrow(s, px, py, math.degrees(ang), color)
    mx = a[0] + (b[0] - a[0]) * frac
    my = a[1] + (b[1] - a[1]) * frac
    rot = rot_radial(theta)
    txt = text if text is not None else "Ø%d" % round(2 * r * 1000)
    rr = math.radians(rot)
    s.text(mx + math.sin(rr) * 2.0, my - math.cos(rr) * 2.0,
           txt, size, "middle", color, "600", rot=rot, halo="#ffffff")


def _arrow(s, x, y, ang_deg, color=INK, L=2.6, w=0.9):
    """Solid arrowhead at (x, y) pointing along `ang_deg` (screen degrees CCW)."""
    a = math.radians(ang_deg)
    bx, by = x - math.cos(a) * L, y + math.sin(a) * L
    px, py = math.sin(a) * w, math.cos(a) * w
    s.path(d_poly_mm([(x, y), (bx + px, by + py), (bx - px, by - py)], True),
           w=None, fill=color)


def dim_angular(s, v, r, t0, t1, text=None, size=2.1, color=BLUE):
    s.path(d_arc(v, r, t0, t1), w="dim", color=color)
    tm = (t0 + t1) / 2.0
    x, y = v.pol(r, tm)
    txt = text if text is not None else "%.1f°" % abs(t1 - t0)
    s.text(x, y, txt, size, "middle", color, "500", rot=rot_tangent(tm),
           baseline="middle", halo="#ffffff")


# ---------------------------------------------------------------------------
# Grid
# ---------------------------------------------------------------------------
def radial_grid(s, v, thetas, r0, r1, labels=None, bubble_r=4.2, color=BLUE,
                bubble_at=None, size=2.4, every_label=1):
    """Radial gridlines with bubbles at the outer end."""
    bubble_at = bubble_at if bubble_at is not None else r1 + v.m(9.0)
    for i, t in enumerate(thetas):
        a, b = v.pol(r0, t), v.pol(bubble_at - v.m(bubble_r + 1.0), t)
        s.line(a[0], a[1], b[0], b[1], w="grid", color=color, dash=DASH_GRID)
        if labels and i % every_label == 0:
            cx, cy = v.pol(bubble_at, t)
            s.circle(cx, cy, bubble_r, w="grid", color=color, fill="#ffffff")
            s.text(cx, cy + 0.85, labels[i], size, "middle", color, "600")


def ring_grid(s, v, radii, labels=None, color=BLUE, t_label=None, bubble_r=4.2,
              t0=0.0, t1=360.0, size=2.4):
    for i, r in enumerate(radii):
        s.path(d_arc(v, r, t0, t1), w="grid", color=color, dash=DASH_GRID)
    if labels and t_label is not None:
        for i, r in enumerate(radii):
            cx, cy = v.pol(r, t_label)
            s.circle(cx, cy, bubble_r, w="grid", color=color, fill="#ffffff")
            s.text(cx, cy + 0.85, labels[i], size, "middle", color, "600")


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------
def north_arrow(s, cx, cy, r=11.0, color=INK):
    s.circle(cx, cy, r, w="thin", color=color)
    s.path(d_poly_mm([(cx, cy - r * 0.86), (cx + r * 0.30, cy + r * 0.55),
                      (cx, cy + r * 0.24)], True), w=None, fill=color)
    s.path(d_poly_mm([(cx, cy - r * 0.86), (cx - r * 0.30, cy + r * 0.55),
                      (cx, cy + r * 0.24)], True), w="fine", color=color, fill="#ffffff")
    s.text(cx, cy - r - 2.4, "N", 3.6, "middle", color, "700")


def scale_bar(s, v, x, y, total_m=20, div=4, h=2.2, color=INK, label=None):
    seg = v.mm(total_m / div)
    for i in range(div):
        s.rect(x + i * seg, y, seg, h, w="fine", color=color,
               fill=(color if i % 2 == 0 else "#ffffff"))
    for i in range(div + 1):
        s.text(x + i * seg, y + h + 3.4, "%g" % (total_m / div * i), 2.1, "middle", color)
    s.text(x + v.mm(total_m) + 3.0, y + h + 3.4, "m", 2.1, "start", color)
    if label:
        s.text(x, y - 2.0, label, 2.3, "start", color, "600")


def level_tag(s, x, y, value, label=None, color=BLUE, size=2.4, anchor="start", flip=False):
    d = -1 if flip else 1
    s.path(d_poly_mm([(x, y), (x + 2.2 * d, y - 2.2), (x - 2.2 * d, y - 2.2)], True),
           w="fine", color=color, fill="#ffffff")
    s.line(x - 12 * d, y, x + 12 * d, y, w="fine", color=color)
    txt = "+%.3f" % value if value >= 0 else "%.3f" % value
    s.text(x + 3.4 * d, y - 3.2, txt, size, anchor, color, "600")
    if label:
        s.text(x + 3.4 * d, y - 6.6, label, size - 0.4, anchor, color, "400")


def section_mark(s, p1, p2, tag="A", color=RED, size=3.2, tail=9.0):
    """Full-width section line with heads at both ends (sheet mm)."""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    nx, ny = uy, -ux
    s.line(x1, y1, x2, y2, w="med", color=color, dash="14,3,3,3")
    for (px, py), (dxs, dys) in (((x1, y1), (-ux, -uy)), ((x2, y2), (ux, uy))):
        ex, ey = px + dxs * tail, py + dys * tail
        s.line(px, py, ex, ey, w="med", color=color)
        s.circle(ex + dxs * 4.6, ey + dys * 4.6, 4.6, w="med", color=color, fill="#ffffff")
        s.text(ex + dxs * 4.6, ey + dys * 4.6 + 1.15, tag, size, "middle", color, "700")
        # direction-of-view flag
        fx, fy = ex + dxs * 4.6, ey + dys * 4.6
        s.path(d_poly_mm([(fx + nx * 4.6, fy + ny * 4.6),
                          (fx + nx * 4.6 + dxs * 3.4, fy + ny * 4.6 + dys * 3.4),
                          (fx + nx * 7.2, fy + ny * 7.2)], True), w=None, fill=color)


def elev_mark(s, x, y, tag, dir_deg=0, color=RED, r=4.6):
    s.circle(x, y, r, w="med", color=color, fill="#ffffff")
    s.text(x, y + 1.15, tag, 3.2, "middle", color, "700")
    a = math.radians(dir_deg)
    s.path(d_poly_mm([(x + math.cos(a) * r, y - math.sin(a) * r),
                      (x + math.cos(a) * (r + 4.0) - math.sin(a) * 2.4,
                       y - math.sin(a) * (r + 4.0) - math.cos(a) * 2.4),
                      (x + math.cos(a) * (r + 4.0) + math.sin(a) * 2.4,
                       y - math.sin(a) * (r + 4.0) + math.cos(a) * 2.4)], True),
           w=None, fill=color)


def room_tag(s, v, r, theta, name, area=None, code=None, size=2.5, color=INK,
             mode="tangent", sub=None):
    x, y = v.pol(r, theta)
    rot = rot_tangent(theta) if mode == "tangent" else rot_radial(theta)
    dy = 0.0
    lines = [(name, size, "600")]
    if sub:
        lines.append((sub, size - 0.6, "400"))
    if area:
        lines.append(("%s m²" % area, size - 0.6, "400"))
    n = len(lines)
    y0 = -(n - 1) * (size * 1.25) / 2.0
    rr = math.radians(rot)
    for i, (txt, sz, wt) in enumerate(lines):
        off = y0 + i * size * 1.25
        px = x - math.sin(rr) * off
        py = y + math.cos(rr) * off
        s.text(px, py, txt, sz, "middle", color if i == 0 else GREY, wt, rot=rot,
               baseline="middle", halo="#ffffff")


def leader(s, v, from_rt, to_xy_mm, text, size=2.2, color=INK, anchor="start", dot=True):
    x0, y0 = v.pol(*from_rt)
    x1, y1 = to_xy_mm
    s.line(x0, y0, x1, y1, w="dim", color=color)
    s.line(x1, y1, x1 + (6 if anchor == "start" else -6), y1, w="dim", color=color)
    if dot:
        s.circle(x0, y0, 0.55, w=None, fill=color)
    s.text(x1 + (7 if anchor == "start" else -7), y1 + 0.9, text, size, anchor, color)


def legend(s, x, y, items, title="LEGEND", size=2.2, sw=6.0, gap=4.4, color=INK):
    s.text(x, y, title, 2.4, "start", GREY, "700", spacing=1.0)
    yy = y + 5.5
    for it in items:
        kind = it.get("kind", "fill")
        if kind == "fill":
            s.rect(x, yy - 2.6, sw, 3.4, w="fine", color=it.get("stroke", INK),
                   fill=it.get("fill", "#ffffff"))
        elif kind == "line":
            s.line(x, yy - 0.9, x + sw, yy - 0.9, w=it.get("w", "thin"),
                   color=it.get("stroke", INK), dash=it.get("dash"))
        elif kind == "dot":
            s.circle(x + sw / 2, yy - 0.9, 1.3, w="fine", color=it.get("stroke", INK),
                     fill=it.get("fill", "#ffffff"))
        s.text(x + sw + 3.2, yy, it["label"], size, "start", color)
        yy += gap
    return yy


def notes_block(s, x, y, title, lines, size=2.2, lead=3.3, width=None, color=INK):
    s.text(x, y, title, 2.4, "start", GREY, "700", spacing=1.0)
    yy = y + 5.4
    for ln in lines:
        s.text(x, yy, ln, size, "start", color)
        yy += lead
    return yy


def key_plan(s, cx, cy, r, highlight=None, label="KEY PLAN", color=INK):
    """Small circular key diagram; `highlight` is a list of (t0,t1) sectors."""
    s.circle(cx, cy, r, w="thin", color=GREY)
    s.circle(cx, cy, r * 0.60, w="thin", color=GREY)
    if highlight:
        for (t0, t1) in highlight:
            n = max(2, int(abs(t1 - t0) / 5))
            pts = []
            for i in range(n + 1):
                t = math.radians(t0 + (t1 - t0) * i / n)
                pts.append((cx + math.cos(t) * r, cy - math.sin(t) * r))
            for i in range(n, -1, -1):
                t = math.radians(t0 + (t1 - t0) * i / n)
                pts.append((cx + math.cos(t) * r * 0.60, cy - math.sin(t) * r * 0.60))
            s.path(d_poly_mm(pts, True), w=None, fill=BLUE, op=0.85)
    s.text(cx, cy + r + 4.4, label, 2.1, "middle", GREY, "700", spacing=0.8)
