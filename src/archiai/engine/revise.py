"""Changing your mind about a project you have already made.

Generating a building is fast, but nobody gets it right first time. What is
needed is not a second roll of the dice: it is the same building with one
thing changed, numbered as the next revision, with a note saying what moved.

Every generation records the input that made it -- a `source` -- normalised to
one of two things: a specification, or an outline. Applying a change to a
source gives a new source, and because the engine is deterministic, building
that source gives exactly the building the change describes. Nothing has to be
kept on the server between the two calls.
"""

import math
import re

from . import brief as B
from . import geom2d as G
from . import layout as L
from . import massing as M


class Rejected(ValueError):
    """The change is understood but cannot be made."""


# ---------------------------------------------------------------------------
# Recording what made a building
# ---------------------------------------------------------------------------
def source_from_spec(spec, brief_text=None, revision="P01"):
    return {
        "kind": "spec",
        "revision": revision,
        "brief_text": brief_text,
        "spec": {"use": spec.use, "shape": spec.shape, "storeys": spec.storeys,
                 "area_m2": spec.area, "entrance_azimuth": spec.entrance,
                 "floor_to_floor_m": spec.floor_to_floor, "name": spec.name},
    }


def source_from_footprint(region, storeys, floor_to_floor, use="office",
                          entrance_azimuth=270.0, name=None, revision="P01",
                          traced=False):
    return {
        "kind": "footprint",
        "revision": revision,
        "traced": bool(traced),
        "footprint": {
            "outer": [[round(x, 3), round(y, 3)] for (x, y) in region.outer],
            "holes": [[[round(x, 3), round(y, 3)] for (x, y) in h]
                      for h in region.holes],
            "storeys": int(storeys),
            "floor_to_floor_m": float(floor_to_floor),
            "use": use, "entrance_azimuth": float(entrance_azimuth),
            "name": name,
        },
    }


def record_result(source, project):
    """The headline numbers, so a later revision can say what moved without
    having to rebuild the old building to find out."""
    m = project.massing
    source["result"] = {
        "gia_m2": round(m.gia(), 1),
        "footprint_m2": round(m.footprint().area, 1),
        "storeys": len(m.levels),
        "height_m": round(m.height, 3),
        "rooms": sum(len(f.rooms) for f in project.floorplans),
    }
    return source


def region_of(source):
    f = source["footprint"]
    return G.Region([(float(x), float(y)) for (x, y) in f["outer"]],
                    [[(float(x), float(y)) for (x, y) in h] for h in f["holes"]])


# ---------------------------------------------------------------------------
# Building one
# ---------------------------------------------------------------------------
def build(source):
    """A source in, (spec | None, massing, brief) out."""
    kind = source.get("kind")
    if kind == "spec":
        s = source["spec"]
        spec = B.Spec(use=s.get("use", "office"), shape=s.get("shape", "bar"),
                      storeys=int(s.get("storeys", 3)), area=s.get("area_m2"),
                      entrance=float(s.get("entrance_azimuth", 270.0)),
                      name=s.get("name"),
                      floor_to_floor=s.get("floor_to_floor_m"))
        if spec.floor_to_floor is None:
            spec.floor_to_floor = B.USE_DEFAULTS.get(
                spec.use, B.USE_DEFAULTS["office"])["f2f"]
        massing, brf = B.build(spec)
        return spec, massing, brf
    if kind == "footprint":
        f = source["footprint"]
        region = region_of(source)
        d = B.USE_DEFAULTS.get(f.get("use", "office"), B.USE_DEFAULTS["office"])
        massing = M.Extrusion(region, storeys=int(f.get("storeys", 3)),
                              floor_to_floor=float(f.get("floor_to_floor_m", 3.9)))
        brf = L.Brief(use=f.get("use", "office"), daylight_depth=d["daylight"],
                      corridor_w=d["corridor"], room_width=d["room_w"],
                      entrance_azimuth=float(f.get("entrance_azimuth", 270.0)),
                      name=f.get("name") or "Drawn footprint")
        brf.accommodation = B.ACCOMMODATION.get(f.get("use", "office"),
                                                B.ACCOMMODATION["office"])
        return None, massing, brf
    raise Rejected("a source must be of kind 'spec' or 'footprint'")


