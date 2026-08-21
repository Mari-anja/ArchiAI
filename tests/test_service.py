"""Service tests. Run with:  PYTHONPATH=src python3 -m pytest tests -q"""

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ARCHIAI_STORAGE", "local")
os.environ.setdefault("ARCHIAI_LOCAL_ROOT", tempfile.mkdtemp(prefix="archiai-test-"))

from archiai.service.app import app          # noqa: E402
from archiai.engine import brief as B        # noqa: E402
from archiai.engine import geom2d as G       # noqa: E402
from archiai.engine import massing as M      # noqa: E402
from archiai.engine import layout as L       # noqa: E402
from archiai.engine import project as PJ     # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_parse_reports_assumptions():
    r = client.post("/v1/parse", json={"brief": "a research lab"})
    body = r.json()
    assert r.status_code == 200
    assert body["spec"]["use"] == "laboratory"
    assert len(body["assumptions"]) >= 3, "unstated fields must be reported"
    assert body["estimated_cost_units"] > 0


def test_parse_reads_what_was_stated():
    r = client.post("/v1/parse", json={
        "brief": "a five-storey school around a courtyard, 9000 sqm, entrance from the west"})
    s = r.json()["spec"]
    assert (s["use"], s["shape"], s["storeys"]) == ("school", "courtyard", 5)
    assert s["area_m2"] == 9000.0 and s["entrance_azimuth"] == 180.0
    assert r.json()["assumptions"] == []


def test_generate_from_brief_hits_the_target_area():
    r = client.post("/v1/generate", json={
        "brief": "a four-storey office around a courtyard, 6000 m2",
        "project_id": "p-1"})
    assert r.status_code == 200
    d = r.json()
    gia = d["manifest"]["project"]["gia_m2"]
    assert abs(gia - 6000) / 6000 < 0.02, "GIA should land within 2%% of the brief"
    kinds = [a["kind"] for a in d["assets"]]
    assert "model" in kinds and "manifest" in kinds
    assert d["cost_units"] > 0 and d["duration_ms"] >= 0


def test_the_set_covers_every_discipline():
    r = client.post("/v1/generate", json={
        "brief": "a four-storey office around a courtyard, 6000 m2"})
    sheets = [a for a in r.json()["assets"] if a["kind"] == "drawing"]
    got = {a["meta"]["discipline"] for a in sheets}
    assert got == {"architectural", "structural", "electrical", "mechanical",
                   "public_health", "fire"}, got
    numbers = {a["number"] for a in sheets}
    for required in ("A-000", "A-010", "A-140", "A-200", "A-300", "A-700",
                     "A-800", "S-010", "P-100"):
        assert required in numbers, "missing %s" % required
    # one plan, ceiling, power, lighting, ventilation and fire plan per storey
    for prefix, count in (("A-1", 4 + 4 + 1), ("E-1", 4), ("E-2", 4),
                          ("M-1", 4), ("FS-1", 4), ("S-1", 4)):
        n = len([x for x in numbers if x.startswith(prefix)])
        assert n == count, "%s: expected %d, got %d" % (prefix, count, n)


def test_disciplines_can_be_filtered():
    r = client.post("/v1/generate", json={
        "brief": "a two-storey office, 1500 m2",
        "disciplines": ["architecture"], "include_model": False})
    sheets = [a for a in r.json()["assets"] if a["kind"] == "drawing"]
    assert {a["meta"]["discipline"] for a in sheets} == {"architectural"}


def test_generate_from_drawn_footprint():
    poly = [[0, 0], [54, 0], [54, 20], [30, 20], [30, 38], [0, 38]]
    r = client.post("/v1/generate", json={
        "footprint": {"outer": poly, "storeys": 3, "use": "gallery"},
        "include_model": False})
    assert r.status_code == 200
    d = r.json()
    assert d["manifest"]["project"]["storeys"] == 3
    assert all(a["kind"] != "model" for a in d["assets"])


def test_manifest_room_schedule_is_populated():
    r = client.post("/v1/generate", json={"brief": "a three-storey office, 3000 m2"})
    levels = r.json()["manifest"]["levels"]
    assert len(levels) == 3
    for lv in levels:
        assert lv["room_count"] > 0
        assert all(rm["area_m2"] > 0 for rm in lv["rooms"])
        named = {rm["name"] for rm in lv["rooms"]}
        assert len(named) > 1, "the schedule should be programmed, not uniform"


def test_idempotency_replays_the_same_generation():
    body = {"brief": "a two-storey office, 1200 m2", "idempotency_key": "k-1"}
    a = client.post("/v1/generate", json=body).json()
    b = client.post("/v1/generate", json={"brief": "totally different",
                                          "idempotency_key": "k-1"}).json()
    assert a["generation_id"] == b["generation_id"]


@pytest.mark.parametrize("body,code", [
    ({}, 422),
    ({"brief": "x", "spec": {"use": "office"}}, 422),
    ({"footprint": {"outer": [[0, 0], [1, 0], [1, 1]]}}, 422),
    ({"spec": {"storeys": 900}}, 422),
    ({"footprint": {"outer": [[0, 0], [1, 0]]}}, 422),
])
def test_bad_requests_are_refused(body, code):
    assert client.post("/v1/generate", json=body).status_code == code


def test_file_serving_rejects_traversal():
    assert client.get("/files/../../etc/passwd").status_code == 404


# --- engine invariants that the service depends on -------------------------

FOOTPRINTS = {
    "courtyard": G.Region(G.rounded_rect(76, 54, 9), [G.rounded_rect(34, 22, 6)]),
    "L-shape": G.Region(G.l_shape(72, 52, 30, 22)),
    "slab": G.Region(G.rectangle(64, 18)),
    "tower": G.Region(G.rectangle(36, 36)),
    "hexagon": G.Region(G.regular_polygon(6, 44), [G.regular_polygon(6, 18)]),
    "ring": G.Region(G.circle(46, 120), [G.circle(26, 120)]),
}


@pytest.mark.parametrize("name", sorted(FOOTPRINTS))
def test_allocation_accounts_for_the_plate(name):
    """Rooms plus circulation should account for the plate less its walls."""
    b = M.Extrusion(FOOTPRINTS[name], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
    fp = p.floorplans[0]
    used = sum(r.area for r in fp.rooms) + fp.circulation_area
    ratio = used / fp.plate.area
    # A re-entrant corner mitres two bands together and they overlap slightly;
    # 1.5% is the observed worst case and is a drawing artefact, not a plan.
    assert 0.90 <= ratio <= 1.015, "%s accounted %.1f%%" % (name, 100 * ratio)


@pytest.mark.parametrize("name", sorted(FOOTPRINTS))
def test_no_room_is_larger_than_its_floor(name):
    b = M.Extrusion(FOOTPRINTS[name], storeys=2, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
    for fp in p.floorplans:
        for r in fp.rooms:
            assert r.area < fp.plate.area * 0.5, "%s: runaway cell %.0f m2" % (name, r.area)


def test_sections_and_elevations_are_non_degenerate():
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=4, floor_to_floor=3.9)
    sec = b.section((0, 0), (1, 0))
    assert len(sec.cut) >= 2 and sec.slabs
    el = b.silhouette(270)
    assert el.outline and len(el.outline[0][0]) > 10


# --- services engine -------------------------------------------------------

def test_services_quantities_are_plausible():
    from archiai.engine import services as SV
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="svc"), {"number": "T"})
    fp = p.floorplans[0]
    t = SV.totals(SV.for_floor(fp))
    area = fp.plate.area
    # a modern LED office lands between 4 and 12 W/m2
    density = t["lighting_load_kw"] * 1000.0 / area
    assert 3.0 <= density <= 14.0, "lighting %.1f W/m2" % density
    # one sprinkler head covers no more than its rated area
    assert t["sprinklers"] >= area / SV.SPRINKLER_COVERAGE * 0.6
    assert t["occupants"] > 0 and t["fresh_air_lps"] > 0


def test_structure_and_foundations_are_consistent():
    from archiai.engine import services as SV
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=6, floor_to_floor=3.6)
    p = PJ.Project(b, L.Brief(name="str"), {"number": "T"})
    st = SV.structure(p, 0)
    fd = SV.foundations(p)
    assert st["storeys_above"] == 6
    assert st["column_load_kn"] > 0
    # pad area must satisfy the bearing pressure it was sized against
    assert fd["pad_m"] ** 2 * fd["bearing_kpa"] >= fd["load_kn"] * 0.98
    assert 150 <= st["slab_depth_mm"] <= 600


def test_escape_distances_are_reported_against_the_limit():
    from archiai.engine import services as SV
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=2, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="fire"), {"number": "T"})
    e = SV.escape(p.floorplans[0])
    assert e.routes and e.worst > 0
    assert e.compliant == (e.worst <= e.limit)
    assert all(r["travel_m"] >= r["direct_m"] for r in e.routes)


def test_roof_plant_stands_on_the_roof():
    from archiai.engine import services as SV
    for name in ("courtyard", "hexagon", "ring", "L-shape"):
        b = M.Extrusion(FOOTPRINTS[name], storeys=2, floor_to_floor=3.9)
        p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
        rf = SV.roof(p)
        top = p.massing.levels[-1].plate
        assert all(top.contains(q) for q in rf["plant"]), \
            "%s: plant enclosure is off the roof" % name
        assert len(rf["outlets"]) >= 2


# --- doors and windows -----------------------------------------------------

def test_every_enclosed_room_gets_a_door():
    from archiai.engine import openings as OP
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="doors"), {"number": "T"})
    for i in range(3):
        fp = p.floorplans[i]
        want = [r for r in fp.rooms if r.cat in OP.ENCLOSED]
        got = OP.doors(p, i)
        rooms_served = set(id(d.room) for d in got if d.room is not None)
        assert len(rooms_served) == len(want), \
            "level %d: %d rooms, %d served" % (i, len(want), len(rooms_served))
        # a stair core is served twice: one FD60S pair and one FD30S single
        cores = [r for r in fp.rooms if r.cat == "core"]
        assert sum(1 for d in got if d.mark == "D4") == len(cores)
        assert sum(1 for d in got if d.mark == "D3") >= len(cores)


def test_doors_sit_on_the_room_they_serve():
    from archiai.engine import openings as OP
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=2, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="pos"), {"number": "T"})
    for d in OP.doors(p, 0):
        if d.room is None:
            continue
        # the door sits on the boundary, so it is within a hair of the ring
        near = L.nearest_on_ring(d.point, d.room.ring)[3]
        assert near < 0.05, "door %s is %.3f m off its room" % (d.mark, near)
        # and its normal points into the room, not out of it
        inward = (d.point[0] + d.normal[0] * 0.35,
                  d.point[1] + d.normal[1] * 0.35)
        assert G.point_in_ring(inward, d.room.ring), \
            "door %s swings out of its room" % d.mark


def test_window_counts_match_the_bays_and_the_glazed_area():
    from archiai.engine import openings as OP
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=4, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="win"), {"number": "T"})
    wins = OP.windows(p)
    assert wins, "no windows derived"
    tot = OP.totals(p)
    assert tot["windows"] == sum(w["count"] for w in wins)
    # the schedule area must equal the sum of the units it lists
    area = sum(w["count"] * w["width_mm"] * w["height_mm"] / 1e6 for w in wins)
    assert abs(area - tot["glazed_area_m2"]) < 0.5
    # glazing cannot exceed the facade it sits in
    facade = G.perimeter(b.footprint().outer) * b.height
    assert 0.05 < tot["glazed_area_m2"] / facade < 0.75
    # every unit is a buildable size
    for w in wins:
        assert 500 <= w["width_mm"] <= 3000
        assert 600 <= w["height_mm"] <= 4000


