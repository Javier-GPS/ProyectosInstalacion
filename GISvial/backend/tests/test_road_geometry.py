import pytest

from app.services.ign_rt import match_ign_to_ways, _valid_link_props
from app.services.road_geometry import assign_tramos, geometry_signature, reconcile, resolve_way


def _way(lon1, lat1, lon2, lat2, way_id=1, **extra):
    geom = [{"lon": lon1, "lat": lat1}, {"lon": lon2, "lat": lat2}]
    way = {"geom": geom, "id": way_id}
    way.update(extra)
    return way


def _link(coords, lane_href=None, **props):
    feature = {
        "id": "VIAL_TR0001",
        "properties": {"fictitious": "false", **props},
        "geometry": {"type": "LineString", "coordinates": coords},
    }
    if lane_href:
        feature["properties"]["formofway_href"] = lane_href
    return feature


class TestIgnMatching:
    def test_matches_nearby_link(self):
        way = _way(-3.7038, 40.4202, -3.7020, 40.4206)
        link = _link(
            [[-3.7039, 40.4201, 600.0], [-3.7020, 40.4205, 600.0]],
            numberoflanes=2,
            functionalclass="mainRoad",
        )
        assert match_ign_to_ways([way], [link]) == 1
        assert way["ignProfile"]["numberoflanes"] == 2
        assert way["ignRef"] == "VIAL_TR0001"

    def test_ignores_far_link(self):
        way = _way(2.15, 41.39, 2.16, 41.39)
        link = _link([[2.0, 40.0], [2.1, 40.1]], numberoflanes=2)
        assert match_ign_to_ways([way], [link]) == 0
        assert "ignProfile" not in way

    def test_skips_fictitious_links(self):
        way = _way(-3.7038, 40.4202, -3.7020, 40.4206)
        link = _link([[-3.7039, 40.4201], [-3.7020, 40.4205]], numberoflanes=2)
        link["properties"]["fictitious"] = "true"
        assert match_ign_to_ways([way], [link]) == 0

    def test_skips_unclassified_links(self):
        # Urban-municipality links in the API carry fictitious=true and no
        # functionalclass — junk for geometry, must be skipped.
        way = _way(-3.7038, 40.4202, -3.7020, 40.4206)
        link = _link([[-3.7039, 40.4201], [-3.7020, 40.4205]], numberoflanes=1)
        assert match_ign_to_ways([way], [link]) == 0

    def test_matches_inventoried_road(self):
        way = _way(-3.7038, 40.4202, -3.7020, 40.4206)
        link = _link(
            [[-3.7039, 40.4201, 600.0], [-3.7020, 40.4205, 600.0]],
            numberoflanes=4,
            functionalclass="mainRoad",
            surfacecategory="paved",
        )
        assert match_ign_to_ways([way], [link]) == 1
        assert way["ignProfile"]["numberoflanes"] == 4

    def test_empty_inputs(self):
        assert match_ign_to_ways([], []) == 0


class TestResolveWay:
    def test_ign_wins_over_osm_for_lanes(self):
        record = {
            "id": 1,
            "tags": {"highway": "residential", "lanes": "2", "maxspeed": "50"},
            "ignProfile": {"numberoflanes": 2, "formofway_href": "http://inspire.ec.europa.eu/codelist/FormOfWayValue/singleCarriageway"},
        }
        result = resolve_way(record)
        assert result["merged"]["lanes"] == 2
        assert result["sources"]["lanes"] == "ign_rt"
        assert result["merged"]["dual"] is False
        assert result["sources"]["dual"] == "ign_rt"

    def test_catastro_section_width_becomes_platform_width(self):
        record = {"id": 2, "tags": {"highway": "primary", "width": "9.0"}, "sectionWidth": 14.0}
        result = resolve_way(record)
        assert result["merged"]["width"] == 9.0  # direct OSM keeps carriageway width
        assert result["merged"]["platformWidth"] == 14.0
        assert result["sources"]["platformWidth"] == "osm_buildings"

    def test_legacy_catastro_estwidth(self):
        record = {"id": 3, "tags": {"highway": "residential"}, "widthSrc": "catastro", "estWidth": 11.0}
        result = resolve_way(record)
        assert result["merged"]["platformWidth"] == 11.0
        assert result["sources"]["platformWidth"] == "catastro"

    def test_osm_buildings_section_width_provenance(self):
        record = {"id": 5, "tags": {"highway": "residential"}, "sectionWidth": 11.5, "sectionWidthSrc": "osm_buildings"}
        result = resolve_way(record)
        assert result["merged"]["platformWidth"] == 11.5
        assert result["sources"]["platformWidth"] == "osm_buildings"

    def test_ign_junk_lanes_never_override_osm(self):
        # IGN numberoflanes=1 (no-data filler) must not beat OSM's real lanes=2
        record = {"id": 6, "tags": {"highway": "residential", "lanes": "2"},
                  "ignProfile": {"numberoflanes": 1, "formofway_href": "http://inspire.ec.europa.eu/codelist/FormOfWayValue/dualCarriageway"}}
        result = resolve_way(record)
        assert result["merged"]["lanes"] == 2
        assert result["sources"]["lanes"] == "osm"

    def test_legacy_record_without_tags(self):
        record = {"id": 4, "estWidth": 6.5, "widthSrc": "lanes", "lanes": 2}
        result = resolve_way(record)
        assert result["merged"]["width"] == 6.5


class TestTramoAssignment:
    def test_splits_on_geometry_change(self):
        targets = [
            {"target_ref": "t0", "source_index": 0, "osmName": "Calle A", "geom": {"width": 6.0, "lanes": 2}},
            {"target_ref": "t1", "source_index": 1, "osmName": "Calle A", "geom": {"width": 8.0, "lanes": 3}},
            {"target_ref": "t2", "source_index": 2, "osmName": "Calle A", "geom": {"width": 8.0, "lanes": 3}},
        ]
        tramos = assign_tramos(targets)
        assert tramos["t0"]["tramoSeq"] == 1
        assert tramos["t1"]["tramoSeq"] == 2
        assert tramos["t2"]["tramoSeq"] == 2
        assert tramos["t2"]["tramoOf"] == 3