# ---------------------------------------------------------------------------
# Reading a change
# ---------------------------------------------------------------------------
COMPASS = {"north": 90.0, "south": 270.0, "east": 0.0, "west": 180.0,
           "north-east": 45.0, "northeast": 45.0, "ne": 45.0,
           "north-west": 135.0, "northwest": 135.0, "nw": 135.0,
           "south-east": 315.0, "southeast": 315.0, "se": 315.0,
           "south-west": 225.0, "southwest": 225.0, "sw": 225.0}

SIZE_WORDS = {"much bigger": 1.60, "bigger": 1.30, "a bit bigger": 1.12,
              "slightly bigger": 1.08, "a bit smaller": 0.90,
              "slightly smaller": 0.94, "smaller": 0.77, "much smaller": 0.62}

CHANGES = ("storeys", "area_m2", "floor_to_floor_m", "use", "shape",
           "entrance", "name", "courtyard", "footprint_scale")

_NUM = re.compile(r"^\s*([+-]?)\s*([0-9]*\.?[0-9]+)\s*(%?)\s*$")


def _read(value, current, what, allow_words=None, minimum=None, maximum=None):
    """A change value against the value it is changing.

    Plain numbers are absolute. A leading sign is relative. A percent is
    proportional. Words like 'bigger' are proportional too, because that is
    how people say it."""
    if isinstance(value, str):
        key = value.strip().lower()
        if allow_words and key in allow_words:
            if current is None:
                raise Rejected("cannot make the %s %s: there isn't one" % (what, key))
            return _clamp(current * allow_words[key], minimum, maximum, what)
        m = _NUM.match(value)
        if not m:
            words = ", ".join(sorted(allow_words)) if allow_words else ""
            raise Rejected("could not read %r as a change to %s; use a number "
                           "like 12, a step like '+2', a proportion like "
                           "'-10%%'%s" % (value, what,
                                          (", or one of: " + words) if words else ""))
        sign, num, pct = m.group(1), float(m.group(2)), m.group(3)
        if pct:
            factor = (1.0 + num / 100.0) if sign == "+" else \
                     (1.0 - num / 100.0) if sign == "-" else num / 100.0
            if current is None:
                raise Rejected("cannot change %s by a percentage: it was never set"
                               % what)
            return _clamp(current * factor, minimum, maximum, what)
        if sign:
            if current is None:
                raise Rejected("cannot adjust %s: it was never set" % what)
            return _clamp(current + (num if sign == "+" else -num),
                          minimum, maximum, what)
        return _clamp(num, minimum, maximum, what)
    if isinstance(value, bool):
        raise Rejected("%s does not take true or false" % what)
    if isinstance(value, (int, float)):
        return _clamp(float(value), minimum, maximum, what)
    raise Rejected("could not read the change to %s" % what)


def _clamp(v, lo, hi, what):
    if lo is not None and v < lo:
        raise Rejected("%s would become %.3g; the least it can be is %.3g"
                       % (what, v, lo))
    if hi is not None and v > hi:
        raise Rejected("%s would become %.3g; the most it can be is %.3g"
                       % (what, v, hi))
    return v


def _fmt(v):
    return "{:,.0f}".format(v).replace(",", " ")


def next_revision(rev):
    m = re.match(r"^([A-Za-z]*)(\d+)$", str(rev or "P01").strip())
    if not m:
        return "P02"
    return "%s%0*d" % (m.group(1), len(m.group(2)), int(m.group(2)) + 1)


# ---------------------------------------------------------------------------
# Geometry changes
# ---------------------------------------------------------------------------
MIN_BAND = 7.0          # metres of building left between a courtyard and the edge