def test_schedule_matrices_agree_with_the_schedule():
    from archiai.engine import openings as OP
    b = M.Extrusion(FOOTPRINTS["hexagon"], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="matrix"), {"number": "T"})
    ds = {d["mark"]: d["count"] for d in OP.door_schedule(p)}
    for mark, per_level in OP.door_matrix(p):
        assert sum(per_level.values()) == ds[mark]
    ws = {w["mark"]: w["count"] for w in OP.windows(p)}
    for mark, per_face in OP.window_matrix(p):
        assert sum(per_face.values()) == ws[mark]


def test_door_and_window_sheet_is_produced_for_every_shape():
    from archiai.engine.draw_schedules import door_window_sheet
    with tempfile.TemporaryDirectory() as d:
        for name in ("slab", "courtyard", "hexagon", "ring", "L-shape"):
            b = M.Extrusion(FOOTPRINTS[name], storeys=2, floor_to_floor=3.9)
            p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
            out = os.path.join(d, "%s.svg" % name)
            door_window_sheet(p, out)
            svg = open(out).read()
            assert "DOOR SCHEDULE" in svg and "WINDOW SCHEDULE" in svg
            assert "DOOR KEY PLAN" in svg
            assert len(svg) > 8000


# --- construction build-ups and details -------------------------------------

def test_build_ups_match_the_model_they_are_cut_from():
    from archiai.engine import buildup as BU
    for wall_t in (0.28, 0.35, 0.45):
        b = M.Extrusion(FOOTPRINTS["slab"], storeys=4, floor_to_floor=3.9)
        p = PJ.Project(b, L.Brief(name="bu", wall_t=wall_t), {"number": "T"})
        w = BU.external_wall(p)
        assert all(l.t > 0 for l in w), "a layer came out at zero thickness"
        # the drawn wall is the wall the plan cuts, to the nearest millimetre
        assert abs(sum(l.t for l in w) - wall_t * 1000.0) <= 2.0
        # the floor zone plus the clear height is the floor to floor height
        flr = BU.upper_floor(p)
        zone = sum(l.t for l in flr)
        assert abs(zone + 2700.0 - 3900.0) <= 2.0, "zone %.0f" % zone
        # and the slab in the build-up is the slab the structure sized
        from archiai.engine import services as SV
        assert flr[2].t == SV.structure(p, 0)["slab_depth_mm"]


def test_u_values_are_in_a_buildable_range():
    from archiai.engine import buildup as BU
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="u"), {"number": "T"})
    sm = BU.summary(p)
    assert 0.10 <= sm["wall"]["u"] <= 0.45
    assert 0.08 <= sm["roof"]["u"] <= 0.30
    assert 0.08 <= sm["ground"]["u"] <= 0.35
    # a roof carries more insulation than a wall, so it performs better
    assert sm["roof"]["u"] < sm["wall"]["u"]


def test_details_and_wall_section_are_drawn_for_every_shape():
    from archiai.engine import draw_details as DD
    with tempfile.TemporaryDirectory() as d:
        for name in ("slab", "courtyard", "hexagon", "ring", "L-shape"):
            b = M.Extrusion(FOOTPRINTS[name], storeys=3, floor_to_floor=3.9)
            p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
            det = os.path.join(d, "%s-500.svg" % name)
            sec = os.path.join(d, "%s-400.svg" % name)
            DD.details_sheet(p, det)
            DD.wall_section_sheet(p, sec)
            a = open(det).read()
            for title in ("FOUNDATION AND GROUND FLOOR JUNCTION",
                          "INTERMEDIATE FLOOR EDGE AND SPANDREL",
                          "PARAPET AND ROOF EDGE", "CURTAIN WALL JAMB"):
                assert title in a, "%s: %s missing" % (name, title)
            c = open(sec).read()
            assert "BUILD-UPS" in c and "HEIGHTS" in c
            assert "WHERE THE SECTION IS CUT" in c
            assert len(a) > 20000 and len(c) > 12000


def test_the_wall_section_follows_a_curved_envelope():
    """A leaning or curved facade must be drawn as it is, not straightened."""
    import math
    from archiai.engine import massing as MM
    from archiai.engine import draw_details as DD
    prof = [(30.0 + 7.5 * math.cos(math.radians(a)),
             2.1 + 7.5 * math.sin(math.radians(a))) for a in range(-160, 161, 5)]

    def plate(z):
        dx = math.sqrt(7.5 ** 2 - (z - 2.1) ** 2)
        return G.Region(G.circle(30.0 + dx, 96),
                        [G.circle(max(30.0 - dx, 0.5), 96)])

    b = MM.Revolve(prof, plates=[(0.0, plate(0.0)), (4.2, plate(4.2))])
    p = PJ.Project(b, L.Brief(name="revolve"), {"number": "T"})
    faces = [b.extent_at(z, (1.0, 0.0))[1] for z in (0.3, 2.1, 5.0, 8.0)]
    assert max(faces) - min(faces) > 1.0, "this envelope should not be straight"
    # the drawn wall must move with the envelope, not stand straight
    from archiai.svgkit import Sheet, View
    from archiai.engine import buildup as BU
    sh = Sheet("A-400", "t", "1:50", "A1", "", {"number": "T"})
    v = View(sh, 50, 200.0, 400.0)
    before = len(sh.body)
    DD.swept_wall(sh, v, BU.external_wall(p),
                  lambda z: b.extent_at(min(max(z, 0.05), b.height - 0.05),
                                        (1.0, 0.0))[1],
                  0.0, b.height)
    xs = []
    for tag in sh.body[before:]:
        for chunk in tag.split('d="')[1:]:
            for tok in chunk.split('"')[0].replace("M", " ").replace("L", " ").split():
                try:
                    xs.append(float(tok))
                except ValueError:
                    pass
    span = (max(faces) - min(faces)) * 1000.0 / 50.0        # mm on the sheet
    drawn = max(xs[::2]) - min(xs[::2])
    assert drawn > span * 0.8, "facade drawn %.1f mm wide, expected %.1f" % (
        drawn, span)

    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "rev.svg")
        DD.wall_section_sheet(p, out)
        assert len(open(out).read()) > 12000


# --- tracing an uploaded sketch --------------------------------------------

def _png(rows):
    """Encode a greyscale grid, so the tests make their own sketches."""
    import struct, zlib
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(kind, body):
        c = kind + body
        return (struct.pack(">I", len(body)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _sketch(polys, w=560, h=420, wobble=2.0, width=3, seed=1):
    """Ink a wobbly outline the way a hand would draw it."""
    import math, random
    rnd = random.Random(seed)
    img = [[240] * w for _ in range(h)]
    for _ in range(200):                                   # paper grain
        img[rnd.randrange(h)][rnd.randrange(w)] = rnd.randrange(160, 225)
    for pts in polys:
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            steps = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1])))
            for s in range(steps + 1):
                t = s / steps
                x = a[0] + (b[0] - a[0]) * t + rnd.uniform(-wobble, wobble)
                y = a[1] + (b[1] - a[1]) * t + rnd.uniform(-wobble, wobble)
                for dy in range(-width, width + 1):
                    for dx in range(-width, width + 1):
                        if dx * dx + dy * dy > width * width:
                            continue
                        xx, yy = int(x) + dx, int(y) + dy
                        if 0 <= xx < w and 0 <= yy < h:
                            img[yy][xx] = 28
    return _png(img)


def _corners(ring):
    import math
    n = len(ring)
    out = []
    for i in range(n):
        a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
        d0 = math.atan2(b[1] - a[1], b[0] - a[0])
        d1 = math.atan2(c[1] - b[1], c[0] - b[0])
        out.append(abs((math.degrees(d1 - d0) + 180.0) % 360.0 - 180.0))
    return out


def test_a_hand_drawn_rectangle_traces_back_to_a_rectangle():
    import math
    from archiai.engine import trace as T
    a = math.radians(5.0)                                  # drawn off square

    def rot(p):
        x, y = p[0] - 280, p[1] - 210
        return (280 + x * math.cos(a) - y * math.sin(a),
                210 + x * math.sin(a) + y * math.cos(a))

    png = _sketch([[rot(p) for p in ((70, 90), (490, 90), (490, 330), (70, 330))]])
    r = T.from_png(png, area_m2=2400.0)
    assert len(r.outer) == 4, "traced %d corners, expected 4" % len(r.outer)
    assert abs(r.area - 2400.0) < 1.0
    for turn in _corners(r.outer):
        assert abs(turn - 90.0) < 3.0, "corner came out at %.1f degrees" % turn
    x0, y0, x1, y1 = r.bbox()
    assert 1.5 < (x1 - x0) / (y1 - y0) < 2.1               # 420 x 240 drawn


def test_a_courtyard_in_the_sketch_survives_as_a_hole():
    from archiai.engine import trace as T
    png = _sketch([[(60, 60), (500, 60), (500, 360), (60, 360)],
                   [(200, 150), (360, 150), (360, 270), (200, 270)]])
    r = T.from_png(png, area_m2=3000.0)
    assert len(r.holes) == 1, "%d holes traced" % len(r.holes)
    hole = abs(G.signed_area(r.holes[0]))
    assert 200.0 < hole < 1400.0, "courtyard came out at %.0f m2" % hole
    assert abs(r.area - 3000.0) < 1.0                      # area is net of it


def test_a_filled_shape_reads_the_same_as_an_outline():
    from archiai.engine import trace as T
    solid = [[240] * 560 for _ in range(420)]
    for y in range(60, 360):
        for x in range(60, 500):
            solid[y][x] = 24
    for y in range(150, 270):                              # a painted courtyard
        for x in range(200, 360):
            solid[y][x] = 240
    r = T.from_png(_png(solid), area_m2=3000.0)
    assert len(r.holes) == 1
    assert len(r.outer) == 4
    assert abs(r.area - 3000.0) < 1.0


def test_a_curve_is_not_straightened_into_a_box():
    """Snapping is for edges that were meant to be square, not for curves."""
    import math
    from archiai.engine import trace as T
    blob = [(280 + 200 * math.cos(t * math.pi / 16),
             210 + 140 * math.sin(t * math.pi / 16)) for t in range(32)]
    r = T.from_png(_sketch([blob], wobble=1.2), area_m2=2000.0)
    assert len(r.outer) >= 10, "a curve collapsed to %d corners" % len(r.outer)
    square = sum(1 for t in _corners(r.outer) if abs(t - 90.0) < 5.0)
    assert square <= 2, "%d right angles invented on a curve" % square


def test_tracing_is_deterministic_and_scales_as_asked():
    from archiai.engine import trace as T
    png = _sketch([[(70, 80), (480, 80), (480, 340), (70, 340)]], seed=4)
    a = T.from_png(png, area_m2=1800.0)
    b = T.from_png(png, area_m2=1800.0)
    assert [tuple(p) for p in a.outer] == [tuple(p) for p in b.outer]
    c = T.from_png(png, width_m=90.0)
    x0, y0, x1, y1 = c.bbox()
    assert abs(max(x1 - x0, y1 - y0) - 90.0) < 0.2


def test_the_traced_outline_builds_the_same_building_when_posted_back():
    """What /v1/trace shows is what /v1/generate builds."""
    png = _sketch([[(70, 80), (480, 80), (480, 340), (70, 340)]], seed=6)
    import base64
    payload = base64.b64encode(png).decode()
    t = client.post("/v1/trace", json={"image": {"data": payload,
                                                 "area_m2": 2200.0}})
    assert t.status_code == 200, t.text
    outline = t.json()

    direct = client.post("/v1/generate", json={
        "image": {"data": payload, "area_m2": 2200.0, "storeys": 2},
        "number": "TR1"})
    posted = client.post("/v1/generate", json={
        "footprint": {"outer": outline["outer"], "holes": outline["holes"],
                      "storeys": 2},
        "number": "TR2"})
    assert direct.status_code == 200 and posted.status_code == 200
    a = direct.json()["manifest"]["project"]
    b = posted.json()["manifest"]["project"]
    assert abs(a["gia_m2"] - b["gia_m2"]) < 1.0
    assert abs(a["footprint_m2"] - b["footprint_m2"]) < 1.0
    assert len(direct.json()["assets"]) == len(posted.json()["assets"])


