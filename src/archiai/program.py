"""The accommodation schedule, expressed the way the building is shaped.

Every room is an annular sector -- (theta0, theta1) x (r0, r1) -- because in a
torus that is the honest unit of plan.  Areas are therefore exact, not
measured off a drawing.
"""

import math
from . import params as P

# ---------------------------------------------------------------------------
CATEGORY = {
    "work":    ("#eef2f7", "#a8bacd", "Workplace"),
    "meet":    ("#f4efe7", "#c9b79a", "Meeting & collaboration"),
    "amenity": ("#f2f6ee", "#a9c19b", "Amenity & wellbeing"),
    "event":   ("#f0ecf4", "#b3a4c4", "Learning & events"),
    "core":    ("#dcdcdc", "#8f8f8f", "Cores & vertical circulation"),
    "plant":   ("#e6e6e1", "#9c9c92", "Plant & back of house"),
    "circ":    ("#f8f8f6", "#c5c5bd", "Primary circulation"),
    "recep":   ("#e9eef4", "#93a8c0", "Entrance & reception"),
    "void":    ("#ffffff", "#b9b9b9", "Void / open to below"),
    "ext":     ("#eef3ea", "#9dbb96", "External / courtyard"),
}

BAND_R0, BAND_R1 = P.R_LOOP, P.R_OUT_00      # 26.000 -> 37.200, the occupied band


class Room:
    __slots__ = ("code", "name", "level", "t0", "t1", "r0", "r1", "cat", "sub", "seats")

    def __init__(self, code, name, level, t0, t1, r0=None, r1=None, cat="work",
                 sub=None, seats=0):
        self.code, self.name, self.level = code, name, level
        self.t0, self.t1 = t0, t1
        self.r0 = BAND_R0 if r0 is None else r0
        self.r1 = BAND_R1 if r1 is None else r1
        self.cat, self.sub, self.seats = cat, sub, seats

    @property
    def area(self):
        return math.pi * (self.t1 - self.t0) / 360.0 * (self.r1 ** 2 - self.r0 ** 2)

    @property
    def tm(self):
        return (self.t0 + self.t1) / 2.0

    @property
    def rm(self):
        return (self.r0 + self.r1) / 2.0

    @property
    def fill(self):
        return CATEGORY[self.cat][0]

    @property
    def stroke(self):
        return CATEGORY[self.cat][1]

    def __repr__(self):
        return "<%s %s %.0fm2>" % (self.code, self.name, self.area)


# ---------------------------------------------------------------------------
# LEVEL 00
# ---------------------------------------------------------------------------
ROOMS_00 = [
    Room("00.01", "Studio East",            0,   0,  38, cat="work"),
    Room("00.C1", "Core A",                 0,  38,  52, cat="core"),
    Room("00.02", "Studio North-East",      0,  52,  80, cat="work"),
    Room("00.03", "Loading & deliveries",   0,  80,  84, cat="plant"),
    Room("00.04", "Service gateway",        0,  84,  96, cat="ext",
         sub="Undercroft, Level 01 over"),
    Room("00.05", "Waste & recycling",      0,  96, 100, cat="plant"),
    Room("00.06", "Central plant room",     0, 100, 114, cat="plant"),
    Room("00.07", "Switchroom, comms & tanks", 0, 114, 128, cat="plant"),
    Room("00.C2", "Core B",                 0, 128, 142, cat="core"),
    Room("00.08", "Fitness studio",         0, 142, 158, cat="amenity"),
    Room("00.09", "Changing & showers",     0, 158, 166, cat="amenity"),
    Room("00.10", "Auditorium",             0, 166, 194, cat="event", seats=120,
         sub="120 seats, flat floor, divisible"),
    Room("00.11", "Seminar rooms 1-3",      0, 194, 204, cat="event"),
    Room("00.12", "Meeting suite",          0, 204, 218, cat="meet"),
    Room("00.C3", "Core C",                 0, 218, 232, cat="core"),
    Room("00.13", "Project & making space", 0, 232, 248, cat="work"),
    Room("00.14", "Gallery",                0, 248, 255, cat="amenity"),
    Room("00.15", "Entrance hall & reception", 0, 255, 285, cat="recep",
         sub="Double height to +9.600"),
    Room("00.16", "Café & servery",         0, 285, 297, cat="amenity"),
    Room("00.17", "Kitchen & stores",       0, 297, 308, cat="amenity"),
    Room("00.C4", "Core D",                 0, 308, 322, cat="core"),
    Room("00.18", "Studio South-East",      0, 322, 360, cat="work"),
]

# ---------------------------------------------------------------------------
# LEVEL 01
# ---------------------------------------------------------------------------
ROOMS_01 = [
    Room("01.01", "Neighbourhood 01",       1,   0,  38, cat="work"),
    Room("01.C1", "Core A",                 1,  38,  52, cat="core"),
    Room("01.02", "Neighbourhood 02",       1,  52,  90, cat="work"),
    Room("01.03", "Neighbourhood 03",       1,  90, 128, cat="work"),
    Room("01.C2", "Core B",                 1, 128, 142, cat="core"),
    Room("01.04", "Neighbourhood 04",       1, 142, 172, cat="work"),
    Room("01.05", "Town Square West",       1, 172, 190, cat="amenity",
         sub="Tea point & informal collaboration"),
    Room("01.06", "Neighbourhood 05",       1, 190, 218, cat="work"),
    Room("01.C3", "Core C",                 1, 218, 232, cat="core"),
    Room("01.07", "Neighbourhood 06",       1, 232, 262, cat="work"),
    Room("01.V1", "Void over entrance hall",1, 262, 278, cat="void"),
    Room("01.08", "Client & leadership suite", 1, 278, 308, cat="meet"),
    Room("01.C4", "Core D",                 1, 308, 322, cat="core"),
    Room("01.09", "Neighbourhood 07",       1, 322, 344, cat="work"),
    Room("01.10", "Town Square East",       1, 344, 360, cat="amenity",
         sub="Tea point & informal collaboration"),
]