# The tallest building an edit may ask for. The service usually sets a lower
# one; this is only here so a stray number cannot reach the engine at all.
MAX_STOREYS = 200


def _scale_hole(region, factor):
    """Grow or shrink the courtyard about its own centre."""
    if not region.holes:
        raise Rejected("this building has no courtyard to change")
    holes = []
    for h in region.holes:
        c = G.centroid(h)
        holes.append(G.scale(h, math.sqrt(factor), about=c))
    out = G.Region(region.outer, holes)
    keep = G.Region(region.outer).offset(MIN_BAND)
    for h in out.holes:
        if not all(keep.contains(p) for p in h):
            raise Rejected("that courtyard would leave less than %.0f m of "
                           "building around it" % MIN_BAND)
    if out.area < 40.0:
        raise Rejected("that courtyard would leave almost no floor area")
    return out


def _drop_holes(region):
    if not region.holes:
        raise Rejected("this building has no courtyard to remove")
    return G.Region(region.outer)


def _scale_region(region, factor):
    c = G.centroid(region.outer)
    return G.Region(G.scale(region.outer, factor, about=c),
                    [G.scale(h, factor, about=c) for h in region.holes])


def _promote(source):
    """Turn a specified building into the outline it produced.

    Editing a courtyard is a change to geometry, and a shape family cannot
    express it. Rather than refuse, the source is promoted: from here on the
    building is held as the outline it had, and can be edited as one."""
    _spec, massing, _brf = build(source)
    s = source["spec"]
    out = source_from_footprint(
        massing.levels[0].plate, s.get("storeys", 3),
        s.get("floor_to_floor_m") or 3.9, s.get("use", "office"),
        s.get("entrance_azimuth", 270.0), s.get("name"),
        source.get("revision", "P01"))
    out["promoted_from"] = s.get("shape")
    return out


# ---------------------------------------------------------------------------
def apply(source, changes, max_storeys=None):
    """(new source, notes). Nothing is mutated; the old source still stands.

    `max_storeys` is the caller's ceiling, so the first refusal a person sees
    quotes the limit that will actually be applied to them."""
    if not isinstance(changes, dict) or not changes:
        raise Rejected("no changes given")
    unknown = [k for k in changes if k not in CHANGES]
    if unknown:
        raise Rejected("cannot change %s; you can change %s"
                       % (", ".join(sorted(unknown)), ", ".join(CHANGES)))

    src = _copy(source)
    cap = min(int(max_storeys or MAX_STOREYS), MAX_STOREYS)
    notes = []

    # a geometric edit on a specified building promotes it to an outline first
    geometric = any(k in changes for k in ("courtyard", "footprint_scale"))
    if geometric and src.get("kind") == "spec":
        src = _promote(src)
        notes.append("Shape held as an outline from here on, so its geometry "
                     "can be edited directly.")

    if src["kind"] == "spec":
        _apply_spec(src, changes, notes, cap)
    else:
        _apply_footprint(src, changes, notes, cap)

    if not notes:
        raise Rejected("those values are already what the project has")
    src["revision"] = next_revision(source.get("revision", "P01"))
    src.pop("result", None)
    return src, notes


def _copy(source):
    out = dict(source)
    for k in ("spec", "footprint"):
        if k in out:
            out[k] = dict(out[k])
    if "footprint" in out:
        out["footprint"]["outer"] = [list(p) for p in out["footprint"]["outer"]]
        out["footprint"]["holes"] = [[list(p) for p in h]
                                     for h in out["footprint"]["holes"]]
    return out


def _entrance(value, current, notes):
    if isinstance(value, str) and value.strip().lower() in COMPASS:
        new = COMPASS[value.strip().lower()]
    else:
        new = _read(value, current, "entrance", minimum=-360.0, maximum=720.0) % 360.0
    if abs(new - (current % 360.0)) < 0.01:
        return None
    facing = {v: k for k, v in COMPASS.items() if len(k) > 2}
    notes.append("Entrance moved to face %s." % facing.get(new, "%g degrees" % new))
    return new


