"""A generated project: massing + brief -> floorplans, grid, sheets, model."""

import os
from . import grid as GR
from . import layout as L


DEFAULT_INFO = {
    "name": "UNTITLED", "subtitle": "Generated project", "number": "AAI-0000",
    "client": "ArchiAI", "architect": "ArchiAI Design Studio",
    "status": "STAGE 2  /  CONCEPT", "rev": "P01", "date": "2026-08-19",
}


class Project:
    def __init__(self, massing, brief=None, info=None, grid=None):
        self.massing = massing
        self.brief = brief or L.Brief()
        self.info = dict(DEFAULT_INFO)
        self.info["name"] = self.brief.name.upper()
        if info:
            self.info.update(info)
        self.grid = grid or GR.choose(massing, self.brief.room_width)
        self.floorplans = [L.allocate(lv, self.brief, i)
                           for i, lv in enumerate(massing.levels)]

    @property
    def gia(self):
        return self.massing.gia()

    def rooms(self):
        return [r for fp in self.floorplans for r in fp.rooms]

    def default_cuts(self):
        from . import geom2d as G
        c = G.centroid(self.massing.footprint().outer)
        return [("A", c, (1.0, 0.0), "Cut east-west through the plan centre"),
                ("B", c, (0.0, 1.0), "Cut north-south through the plan centre")]

    def build(self, out_dir, elevations=(270, 0, 90, 180)):
        from . import draw
        d = os.path.join(out_dir, "drawings")
        os.makedirs(d, exist_ok=True)
        num = self.info["number"]
        made = []
        for i in range(len(self.massing.levels)):
            made.append(draw.plan_sheet(self, i, os.path.join(d, "%s-A-1%02d.svg" % (num, i))))
        made.append(draw.elevation_sheet(
            self, list(elevations[:2]), os.path.join(d, "%s-A-200.svg" % num), number="A-200"))
        if len(elevations) > 2:
            made.append(draw.elevation_sheet(
                self, list(elevations[2:]), os.path.join(d, "%s-A-201.svg" % num),
                number="A-201"))
        made.append(draw.section_sheet(
            self, self.default_cuts(), os.path.join(d, "%s-A-300.svg" % num)))
        return made

    def __repr__(self):
        return "<Project %s: %s, %d levels, %.0f m2>" % (
            self.info["name"], self.massing.name, len(self.massing.levels), self.gia)