def test_uploads_are_refused_clearly_when_they_are_not_usable():
    import base64
    bad = client.post("/v1/trace", json={"image": {"data": "not base64!!"}})
    assert bad.status_code == 422 and "base64" in bad.json()["detail"]

    blank = _png([[245] * 80 for _ in range(60)])
    r = client.post("/v1/trace", json={
        "image": {"data": base64.b64encode(blank).decode(), "area_m2": 500}})
    assert r.status_code == 422

    # a broken image must come back as a sentence, whether or not the server
    # has Pillow installed to read anything beyond PNG
    jpeg = base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 64).decode()
    r = client.post("/v1/trace", json={"image": {"data": jpeg}})
    assert r.status_code == 422
    assert "PNG" in r.json()["detail"]

    truncated = base64.b64encode(_sketch([[(20, 20), (200, 20), (200, 150),
                                           (20, 150)]])[:400]).decode()
    r = client.post("/v1/trace", json={"image": {"data": truncated}})
    assert r.status_code == 422

    two = client.post("/v1/generate", json={"brief": "an office",
                                            "image": {"data": "aGk="}})
    assert two.status_code == 422


# --- views and renders ------------------------------------------------------

def test_the_sun_is_where_the_sun_is():
    from archiai.engine import view as V
    _v, alt, az = V.sun(51.5, 172, 12.0)          # London, midsummer noon
    assert 60.0 < alt < 64.0 and abs(az - 180.0) < 1.0
    _v, alt, az = V.sun(51.5, 355, 12.0)          # midwinter noon
    assert 13.0 < alt < 17.0 and abs(az - 180.0) < 1.0
    _v, alt, az = V.sun(-33.9, 355, 12.0)         # Sydney, their midsummer
    assert alt > 75.0 and (az < 5.0 or az > 355.0)
    _v, alt, _az = V.sun(51.5, 172, 1.0)          # the middle of the night
    assert alt < 0.0


def test_the_shadow_falls_away_from_the_sun():
    from archiai.engine import view as V
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=4, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="sun"), {"number": "T"})
    cx, cy = G.centroid(b.footprint().outer)
    for hour, ex, ey in ((9.0, -1.0, 0.0), (14.0, 1.0, 0.0), (12.0, 0.0, 1.0)):
        sd, alt, _az = V.sun(51.5, 172, hour)
        quads = V.shadow_quads(p, sd, alt)
        assert quads, "no shadow at %.0f:00" % hour
        pts = [q for quad in quads for q in quad]
        mx = sum(q[0] for q in pts) / len(pts) - cx
        my = sum(q[1] for q in pts) / len(pts) - cy
        if ex:
            assert mx * ex > 0, "shadow at %.0f:00 fell the wrong way" % hour
        if ey:
            assert my * ey > 0, "shadow at %.0f:00 fell the wrong way" % hour
        assert all(abs(q[2]) < 0.05 for q in pts), "shadow left the ground"
    # and none at night
    sd, alt, _az = V.sun(51.5, 172, 1.0)
    assert V.shadow_quads(p, sd, alt) == []


def test_every_named_view_renders_for_every_shape():
    from archiai.engine import view as V
    for name in ("slab", "courtyard", "tower", "hexagon"):
        b = M.Extrusion(FOOTPRINTS[name], storeys=3, floor_to_floor=3.9)
        p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
        for v in V.NAMED:
            svg = V.render(p, v, width=640, height=400)
            assert svg.startswith("<svg") and svg.endswith("</svg>")
            assert svg.count("<path") > 30, "%s/%s drew %d paths" % (
                name, v, svg.count("<path"))


def test_a_view_is_the_same_picture_every_time():
    """Determinism is what lets a view be asked for again later."""
    from archiai.engine import view as V
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=4, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="det"), {"number": "T"})
    kw = dict(addons=("ground", "sky", "shadow", "context", "trees", "cars",
                      "people"), width=800, height=500)
    assert V.render(p, "aerial-ne", **kw) == V.render(p, "aerial-ne", **kw)
    q = PJ.Project(M.Extrusion(FOOTPRINTS["courtyard"], storeys=4,
                               floor_to_floor=3.9),
                   L.Brief(name="det"), {"number": "T"})
    assert V.render(p, "aerial-ne", **kw) == V.render(q, "aerial-ne", **kw)


def test_cameras_stand_outside_the_building_and_frame_it():
    from archiai.engine import view as V
    for name in ("slab", "courtyard", "tower"):
        for storeys in (1, 4, 14):
            b = M.Extrusion(FOOTPRINTS[name], storeys=storeys,
                            floor_to_floor=3.9)
            p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
            plate = b.footprint()
            for v in ("entrance", "eye-south", "eye-east", "aerial-ne",
                      "aerial-sw"):
                cam = V.camera(p, v, width=1600, height=1000)
                assert not plate.contains((cam.eye[0], cam.eye[1])), \
                    "%s/%d: the %s camera is inside the building" % (
                        name, storeys, v)
                # the building fits the frame
                x0, y0, x1, y1 = plate.bbox()
                corners = [(x, y, z) for x in (x0, x1) for y in (y0, y1)
                           for z in (0.0, b.height)]
                for c in corners:
                    cc = cam.to_cam(c)
                    if cc[2] < cam.NEAR:
                        continue
                    px, py = cam.project(cc)
                    assert -80 <= px <= cam.width + 80, \
                        "%s/%d/%s: %.0f off frame" % (name, storeys, v, px)
                    assert -80 <= py <= cam.height + 80, \
                        "%s/%d/%s: %.0f off frame" % (name, storeys, v, py)


def test_a_courtyard_view_stands_in_the_courtyard():
    from archiai.engine import view as V
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=4, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="court"), {"number": "T"})
    cam = V.camera(p, "courtyard")
    hole = b.footprint().holes[0]
    assert G.point_in_ring((cam.eye[0], cam.eye[1]), hole)
    assert 1.0 < cam.eye[2] < 3.0
    # a building without one falls back to a view that exists
    solid_b = M.Extrusion(FOOTPRINTS["slab"], storeys=2, floor_to_floor=3.9)
    q = PJ.Project(solid_b, L.Brief(name="solid"), {"number": "T"})
    assert V.render(q, "courtyard", width=640, height=400).startswith("<svg")


def test_unknown_views_styles_and_addons_are_refused():
    from archiai.engine import view as V
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=2, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="bad"), {"number": "T"})
    for kw in ({"name": "from-the-moon"}, {"style": "photoreal"},
               {"addons": ("ground", "unicorns")}):
        with pytest.raises(ValueError):
            V.render(p, **kw)


