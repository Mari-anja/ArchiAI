"""Doors and windows: where they are, what type, and how many.

Both are derived from the plan rather than invented. A door exists because a
room is enclosed and has to be reached from a corridor; a window exists
because the facade has a structural bay. Counting them is then just counting.
"""

import math
from . import geom2d as G
from .layout import nearest_on_ring

# Rooms that get a door. Workspace is open plan and reached directly from the
# circulation, so it does not.
ENCLOSED = ("meet", "plant", "core", "amenity")

DOOR_TYPES = [
    ("D1", "Single leaf, timber, paint finish", 926, 2040, "—", "Internal"),
    ("D2", "Double leaf, timber, paint finish", 1852, 2040, "—", "Internal"),
    ("D3", "Single leaf, FD30S, self-closing", 926, 2040, "FD30S", "Store, plant"),
    ("D4", "Double leaf, FD60S, self-closing", 1852, 2040, "FD60S", "Stair core"),
    ("D5", "Automatic sliding, glazed", 2400, 2400, "—", "Main entrance"),
]

REVEAL = 0.85          # from the structural bay line to the frame
SILL = 0.95
HEAD_GAP = 0.75


class Opening:
    __slots__ = ("mark", "point", "normal", "room", "width", "height")

    def __init__(self, mark, point, normal, room, width, height):
        self.mark, self.point, self.normal = mark, point, normal
        self.room, self.width, self.height = room, width, height


# ---------------------------------------------------------------------------
def _door_mark(room):
    if room.cat == "core":
        return "D4"
    if room.cat == "plant":
        return "D3"
    if room.area > 60.0:
        return "D2"
    return "D1"


