"""Building services, computed rather than decorated.

Every layout here comes from a sizing rule an engineer would recognise: lux
levels against a lumen method, fresh air against occupancy, sprinkler heads
against a coverage limit. The numbers are concept-stage -- they are what an
architect coordinates with before a services engineer designs the real thing --
and each sheet says so on its face.
"""

import math
from . import geom2d as G


# ---------------------------------------------------------------------------
# Design criteria, by room category
# ---------------------------------------------------------------------------
LUX = {"work": 500, "meet": 500, "recep": 300, "amenity": 200,
       "circ": 150, "core": 150, "plant": 200, "void": 0}

# m2 per person, for fresh air and occupancy
DENSITY = {"work": 10.0, "meet": 3.0, "recep": 10.0, "amenity": 5.0,
           "circ": 0.0, "core": 0.0, "plant": 0.0, "void": 0.0}

FRESH_AIR_LPS = 10.0          # litres/second/person
TERMINAL_LPS = 60.0           # capacity of one supply diffuser

LUMINAIRE_LUMENS = 4800.0     # 600 x 600 LED panel
UTILISATION = 0.70
MAINTENANCE = 0.90
LUMINAIRE_EFFECTIVE = LUMINAIRE_LUMENS * UTILISATION * MAINTENANCE

SPRINKLER_COVERAGE = 12.0     # m2 per head, ordinary hazard
SPRINKLER_MAX_SPACING = 4.6   # m
DETECTOR_COVERAGE = 100.0     # m2 per smoke detector
SOCKET_SPACING = 3.5          # m along the perimeter
FLOOR_BOX_GRID = 3.6          # m
CEILING_MODULE = 0.6          # m

ESCAPE_LIMIT_TWO_WAY = 45.0   # m, more than one direction of travel
ESCAPE_LIMIT_ONE_WAY = 18.0   # m, single direction
ROUTE_FACTOR = 1.30           # straight line to walked distance, concept stage


# ---------------------------------------------------------------------------
# Placement helpers
# ---------------------------------------------------------------------------
def grid_in_ring(ring, spacing, inset=0.5, phase=0.5):
    """Points on a regular grid that fall inside a room, inset from its walls."""
    inner = G.offset_ring(ring, -inset) if inset else ring
    if len(inner) < 3 or G.area(inner) < 1e-6:
        inner = ring
    x0, y0, x1, y1 = G.bbox(inner)
    pts = []
    nx = max(1, int(round((x1 - x0) / spacing)))
    ny = max(1, int(round((y1 - y0) / spacing)))
    for i in range(nx):
        for j in range(ny):
            p = (x0 + (i + phase) * (x1 - x0) / nx,
                 y0 + (j + phase) * (y1 - y0) / ny)
            if G.point_in_ring(p, inner):
                pts.append(p)
    return pts


def n_points_in_ring(ring, n, inset=0.5):
    """Roughly n points spread inside a room. Tightens the grid until it fits."""
    if n <= 0:
        return []
    a = G.area(ring)
    spacing = math.sqrt(max(a, 1.0) / n)
    for _ in range(14):
        pts = grid_in_ring(ring, spacing, inset)
        if len(pts) >= n:
            return _thin(pts, n)
        spacing *= 0.88
    return _thin(pts, n) if pts else [G.centroid(ring)]


def _thin(pts, n):
    if len(pts) <= n:
        return pts
    step = len(pts) / float(n)
    return [pts[int(i * step)] for i in range(n)]