def _apply_spec(src, changes, notes, cap=MAX_STOREYS):
    s = src["spec"]
    if "storeys" in changes:
        n = int(round(_read(changes["storeys"], s.get("storeys"), "storeys",
                            minimum=1, maximum=cap)))
        if n != s.get("storeys"):
            was = s["storeys"]
            notes.append("Storeys %d to %d." % (was, n))
            s["storeys"] = n
            # Adding a storey means a taller building, not a thinner one. The
            # floor plate is held and the total area follows, unless the total
            # area is being set in the same breath, in which case that wins.
            if "area_m2" not in changes and s.get("area_m2"):
                grown = s["area_m2"] * n / float(was)
                notes.append("Floor plate held, so total floor area %s to %s m²."
                             % (_fmt(s["area_m2"]), _fmt(grown)))
                s["area_m2"] = grown
    if "area_m2" in changes:
        a = _read(changes["area_m2"], s.get("area_m2"), "floor area",
                  minimum=40.0)
        if s.get("area_m2") is None or abs(a - s["area_m2"]) > 0.5:
            notes.append("Total floor area %s to %s m²."
                         % (_fmt(s["area_m2"]) if s.get("area_m2") else "auto",
                            _fmt(a)))
            s["area_m2"] = a
    if "footprint_scale" in changes:                     # promoted, not reached
        raise Rejected("internal: footprint_scale on a spec source")
    if "floor_to_floor_m" in changes:
        f = _read(changes["floor_to_floor_m"], s.get("floor_to_floor_m"),
                  "floor to floor height", minimum=2.2, maximum=12.0)
        if s.get("floor_to_floor_m") is None or abs(f - s["floor_to_floor_m"]) > 0.005:
            notes.append("Floor to floor %.2f to %.2f m."
                         % (s.get("floor_to_floor_m") or 0.0, f))
            s["floor_to_floor_m"] = f
    if "shape" in changes:
        want = str(changes["shape"]).strip().lower()
        if want not in B.SHAPES:
            raise Rejected("shape must be one of %s" % ", ".join(sorted(B.SHAPES)))
        if want != s.get("shape"):
            notes.append("Shape changed from %s to %s." % (s["shape"], want))
            s["shape"] = want
    if "use" in changes:
        want = str(changes["use"]).strip().lower()
        if want not in B.USE_DEFAULTS:
            raise Rejected("no idea how to plan a %s; the uses it knows are %s"
                           % (want, ", ".join(sorted(B.USE_DEFAULTS))))
        if want != s.get("use"):
            notes.append("Use changed from %s to %s." % (s["use"], want))
            s["use"] = want
    if "entrance" in changes:
        new = _entrance(changes["entrance"], s.get("entrance_azimuth", 270.0), notes)
        if new is not None:
            s["entrance_azimuth"] = new
    if "name" in changes:
        if changes["name"] != s.get("name"):
            notes.append("Renamed to %s." % changes["name"])
            s["name"] = str(changes["name"])
    if "courtyard" in changes:                           # promoted, not reached
        raise Rejected("internal: courtyard on a spec source")