# Cellular rooms lining the courtyard edge of the occupied band on Level 01.
FOCUS_01 = [
    (  4,  34), ( 56,  86), ( 94, 124), (146, 168),
    (194, 214), (236, 258), (282, 304), (326, 342),
]
FOCUS_R0, FOCUS_R1 = P.R_LOOP, P.R_LOOP + 2.800     # 26.000 -> 28.800
FOCUS_W = 3.600                                      # nominal chord width, m

# Sectors that receive open-plan desking (level -> list of (t0, t1))
DESK_SECTORS = {
    0: [(2, 36), (54, 78), (234, 246), (324, 358)],  # ground-floor studios
    1: [(4, 34), (56, 86), (94, 124), (146, 168), (194, 214),
        (236, 258), (326, 342)],
}
DESK_R0, DESK_R1 = 29.300, 36.900     # outer band kept for desking on both levels
DESK_R0_L0 = 26.400


# ---------------------------------------------------------------------------
# Furniture generation
# ---------------------------------------------------------------------------
def _rect_polar(r_c, t_c, dr, dt_arc):
    """Rectangle centred at (r_c, t_c), dr deep radially and dt_arc wide along
    the arc, returned as four model-space points."""
    half_t = math.degrees(dt_arc / 2.0 / r_c)
    pts = []
    for (rr, tt) in ((r_c - dr / 2, t_c - half_t), (r_c + dr / 2, t_c - half_t),
                     (r_c + dr / 2, t_c + half_t), (r_c - dr / 2, t_c + half_t)):
        a = math.radians(tt)
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    return pts


def desks(level):
    """Generate individual desk rectangles across the workplace sectors.

    Desks are 1.600 x 0.800, benched 3-wide and 2-deep, so each cluster is a
    4.800 arc x 1.600 radial block.  Returns (list_of_polygons, count)."""
    out, n = [], 0
    r0 = DESK_R0_L0 if level == 0 else DESK_R0
    rows = []
    rr = r0 + 0.9
    while rr + 1.6 <= DESK_R1:
        rows.append(rr + 0.8)
        rr += 1.6 + 1.400          # bench depth + circulation aisle
    for (t0, t1) in DESK_SECTORS.get(level, []):
        for r_c in rows:
            pitch_arc = 4.800 + 1.100
            span_arc = math.radians(t1 - t0) * r_c
            count = int(span_arc // pitch_arc)
            if count < 1:
                continue
            used = count * pitch_arc - 1.100
            start = t0 + math.degrees((span_arc - used) / 2.0 / r_c)
            for i in range(count):
                c_arc = start + math.degrees((i * pitch_arc + 2.400) / r_c)
                for dr_i in (-0.4, 0.4):
                    for k in (-1, 0, 1):
                        tc = c_arc + math.degrees(k * 1.600 / r_c)
                        out.append(_rect_polar(r_c + dr_i * 2, tc, 0.800, 1.520))
                        n += 1
    return out, n


def focus_rooms(level=1):
    """Cellular focus / meeting rooms along the courtyard edge of Level 01."""
    rooms = []
    rc = (FOCUS_R0 + FOCUS_R1) / 2.0
    for (t0, t1) in FOCUS_01:
        span = math.radians(t1 - t0) * rc
        n = int(span // (FOCUS_W + 0.0))
        if n < 1:
            continue
        step = (t1 - t0) / n
        for i in range(n):
            a0, a1 = t0 + i * step, t0 + (i + 1) * step
            rooms.append((a0, a1, FOCUS_R0, FOCUS_R1))
    return rooms


# ---------------------------------------------------------------------------
# Core internals
# ---------------------------------------------------------------------------
def core_parts(t_c, half=7.0):
    """Sub-division of a typical core, returned as annular sectors."""
    a0, a1 = t_c - half, t_c + half
    am = t_c
    return [
        ("Lift lobby",      a0,      a1,     26.000, 28.400, "circ"),
        ("Escape stair",    a0,      am - 0.4, 28.400, 32.200, "core"),
        ("Lifts x2",        am + 0.4, a1,    28.400, 32.200, "core"),
        ("WC",              a0,      am - 0.4, 32.200, 35.600, "core"),
        ("Accessible WC",   am + 0.4, a1,    32.200, 35.600, "core"),
        ("Risers & cleaner", a0,     a1,     35.600, 37.200, "plant"),
    ]


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------
def gia(level):
    """Gross internal area of a plate, less the sectors that are not floor."""
    plate = math.pi * (P.R_OUT_00 ** 2 - P.R_IN_00 ** 2)
    rooms = ROOMS_00 if level == 0 else ROOMS_01
    subtract = sum(r.area for r in rooms if r.cat in ("void", "ext"))
    return plate - subtract


def schedule(level):
    rooms = ROOMS_00 if level == 0 else ROOMS_01
    return sorted(rooms, key=lambda r: r.code)


def by_category(level):
    rooms = ROOMS_00 if level == 0 else ROOMS_01
    agg = {}
    for r in rooms:
        agg.setdefault(r.cat, 0.0)
        agg[r.cat] += r.area
    return agg


def room_at(level, theta):
    """The room occupying a given plan angle on a given level."""
    t = theta % 360.0
    for r in (ROOMS_00 if level == 0 else ROOMS_01):
        if r.t0 <= t < r.t1:
            return r
    return None