def along_boundary(ring, spacing, inset=0.18, skip_short=1.2):
    """Points just inside the wall line, with the inward normal at each."""
    r = G.dedupe(ring)
    out = []
    n = len(r)
    for i in range(n):
        a, b = r[i], r[(i + 1) % n]
        seg = math.dist(a, b)
        if seg < skip_short:
            continue
        nx, ny = G._edge_normal(a, b)           # outward for a CCW ring
        inx, iny = -nx, -ny
        count = max(1, int(seg // spacing))
        for k in range(count):
            t = (k + 0.5) / count
            p = (a[0] + (b[0] - a[0]) * t + inx * inset,
                 a[1] + (b[1] - a[1]) * t + iny * inset)
            out.append((p, (inx, iny)))
    return out


# ---------------------------------------------------------------------------
# Per-room services
# ---------------------------------------------------------------------------
class RoomServices:
    """Everything one room needs, sized from its area and category."""

    __slots__ = ("room", "lux", "luminaires", "occupants", "airflow_lps",
                 "supply", "extract", "sockets", "data", "floor_boxes",
                 "sprinklers", "detectors", "ceiling")

    def __init__(self, room):
        self.room = room
        cat = room.cat
        area = room.area
        self.lux = LUX.get(cat, 200)

        n_lum = 0 if self.lux == 0 else max(1, int(math.ceil(
            self.lux * area / LUMINAIRE_EFFECTIVE)))
        self.luminaires = n_points_in_ring(room.ring, n_lum, inset=0.55)

        dens = DENSITY.get(cat, 0.0)
        self.occupants = int(round(area / dens)) if dens else 0
        self.airflow_lps = self.occupants * FRESH_AIR_LPS
        n_sup = int(math.ceil(self.airflow_lps / TERMINAL_LPS)) if self.airflow_lps else 0
        self.supply = n_points_in_ring(room.ring, n_sup, inset=0.9)
        self.extract = n_points_in_ring(room.ring, max(0, n_sup - 1), inset=1.4) \
            if n_sup > 1 else []

        if cat in ("work", "meet", "recep", "amenity"):
            self.sockets = along_boundary(room.ring, SOCKET_SPACING)
            self.data = self.sockets[::2]
            self.floor_boxes = (grid_in_ring(room.ring, FLOOR_BOX_GRID, 1.2)
                                if area > 30 and cat == "work" else [])
        else:
            self.sockets = along_boundary(room.ring, SOCKET_SPACING * 2.2)
            self.data, self.floor_boxes = [], []

        n_spr = max(1, int(math.ceil(area / SPRINKLER_COVERAGE)))
        self.sprinklers = n_points_in_ring(room.ring, n_spr, inset=0.5)
        n_det = max(1, int(math.ceil(area / DETECTOR_COVERAGE)))
        self.detectors = n_points_in_ring(room.ring, n_det, inset=1.0)

        self.ceiling = "grid" if cat in ("work", "meet", "recep", "amenity") \
            else ("plaster" if cat in ("core",) else "exposed")


def for_floor(floorplan):
    return [RoomServices(r) for r in floorplan.rooms]


def totals(services):
    """Whole-floor loads, the numbers that end up in the notes panel."""
    lum = sum(len(s.luminaires) for s in services)
    return {
        "luminaires": lum,
        "lighting_load_kw": round(lum * 36.0 / 1000.0, 1),     # 36 W panels
        "occupants": sum(s.occupants for s in services),
        "fresh_air_lps": round(sum(s.airflow_lps for s in services)),
        "supply_terminals": sum(len(s.supply) for s in services),
        "sockets": sum(len(s.sockets) for s in services),
        "floor_boxes": sum(len(s.floor_boxes) for s in services),
        "sprinklers": sum(len(s.sprinklers) for s in services),
        "detectors": sum(len(s.detectors) for s in services),
        "small_power_kw": round(sum(s.occupants for s in services) * 0.20, 1),
    }


# ---------------------------------------------------------------------------
# Distribution: where the risers and boards sit, and how routes reach them
# ---------------------------------------------------------------------------
def risers(floorplan):
    """One distribution point per core: boards, stacks and duct risers."""
    return [(G.centroid(r.ring), r.name) for r in floorplan.rooms if r.cat == "core"]


def containment(floorplan):
    """Horizontal routes: every circulation ring, drawn as its centreline."""
    routes = []
    for circ in floorplan.circulation:
        routes.append(circ.outer)
        routes += list(circ.holes)
    return routes


def nearest_riser(point, riser_pts):
    if not riser_pts:
        return None, 0.0
    best, bd = None, 1e18
    for (p, name) in riser_pts:
        d = math.dist(point, p)
        if d < bd:
            best, bd = (p, name), d
    return best, bd


# ---------------------------------------------------------------------------
# Fire: escape routes and travel distances
# ---------------------------------------------------------------------------
class EscapeCheck:
    __slots__ = ("routes", "worst", "worst_room", "limit", "compliant")

    def __init__(self, routes, limit):
        self.routes = routes
        self.limit = limit
        self.worst = max((r["travel_m"] for r in routes), default=0.0)
        self.worst_room = next((r["room"] for r in routes
                                if abs(r["travel_m"] - self.worst) < 1e-9), None)
        self.compliant = self.worst <= limit


def escape(floorplan, limit=ESCAPE_LIMIT_TWO_WAY):
    """Distance from every room to its nearest protected stair.

    Straight line with a routing allowance, which is how travel distance is
    checked at concept stage before a fire engineer walks the real path."""
    cores = risers(floorplan)
    routes = []
    for r in floorplan.rooms:
        if r.cat == "core":
            continue
        c = r.centroid
        (target, name), d = nearest_riser(c, cores) or ((None, ""), 0.0)
        if target is None:
            continue
        routes.append({"room": r.name, "code": r.code, "from": c, "to": target,
                       "core": name, "direct_m": round(d, 1),
                       "travel_m": round(d * ROUTE_FACTOR, 1)})
    return EscapeCheck(routes, limit)


# ---------------------------------------------------------------------------
# Roof
# ---------------------------------------------------------------------------
def _fit_rect_inside(region, w, h, tries=24):
    """Largest-clearance position for a rectangle that fits inside a region.

    A courtyard building has a hole in the middle of its bounding box, so the
    centroid of the outer ring is often not on the roof at all. This looks for
    somewhere the plant can actually stand."""
    x0, y0, x1, y1 = region.bbox()
    best, best_score = None, -1.0
    for i in range(tries):
        for j in range(tries):
            cx = x0 + (i + 0.5) * (x1 - x0) / tries
            cy = y0 + (j + 0.5) * (y1 - y0) / tries
            rect = G.rectangle(w, h, cx, cy)
            if not all(region.contains(p) for p in rect):
                continue
            mid = [((rect[k][0] + rect[(k + 1) % 4][0]) / 2.0,
                    (rect[k][1] + rect[(k + 1) % 4][1]) / 2.0) for k in range(4)]
            if not all(region.contains(p) for p in mid):
                continue
            clear = min(_ring_clearance(p, region) for p in rect)
            if clear > best_score:
                best, best_score = rect, clear
    return best


def _ring_clearance(p, region):
    d = 1e18
    for ring in region.rings:
        n = len(ring)
        for k in range(n):
            a, b = ring[k], ring[(k + 1) % n]
            ex, ey = b[0] - a[0], b[1] - a[1]
            l2 = ex * ex + ey * ey
            t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((p[0] - a[0]) * ex +
                                                          (p[1] - a[1]) * ey) / l2))
            d = min(d, math.dist(p, (a[0] + ex * t, a[1] + ey * t)))
    return d



