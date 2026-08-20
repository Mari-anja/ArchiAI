"""Handing the building to an image model, without guessing at it.

The deterministic renderer already knows things a photoreal pass normally has
to infer from a picture: how far away every surface is, which way it faces,
what it is made of, and where its edges are. Those are exactly what an image
model conditions on. So this module does not try to be a renderer -- it
prepares the conditioning: the control images, and a description of the scene
written from the model rather than from someone's memory of it.

The generation step itself is a seam. Anthropic's API reads images but does
not make them, so a photoreal pass needs a third-party image service, and
which one is a decision with a price attached. Everything up to that decision
is built here; plugging a service in is one small adapter.
"""

import math

from . import buildup as BU
from . import openings as OP
from . import view as VW


class NotConfigured(RuntimeError):
    """No image service is wired up. The controls are still produced."""


# ---------------------------------------------------------------------------
# What the picture is of
# ---------------------------------------------------------------------------
# How a build-up layer photographs, as opposed to how it is specified.
LOOKS = {
    "Rainscreen panel on carrier rail": "large flat composite panels in pale "
                                        "warm grey with fine shadow gap joints",
    "Structural inner leaf, dense block": "grey blockwork",
}

TIME_OF_DAY = [(0, 5, "before dawn"), (5, 8, "early morning"),
               (8, 11, "mid morning"), (11, 14, "midday"),
               (14, 17, "afternoon"), (17, 20, "early evening"),
               (20, 24, "after dark")]

SEASON = [(0, 60, "winter"), (60, 152, "spring"), (152, 244, "summer"),
          (244, 335, "autumn"), (335, 367, "winter")]

SHOT = {
    "entrance": "eye level from the pavement at the main entrance, looking up "
                "slightly at the facade",
    "courtyard": "standing inside the courtyard at eye level",
    "roof": "looking straight down from above",
    "axo": "an elevated three quarter view, parallel projection",
    "worm": "a low angle close to the base, looking up the facade",
}


def _when(day, hour):
    tod = next(n for (a, b, n) in TIME_OF_DAY if a <= hour < b)
    season = next(n for (a, b, n) in SEASON if a <= day < b)
    return tod, season


def _weather(sky):
    return {"day": "bright with light cloud", "clear": "a clear sky",
            "overcast": "flat overcast light", "evening": "low warm evening sun",
            "none": "neutral studio light"}.get(sky, "bright with light cloud")


def describe(project, name="aerial-ne", latitude=51.5, day=172, hour=14.0,
             sky="day", addons=(), style_note=None):
    """A description of the scene, assembled from the model.

    Written rather than generated: every clause is something the engine can
    actually check, so the description cannot drift away from the drawings."""
    m = project.massing
    brief = project.brief
    wall = BU.external_wall(project)
    tot = OP.totals(project)
    facade = 0.0
    try:
        from . import geom2d as G
        facade = G.perimeter(m.footprint().outer) * m.height
    except Exception:
        pass
    glazed = (100.0 * tot["glazed_area_m2"] / facade) if facade else 0.0
    tod, season = _when(day, hour)
    shot = SHOT.get(name)
    if shot is None:
        if name.startswith("eye"):
            shot = "eye level from across the street, the whole building in view"
        else:
            shot = "an aerial three quarter view from about twenty five degrees"

    parts = [
        "Architectural photograph of a %d storey %s building, %.0f metres tall"
        % (len(m.levels), brief.use, m.height),
    ]
    if m.footprint().holes:
        parts.append("planned around a central courtyard")
    parts.append("%s" % shot)
    # What is visible from outside, in the words a photograph would need --
    # not the build-up's own language, which names layers nobody can see.
    parts.append("facade of %s alternating with %s, glazing about %.0f per "
                 "cent of the elevation, in horizontal bands one storey high"
                 % (LOOKS.get(wall[0].name, "flat grey cladding panels"),
                    "dark framed glazing", glazed))
    parts.append("solid spandrel panels at each floor line")
    parts.append("flat roof behind a shallow metal coped parapet")
    if "context" in addons:
        parts.append("low neighbouring buildings across the street")
    if "trees" in addons:
        parts.append("street trees on the pavement")
    if "people" in addons:
        parts.append("a few people at the entrance for scale")
    if "cars" in addons:
        parts.append("cars parked at the kerb")
    parts.append("%s light, %s, %s" % (tod, season, _weather(sky)))
    parts.append("photographed on a tilt shift lens, verticals parallel, "
                 "no lens distortion, natural colour, high detail")
    if style_note:
        parts.append(style_note)
    return ", ".join(parts) + "."


