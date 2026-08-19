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

    def build(self, out_dir):
        from . import draw
        os.makedirs(os.path.join(out_dir, "drawings"), exist_ok=True)
        made = []
        for i in range(len(self.massing.levels)):
            path = os.path.join(out_dir, "drawings", "%s-A-1%02d.svg"
                                % (self.info["number"], i))
            made.append(draw.plan_sheet(self, i, path))
        return made

    def __repr__(self):
        return "<Project %s: %s, %d levels, %.0f m2>" % (
            self.info["name"], self.massing.name, len(self.massing.levels), self.gia)