def roof(project, outlet_spacing=14.0, plant_fraction=0.09):
    """Falls, outlets, plant enclosure and access for the top plate."""
    top = project.massing.levels[-1].plate
    area = top.area
    outlets = []
    for ring in top.rings:
        per = G.perimeter(ring)
        n = max(2, int(round(per / outlet_spacing)))
        cum = [0.0]
        for i in range(len(ring)):
            cum.append(cum[-1] + math.dist(ring[i], ring[(i + 1) % len(ring)]))
        for k in range(n):
            t = cum[-1] * k / n
            for j in range(len(cum) - 1):
                if cum[j] <= t <= cum[j + 1]:
                    seg = cum[j + 1] - cum[j] or 1.0
                    u = (t - cum[j]) / seg
                    a, b = ring[j], ring[(j + 1) % len(ring)]
                    nx, ny = G._edge_normal(a, b)
                    outlets.append((a[0] + (b[0] - a[0]) * u - nx * 0.9,
                                    a[1] + (b[1] - a[1]) * u - ny * 0.9))
                    break
    plant_area = area * plant_fraction
    side = math.sqrt(max(plant_area, 4.0))
    plant = _fit_rect_inside(top, side * 1.6, side / 1.6) or \
        _fit_rect_inside(top, side, side) or \
        G.rectangle(side, side, *G.centroid(top.outer))
    return {"plate": top, "area_m2": round(area, 1), "outlets": outlets,
            "plant": plant, "plant_area_m2": round(plant_area, 1),
            "falls": "1:80 to outlets", "walkway_w": 1.2}


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------
DEAD_KPA = 5.5            # slab, finishes, services, ceiling
LIVE_KPA = 4.0            # office imposed, including partitions
BEARING_KPA = 200.0       # allowable ground bearing pressure
CONCRETE_KNM3 = 25.0


def _round_up(v, step):
    return math.ceil(v / step) * step


def columns_for(project, level_index=0):
    """Grid intersections that land on the plate."""
    from .grid import OrthoGrid
    g = project.grid
    plate = project.massing.levels[level_index].plate
    if isinstance(g, OrthoGrid):
        return [p for p in g.columns(plate)]
    rings = getattr(g, "rings", []) or [30.0]
    return g.columns(rings)


def structure(project, level_index=0):
    """Columns, their tributary areas and the load each carries to ground."""
    from .grid import OrthoGrid
    g = project.grid
    cols = columns_for(project, level_index)
    n_above = len(project.massing.levels) - level_index
    if isinstance(g, OrthoGrid):
        sx, sy = g.actual_spacing
    else:
        sx = sy = project.brief.room_width
    trib = max(4.0, sx * sy)
    udl = DEAD_KPA + LIVE_KPA
    load_kn = trib * udl * max(1, n_above)
    return {
        "columns": cols, "spacing": (sx, sy), "tributary_m2": round(trib, 1),
        "storeys_above": n_above, "udl_kpa": udl,
        "column_load_kn": round(load_kn),
        "column_size_mm": int(_round_up(200 + load_kn / 30.0, 50)),
        "beam_depth_mm": int(_round_up(max(sx, sy) * 1000.0 / 20.0, 25)),
        "slab_depth_mm": int(_round_up(min(sx, sy) * 1000.0 / 30.0, 25)),
    }


def foundations(project):
    """Pad sizes from column load and allowable bearing pressure."""
    st = structure(project, 0)
    n = st["column_load_kn"]
    area = n / BEARING_KPA
    side = _round_up(math.sqrt(max(area, 0.36)), 0.1)
    depth = _round_up(max(0.45, side * 0.28), 0.05)
    return {
        "pads": st["columns"], "load_kn": n,
        "pad_m": round(side, 2), "depth_m": round(depth, 2),
        "bearing_kpa": BEARING_KPA,
        "pad_volume_m3": round(side * side * depth, 2),
        "concrete_m3": round(side * side * depth * len(st["columns"]), 1),
        "strip_width_m": 0.9,
    }