def test_the_view_endpoint_returns_pictures_of_the_same_building():
    r = client.post("/v1/view", json={
        "brief": "a 5 storey office of 8000 m2 with a courtyard",
        "views": [{"name": "aerial-ne", "width": 800, "height": 500},
                  {"name": "entrance", "width": 800, "height": 500,
                   "hour": 9.0, "label": "Arrival"},
                  {"name": "axo", "style": "line", "addons": [],
                   "width": 800, "height": 500}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["assets"]) == 3
    assert all(a["kind"] == "view" for a in body["assets"])
    assert body["assets"][1]["title"] == "Arrival"
    assert all(a["content_type"] == "image/svg+xml" for a in body["assets"])
    sun = body["manifest"]["views"][1]["sun"]
    assert sun["hour"] == 9.0 and sun["altitude_deg"] > 0

    # the same brief through /v1/generate describes the same building
    g = client.post("/v1/generate", json={
        "brief": "a 5 storey office of 8000 m2 with a courtyard",
        "disciplines": ["architecture"]})
    assert abs(g.json()["manifest"]["project"]["gia_m2"]
               - body["manifest"]["project"]["gia_m2"]) < 1.0

    bad = client.post("/v1/view", json={"brief": "an office",
                                        "views": [{"name": "nowhere"}]})
    assert bad.status_code == 422
    none = client.post("/v1/view", json={"brief": "an office", "views": []})
    assert none.status_code == 422


def test_generate_can_include_views_with_the_drawings():
    r = client.post("/v1/generate", json={
        "brief": "a 3 storey school of 4000 m2",
        "disciplines": ["architecture"],
        "views": [{"name": "aerial-nw", "width": 640, "height": 400},
                  {"name": "eye-south", "width": 640, "height": 400}]})
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = [a["kind"] for a in body["assets"]]
    assert kinds.count("view") == 2 and kinds.count("drawing") > 5
    assert len(body["manifest"]["views"]) == 2
    assert body["manifest"]["views"][0]["projection"] == "perspective"


# --- changing your mind -----------------------------------------------------

def _generate(**body):
    body.setdefault("disciplines", ["architecture"])
    r = client.post("/v1/generate", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _revise(source, changes, **extra):
    body = {"source": source, "changes": changes,
            "disciplines": ["architecture"]}
    body.update(extra)
    return client.post("/v1/revise", json=body)


def test_every_generation_records_what_made_it():
    """A project you cannot rebuild is a project you cannot revise."""
    from archiai.engine import revise as RV
    text = _generate(brief="a 4 storey office of 5000 m2 with a courtyard")
    src = text["manifest"]["source"]
    assert src["kind"] == "spec" and src["revision"] == "P01"
    assert src["spec"]["storeys"] == 4 and src["brief_text"]
    assert src["result"]["gia_m2"] == text["manifest"]["project"]["gia_m2"]

    drawn = _generate(footprint={"outer": [[0, 0], [60, 0], [60, 30], [0, 30]],
                                 "storeys": 2})
    d = drawn["manifest"]["source"]
    assert d["kind"] == "footprint" and len(d["footprint"]["outer"]) == 4
    assert d["traced"] is False

    png = _sketch([[(70, 80), (480, 80), (480, 340), (70, 340)]], seed=9)
    import base64
    up = _generate(image={"data": base64.b64encode(png).decode(),
                          "area_m2": 1800, "storeys": 3})
    u = up["manifest"]["source"]
    assert u["kind"] == "footprint" and u["traced"] is True

    # and the recorded source rebuilds the same building
    for m in (text, drawn, up):
        _spec, massing, _brf = RV.build(m["manifest"]["source"])
        assert abs(massing.gia() - m["manifest"]["project"]["gia_m2"]) < 1.0


def test_adding_storeys_makes_it_taller_not_thinner():
    """The obvious reading of 'two more storeys' is the one that happens."""
    base = _generate(brief="a 6 storey office of 12000 m2")
    src = base["manifest"]["source"]
    r = _revise(src, {"storeys": "+2"})
    assert r.status_code == 200, r.text
    after = r.json()["manifest"]["project"]
    before = base["manifest"]["project"]
    assert after["storeys"] == before["storeys"] + 2
    assert abs(after["footprint_m2"] - before["footprint_m2"]) < 30.0
    assert after["gia_m2"] > before["gia_m2"] * 1.25
    # unless the total area is set in the same breath, which wins
    r2 = _revise(src, {"storeys": "+2", "area_m2": 12000})
    kept = r2.json()["manifest"]["project"]
    assert abs(kept["gia_m2"] - before["gia_m2"]) < before["gia_m2"] * 0.05
    assert kept["footprint_m2"] < before["footprint_m2"] * 0.85


def test_a_revision_says_what_changed_and_measures_it():
    base = _generate(brief="a 5 storey office of 9000 m2 with a courtyard")
    r = _revise(base["manifest"]["source"],
                {"entrance": "north", "name": "Northgate"})
    assert r.status_code == 200, r.text
    man = r.json()["manifest"]
    assert man["project"]["revision"] == "P02"
    assert man["revision"]["of"] == "P01"
    assert any("north" in n.lower() for n in man["revision"]["changed"])
    assert any("Northgate" in n for n in man["revision"]["changed"])
    d = man["revision"]["measured"]
    assert d["before"]["gia_m2"] == base["manifest"]["project"]["gia_m2"]
    assert abs(d["delta"]["gia_m2"]) < 1.0          # turning it does not resize it
    assert man["project"]["name"] == "NORTHGATE"


def test_revisions_chain_and_step_their_number():
    src = _generate(brief="a 4 storey office of 6000 m2 with a courtyard"
                    )["manifest"]["source"]
    seen = ["P01"]
    for changes in ({"storeys": 5}, {"courtyard": "bigger"},
                    {"entrance": "east"}, {"floor_to_floor_m": "+0.3"}):
        r = _revise(src, changes)
        assert r.status_code == 200, "%s: %s" % (changes, r.text)
        man = r.json()["manifest"]
        src = man["source"]
        seen.append(man["project"]["revision"])
        assert src["result"]["gia_m2"] == man["project"]["gia_m2"]
    assert seen == ["P01", "P02", "P03", "P04", "P05"]


def test_editing_geometry_promotes_a_specified_shape_to_an_outline():
    """A shape family cannot say 'courtyard 30 percent bigger'; an outline can."""
    base = _generate(brief="a 4 storey office of 6000 m2 with a courtyard")
    src = base["manifest"]["source"]
    assert src["kind"] == "spec"
    r = _revise(src, {"courtyard": "+30%"})
    assert r.status_code == 200, r.text
    man = r.json()["manifest"]
    assert man["source"]["kind"] == "footprint"
    assert man["source"]["promoted_from"] == "courtyard"
    assert any("outline" in n for n in man["revision"]["changed"])
    assert man["project"]["gia_m2"] < base["manifest"]["project"]["gia_m2"]
    # and the courtyard really did grow
    hole_before = 0.0
    hole_after = sum(abs(G.signed_area([tuple(p) for p in h]))
                     for h in man["source"]["footprint"]["holes"])
    assert hole_after > 0
    # removing it entirely gives the floor area back
    gone = _revise(man["source"], {"courtyard": "none"})
    assert gone.status_code == 200
    assert not gone.json()["manifest"]["source"]["footprint"]["holes"]
    assert gone.json()["manifest"]["project"]["gia_m2"] > man["project"]["gia_m2"]


def test_changes_that_cannot_be_made_are_refused_in_plain_words():
    src = _generate(brief="a 3 storey office of 3000 m2")["manifest"]["source"]
    cases = [
        ({"storeys": 0}, "least"),
        ({"colour": "blue"}, "cannot change colour"),
        ({"storeys": 3}, "already"),
        ({}, None),
        ({"area_m2": "lots"}, "could not read"),
        ({"courtyard": "bigger"}, "courtyard"),      # this one has none
    ]
    for changes, needle in cases:
        r = _revise(src, changes)
        assert r.status_code == 422, "%s was accepted" % changes
        if needle:
            assert needle in r.json()["detail"], \
                "%s said %r" % (changes, r.json()["detail"])


def test_a_courtyard_cannot_eat_the_building():
    """A change that would leave no building around the courtyard is refused."""
    src = _generate(brief="a 3 storey office of 4000 m2 with a courtyard"
                    )["manifest"]["source"]
    grown = _revise(src, {"courtyard": "+20%"})
    assert grown.status_code == 200
    r = _revise(grown.json()["manifest"]["source"], {"courtyard": "+900%"})
    assert r.status_code == 422
    assert "building around it" in r.json()["detail"]


def test_a_revision_is_a_full_project_with_its_pictures():
    src = _generate(brief="a 3 storey school of 3500 m2")["manifest"]["source"]
    r = _revise(src, {"storeys": 4},
                parent_generation_id="gen-under-test",
                views=[{"name": "aerial-ne", "width": 640, "height": 400}])
    assert r.status_code == 200, r.text
    body = r.json()
    kinds = [a["kind"] for a in body["assets"]]
    assert kinds.count("drawing") > 5 and kinds.count("view") == 1
    assert kinds.count("model") == 2 and kinds.count("manifest") == 1
    assert body["manifest"]["revision"]["parent"] == "gen-under-test"
    # the drawings carry the new revision in their titleblock
    from archiai.service.config import settings
    sheet = next(a for a in body["assets"] if a["kind"] == "drawing")
    with open(os.path.join(settings.local_root, sheet["key"])) as fh:
        svg = fh.read()
    assert "P02" in svg and "P01" not in svg


# --- handing it to someone: the PDF ----------------------------------------

def _pdf_objects(data):
    """Every object body, keyed by number, so the file can be checked without
    a PDF library."""
    import re as _re
    out = {}
    for m in _re.finditer(rb"(\d+) 0 obj\r?\n(.*?)\r?\nendobj", data, _re.S):
        out[int(m.group(1))] = m.group(2)
    return out


def _pdf_check(data):
    """Structural sanity: a PDF that says it has objects it does not have will
    not open, and a viewer will not tell you which one was missing."""
    import re as _re
    import zlib as _zlib
    assert data.startswith(b"%PDF-1."), "not a PDF"
    assert data.rstrip().endswith(b"%%EOF")
    objs = _pdf_objects(data)
    assert objs, "no objects"
    size = int(_re.search(rb"/Size (\d+)", data).group(1))
    assert max(objs) < size
    # every indirect reference resolves
    for num, body in objs.items():
        for ref in _re.findall(rb"(\d+) 0 R", body):
            assert int(ref) in objs, "object %d points at missing %s" % (num, ref)
    # every named resource a page uses is declared in that page
    pages = [b for b in objs.values() if b"/Type /Page" in b and b"/Pages" not in b]
    assert pages, "no pages"
    for page in pages:
        content = int(_re.search(rb"/Contents (\d+) 0 R", page).group(1))
        stream = objs[content]
        body = stream.split(b"stream\n", 1)[1].rsplit(b"\nendstream", 1)[0]
        if b"/FlateDecode" in stream:
            body = _zlib.decompress(body)
        for name in set(_re.findall(rb"/((?:Pt|Sh|GS|F)\d+)\s", body)):
            assert b"/" + name + b" " in page, \
                "page uses /%s but does not declare it" % name.decode()
    return objs


def test_a_sheet_becomes_a_pdf_page_at_true_paper_size():
    from archiai.engine import pdf as P
    import io as _io
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="pdf"), {"number": "T"})
    with tempfile.TemporaryDirectory() as d:
        register = p.build(d, disciplines=["architecture"])
        buf = _io.BytesIO()
        P.write([path for (_n, _t, _s, path) in register], buf, title="Set")
        data = buf.getvalue()
    objs = _pdf_check(data)
    # A1 is 841 x 594 mm, which is 2383.9 x 1683.8 points
    boxes = [b for b in objs.values() if b"/MediaBox" in b]
    assert boxes, "no MediaBox"
    for box in boxes:
        nums = [float(v) for v in
                box.split(b"/MediaBox [")[1].split(b"]")[0].split()]
        assert abs(nums[2] - 841 * 72 / 25.4) < 0.5
        assert abs(nums[3] - 594 * 72 / 25.4) < 0.5
    assert len(boxes) == len(register)
    # the text is real text, not outlines
    assert b"/BaseFont /Helvetica" in data


def test_a_render_gets_a_page_it_fits_on():
    from archiai.engine import pdf as P
    from archiai.engine import view as V
    import io as _io
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=4, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="v"), {"number": "T"})
    svg = V.render(p, "aerial-ne", width=1600, height=1000)
    conv = P.Converter(svg)
    assert conv.page_w <= 420.1 and conv.page_h <= 297.1
    assert abs(conv.page_w / conv.page_h - 1.6) < 0.01      # aspect held
    buf = _io.BytesIO()
    P.write([svg], buf)
    _pdf_check(buf.getvalue())


def test_arcs_and_paths_convert_to_something_that_ends_where_it_should():
    from archiai.engine import pdf as P
    ops = P.path_ops("M 100 50 A 50 50 0 0 1 150 100")
    assert ops[0] == "100 50 m"
    last = [float(v) for v in ops[-1].split()[:-1]]
    assert abs(last[-2] - 150) < 0.01 and abs(last[-1] - 100) < 0.01
    # a full circle drawn as two half arcs closes on itself
    ops = P.path_ops("M 10 0 A 10 10 0 1 1 -10 0 A 10 10 0 1 1 10 0")
    last = [float(v) for v in ops[-1].split()[:-1]]
    assert abs(last[-2] - 10) < 0.05 and abs(last[-1] - 0) < 0.05
    # relative commands and shorthand curves
    assert P.path_ops("m 5 5 l 5 0 z") == ["5 5 m", "10 5 l", "h"]


def test_text_is_measured_so_it_lands_where_the_svg_puts_it():
    from archiai.engine import pdf as P
    # Helvetica: an 'i' is narrow and an 'M' is wide, and bold is wider
    assert P.text_width("i", 10) < P.text_width("M", 10)
    assert P.text_width("ABC", 10, bold=True) > P.text_width("ABC", 10)
    assert abs(P.text_width("", 10)) < 1e-9
    # letter spacing counts
    assert abs(P.text_width("AAA", 10, spacing=2.0)
               - P.text_width("AAA", 10) - 6.0) < 1e-6
    # the characters the sheets actually use are all measurable
    for ch in "—·²é³–½°":
        assert P.text_width(ch, 10) > 0


def test_every_sheet_in_a_set_survives_the_conversion():
    from archiai.engine import pdf as P
    import io as _io
    for name in ("slab", "courtyard", "hexagon", "ring"):
        b = M.Extrusion(FOOTPRINTS[name], storeys=2, floor_to_floor=3.9)
        p = PJ.Project(b, L.Brief(name=name), {"number": "T"})
        with tempfile.TemporaryDirectory() as d:
            register = p.build(d)
            buf = _io.BytesIO()
            P.write([path for (_n, _t, _s, path) in register], buf)
            _pdf_check(buf.getvalue())


def test_the_service_returns_the_whole_set_as_one_pdf():
    r = client.post("/v1/generate", json={
        "brief": "a 3 storey office of 3000 m2 with a courtyard",
        "disciplines": ["architecture"],
        "views": [{"name": "aerial-ne", "width": 800, "height": 500}]})
    assert r.status_code == 200, r.text
    body = r.json()
    docs = [a for a in body["assets"] if a["kind"] == "document"]
    doc = next(a for a in docs if a["meta"].get("format") == "pdf")
    assert doc["content_type"] == "application/pdf"
    assert doc["meta"]["vector"] is True
    drawings = sum(1 for a in body["assets"] if a["kind"] == "drawing")
    assert doc["meta"]["pages"] == drawings + 1          # sheets plus the view
    listed = {d["format"]: d for d in body["manifest"]["documents"]}
    assert listed["pdf"]["pages"] == doc["meta"]["pages"]

    from archiai.service.config import settings
    with open(os.path.join(settings.local_root, doc["key"]), "rb") as fh:
        _pdf_check(fh.read())

    off = client.post("/v1/generate", json={
        "brief": "a 2 storey office of 1200 m2", "disciplines": ["architecture"],
        "include_pdf": False, "include_page": False})
    assert not [a for a in off.json()["assets"] if a["kind"] == "document"]
    only_page = client.post("/v1/generate", json={
        "brief": "a 2 storey office of 1200 m2", "disciplines": ["architecture"],
        "include_pdf": False, "turntable": 0})
    formats = {a["meta"].get("format") for a in only_page.json()["assets"]
               if a["kind"] == "document"}
    assert formats == {"html"}


