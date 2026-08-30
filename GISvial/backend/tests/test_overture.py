import struct

from app.services.overture_source import (
    _coords,
    _width_from_rules,
    match_overture_to_ways,
)
from app.services.road_geometry import resolve_way


def _wkb_line(points):
    """Little-endian WKB: LineString type 2."""
    buf = struct.pack("<BI", 1, 2) + struct.pack("<I", len(points))
    for lon, lat in points:
        buf += struct.pack("<dd", lon, lat)
    return buf


class TestOvertureParsing:
    def test_wkb_line_coords(self):
        data = _wkb_line([(1.21, 41.09), (1.22, 41.10)])
        assert _coords(data) == [[1.21, 41.09], [1.22, 41.10]]

    def test_width_rules_scoped_and_global(self):
        assert _width_from_rules([{"value": 10.0, "between": None}]) == 10.0
        assert _width_from_rules([{"value": 4.5, "between": [0.1, 0.9]}]) == 4.5
        assert _width_from_rules([]) is None
        assert _width_from_rules(None) is None
        assert _width_from_rules([{"value": 0.5}]) is None  # sanity bounds

    def test_surface_and_maxspeed_rules(self):
        from app.services.overture_source import _maxspeed, _surface

        assert _surface([{"value": "paved"}]) == "paved"
        assert _maxspeed([{"value": {"max_speed": {"value": 50, "unit": "km/h"}}}]) == 50
        assert _maxspeed([{"value": {"max_speed": {"value": 0}}}]) is None


class TestOvertureMatching:
    def test_matches_aligned_way(self):
        way = {
            "id": 1,
            "geom": [{"lat": 41.10, "lon": 1.21}, {"lat": 41.1002, "lon": 1.2102}],
        }
        segs = [{
            "id": "seg1",
            "geometry": [[1.21, 41.10], [1.2102, 41.1002]],
            "width": 10.0,
            "class": "residential",
            "surface": "paved",
        }]
        assert match_overture_to_ways([way], segs) == 1
        assert way["overtureProfile"]["width"] == 10.0
        assert way["overtureRef"] == "seg1"

    def test_skips_far_way(self):
        way = {"id": 2, "geom": [{"lat": 40.0, "lon": 2.0}, {"lat": 40.001, "lon": 2.001}]}
        segs = [{"id": "seg1", "geometry": [[1.21, 41.10], [1.2102, 41.1002]], "width": 10.0}]
        assert match_overture_to_ways([way], segs) == 0


class TestOvertureResolution:
    def test_overture_width_wins_over_osm_default(self):
        record = {
            "id": 1,
            "tags": {"highway": "residential"},  # no explicit width → default estimate
            "overtureProfile": {"width": 10.0, "class": "residential", "surface": "paved"},
        }
        result = resolve_way(record)
        assert result["merged"]["width"] == 10.0
        assert result["sources"]["width"] == "overture"

    def test_osm_explicit_width_beats_overture(self):
        record = {
            "id": 2,
            "tags": {"highway": "residential", "width": "6.5"},
            "overtureProfile": {"width": 10.0, "class": "residential"},
        }
        result = resolve_way(record)
        assert result["merged"]["width"] == 6.5
        assert result["sources"]["width"] == "osm"
