"""Regenerate the whole document set.

    python3 -m archiai.build [output-dir]

Every sheet, the mesh, the OpenSCAD source and the viewer come from
`archiai.params`; nothing is drawn by hand.
"""

import os, sys, time
from . import params as P
from . import program as PG
from . import plans, elevations, sections, details, structure, sheets, axo
from . import model3d, scad, viewer

PREFIX = P.PROJECT["number"]


def dwg(out_dir, number):
    return os.path.join(out_dir, "drawings", "%s-%s.svg" % (PREFIX, number))


TASKS = [
    ("A-000", "Cover Sheet and Drawing Register",
     lambda o: sheets.cover_sheet(dwg(o, "A-000"))),
    ("A-010", "Site Plan",
     lambda o: plans.site_plan(dwg(o, "A-010"))),
    ("A-100", "Level 00 Ground Floor Plan",
     lambda o: plans.level_plan(0, dwg(o, "A-100"))),
    ("A-101", "Level 01 First Floor Plan",
     lambda o: plans.level_plan(1, dwg(o, "A-101"))),
    ("A-102", "Roof Plan",
     lambda o: plans.roof_plan(dwg(o, "A-102"))),
    ("A-200", "Elevations South and East",
     lambda o: elevations.elevations_sheet(dwg(o, "A-200"), "A-200")),
    ("A-201", "Elevations North and West",
     lambda o: elevations.elevations_sheet(dwg(o, "A-201"), "A-201")),
    ("A-202", "Developed Elevations",
     lambda o: elevations.developed_sheet(dwg(o, "A-202"))),
    ("A-300", "Sections A-A and B-B",
     lambda o: sections.sections_sheet(dwg(o, "A-300"))),
    ("A-301", "Typical Bay Radial Section",
     lambda o: details.bay_section(dwg(o, "A-301"))),
    ("A-500", "Envelope Details",
     lambda o: details.details_sheet(dwg(o, "A-500"))),
    ("A-600", "Level 01 Framing Plan",
     lambda o: structure.framing_plan(dwg(o, "A-600"))),
    ("A-700", "Area Schedule and Accommodation",
     lambda o: sheets.schedule_sheet(dwg(o, "A-700"))),
    ("A-800", "Axonometric and Assembly",
     lambda o: axo.axo_sheet(dwg(o, "A-800"))),
]


def build(out_dir="output"):
    t0 = time.time()
    os.makedirs(os.path.join(out_dir, "drawings"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "model"), exist_ok=True)
    print("TORUS  %s  rev %s" % (PREFIX, P.PROJECT["rev"]))
    print("-" * 62)
    made = []
    for number, title, fn in TASKS:
        path = fn(out_dir)
        kb = os.path.getsize(path) / 1024.0
        print("  %-6s  %-38s %7.0f kB" % (number, title, kb))
        made.append(path)

    print("-" * 62)
    obj = os.path.join(out_dir, "model", "torus-office.obj")
    mtl = os.path.join(out_dir, "model", "torus-office.mtl")
    m = model3d.export(obj, mtl)
    print("  MESH    %-38s %7.0f kB" % (
        "%d faces, %d vertices" % (m.face_count, len(m.v)),
        os.path.getsize(obj) / 1024.0))
    sc = scad.write(os.path.join(out_dir, "model", "torus-office.scad"))
    print("  SCAD    %-38s %7.0f kB" % ("parametric source", os.path.getsize(sc) / 1024.0))
    vw = viewer.write(os.path.join(out_dir, "model", "viewer.html"))
    print("  VIEWER  %-38s %7.0f kB" % ("self-contained WebGL", os.path.getsize(vw) / 1024.0))

    print("-" * 62)
    print("  GIA %s m²   |   %d workstations   |   %d sheets   |   %.1fs" % (
        "{:,.0f}".format(PG.gia(0) + PG.gia(1)).replace(",", " "),
        PG.desks(0)[1] + PG.desks(1)[1], len(TASKS), time.time() - t0))
    return made


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "output")