# --- handing it to someone: the page ----------------------------------------

def test_the_project_page_holds_everything_and_needs_nothing():
    """One file, no network. That is the whole point of it."""
    from archiai.engine import webpage as W
    from archiai.engine import view as V
    import io as _io
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="page"), {"number": "T"})
    with tempfile.TemporaryDirectory() as d:
        register = p.build(d, disciplines=["architecture"])
        views = [{"svg": V.render(p, "aerial-ne", width=600, height=380),
                  "title": "Aerial", "note": "from the north-east"}]
        buf = _io.BytesIO()
        W.build(p, buf, sheets=register, views=views, turntable=4)
        page = buf.getvalue().decode("utf-8")

    assert page.startswith("<!doctype html>") and page.rstrip().endswith("</html>")

    # Nothing is fetched from anywhere. The xmlns on every SVG is a namespace
    # name that happens to look like a URL and is never resolved, so the test
    # looks for the things that actually cause a request.
    fetches = [bad for bad in ('src="http', "src='http", 'href="http',
                               "href='http", "url(http", "<link ", "<iframe",
                               "@import", "fetch(", "XMLHttpRequest",
                               "<script src")
               if bad in page]
    assert fetches == [], "page reaches out: %s" % fetches

    import html as _html
    missing = []
    for (number, title, _scale, _path) in register:
        if 'id="svg-%s"' % number not in page:
            missing.append("body of " + number)
        if 'data-id="%s"' % number not in page:
            missing.append("link to " + number)
        if _html.escape(title) not in page:
            missing.append("title of " + number)
    assert missing == [], "not on the page: %s" % missing[:5]

    assert page.count("<svg") >= len(register) + 1 + 4      # sheets, view, frames
    assert "Aerial" in page and "from the north-east" in page
    assert "%d" % len(b.levels) in page


def test_the_page_addresses_a_single_drawing_by_link():
    from archiai.engine import webpage as W
    import io as _io
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=2, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="link"), {"number": "T"})
    with tempfile.TemporaryDirectory() as d:
        register = p.build(d, disciplines=["architecture"])
        buf = _io.BytesIO()
        W.build(p, buf, sheets=register, turntable=0)
        page = buf.getvalue().decode("utf-8")
    assert "open_from_hash" in page and "hashchange" in page
    assert "#' + current" in page or "'#' + current" in page
    assert "tab-model" not in page          # no turntable was asked for


def test_the_service_returns_the_page_as_a_document():
    r = client.post("/v1/generate", json={
        "brief": "a 3 storey office of 3000 m2",
        "disciplines": ["architecture"],
        "turntable": 3,
        "views": [{"name": "aerial-ne", "width": 600, "height": 380}]})
    assert r.status_code == 200, r.text
    body = r.json()
    docs = {a["meta"].get("format"): a for a in body["assets"]
            if a["kind"] == "document"}
    assert set(docs) == {"pdf", "html"}
    page = docs["html"]
    assert page["content_type"] == "text/html"
    assert page["meta"]["self_contained"] is True
    assert page["meta"]["views"] == 1
    drawings = sum(1 for a in body["assets"] if a["kind"] == "drawing")
    assert page["meta"]["sheets"] == drawings

    from archiai.service.config import settings
    with open(os.path.join(settings.local_root, page["key"])) as fh:
        text = fh.read()
    assert 'src="http' not in text and "<link " not in text

    off = client.post("/v1/generate", json={
        "brief": "a 2 storey office of 1200 m2", "disciplines": ["architecture"],
        "include_page": False, "include_pdf": False})
    assert not [a for a in off.json()["assets"] if a["kind"] == "document"]


# --- preparing a photoreal pass ---------------------------------------------

def _fills(svg):
    import re as _re
    return set(_re.findall(r'fill="(#[0-9a-fA-F]{6})"', svg))


def test_each_pass_says_something_different_about_the_same_view():
    from archiai.engine import view as V
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=4, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="pass"), {"number": "T"})
    kw = dict(addons=("ground", "context", "trees"), width=600, height=380)
    out = {k: V.render(p, "aerial-ne", style=k, **kw) for k in V.PASSES}
    assert len(set(out.values())) == len(V.PASSES), "two passes came out alike"

    # depth runs from near-bright to far-dark, and is grey all the way
    greys = _fills(out["depth"])
    assert len(greys) > 20, "depth has only %d levels" % len(greys)
    for g in greys:
        assert g[1:3] == g[3:5] == g[5:7], "depth is not grey: %s" % g
    vals = sorted(int(g[1:3], 16) for g in greys)
    assert vals[0] < 60 and vals[-1] > 200, "depth range is %s..%s" % (
        vals[0], vals[-1])

    # segmentation uses only the agreed colours
    allowed = {V._hex(c) for c in V.SEGMENT.values()} | {V._hex(V.SEGMENT_SKY)}
    assert _fills(out["segment"]) <= allowed, \
        "unexpected colours: %s" % (_fills(out["segment"]) - allowed)

    # a line pass is line work, not fills
    assert out["line"].count("stroke=") > 200
    assert _fills(out["line"]) <= {"#ffffff"}


def test_the_passes_line_up_with_each_other_and_with_the_render():
    """They are only useful as controls if they are the same camera."""
    from archiai.engine import photoreal as PR
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=5, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="align"), {"number": "T"})
    pack = PR.package(p, "eye-south", width=640, height=400)
    sizes = {tuple(_svg_size(v)) for v in pack["controls"].values()}
    sizes.add(tuple(_svg_size(pack["base"])))
    assert sizes == {(640, 400)}, "the controls are not one camera: %s" % sizes
    # and the silhouette agrees: the same faces are drawn in each
    counts = {k: v.count("<path") for k, v in pack["controls"].items()}
    assert max(counts.values()) - min(counts.values()) < max(counts.values()) * 0.6


def _svg_size(svg):
    import re as _re
    m = _re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def test_the_description_is_written_from_the_model():
    from archiai.engine import photoreal as PR
    b = M.Extrusion(FOOTPRINTS["courtyard"], storeys=7, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="words", use="office"), {"number": "T"})
    text = PR.describe(p, "entrance", hour=9.0, sky="clear",
                       addons=("context", "trees", "people"))
    assert "7 storey" in text and "office" in text
    assert "%.0f metres" % b.height in text
    assert "courtyard" in text                     # this plate has one
    assert "morning" in text and "clear sky" in text
    assert "street trees" in text and "people" in text
    # it describes what a camera would see, not what a specification says
    for jargon in ("carrier rail", "inner leaf", "dense block", "rainscreen"):
        assert jargon not in text, "%r leaked into the description" % jargon

    solid = PJ.Project(M.Extrusion(FOOTPRINTS["slab"], storeys=2,
                                   floor_to_floor=3.9),
                       L.Brief(name="solid"), {"number": "T"})
    assert "courtyard" not in PR.describe(solid, "eye-north")
    # the same building, described the same way, every time
    assert PR.describe(p, "entrance") == PR.describe(p, "entrance")


def test_the_image_service_is_a_seam_that_can_be_closed_in_one_adapter():
    from archiai.engine import photoreal as PR
    b = M.Extrusion(FOOTPRINTS["slab"], storeys=3, floor_to_floor=3.9)
    p = PJ.Project(b, L.Brief(name="seam"), {"number": "T"})
    pack = PR.package(p, "aerial-ne", width=512, height=384,
                      which=("depth", "line"))
    assert set(pack["controls"]) == {"depth", "line"}
    assert pack["prompt"] and pack["negative_prompt"]

    with pytest.raises(PR.NotConfigured):
        PR.backend("none").generate(pack["prompt"], pack["controls"])
    with pytest.raises(PR.NotConfigured):
        PR.backend("a-service-that-does-not-exist")

    seen = {}

    class Fake(PR.Backend):
        name = "fake"

        def generate(self, prompt, controls, negative=None, width=1280,
                     height=800, seed=None, strength=0.75, options=None):
            seen.update(prompt=prompt, controls=sorted(controls), seed=seed)
            return b"\x89PNG\r\n\x1a\nfake", "image/png"

    PR.register("fake", Fake)
    try:
        data, ct = PR.backend("fake").generate(pack["prompt"], pack["controls"],
                                               seed=7)
        assert ct == "image/png" and data.startswith(b"\x89PNG")
        assert seen["controls"] == ["depth", "line"] and seen["seed"] == 7
    finally:
        PR._BACKENDS.pop("fake", None)


