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

    def build(self, out_dir, elevations=(270, 0, 90, 180), disciplines=None):
        """Generate the whole set. Returns [(number, title, scale, path), ...].

        `disciplines` selects families: architecture, electrical, mechanical,
        public_health, fire, structure. Omit for everything."""
        from . import (draw, draw_services as DS, draw_schedules as DSC,
               draw_details as DD)
        want = set(disciplines or ("architecture", "electrical", "mechanical",
                                   "public_health", "fire", "structure"))
        d = os.path.join(out_dir, "drawings")
        os.makedirs(d, exist_ok=True)
        num = self.info["number"]
        n_levels = len(self.massing.levels)
        made = []

        def add(sheet_no, title, scale, fn, *a, **kw):
            path = os.path.join(d, "%s-%s.svg" % (num, sheet_no))
            fn(*a, path, **kw)
            made.append((sheet_no, title, scale, path))

        if "architecture" in want:
            add("A-010", "Site Plan", "1:500", DSC.site_sheet, self)
            for i, lv in enumerate(self.massing.levels):
                add("A-1%02d" % i, "%s — Floor Plan" % lv.name, "1:150",
                    draw.plan_sheet, self, i)
            add("A-140", "Roof Plan", "1:150", DS.roof_sheet, self)
            for i, lv in enumerate(self.massing.levels):
                add("A-15%d" % i, "%s — Reflected Ceiling" % lv.name, "1:150",
                    DS.rcp_sheet, self, i)
            add("A-200", "Elevations — South and East", "1:150",
                draw.elevation_sheet, self, list(elevations[:2]), number="A-200")
            if len(elevations) > 2:
                add("A-201", "Elevations — North and West", "1:150",
                    draw.elevation_sheet, self, list(elevations[2:]), number="A-201")
            add("A-300", "Sections", "1:150", draw.section_sheet, self,
                self.default_cuts())
            add("A-400", "Typical Wall Section", "1:50",
                DD.wall_section_sheet, self)
            add("A-500", "Envelope Details", "1:10", DD.details_sheet, self)
            add("A-700", "Area Schedule and Accommodation", "—",
                DSC.schedule_sheet, self)
            add("A-710", "Door and Window Schedule", "—",
                DSC.door_window_sheet, self)
            add("A-800", "Axonometric and Assembly", "NTS", DSC.axo_sheet, self)

        if "structure" in want:
            add("S-010", "Foundation Plan", "1:150", DS.foundation_sheet, self)
            for i, lv in enumerate(self.massing.levels):
                add("S-1%02d" % i, "%s — Framing Plan" % lv.name, "1:150",
                    DS.framing_sheet, self, i)

        if "electrical" in want:
            for i, lv in enumerate(self.massing.levels):
                add("E-10%d" % i, "%s — Small Power and Data" % lv.name, "1:150",
                    DS.power_sheet, self, i)
            for i, lv in enumerate(self.massing.levels):
                add("E-20%d" % i, "%s — Lighting" % lv.name, "1:150",
                    DS.lighting_sheet, self, i)

        if "mechanical" in want:
            for i, lv in enumerate(self.massing.levels):
                add("M-10%d" % i, "%s — Ventilation" % lv.name, "1:150",
                    DS.ventilation_sheet, self, i)

        if "public_health" in want:
            add("P-100", "Drainage — Below Ground", "1:150", DS.drainage_sheet, self)

        if "fire" in want:
            for i, lv in enumerate(self.massing.levels):
                add("FS-10%d" % i, "%s — Fire Strategy" % lv.name, "1:150",
                    DS.fire_sheet, self, i)

        register = [(n, t, sc) for (n, t, sc, _) in made]
        cover = os.path.join(d, "%s-A-000.svg" % num)
        DSC.cover_sheet(self, [("A-000", "Cover Sheet and Drawing Register", "—")]
                        + register, cover)
        made.insert(0, ("A-000", "Cover Sheet and Drawing Register", "—", cover))
        return made

    def __repr__(self):
        return "<Project %s: %s, %d levels, %.0f m2>" % (
            self.info["name"], self.massing.name, len(self.massing.levels), self.gia)
