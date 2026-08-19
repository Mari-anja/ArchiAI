"""From a sentence to a building.

Deterministic parsing: no model call, no guessing. What it cannot read from
the text it takes from the use-class defaults, and it reports every assumption
it made so the caller can show them and let the user correct them.
"""

import math
import re
from . import geom2d as G
from . import layout as L
from . import massing as M


# ---------------------------------------------------------------------------
# Accommodation by use class. Shares are of net usable area, excluding cores
# and primary circulation, which the allocator has already taken out.
# ---------------------------------------------------------------------------
ACCOMMODATION = {
    "office": [
        ("Workspace", 0.58, "work"), ("Meeting suite", 0.13, "meet"),
        ("Café and social", 0.08, "amenity"), ("Reception", 0.05, "recep"),
        ("Focus rooms", 0.09, "meet"), ("Plant and stores", 0.07, "plant"),
    ],
    "school": [
        ("Classroom", 0.46, "work"), ("Laboratory", 0.12, "work"),
        ("Hall", 0.10, "amenity"), ("Library", 0.08, "amenity"),
        ("Staff and admin", 0.10, "meet"), ("Dining", 0.08, "amenity"),
        ("Plant and stores", 0.06, "plant"),
    ],
    "residential": [
        ("Apartment", 0.78, "work"), ("Shared amenity", 0.09, "amenity"),
        ("Concierge", 0.04, "recep"), ("Plant and stores", 0.09, "plant"),
    ],
    "gallery": [
        ("Gallery", 0.58, "work"), ("Temporary exhibition", 0.14, "work"),
        ("Café", 0.08, "amenity"), ("Shop and foyer", 0.07, "recep"),
        ("Workshop and store", 0.13, "plant"),
    ],
    "laboratory": [
        ("Write-up and desks", 0.30, "work"), ("Laboratory", 0.40, "work"),
        ("Meeting", 0.10, "meet"), ("Amenity", 0.08, "amenity"),
        ("Plant and stores", 0.12, "plant"),
    ],
}

USE_DEFAULTS = {
    "office":      dict(f2f=3.90, daylight=7.5, room_w=7.2, corridor=2.4),
    "school":      dict(f2f=3.60, daylight=7.5, room_w=8.4, corridor=3.0),
    "residential": dict(f2f=3.10, daylight=6.5, room_w=6.6, corridor=1.8),
    "gallery":     dict(f2f=5.20, daylight=9.0, room_w=9.6, corridor=3.0),
    "laboratory":  dict(f2f=4.20, daylight=8.0, room_w=7.8, corridor=2.6),
}

SHAPES = {
    "courtyard": "courtyard", "court": "courtyard", "atrium": "courtyard",
    "doughnut": "ring", "donut": "ring", "torus": "torus", "ring": "ring",
    "circular": "circle", "round": "circle", "cylinder": "circle",
    "l-shaped": "L", "l shaped": "L", "lshaped": "L",
    "square": "square", "rectangular": "bar", "slab": "bar", "bar": "bar",
    "tower": "tower", "hexagonal": "hex", "hexagon": "hex",
    "triangular": "tri", "octagonal": "oct",
}

COMPASS = {"north": 90.0, "south": 270.0, "east": 0.0, "west": 180.0,
           "north-east": 45.0, "north-west": 135.0,
           "south-east": 315.0, "south-west": 225.0}


class Spec:
    """What was asked for, plus what had to be assumed."""

    def __init__(self, use="office", storeys=3, area=None, shape="bar",
                 entrance=270.0, name=None, floor_to_floor=None):
        self.use, self.storeys, self.area = use, storeys, area
        self.shape, self.entrance = shape, entrance
        self.name = name or shape.title() + " " + use
        self.floor_to_floor = floor_to_floor
        self.assumptions = []

    def assume(self, what):
        self.assumptions.append(what)

    def __repr__(self):
        return "<Spec %s %s, %d storeys, %s m2, entrance %g deg>" % (
            self.shape, self.use, self.storeys,
            ("%.0f" % self.area) if self.area else "auto", self.entrance)


# ---------------------------------------------------------------------------
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12, "single": 1, "double": 2}