def test_the_endpoint_returns_the_controls_whether_or_not_it_can_generate():
    r = client.post("/v1/photoreal", json={
        "brief": "a 4 storey office of 5000 m2 with a courtyard",
        "shots": [{"name": "entrance", "width": 512, "height": 384,
                   "controls": ["depth", "line"], "label": "Arrival"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "controls_only"
    kinds = body["manifest"]["produced"]
    assert kinds == {"view": 1, "control": 2, "recipe": 1}
    controls = [a for a in body["assets"] if a["kind"] == "control"]
    assert {a["meta"]["control"] for a in controls} == {"depth", "line"}
    assert all(a["meta"]["sun"]["altitude_deg"] > 0 for a in controls)

    from archiai.service.config import settings
    recipe = next(a for a in body["assets"] if a["kind"] == "recipe")
    with open(os.path.join(settings.local_root, recipe["key"])) as fh:
        spec = json.load(fh)
    assert "prompt" in spec and "negative_prompt" in spec
    assert set(spec["controls"]) == {"depth", "line"}
    assert "no image service is configured" in spec["reason"]

    bad = client.post("/v1/photoreal", json={
        "brief": "an office", "shots": [{"name": "aerial-ne",
                                         "controls": ["x-ray"]}]})
    assert bad.status_code == 422 and "x-ray" in bad.json()["detail"]


def test_a_configured_image_service_is_used_when_there_is_one(monkeypatch):
    from archiai.engine import photoreal as PR
    from archiai.service import generate as gen
    from archiai.service.config import settings

    class Fake(PR.Backend):
        name = "fake"

        def generate(self, prompt, controls, negative=None, width=1280,
                     height=800, seed=None, strength=0.75, options=None):
            assert "storey" in prompt
            return b"\x89PNG\r\n\x1a\nfake-bytes", "image/png"

    PR.register("fake", Fake)
    monkeypatch.setattr(settings, "image_backend", "fake")
    try:
        r = client.post("/v1/photoreal", json={
            "brief": "a 3 storey office of 3000 m2",
            "shots": [{"name": "aerial-ne", "width": 512, "height": 384,
                       "controls": ["depth"]}]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "complete"
        assert body["manifest"]["image_service"] == "fake"
        shot = next(a for a in body["assets"] if a["kind"] == "photoreal")
        assert shot["content_type"] == "image/png"
        assert shot["meta"]["service"] == "fake" and shot["meta"]["prompt"]
        assert not [a for a in body["assets"] if a["kind"] == "recipe"]
    finally:
        PR._BACKENDS.pop("fake", None)


# --- trying it by hand ------------------------------------------------------

def test_the_test_page_is_served_and_calls_the_routes_it_needs():
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    page = r.text
    for bit in ("Describe", "Draw", "Upload", "Generate the project",
                "playground.js"):
        assert bit in page, "%r missing from the page" % bit

    j = client.get("/playground.js")
    assert j.status_code == 200
    code = j.text
    for route in ("/v1/parse", "/v1/trace", "/v1/generate", "/v1/revise"):
        assert route in code, "the page never calls %s" % route
    assert "Change your mind" in code       # the edit loop is offered
    for change in ('"storeys":"+1"', '"courtyard":"bigger"', '"entrance":"north"'):
        assert change in code, "%s is not offered" % change
    # it only talks to itself
    assert "http://" not in code and "https://" not in code


def test_the_command_line_builds_a_project_from_words():
    from archiai import __main__ as cli
    with tempfile.TemporaryDirectory() as d:
        code = cli.main(["a 4 storey office of 5000 m2 with a courtyard",
                         "--out", d, "--only", "architecture", "--views", "1",
                         "--turntable", "0", "--number", "CLI-1"])
        assert code == 0
        folder = os.path.join(d, "courtyard-office")
        assert os.path.isdir(os.path.join(folder, "drawings"))
        assert len(os.listdir(os.path.join(folder, "drawings"))) > 5
        pdf = os.path.join(folder, "CLI-1-drawings.pdf")
        page = os.path.join(folder, "CLI-1-project.html")
        assert os.path.getsize(pdf) > 20000
        assert os.path.getsize(page) > 20000
        with open(pdf, "rb") as fh:
            _pdf_check(fh.read())


def test_the_command_line_takes_a_sketch_and_an_outline():
    from archiai import __main__ as cli
    with tempfile.TemporaryDirectory() as d:
        png = os.path.join(d, "sketch.png")
        with open(png, "wb") as fh:
            fh.write(_sketch([[(60, 60), (500, 60), (500, 360), (60, 360)]]))
        assert cli.main(["--image", png, "--area", "1500", "--storeys", "3",
                         "--out", d, "--only", "architecture", "--views", "0",
                         "--turntable", "0", "--no-page"]) == 0
        assert os.path.isdir(os.path.join(d, "sketch", "drawings"))

        shape = os.path.join(d, "plot.json")
        with open(shape, "w") as fh:
            json.dump({"outer": [[0, 0], [60, 0], [60, 30], [0, 30]],
                       "holes": []}, fh)
        assert cli.main(["--footprint", shape, "--storeys", "2", "--out", d,
                         "--only", "architecture", "--views", "0",
                         "--turntable", "0", "--no-pdf",
                         "--name", "Plot"]) == 0
        assert os.path.isfile(os.path.join(d, "plot", "AAI-0001-project.html"))


def test_the_command_line_says_what_is_wrong_rather_than_traceback(capsys):
    from archiai import __main__ as cli
    with tempfile.TemporaryDirectory() as d:
        # a missing file is a message and a non-zero exit, not a stack trace
        code = cli.main(["--image", os.path.join(d, "nope.png"), "--area",
                         "800", "--out", d])
        assert code == 2
        assert "Could not build that" in capsys.readouterr().err
        # and the arguments that cannot work are refused up front
        for argv in ([], ["--image", "x.png"]):
            with pytest.raises(SystemExit) as e:
                cli.main(argv + ["--out", d])
            assert e.value.code != 0


def test_one_command_runs_either_the_page_or_the_engine():
    """`run.py` is the whole setup story, so it has to route correctly."""
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "archiai_run", os.path.join(root, "run.py"))
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)

    # arguments mean the engine, and the engine needs nothing installed
    with tempfile.TemporaryDirectory() as d:
        assert run.main(["a 2 storey office of 1200 m2", "--out", d,
                         "--only", "architecture", "--views", "0",
                         "--turntable", "0", "--no-pdf", "--no-page"]) == 0
        assert os.path.isdir(os.path.join(d, "bar-office", "drawings"))

    # no arguments means the page, which is only reached once the packages are
    # there; with them missing it must offer to set them up rather than fail
    calls = []
    run.setup_and_restart = lambda: calls.append("setup") or 0
    real_have = run.have
    run.have = lambda mods: False
    try:
        assert run.main([]) == 0 and calls == ["setup"]
    finally:
        run.have = real_have

    served = []
    run.serve = lambda port, open_browser=True: served.append((port, open_browser)) or 0
    run.have = lambda mods: True
    try:
        assert run.main(["--no-browser", "--port=9111"]) == 0
        assert served == [(9111, False)]
    finally:
        run.have = real_have


# --- refusing what it cannot honestly build ---------------------------------

def test_an_outline_says_what_is_wrong_with_it_in_words_a_person_can_act_on():
    """Every complaint names the fault and what to do, never a stack trace."""
    def sq(w, h, cx=0.0, cy=0.0):
        return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
                (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]

    cases = [
        (G.Region([(0, 0), (40, 30), (40, 0), (0, 30)]), "no area"),
        (G.Region(sq(2, 2)), "wrong un"),
        (G.Region([(0, 0), (80, 0), (80, 0.4), (0, 0.4)]), "3 m across"),
        (G.Region(sq(50, 30), [sq(10, 10, 100, 100)]), "not inside"),
        (G.Region(sq(30, 20), [sq(60, 50)]), "not inside"),
        (G.Region([(0, 0), (10, 0), (10, 0), (0, 0)]), "three separate"),
    ]
    for region, wanted in cases:
        faults = G.problems(region)
        assert faults, "%r should have been refused" % (region.outer[:2],)
        assert wanted in " ".join(faults), (wanted, faults)

    # and a plain, buildable outline has nothing said against it
    assert G.problems(G.Region(sq(60, 40), [sq(12, 12)])) == []
    assert G.problems(G.Region(sq(1000, 1000)), max_area=400000.0)


def test_the_engine_names_the_uses_and_shapes_it_knows():
    """An unknown word is answered with the list, not a KeyError."""
    for kwargs in ({"use": "submarine"}, {"shape": "trapezoid"}):
        with pytest.raises(ValueError) as e:
            B.Spec(**kwargs)
        assert "knows are" in str(e.value)
    r = client.post("/v1/generate", json={
        "spec": {"use": "submarine", "storeys": 2, "area_m2": 900}})
    assert r.status_code == 422 and "submarine" in r.json()["detail"]


def test_the_cost_of_a_request_is_measured_in_sheets_not_floor_area():
    """A tall tower on a small plate is little building and much drawing."""
    from archiai.service import generate as GEN
    per = GEN.estimate_sheets(2) - GEN.estimate_sheets(1)
    assert per >= 6                           # every discipline draws a plan
    many = GEN.estimate_sheets(50)
    assert many - GEN.estimate_sheets(1) == 49 * per
    assert GEN.estimate_sheets(50, ["architecture"]) < many

    with pytest.raises(GEN.Refused) as e:
        GEN._guard(50, 500.0, ["architecture"])    # a 10 m2 plate, 50 up
    assert "too small to plan" in str(e.value)

    from archiai.service.config import settings
    was = settings.max_sheets
    settings.max_sheets = 40
    try:
        with pytest.raises(GEN.Refused) as e:
            GEN._guard(30, 30000.0)
        assert "sheets" in str(e.value) and "fewer storeys" in str(e.value)
        # the same building drawn by one discipline is under the same cap
        GEN._guard(4, 4000.0, ["architecture"])
    finally:
        settings.max_sheets = was


def test_a_picture_that_is_not_a_drawing_is_refused_rather_than_guessed_at():
    """Grain, a shadow, a photographed screen: none of them are a plan."""
    import base64, random
    rnd = random.Random(7)
    noise = _png([[rnd.randrange(256) for _ in range(120)] for _ in range(90)])
    for kind, data in (("noise", noise),
                       ("all black", _png([[5] * 120 for _ in range(90)])),
                       ("blank", _png([[250] * 120 for _ in range(90)]))):
        r = client.post("/v1/trace", json={
            "image": {"data": base64.b64encode(data).decode(), "area_m2": 1500}})
        assert r.status_code == 422, (kind, r.status_code)
        assert "Traceback" not in r.json()["detail"]

    # and generating from the same picture is refused too, not built anyway
    r = client.post("/v1/generate", json={
        "image": {"data": base64.b64encode(noise).decode(), "area_m2": 1500},
        "disciplines": ["architecture"], "include_pdf": False,
        "include_page": False, "turntable": 0})
    assert r.status_code == 422


def test_a_real_sketch_still_reads_after_the_picture_check():
    """The check must not cost the engine the drawings it can read."""
    import base64, math
    shapes = {
        "rectangle": [[(60, 60), (500, 60), (500, 360), (60, 360)]],
        "L": [[(60, 60), (500, 60), (500, 200), (260, 200), (260, 360),
               (60, 360)]],
        "comb": [[(60, 60), (500, 60), (500, 130), (200, 130), (200, 200),
                  (500, 200), (500, 270), (200, 270), (200, 340), (500, 340),
                  (500, 400), (60, 400)]],
        "round": [[(280 + 190 * math.cos(t * math.pi / 24),
                    210 + 150 * math.sin(t * math.pi / 24)) for t in range(48)]],
    }
    for name, polys in shapes.items():
        r = client.post("/v1/trace", json={
            "image": {"data": base64.b64encode(_sketch(polys)).decode(), "area_m2": 1500}})
        assert r.status_code == 200, (name, r.json())
        assert len(r.json()["outer"]) >= 3


def test_a_tall_building_is_drawn_in_seconds_not_minutes():
    """Height must not be re-measured once per line of a swept drawing."""
    import time
    from archiai.engine import draw_details as DD
    spec = B.Spec(use="office", storeys=40, area=32000.0, floor_to_floor=3.6)
    massing, brf = B.build(spec)
    p = PJ.Project(massing, brf)
    with tempfile.TemporaryDirectory() as d:
        t0 = time.time()
        DD.wall_section_sheet(p, os.path.join(d, "ws.svg"))
        assert time.time() - t0 < 5.0

    # the mesh is measured once and remembered, and remembering is safe:
    # adding to it forgets again
    m = massing.mesh()
    assert m.bounds() is m.bounds()
    before = m.bounds()
    m.quad((0, 0, 999), (1, 0, 999), (1, 1, 999), (0, 1, 999))
    assert m.bounds()[5] > before[5]


def test_solidity_and_raggedness_tell_a_plan_from_a_mess():
    ring = [(0, 0), (40, 0), (40, 30), (0, 30)]
    assert abs(G.solidity(ring) - 1.0) < 1e-9
    assert abs(G.raggedness(ring) - (140 / (1200 ** 0.5))) < 1e-9
    # a courtyard block's outer ring is still a box; an L is not
    lsh = G.l_shape(40, 30, 20, 15)
    assert 0.5 < G.solidity(lsh) < 0.95
    assert G.raggedness(lsh) > G.raggedness(ring)


# --- asking for it in your own words ----------------------------------------

def test_a_hotel_plans_like_a_hotel_and_not_like_an_office():
    """A guest room is a narrow bay, not a slice of open floor."""
    spec = B.parse("a 5 storey hotel of 7000 m2 with a courtyard")
    assert spec.use == "hotel"
    assert not any("Use not stated" in a for a in spec.assumptions)

    rooms = {}
    for use in ("hotel", "office"):
        s = B.parse("a 5 storey %s of 7000 m2 with a courtyard" % use)
        massing, brf = B.build(s)
        p = PJ.Project(massing, brf)
        fp = p.floorplans[2]
        named = [r for r in fp.rooms if r.cat == "work"]
        rooms[use] = sum(r.area for r in named) / len(named)
        assert massing.height > 0

    # a guest room is 25-40 m2; an office floorplate is cut far coarser
    assert 22.0 < rooms["hotel"] < 45.0, rooms
    assert rooms["office"] > rooms["hotel"] * 1.4, rooms


def test_a_use_it_cannot_plan_is_named_rather_than_silently_swapped():
    """Saying "use not stated" when it plainly was is the wrong answer."""
    spec = B.parse("a 4 storey hospital of 9000 m2")
    assert spec.use == "office"
    said = " ".join(spec.assumptions)
    assert "hospital" in said and "office" in said
    assert "Use not stated" not in said        # it was stated; it is not planned

    # and a brief that really says nothing still gets the honest version
    assert any("Use not stated" in a
               for a in B.parse("a 3 storey building of 2000 m2").assumptions)


def test_every_use_the_engine_offers_can_be_planned_end_to_end():
    """A half-added use must not reach a person as a KeyError."""
    for use in sorted(B.USE_DEFAULTS):
        assert use in B.ACCOMMODATION and use in B.INTERNAL, use
        spec = B.Spec(use=use, storeys=2, area=2400.0, floor_to_floor=3.6)
        massing, brf = B.build(spec)
        p = PJ.Project(massing, brf)
        assert p.floorplans[0].rooms, use
        with tempfile.TemporaryDirectory() as d:
            assert p.build(d, disciplines=["architecture"]), use


def test_the_page_reads_its_menus_from_the_engine():
    """A hand-written menu drifts and starts offering the impossible."""
    v = client.get("/v1/vocabulary").json()
    assert set(v["uses"]) == set(B.USE_DEFAULTS)
    assert "warehouse" not in v["uses"] and "warehouse" in v["unplanned"]
    assert v["max_storeys"] >= 1 and v["max_area_m2"] > 0

    # every use it offers is one /v1/generate will actually accept
    for use in v["uses"]:
        r = client.post("/v1/generate", json={
            "spec": {"use": use, "storeys": 2, "area_m2": 2400},
            "disciplines": ["architecture"], "include_pdf": False,
            "include_page": False, "turntable": 0, "views": []})
        assert r.status_code == 200, (use, r.json())

    # and the page does not hard-code a list of its own
    js = client.get("/playground.js").text
    assert "/v1/vocabulary" in js
    html = client.get("/").text
    assert "warehouse" not in html and "apartments" not in html


def test_the_estimate_of_size_matches_what_is_actually_drawn():
    """Being told "about 8 sheets" and getting 21 is not an estimate."""
    from archiai.service import generate as GEN
    for storeys in (1, 5, 20):
        said = client.post("/v1/parse", json={
            "brief": "a %d storey office of %d m2" % (storeys, 900 * storeys),
            "disciplines": ["architecture"]}).json()["estimated_sheets"]
        got = GEN.estimate_sheets(storeys, ["architecture"])
        assert said == got

    r = client.post("/v1/generate", json={
        "brief": "a 5 storey office of 4500 m2", "disciplines": ["architecture"],
        "include_pdf": False, "include_page": False, "turntable": 0, "views": []})
    drawn = len([a for a in r.json()["assets"] if a["kind"] == "drawing"])
    said = client.post("/v1/parse", json={
        "brief": "a 5 storey office of 4500 m2",
        "disciplines": ["architecture"]}).json()["estimated_sheets"]
    assert abs(drawn - said) <= 2, (drawn, said)


def test_the_drawings_can_be_read_without_leaving_the_page():
    """Fifty sheets listed by name is a filing cabinet, not a drawing set."""
    code = client.get("/playground.js").text
    # a list to choose from, one sheet shown, and a way to move around it
    for bit in ("#blist", "#b-img", "function pick(", "function fit(",
                "function zoom(", "function step(", "showKind("):
        assert bit in code, "the sheet browser has no %s" % bit
    # arrow keys, the wheel, and dragging
    for bit in ("ArrowRight", "wheel", "pointerdown"):
        assert bit in code, "%s does nothing" % bit
    # and changing your mind keeps you on the drawing you were reading
    assert "HELD" in code and "was.number" in code

    html = client.get("/").text
    for bit in ("browse", "blist", "stage", "bview"):
        assert bit in html, "the browser has no %s in its markup" % bit


def test_the_page_shows_what_it_read_rather_than_settings_it_ignores():
    """In Describe mode the words decide, so the boxes must say so."""
    code = client.get("/playground.js").text
    assert 'readout' in code and 'change the words above' in code
    # the brief is what is sent; the boxes are not smuggled in beside it
    assert "return { brief, ...strip(b) };" in code


# --- reading a brief the way a person writes one ----------------------------

BRIEF = ("A monumental structure appears to hover above the ground on a forest "
         "of extremely thin mirrored columns. The entire ground floor is open "
         "to nature, planted and walkable, with only the lift cores touching "
         "the earth.")

READING = {
    "use": "gallery", "use_is_a_stretch": False, "asked_for": "",
    "storeys": 3, "area_m2": None, "shape": "bar",
    "entrance": "south", "entrance_stated": False, "floor_to_floor_m": 5.2,
    "lift_m": 9.0,
    "columns": {"spacing_m": 6.0, "diameter_mm": 180, "shape": "round",
                "material": "mirror"},
    "cores_to_ground": 2, "ground": "planted", "facade": "mirror",
    "setback_m": 0.0, "name": "Hovering Pavilion",
    "intent": "A mass held clear of a landscape that runs on beneath it.",
    "unreadable": ["a mirrored soffit reflecting the planting"],
}


def test_the_keyword_parser_is_deaf_to_how_people_write_briefs():
    """The reason the reader exists, kept in front of us."""
    spec = B.parse(BRIEF)
    assert spec.shape == "circle"          # from "round" inside "ground"
    assert spec.lift_m == 0.0
    # nothing in that brief about being an office, and nothing about a cylinder
    assert "round" in BRIEF.lower()


def test_a_reading_becomes_the_building_the_brief_describes():
    from archiai.engine import interpret as IN
    spec = IN.to_spec(READING, BRIEF)
    assert spec.use == "gallery" and spec.shape == "bar"
    assert spec.lift_m == 9.0 and spec.cores_to_ground == 2
    assert spec.columns["diameter_mm"] == 180
    assert spec.name == "Hovering Pavilion" and spec.intent

    massing, brf = B.build(spec)
    assert massing.lift == 9.0
    assert len(massing.columns) > 12          # a forest, not four posts
    assert len(massing.cores) == 2
    assert massing.levels[0].ffl == 9.0       # the ground is left open
    assert all(c.size < 0.30 for c in massing.columns)   # extremely thin

    # and it draws: the whole set, with the undercroft in it
    p = PJ.Project(massing, brf)
    with tempfile.TemporaryDirectory() as d:
        made = p.build(d, disciplines=["architecture"])
        assert made
    from archiai.engine import view as V
    svg = V.render(p, "entrance", width=700, height=440)
    assert "soffit" not in svg                 # materials are resolved to colour
    assert len(svg) > 20000


def test_what_the_brief_asked_for_and_did_not_get_is_said_out_loud():
    from archiai.engine import interpret as IN
    said = " ".join(IN.to_spec(READING, BRIEF).assumptions)
    assert "mirrored soffit" in said
    assert "No floor area given" in said
    assert "Entrance orientation not stated" in said

    stretch = dict(READING, use="office", use_is_a_stretch=True,
                   asked_for="chapel")
    said = " ".join(IN.to_spec(stretch, BRIEF).assumptions)
    assert "chapel" in said and "office" in said

    # the sentences have to read like sentences
    assert "as a office" not in said and "as an gallery" not in said
    # a use it could not name at all is not reported as an unbuildable thing
    unnamed = dict(READING, use_is_a_stretch=True, asked_for="")
    said = " ".join(IN.to_spec(unnamed, BRIEF).assumptions)
    assert "does not say what the building is for" in said
    assert "cannot build" not in said.split("Not in these drawings")[0]
    # what is missing is listed once, not once per line
    many = dict(READING, unreadable=["bridges across the void",
                                     "planting in the atrium", "a water feature"])
    said = [a for a in IN.to_spec(many, BRIEF).assumptions
            if "cannot build" in a]
    assert len(said) == 1 and said[0].count(";") == 2
    # and the direction named is the direction used
    north = dict(READING, entrance="north", entrance_stated=False)
    spec = IN.to_spec(north, BRIEF)
    assert spec.entrance == 90.0
    assert "to the north" in " ".join(spec.assumptions)


def test_the_reader_cannot_ask_for_what_the_engine_cannot_build():
    """Everything the model says is clamped; it never gets the last word."""
    from archiai.engine import interpret as IN
    wild = {
        "use": "submarine", "shape": "hyperboloid", "storeys": 9999,
        "area_m2": -5, "entrance": "upwards", "floor_to_floor_m": 400,
        "lift_m": 900, "cores_to_ground": 99,
        "columns": {"spacing_m": 0.1, "diameter_mm": 99999, "shape": "blob",
                    "material": "unobtanium"},
        "setback_m": 999,
    }
    spec = IN.to_spec(wild, "a 4 storey school of 3000 m2")
    assert spec.use == "school" and spec.shape in set(B.SHAPES.values())
    assert 1 <= spec.storeys <= 60
    assert spec.area is None or spec.area > 0
    assert 0 <= spec.lift_m <= 30
    assert 3.0 <= spec.columns["spacing_m"] <= 24.0
    assert 80 <= spec.columns["diameter_mm"] <= 2000
    assert spec.columns["shape"] in ("round", "square")
    assert 0 <= spec.cores_to_ground <= 6
    assert 0 <= spec.setback <= 12
    B.build(spec)                              # and it still builds

    # a reading that says nothing at all falls back to the words themselves
    spec = IN.to_spec({}, "a 5 storey hotel of 7000 m2")
    assert spec.use == "hotel" and spec.storeys == 5


def test_a_brief_is_read_by_keyword_when_there_is_no_model_and_says_so():
    from archiai.engine import interpret as IN
    spec, how, why = IN.parse("a 4 storey office of 6000 m2 with a courtyard")
    assert how in ("model", "keyword")
    assert (why is None) == (how == "model")
    assert spec.use == "office" and spec.storeys == 4

    # the page is told which happened, so nobody is left wondering
    r = client.post("/v1/parse", json={"brief": "a 3 storey school of 2000 m2"})
    assert r.status_code == 200
    assert r.json()["spec"]["read_by"] in ("model", "keyword")
    assert "reads_prose" in client.get("/v1/vocabulary").json()
    assert "read_by" in client.get("/playground.js").text


def test_a_lifted_building_is_lifted_everywhere_not_just_in_the_render():
    """A move the drawings do not show is a move that did not happen."""
    from archiai.engine import massing as M
    foot = G.Region(G.rectangle(46, 30))
    m = M.Extrusion(foot, storeys=3, floor_to_floor=4.2, lift=8.0,
                    columns=M.piloti(foot, spacing=8.0, size=0.2),
                    cores=M.core_supports(foot, 2))
    # in plan, below the lift, the floor is columns and cores -- not a slab
    under = m.bands_at(4.0)
    assert len(under) == len(m.columns) + len(m.cores)
    assert sum(b.area for b in under) < foot.area * 0.2

    # above it, the building is whole again
    assert len(m.bands_at(12.0)) == 1

    # in section, the lift is a level the drawing knows about
    assert 8.0 in [round(z, 3) for z in m.joint_heights()]
    assert m.section((0, 0), (1.0, 0.0))

    # and the same building with no lift has none of it
    plain = M.Extrusion(foot, storeys=3, floor_to_floor=4.2)
    assert plain.lift == 0.0 and plain.columns == [] and plain.cores == []
    assert plain.levels[0].ffl == 0.0


def test_a_building_you_walk_under_gets_a_drawing_of_what_you_walk_through():
    from archiai.engine import massing as M, interpret as IN
    spec = IN.to_spec(READING, BRIEF)
    massing, brf = B.build(spec)
    p = PJ.Project(massing, brf)
    with tempfile.TemporaryDirectory() as d:
        made = p.build(d, disciplines=["architecture"])
        assert "A-090" in [n for n, *_ in made]
        body = open([x for x in made if x[0] == "A-090"][0][3]).read()
    assert "CORE" in body and "GROUND PLANE" in body
    assert "Building held 9.0 m clear of the ground." in body
    assert "columns at 180 mm; 2 core(s) to foundation." in body

    # a building on the ground has no such sheet, because there is nothing under it
    plain, brf2 = B.build(B.Spec(use="office", storeys=3, area=3000.0,
                                 floor_to_floor=3.9))
    with tempfile.TemporaryDirectory() as d:
        made = PJ.Project(plain, brf2).build(d, disciplines=["architecture"])
    assert "A-090" not in [n for n, *_ in made]


def test_the_page_cannot_be_served_from_a_stale_cache():
    """A cached page looks exactly like an engine that has not changed."""
    for path in ("/", "/playground.js"):
        r = client.get(path)
        assert r.status_code == 200
        assert "no-store" in r.headers.get("cache-control", ""), path

    # and the page says which engine answered, and whether it can read prose
    code = client.get("/playground.js").text
    assert "/v1/health" in code and "reads_prose" in code
    assert "read by keyword only" in code
    assert 'id="build"' in client.get("/").text


def test_a_key_can_live_in_the_project_instead_of_a_terminal():
    """An export dies with the window it was typed in; a setting should not."""
    from archiai import env as ENV
    keep = dict(os.environ)
    try:
        for k in ("ANTHROPIC_API_KEY", "ARCHIAI_TEST_ONLY"):
            os.environ.pop(k, None)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, ".env")
            open(p, "w").write(
                "# comments and blank lines are skipped\n\n"
                "ANTHROPIC_API_KEY=sk-ant-fromfile\n"
                "export ARCHIAI_TEST_ONLY='quoted'\n"
                "a line with no equals sign\n")
            assert set(ENV.load(p)) == {"ANTHROPIC_API_KEY", "ARCHIAI_TEST_ONLY"}
            assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-fromfile"
            assert os.environ["ARCHIAI_TEST_ONLY"] == "quoted"

            from archiai.engine import interpret as IN
            assert IN.credentials() == "environment"

            # a real export outranks the file, and is never overwritten
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-exported"
            assert ENV.load(p) == []
            assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-exported"

        # a missing file is silence, not an error
        assert ENV.load(os.path.join(d, "gone")) == []
    finally:
        os.environ.clear()
        os.environ.update(keep)

    # and a real key must never be committable
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert ".env" in open(os.path.join(root, ".gitignore")).read()


def test_a_void_can_open_as_it_rises_without_ever_snapping_shut():
    """Dense below, light above: the inside changes, the outside does not."""
    from archiai.engine import massing as M
    foot = G.Region(G.rectangle(66, 50), [G.rectangle(20, 14)])
    m = M.Extrusion(foot, storeys=9, floor_to_floor=4.2, void_growth=2.1)

    voids = [abs(G.signed_area(lv.plate.holes[0])) if lv.plate.holes else 0.0
             for lv in m.levels]
    assert voids[0] < voids[3] < voids[-1]          # it opens going up
    assert all(b >= a - 1.0 for a, b in zip(voids, voids[1:]))  # never shuts
    # the outside is untouched, which is what makes it monolithic
    assert all(abs(G.area(lv.plate.outer) - G.area(foot.outer)) < 1.0
               for lv in m.levels)
    # and it stops rather than eating the building
    assert all(lv.plate.area > foot.area * 0.15 for lv in m.levels)

    plain = M.Extrusion(foot, storeys=9, floor_to_floor=4.2)
    assert len({round(lv.plate.area) for lv in plain.levels}) == 1


def test_the_facade_a_brief_asks_for_is_the_facade_that_gets_drawn():
    """A field the pictures ignore is a field that lies."""
    from archiai.engine import view as V, interpret as IN
    for facade, opaque in (("concrete", True), ("stone", True),
                           ("glass", False), ("mirror", False)):
        spec = IN.to_spec({"facade": facade, "storeys": 2, "shape": "bar"},
                          "a 2 storey office of 1800 m2")
        assert spec.facade == facade
        massing, brf = B.build(spec)
        assert brf.facade == facade
        p = PJ.Project(massing, brf)
        mat, band = V._facade(p)
        assert mat == facade
        assert (band < 1.0) is opaque, facade
        assert mat in V.MATERIALS and mat in V.SEGMENT
        assert len(V.render(p, "entrance", width=600, height=380)) > 8000

    # an unknown facade falls back rather than failing
    p = PJ.Project(*B.build(B.Spec(use="office", storeys=2, area=1800.0,
                                   floor_to_floor=3.9, facade="unobtanium")))
    assert V._facade(p) == V.FACADES["glass"]


def test_the_void_can_be_looked_up_from_the_bottom():
    """A void that widens as it rises is only legible from underneath."""
    from archiai.engine import view as V, interpret as IN
    spec = IN.to_spec({"shape": "courtyard", "storeys": 8, "void_growth_m": 2.0,
                       "facade": "concrete"}, "an 8 storey office of 14000 m2")
    massing, brf = B.build(spec)
    p = PJ.Project(massing, brf)
    cam = V.camera(p, "courtyard", width=800, height=500)

    hole = max(massing.footprint().holes, key=lambda h: abs(G.signed_area(h)))
    assert G.point_in_ring((cam.eye[0], cam.eye[1]), hole)   # not inside a wall
    assert cam.eye[2] < 3.0                                  # standing on the ground
    assert cam.target[2] > massing.height * 0.9              # looking up it
    assert len(V.render(p, "courtyard", width=700, height=440)) > 8000


def test_a_reader_that_fails_says_why_instead_of_going_quiet():
    """Silent degradation is indistinguishable from a broken feature."""
    from archiai.engine import interpret as IN
    import anthropic

    class Blk:
        def __init__(self, t, text=""):
            self.type, self.text = t, text

    class Resp:
        def __init__(self, stop, blocks):
            self.stop_reason, self.content = stop, blocks

    class Fake:
        answer = None

        def with_options(self, **kw):
            return self

        class messages:
            @staticmethod
            def create(**kw):
                return Fake.answer

    real = IN._client
    IN._client = lambda: Fake()
    try:
        cases = {
            "ran out of room": Resp("max_tokens", [Blk("text", '{"use":')]),
            "answered with nothing": Resp("end_turn", [Blk("thinking")]),
            "did not answer in the vocabulary":
                Resp("end_turn", [Blk("text", "Sure! Here is your building.")]),
            "declined": Resp("refusal", []),
        }
        for expect, resp in cases.items():
            Fake.answer = resp
            spec, how, why = IN.parse("a 3 storey office of 2000 m2")
            assert how == "keyword", expect
            assert expect in why, (expect, why)
            assert spec.storeys == 3          # and it still built something

        Fake.answer = Resp("end_turn",
                           [Blk("text", '{"use":"hotel","storeys":4}')])
        spec, how, why = IN.parse("a 3 storey office of 2000 m2")
        assert how == "model" and why is None and spec.use == "hotel"

        # a hard failure must never take the request down with it
        class Boom:
            def with_options(self, **kw):
                return self

            class messages:
                @staticmethod
                def create(**kw):
                    raise anthropic.APIConnectionError(request=None)

        IN._client = lambda: Boom()
        spec, how, why = IN.parse("a 3 storey office of 2000 m2")
        assert how == "keyword" and "could not be reached" in why
    finally:
        IN._client = real

    # and the reason reaches the page rather than stopping at the service
    r = client.post("/v1/parse", json={"brief": "a 3 storey office of 2000 m2"})
    assert "read_note" in r.json()["spec"]
    assert "read_note" in client.get("/playground.js").text


def test_the_reader_can_be_tested_without_a_browser():
    """One command that makes a real call and says exactly what happened."""
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "archiai_run_check", os.path.join(root, "run.py"))
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    assert hasattr(run, "check") and "--check" in open(
        os.path.join(root, "run.py")).read()

    keep = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        from archiai.engine import interpret as IN
        if IN.credentials() is None:            # no key: it must say so, not crash
            assert run.check("a 3 storey office") == 2
    finally:
        if keep:
            os.environ["ANTHROPIC_API_KEY"] = keep


def test_a_rejected_key_can_be_diagnosed_without_printing_it():
    """A bad key is usually revoked, half-pasted, or the example left in."""
    from archiai.engine import interpret as IN
    keep = os.environ.get("ANTHROPIC_API_KEY")
    try:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        assert IN.fingerprint() is None

        real = "sk-ant-api03-" + "x" * 95
        os.environ["ANTHROPIC_API_KEY"] = real
        fp = IN.fingerprint()
        assert fp["notes"] == [] and fp["length"] == len(real)
        assert real not in fp["shown"]                  # never the whole key
        assert fp["shown"].startswith("sk-ant-api") and "..." in fp["shown"]

        for bad, expect in (("sk-ant-your-key-here", "example text"),
                            ("sk-ant-api03-tooshort", "too short"),
                            ("nope-" + "y" * 100, "sk-ant-")):
            os.environ["ANTHROPIC_API_KEY"] = bad
            notes = " ".join(IN.fingerprint()["notes"])
            assert expect in notes, (bad, notes)
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if keep:
            os.environ["ANTHROPIC_API_KEY"] = keep


def test_the_reader_schema_is_one_the_api_will_accept():
    """A schema the API rejects is a reader that never runs at all.

    Structured output takes a subset of JSON Schema. The rejection only
    arrives as a 400 from a real call, so the shape is checked here instead."""
    from archiai.engine import interpret as IN

    BANNED = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
              "minLength", "maxLength", "minItems", "maxItems", "pattern",
              "format", "default", "$ref", "allOf", "oneOf", "not")

    def walk(node, path="schema"):
        out = []
        if isinstance(node, dict):
            for k in BANNED:
                if k in node:
                    out.append("%s.%s" % (path, k))
            for k, v in node.items():
                out += walk(v, "%s.%s" % (path, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                out += walk(v, "%s[%d]" % (path, i))
        return out

    assert walk(IN.SCHEMA) == []

    # every object must be closed and list every one of its properties, or
    # the API rejects it
    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for v in node:
                yield from objects(v)

    for obj in objects(IN.SCHEMA):
        assert obj.get("additionalProperties") is False
        assert set(obj["properties"]) == set(obj["required"])

    # and it survives the round trip the API does to it
    import json
    assert json.loads(json.dumps(IN.SCHEMA)) == IN.SCHEMA

    # the ranges the schema can no longer state are still enforced, here
    wild = {"storeys": 9999, "cores_to_ground": 99, "lift_m": 900,
            "setback_m": 999, "void_growth_m": 99, "shape": "courtyard",
            "columns": {"spacing_m": 0.1, "diameter_mm": 99999}}
    spec = IN.to_spec(wild, "a 3 storey office of 2000 m2")
    assert 1 <= spec.storeys <= 60 and 0 <= spec.cores_to_ground <= 6
    assert 0 <= spec.lift_m <= 30 and 0 <= spec.setback <= 12
    assert 0 <= spec.void_growth_m <= 6
    assert 3.0 <= spec.columns["spacing_m"] <= 24.0
    assert 80 <= spec.columns["diameter_mm"] <= 2000


def test_a_port_someone_else_is_sitting_on_is_stepped_over():
    """An engine left running in a closed terminal is normal, not fatal."""
    import importlib.util, socket
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "archiai_run_port", os.path.join(root, "run.py"))
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)

    held = socket.socket()
    held.bind(("127.0.0.1", 0))
    taken = held.getsockname()[1]
    try:
        assert run.free_port(taken) == taken + 1
    finally:
        held.close()

    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    n = free.getsockname()[1]
    free.close()
    assert run.free_port(n) == n