def _apply_footprint(src, changes, notes, cap=MAX_STOREYS):
    f = src["footprint"]
    region = region_of(src)
    moved = False

    if "shape" in changes:
        raise Rejected("this project's shape is an outline you drew, traced or "
                       "edited; change footprint_scale or courtyard instead, "
                       "or start a new project from a brief")

    if "storeys" in changes:
        n = int(round(_read(changes["storeys"], f.get("storeys"), "storeys",
                            minimum=1, maximum=cap)))
        if n != f["storeys"]:
            notes.append("Storeys %d to %d." % (f["storeys"], n))
            f["storeys"] = n
    if "floor_to_floor_m" in changes:
        v = _read(changes["floor_to_floor_m"], f.get("floor_to_floor_m"),
                  "floor to floor height", minimum=2.2, maximum=12.0)
        if abs(v - f["floor_to_floor_m"]) > 0.005:
            notes.append("Floor to floor %.2f to %.2f m."
                         % (f["floor_to_floor_m"], v))
            f["floor_to_floor_m"] = v
    if "courtyard" in changes:
        v = changes["courtyard"]
        if isinstance(v, str) and v.strip().lower() in ("none", "remove", "no"):
            before = sum(G.area(h) for h in region.holes)
            region = _drop_holes(region)
            notes.append("Courtyard removed (%s m²)." % _fmt(before))
            moved = True
        else:
            before = sum(G.area(h) for h in region.holes) or None
            factor = _read(v, before, "courtyard area",
                           allow_words=SIZE_WORDS, minimum=1.0)
            factor = factor / before if before else 1.0
            if abs(factor - 1.0) > 0.005:
                region = _scale_hole(region, factor)
                after = sum(G.area(h) for h in region.holes)
                notes.append("Courtyard %s to %s m²."
                             % (_fmt(before), _fmt(after)))
                moved = True
    if "footprint_scale" in changes:
        k = _read(changes["footprint_scale"], 1.0, "footprint scale",
                  allow_words=SIZE_WORDS, minimum=0.1, maximum=10.0)
        if abs(k - 1.0) > 0.002:
            before = region.area
            region = _scale_region(region, math.sqrt(k) if k > 0 else 1.0)
            notes.append("Footprint %s to %s m²." % (_fmt(before), _fmt(region.area)))
            moved = True
    if "area_m2" in changes:
        target = _read(changes["area_m2"],
                       region.area * f["storeys"], "floor area", minimum=40.0)
        want_plate = target / max(f["storeys"], 1)
        k = math.sqrt(want_plate / region.area) if region.area > 0 else 1.0
        if abs(k - 1.0) > 0.002:
            before = region.area * f["storeys"]
            region = _scale_region(region, k)
            notes.append("Total floor area %s to %s m²."
                         % (_fmt(before), _fmt(region.area * f["storeys"])))
            moved = True
    if "use" in changes:
        want = str(changes["use"]).strip().lower()
        if want not in B.USE_DEFAULTS:
            raise Rejected("no idea how to plan a %s; the uses it knows are %s"
                           % (want, ", ".join(sorted(B.USE_DEFAULTS))))
        if want != f.get("use"):
            notes.append("Use changed from %s to %s." % (f["use"], want))
            f["use"] = want
    if "entrance" in changes:
        new = _entrance(changes["entrance"], f.get("entrance_azimuth", 270.0), notes)
        if new is not None:
            f["entrance_azimuth"] = new
    if "name" in changes:
        if changes["name"] != f.get("name"):
            notes.append("Renamed to %s." % changes["name"])
            f["name"] = str(changes["name"])

    if moved:
        f["outer"] = [[round(x, 3), round(y, 3)] for (x, y) in region.outer]
        f["holes"] = [[[round(x, 3), round(y, 3)] for (x, y) in h]
                      for h in region.holes]


# ---------------------------------------------------------------------------
def compare(before, project):
    """What actually moved, measured rather than promised."""
    m = project.massing
    now = {"gia_m2": round(m.gia(), 1),
           "footprint_m2": round(m.footprint().area, 1),
           "storeys": len(m.levels), "height_m": round(m.height, 3),
           "rooms": sum(len(f.rooms) for f in project.floorplans)}
    if not before:
        return {"after": now}
    out = {"before": dict(before), "after": now, "delta": {}}
    for k, v in now.items():
        old = before.get(k)
        if isinstance(old, (int, float)):
            d = round(v - old, 3)
            out["delta"][k] = d
            if old:
                out["delta"][k + "_pct"] = round(100.0 * d / old, 1)
    return out