def parse(text):
    """Read a brief. Everything not stated is defaulted and recorded."""
    t = " " + text.lower().strip() + " "
    spec = Spec()

    for word, use in (("office", "office"), ("workplace", "office"),
                      ("school", "school"), ("college", "school"),
                      ("apartment", "residential"), ("housing", "residential"),
                      ("residential", "residential"), ("flats", "residential"),
                      ("gallery", "gallery"), ("museum", "gallery"),
                      ("lab", "laboratory"), ("research", "laboratory")):
        if word in t:
            spec.use = use
            break
    else:
        spec.assume("Use not stated; assumed office.")

    m = re.search(r"(\d+)[-\s]*(?:storey|storeys|story|stories|floor|floors|levels?)", t)
    if m:
        spec.storeys = max(1, min(60, int(m.group(1))))
    else:
        m = re.search(r"\b(%s)[-\s]*(?:storey|storeys|story|stories|floor|floors)"
                      % "|".join(NUM_WORDS), t)
        if m:
            spec.storeys = NUM_WORDS[m.group(1)]
        else:
            spec.assume("Number of storeys not stated; assumed 3.")

    m = re.search(r"([\d][\d,\s]*\d|\d)\s*(?:m2|m²|sqm|sq\.?\s*m|square\s*met\w*)", t)
    if m:
        spec.area = float(re.sub(r"[,\s]", "", m.group(1)))
    else:
        spec.assume("Floor area not stated; sized from the storey count.")

    for key in sorted(SHAPES, key=len, reverse=True):
        if key in t:
            spec.shape = SHAPES[key]
            break
    else:
        spec.assume("Shape not stated; assumed a rectangular bar.")

    m = re.search(r"(?:entrance|entry|approach|arrival|access)[^.]{0,24}?"
                  r"(north-east|north-west|south-east|south-west|north|south|east|west)", t)
    if not m:
        m = re.search(r"(north-east|north-west|south-east|south-west|north|south|east|west)"
                      r"[^.]{0,16}?(?:entrance|entry|approach|facing)", t)
    if m:
        spec.entrance = COMPASS[m.group(1)]
    else:
        spec.assume("Entrance orientation not stated; assumed from the south.")

    m = re.search(r"(?:called|named)\s+[\"']?([\w\s-]{2,40}?)[\"']?\s*(?:[.,]|$)", t)
    if m:
        spec.name = m.group(1).strip().title()
    else:
        spec.name = ("%s %s" % (spec.shape, spec.use)).title()

    d = USE_DEFAULTS[spec.use]
    if spec.floor_to_floor is None:
        spec.floor_to_floor = d["f2f"]
    return spec


# ---------------------------------------------------------------------------
def footprint_family(shape):
    """A one-parameter family of footprints, scaled by s."""
    if shape == "courtyard":
        return lambda s: G.Region(G.rounded_rect(1.42 * s, s, 0.17 * s),
                                  [G.rounded_rect(0.60 * s, 0.36 * s, 0.11 * s)])
    if shape in ("ring", "torus"):
        return lambda s: G.Region(G.circle(0.5 * s, 120),
                                  [G.circle(0.30 * s, 120)])
    if shape == "circle":
        return lambda s: G.Region(G.circle(0.5 * s, 120))
    if shape == "L":
        return lambda s: G.Region(G.l_shape(1.38 * s, s, 0.58 * s, 0.42 * s))
    if shape == "hex":
        return lambda s: G.Region(G.regular_polygon(6, 0.5 * s))
    if shape == "oct":
        return lambda s: G.Region(G.regular_polygon(8, 0.5 * s))
    if shape == "tri":
        return lambda s: G.Region(G.regular_polygon(3, 0.58 * s))
    if shape == "square":
        return lambda s: G.Region(G.rounded_rect(s, s, 0.06 * s))
    if shape == "tower":
        return lambda s: G.Region(G.rounded_rect(s, 0.92 * s, 0.10 * s))
    return lambda s: G.Region(G.rounded_rect(1.9 * s, 0.42 * s, 0.05 * s))  # bar


def size_for_area(family, target_plate, lo=8.0, hi=420.0, tol=0.004):
    """Bisect the family's scale until one plate hits the target area."""
    for _ in range(70):
        mid = (lo + hi) / 2.0
        a = family(mid).area
        if abs(a - target_plate) / max(target_plate, 1.0) < tol:
            return mid
        if a < target_plate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def build(spec):
    """Spec -> (massing, brief). The engine takes it from here."""
    d = USE_DEFAULTS[spec.use]
    family = footprint_family(spec.shape)
    if spec.area:
        target = spec.area / float(spec.storeys)
    else:
        target = 900.0 + 140.0 * spec.storeys
        spec.assume("Plate sized at %.0f m2 from the storey count." % target)
    s = size_for_area(family, target)
    setbacks = {}
    if spec.shape == "tower" and spec.storeys >= 9:
        for i in range(spec.storeys):
            if i >= spec.storeys * 0.7:
                setbacks[i] = 3.0
            elif i >= spec.storeys * 0.45:
                setbacks[i] = 1.5

    # Setbacks take area off the upper floors, so sizing the base plate alone
    # undershoots the target. Rebuild a couple of times against actual GIA.
    massing = M.Extrusion(family(s), storeys=spec.storeys,
                          floor_to_floor=spec.floor_to_floor, setbacks=setbacks)
    if spec.area:
        for _ in range(6):
            err = massing.gia() / spec.area
            if abs(err - 1.0) < 0.005:
                break
            s /= math.sqrt(err)
            massing = M.Extrusion(family(s), storeys=spec.storeys,
                                  floor_to_floor=spec.floor_to_floor,
                                  setbacks=setbacks)
    brief = L.Brief(use=spec.use, daylight_depth=d["daylight"],
                    corridor_w=d["corridor"], room_width=d["room_w"],
                    entrance_azimuth=spec.entrance, name=spec.name)
    brief.accommodation = ACCOMMODATION[spec.use]
    return massing, brief


def from_text(text):
    spec = parse(text)
    massing, brief = build(spec)
    return spec, massing, brief
