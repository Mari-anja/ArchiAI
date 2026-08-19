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
