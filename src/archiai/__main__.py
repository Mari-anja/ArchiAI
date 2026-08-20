"""Try the engine without running anything.

    python -m archiai "a 6 storey office of 11000 m2 with a courtyard"

One command, one folder: every drawing, the model, the views, the whole set as
one PDF, and a page you can open. No server, no keys, no dependencies beyond
the standard library.
"""

import argparse
import json
import os
import sys
import time

from .engine import brief as B
from .engine import geom2d as G
from .engine import layout as L
from .engine import massing as M
from .engine import pdf as PDF
from .engine import project as PJ
from .engine import trace as T
from .engine import view as VW
from .engine import webpage as WEB


DEFAULT_VIEWS = [("aerial-ne", "Site aerial"), ("entrance", "Arrival")]


def _slug(s):
    keep = [c.lower() if c.isalnum() else "-" for c in (s or "project")]
    out = "".join(keep).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out[:48] or "project"


def _fmt(v):
    return "{:,.0f}".format(v).replace(",", " ")


def build_project(args):
    """Whichever way the building was described, one Project comes back."""
    if args.image:
        with open(args.image, "rb") as fh:
            data = fh.read()
        region = T.from_png(data, area_m2=args.area, width_m=args.width)
        name = args.name or os.path.splitext(os.path.basename(args.image))[0]
        return _from_region(region, args, name), None
    if args.footprint:
        with open(args.footprint) as fh:
            f = json.load(fh)
        region = G.Region([tuple(p) for p in f["outer"]],
                          [[tuple(p) for p in h] for h in f.get("holes", [])])
        return _from_region(region, args, args.name or "Drawn footprint"), None
    spec, massing, brf = B.from_text(args.brief)
    info = {"number": args.number, "name": (args.name or spec.name).upper(),
            "subtitle": args.brief}
    return PJ.Project(massing, brf, info), spec


MAX_AREA = 400000.0


def _from_region(region, args, name):
    faults = G.problems(region, max_area=MAX_AREA)
    if faults:
        raise ValueError(faults[0])
    d = B.USE_DEFAULTS.get(args.use, B.USE_DEFAULTS["office"])
    massing = M.Extrusion(region, storeys=args.storeys,
                          floor_to_floor=args.floor_to_floor)
    brf = L.Brief(use=args.use, daylight_depth=d["daylight"],
                  corridor_w=d["corridor"], room_width=d["room_w"],
                  entrance_azimuth=args.entrance, name=name)
    brf.accommodation = B.ACCOMMODATION.get(args.use, B.ACCOMMODATION["office"])
    return PJ.Project(massing, brf,
                      {"number": args.number, "name": name.upper(),
                       "subtitle": "%d storeys" % args.storeys})


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m archiai",
        description="Turn a brief, an outline or a sketch into a complete "
                    "architectural project.")
    ap.add_argument("brief", nargs="?",
                    help='what to build, in words: "a 6 storey office of '
                         '11000 m2 with a courtyard"')
    ap.add_argument("--image", metavar="FILE",
                    help="a PNG of a sketched outline to trace instead")
    ap.add_argument("--footprint", metavar="FILE",
                    help='JSON: {"outer": [[x,y],...], "holes": [...]} in metres')
    ap.add_argument("--out", default="output", metavar="DIR",
                    help="where to put it (default: output)")
    ap.add_argument("--storeys", type=int, default=3,
                    help="for --image and --footprint (default: 3)")
    ap.add_argument("--area", type=float, default=None,
                    help="for --image: floor area of one storey, m2")
    ap.add_argument("--width", type=float, default=None,
                    help="for --image: overall width in metres")
    ap.add_argument("--use", default="office",
                    help="office, school, gallery, apartments, hotel, warehouse")
    ap.add_argument("--entrance", type=float, default=270.0,
                    help="direction the entrance faces, degrees (270 = south)")
    ap.add_argument("--floor-to-floor", type=float, default=3.9, dest="floor_to_floor")
    ap.add_argument("--name", default=None)
    ap.add_argument("--number", default="AAI-0001")
    ap.add_argument("--only", metavar="D", action="append",
                    help="one discipline only: architecture, structure, "
                         "electrical, mechanical, public_health, fire")
    ap.add_argument("--views", type=int, default=2,
                    help="how many views to render (default: 2, 0 for none)")
    ap.add_argument("--turntable", type=int, default=6,
                    help="frames in the page's turntable (default: 6)")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--no-page", action="store_true")
    args = ap.parse_args(argv)

    if not (args.brief or args.image or args.footprint):
        ap.error("give a brief in words, or --image, or --footprint")
    if args.image and not (args.area or args.width):
        ap.error("--image needs --area or --width so the outline can be scaled")

    t0 = time.time()
    try:
        project, spec = build_project(args)
    except (ValueError, OSError) as e:
        print("Could not build that: %s" % e, file=sys.stderr)
        return 2

    out = os.path.join(args.out, _slug(project.info.get("name")))
    os.makedirs(out, exist_ok=True)
    if spec and spec.assumptions:
        print("Assumed:")
        for a in spec.assumptions:
            print("  " + a)

    register = project.build(out, disciplines=args.only)
    print("%d sheets" % len(register))

    views = []
    for (name, title) in DEFAULT_VIEWS[:max(args.views, 0)]:
        svg = VW.render(project, name,
                        addons=("ground", "sky", "shadow", "context", "trees",
                                "cars", "people"), width=1600, height=1000)
        path = os.path.join(out, "views", "%s.svg" % name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(svg)
        views.append({"svg": svg, "title": title, "note": name})
    if views:
        print("%d views" % len(views))

    made = []
    if not args.no_pdf:
        pages = []
        for (_n, _t, _s, path) in register:
            with open(path) as fh:
                pages.append(fh.read())
        pages += [v["svg"] for v in views]
        pdf_path = os.path.join(out, "%s-drawings.pdf" % args.number)
        PDF.write(pages, pdf_path, title=project.info.get("name"))
        made.append(("PDF", pdf_path, len(pages)))
    if not args.no_page:
        page_path = os.path.join(out, "%s-project.html" % args.number)
        WEB.build(project, page_path, sheets=register, views=views,
                  turntable=max(args.turntable, 0))
        made.append(("Page", page_path, None))

    m = project.massing
    print("\n%s — %d storeys, %s m2, %.1f m tall"
          % (project.info.get("name"), len(m.levels), _fmt(m.gia()), m.height))
    for (what, path, n) in made:
        size = os.path.getsize(path) / 1e6
        extra = " (%d pages)" % n if n else ""
        print("  %-5s %s  %.1f MB%s" % (what, path, size, extra))
    print("  Sheets in %s" % os.path.join(out, "drawings"))
    print("\nDone in %.1f s. Open the page in a browser to look through it."
          % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
