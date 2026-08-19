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

    jpeg = base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 64).decode()
    r = client.post("/v1/trace", json={"image": {"data": jpeg}})
    assert r.status_code == 422
    assert "PNG" in r.json()["detail"] or "Pillow" in r.json()["detail"]

    two = client.post("/v1/generate", json={"brief": "an office",
                                            "image": {"data": "aGk="}})
    assert two.status_code == 422
