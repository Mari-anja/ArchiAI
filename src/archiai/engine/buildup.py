"""How the building is actually made, layer by layer.

Every construction detail on the drawings is cut through one of these stacks.
Keeping them here means the detail, the wall section and the U-value all read
the same numbers, and a change to the wall thickness redraws all three.

A stack runs from outside to inside (walls and roofs) or top to bottom
(floors). Thicknesses are in millimetres; they always add up to the overall
thickness the model holds, so the drawn detail is the same wall the plan cuts.
"""

from . import services as SV


class Layer:
    """One material in a build-up."""
    __slots__ = ("t", "name", "pattern", "fill", "line")

    def __init__(self, t, name, pattern=None, fill=None, line="fine"):
        self.t = float(t)              # mm
        self.name = name
        self.pattern = pattern         # svgkit hatch name, or None
        self.fill = fill               # flat colour when there is no hatch
        self.line = line               # "cut" for structure, "fine" for finishes

    def __repr__(self):
        return "<%s %.0f>" % (self.name, self.t)


def _scaled(fixed, flexible, total):
    """Fit a stack to a known overall thickness.

    The fixed layers keep their thickness; whatever is left goes to the
    flexible ones in proportion. That is how a real build-up is adjusted: the
    cladding and the finish do not change, the insulation and the inner leaf
    take up the difference."""
    fix = sum(l.t for l in fixed)
    want = sum(l.t for l in flexible)
    left = max(total - fix, 0.0)
    if want > 0:
        k = left / want
        for l in flexible:
            l.t = round(l.t * k)
    return fix + sum(l.t for l in flexible)


# ---------------------------------------------------------------------------
def external_wall(project):
    """Outside to inside, adding up to the model's wall thickness."""
    total = project.brief.wall_t * 1000.0
    cladding = Layer(40, "Rainscreen panel on carrier rail", None, "#c9ccd0", "med")
    cavity = Layer(50, "Ventilated and drained cavity", None, "#ffffff")
    insul = Layer(140, "Rigid mineral wool insulation", "insul")
    leaf = Layer(140, "Structural inner leaf, dense block", "block", None, "cut")
    finish = Layer(15, "Skim on plasterboard lining", "plaster")
    fixed = [cladding, cavity, finish]
    flex = [insul, leaf]
    _scaled(fixed, flex, total)
    return [cladding, cavity, insul, leaf, finish]


def ground_floor(project):
    """Top down, from the finished floor to the bottom of the hardcore."""
    return [
        Layer(20, "Floor finish on levelling compound", None, "#e6e2da", "med"),
        Layer(75, "Sand cement screed with underfloor heating", "screed"),
        Layer(0.6, "Separating layer", None, "#8d8d88"),
        Layer(120, "Rigid insulation, taped joints", "insul"),
        Layer(1.2, "Damp proof membrane, lapped to the DPC", None, "#3b4148", "med"),
        Layer(200, "Reinforced ground bearing slab", "concrete", None, "cut"),
        Layer(50, "Sand blinding", "screed"),
        Layer(150, "Compacted hardcore", "gravel"),
    ]


def upper_floor(project, level=0):
    """Top down through a suspended floor, sized from the structure."""
    st = SV.structure(project, level)
    lv = project.massing.levels[min(level, len(project.massing.levels) - 1)]
    slab = float(st["slab_depth_mm"])
    ceiling_void = max(round(lv.to_ffl * 1000.0 - slab - 175 - 2700), 250)
    return [
        Layer(30, "Carpet tile on raised floor panel", None, "#dedad2", "med"),
        Layer(120, "Raised access floor void on pedestals", None, "#f6f5f2"),
        Layer(slab, "Reinforced concrete slab", "concrete", None, "cut"),
        Layer(ceiling_void, "Services zone: ductwork, containment, sprinklers",
              None, "#fbfbfa"),
        Layer(25, "Suspended ceiling on exposed tee grid", None, "#efefec", "med"),
    ]


def roof(project):
    """Top down through a warm flat roof."""
    st = SV.structure(project, len(project.massing.levels) - 1)
    return [
        Layer(50, "Washed rounded ballast, 20/40 mm", "gravel"),
        Layer(4, "Single ply waterproofing, loose laid", None, "#3b4148", "med"),
        Layer(180, "Tapered insulation laid to 1:80 falls", "insul"),
        Layer(1.2, "Vapour control layer", None, "#6d7581"),
        Layer(float(st["slab_depth_mm"]), "Reinforced concrete roof slab",
              "concrete", None, "cut"),
        Layer(300, "Services zone", None, "#fbfbfa"),
        Layer(25, "Suspended ceiling", None, "#efefec", "med"),
    ]


# ---------------------------------------------------------------------------
# Thermal check: the same layers, read as resistances
# ---------------------------------------------------------------------------
CONDUCTIVITY = {          # W/mK, generic values for a concept-stage check
    "Rainscreen panel on carrier rail": 45.0,
    "Rigid mineral wool insulation": 0.034,
    "Rigid insulation, taped joints": 0.022,
    "Tapered insulation laid to 1:80 falls": 0.022,
    "Structural inner leaf, dense block": 1.13,
    "Skim on plasterboard lining": 0.21,
    "Reinforced concrete slab": 2.30,
    "Reinforced concrete roof slab": 2.30,
    "Reinforced ground bearing slab": 2.30,
    "Sand cement screed with underfloor heating": 1.15,
    "Compacted hardcore": 2.00,
    "Sand blinding": 2.00,
}
SURFACE_R = {"wall": 0.17, "roof": 0.14, "floor": 0.21}


def u_value(layers, kind="wall"):
    """W/m²K for a stack, ignoring layers that are voids or membranes."""
    r = SURFACE_R.get(kind, 0.17)
    for l in layers:
        k = CONDUCTIVITY.get(l.name)
        if k:
            r += (l.t / 1000.0) / k
        elif l.pattern is None and l.t > 20:      # unventilated cavity or void
            r += 0.18
    return round(1.0 / r, 3)


def summary(project):
    """The build-ups the drawings use, with their U-values."""
    w, g, u, rf = (external_wall(project), ground_floor(project),
                   upper_floor(project), roof(project))
    return {
        "wall": {"layers": w, "thickness_mm": round(sum(l.t for l in w)),
                 "u": u_value(w, "wall")},
        "ground": {"layers": g, "thickness_mm": round(sum(l.t for l in g)),
                   "u": u_value(g, "floor")},
        "floor": {"layers": u, "thickness_mm": round(sum(l.t for l in u))},
        "roof": {"layers": rf, "thickness_mm": round(sum(l.t for l in rf)),
                 "u": u_value(rf, "roof")},
    }