def door_position(room, circ_rings, max_edges=16):
    """Put the door on the wall closest to a corridor, facing into the room."""
    ring = room.ring
    n = len(ring)
    step = max(1, n // max_edges)
    best, best_d = None, 1e18
    for k in range(0, n, step):
        a, b = ring[k], ring[(k + 1) % n]
        if math.dist(a, b) < 1.1:
            continue
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        d = 1e18
        for cr in circ_rings:
            hit = nearest_on_ring(mid, cr)
            if hit and hit[3] < d:
                d = hit[3]
        if d < best_d:
            nx, ny = G._edge_normal(a, b)
            best, best_d = (mid, (-nx, -ny)), d
    return best


def doors(project, level_index):
    """Every door on a level, positioned and marked."""
    fp = project.floorplans[level_index]
    circ_rings = []
    for c in fp.circulation:
        circ_rings += [G.resample(r, 2.0) for r in c.rings]
    if not circ_rings:
        circ_rings = [G.resample(fp.plate.outer, 2.0)]

    out = []
    for r in fp.rooms:
        if r.cat not in ENCLOSED:
            continue
        pos = door_position(r, circ_rings)
        if not pos:
            continue
        mark = _door_mark(r)
        spec = next(t for t in DOOR_TYPES if t[0] == mark)
        out.append(Opening(mark, pos[0], pos[1], r, spec[2] / 1000.0,
                           spec[3] / 1000.0))
        if r.cat == "core":                    # a stair needs two, side by side
            # Offset along the wall, then put it back on the wall: a small
            # core has a short wall, and a fixed offset walks the second door
            # straight off the end of it.
            tx, ty = -pos[1][1], pos[1][0]
            off = spec[2] / 1000.0 / 2.0 + 0.80
            for k in (1.0, 0.6, 0.35, -1.0, -0.6, -0.35):
                p = (pos[0][0] + tx * off * k, pos[0][1] + ty * off * k)
                hit = nearest_on_ring(p, r.ring)
                if not hit or hit[3] >= 0.04:
                    continue
                # Round a corner the wall faces a different way, so take the
                # normal of the edge the door actually landed on.
                a, b = r.ring[hit[1]], r.ring[(hit[1] + 1) % len(r.ring)]
                nx, ny = G._edge_normal(a, b)
                out.append(Opening("D3", hit[0], (-nx, -ny), r, 0.926, 2.04))
                break
    if level_index == 0:
        az = math.radians(project.brief.entrance_azimuth)
        x0, y0, x1, y1 = fp.plate.bbox()
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rad = max(x1 - x0, y1 - y0) / 2.0
        p = (cx + math.cos(az) * rad, cy + math.sin(az) * rad)
        hit = nearest_on_ring(p, G.resample(fp.plate.outer, 1.5))
        if hit:
            out.append(Opening("D5", hit[0], (-math.cos(az), -math.sin(az)),
                               None, 2.4, 2.4))
    return out


# ---------------------------------------------------------------------------
MODULE = 1.60          # target curtain wall module width
CURTAIN_MIN = 3.0      # a clear bay wider than this is glazed as curtain walling


def _split(clear):
    """A clear bay divided into equal glazed modules."""
    if clear < CURTAIN_MIN:
        return 1, clear
    n = max(2, int(math.ceil(clear / MODULE)))
    return n, clear / n


ELEV = {270.0: "South", 0.0: "East", 90.0: "North", 180.0: "West"}


def _window_rows(project):
    """(width, height, curtain) -> {elevation: count}, straight off the bays."""
    from .draw import facade_bays
    m = project.massing
    rows = {}
    for az, label in ELEV.items():
        bays = facade_bays(project, az)
        if len(bays) < 2:
            continue
        for i, lv in enumerate(m.levels):
            top = (m.levels[i + 1].ffl if i + 1 < len(m.levels)
                   else getattr(m, "top", m.height))
            h = round(top - lv.ffl - SILL - HEAD_GAP, 2)
            if h < 0.6:
                continue
            for k in range(len(bays) - 1):
                clear = bays[k + 1] - bays[k] - 2 * REVEAL
                if clear < 0.5:
                    continue
                n, w = _split(clear)
                key = (round(w, 1), round(h, 1), n > 1)
                rows.setdefault(key, {})
                rows[key][label] = rows[key].get(label, 0) + n
    return rows


def _marked(rows):
    """Rows in schedule order, each carrying its mark."""
    out = []
    ordered = sorted(rows.items(),
                     key=lambda kv: (-sum(kv[1].values()), kv[0]))
    for i, ((w, h, curtain), by_elev) in enumerate(ordered):
        out.append(((w, h, curtain), "%s%d" % ("CW" if curtain else "W", i + 1),
                    by_elev))
    return out


def windows(project):
    """Windows per elevation, from the structural bays of the facade.

    A narrow bay becomes one punched window. A wide bay is glazed as curtain
    walling and divided into equal modules, because that is how a facade of
    that span is actually built."""
    out = []
    for ((w, h, curtain), mark, by_elev) in _marked(_window_rows(project)):
        out.append({
            "mark": mark,
            "width_mm": int(round(w * 1000)), "height_mm": int(round(h * 1000)),
            "count": sum(by_elev.values()),
            "type": "Curtain wall module, capped mullion" if curtain
                    else "Aluminium composite casement",
            "glazing": "Double, low-e, argon, Ug 1.1",
            "note": "Opening light at alternate modules" if curtain
                    else "Openable vent to every third bay",
        })
    return out


def window_matrix(project):
    """[(mark, {elevation: count}), ...] in the same order as windows()."""
    return [(mark, by_elev)
            for (_, mark, by_elev) in _marked(_window_rows(project))]


def door_matrix(project):
    """[(mark, {level name: count}), ...] in schedule order."""
    per = {}
    for i, lv in enumerate(project.massing.levels):
        for d in doors(project, i):
            per.setdefault(d.mark, {})
            per[d.mark][lv.name] = per[d.mark].get(lv.name, 0) + 1
    return [(mark, per[mark]) for (mark, *_) in DOOR_TYPES if mark in per]


def door_schedule(project):
    """Doors totalled by type across every level."""
    counts, where = {}, {}
    for i in range(len(project.massing.levels)):
        for d in doors(project, i):
            counts[d.mark] = counts.get(d.mark, 0) + 1
            where.setdefault(d.mark, set()).add(project.massing.levels[i].name)
    out = []
    for (mark, desc, w, h, fire, use) in DOOR_TYPES:
        if mark not in counts:
            continue
        out.append({"mark": mark, "description": desc, "width_mm": w,
                    "height_mm": h, "fire": fire, "use": use,
                    "count": counts[mark],
                    "levels": len(where.get(mark, ()))})
    return out


def totals(project):
    d = door_schedule(project)
    w = windows(project)
    return {"door_types": len(d), "doors": sum(x["count"] for x in d),
            "window_types": len(w), "windows": sum(x["count"] for x in w),
            "glazed_area_m2": round(sum(
                x["count"] * x["width_mm"] * x["height_mm"] / 1e6 for x in w), 1)}