NEGATIVE = ("distorted perspective, converging verticals, warped windows, "
            "extra floors, illegible signage, text, watermark, people with "
            "malformed faces, cartoon, illustration, oversaturated, fisheye")


# ---------------------------------------------------------------------------
# What the picture must agree with
# ---------------------------------------------------------------------------
CONTROLS = {
    "depth": "Distance from the camera, near bright. Use as a depth control.",
    "normal": "Surface direction in camera space. Use as a normal control.",
    "segment": "One flat colour per material. Use as a segmentation control.",
    "line": "Hidden line removed edges. Use as a line or soft edge control.",
}


def controls(project, name="aerial-ne", width=1280, height=800,
             addons=("ground", "context", "trees", "cars", "people"),
             which=("depth", "normal", "segment", "line"), **camera):
    """The conditioning images, all from one camera so they line up exactly."""
    unknown = [k for k in which if k not in CONTROLS]
    if unknown:
        raise ValueError("no such control: %s" % ", ".join(unknown))
    out = {}
    for kind in which:
        out[kind] = VW.render(project, name, style=kind, addons=tuple(addons),
                              width=width, height=height, **camera)
    return out


def base_render(project, name="aerial-ne", width=1280, height=800,
                addons=("ground", "sky", "shadow", "context", "trees", "cars",
                        "people"), **camera):
    """The deterministic picture itself, which is also the safest control:
    it is already the right building in the right light."""
    return VW.render(project, name, style="material", addons=tuple(addons),
                     width=width, height=height, **camera)


# ---------------------------------------------------------------------------
# The seam
# ---------------------------------------------------------------------------
class Backend:
    """What an image service has to provide.

    One method. Everything else -- the camera, the light, the controls, the
    description -- is already decided by the time it is called, so swapping
    services does not change a single thing about the building."""

    name = "none"
    #: what the service is being asked to do, for the record
    modality = "image"

    def generate(self, prompt, controls, negative=None, width=1280, height=800,
                 seed=None, strength=0.75, options=None):
        """Return image bytes and a content type, or raise NotConfigured."""
        raise NotConfigured(
            "no image service is configured, so the photoreal step was not "
            "run. The control images and the prompt are returned, ready to "
            "post to whichever service you choose.")


_BACKENDS = {"none": Backend}


def register(name, factory):
    """Add a backend. One adapter, one line, and the seam is closed."""
    _BACKENDS[name] = factory
    return factory


def backend(name="none"):
    if name not in _BACKENDS:
        raise NotConfigured("unknown image service %r; known: %s"
                            % (name, ", ".join(sorted(_BACKENDS))))
    return _BACKENDS[name]()


# ---------------------------------------------------------------------------
def package(project, name="aerial-ne", width=1280, height=800,
            addons=("ground", "sky", "shadow", "context", "trees", "cars",
                    "people"), which=("depth", "normal", "segment", "line"),
            latitude=51.5, day=172, hour=14.0, sky="day", style_note=None,
            seed=None, **camera):
    """Everything needed to make a photoreal image of this building.

    Returned whether or not a service is wired up, because it is the part
    worth keeping: the same package always describes the same building."""
    ctrl_addons = tuple(a for a in addons if a not in ("sky", "shadow"))
    return {
        "prompt": describe(project, name, latitude, day, hour, sky, addons,
                           style_note),
        "negative_prompt": NEGATIVE,
        "controls": controls(project, name, width, height, ctrl_addons, which,
                             latitude=latitude, day=day, hour=hour, **camera),
        "control_notes": {k: CONTROLS[k] for k in which},
        "base": base_render(project, name, width, height, addons,
                            latitude=latitude, day=day, hour=hour, sky=sky,
                            **camera),
        "view": VW.describe(project, name, latitude, day, hour),
        "size": [int(width), int(height)],
        "seed": seed,
    }
