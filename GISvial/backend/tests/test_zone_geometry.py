import copy
import unittest
from types import SimpleNamespace

from app.services.zone_geometry import normalize_bbox, normalize_zone_geometry


class ZoneGeometryTests(unittest.TestCase):
    def test_normalizes_current_and_legacy_bbox(self):
        self.assertEqual(
            normalize_bbox("38.026,38.066,-2.868,-2.828", (38.04, -2.84))[0],
            [-2.868, 38.026, -2.828, 38.066],
        )
        self.assertEqual(
            normalize_bbox("41.49,1.87,41.53,1.93", (41.51, 1.9))[0],
            [1.87, 41.49, 1.93, 41.53],
        )

    def test_normalizes_legacy_polygon_without_mutation(self):
        polygon = [[41.49, 1.87], [41.49, 1.93], [41.53, 1.93], [41.53, 1.87]]
        original = copy.deepcopy(polygon)
        zone = SimpleNamespace(
            bbox="41.49,1.87,41.53,1.93",
            bounds_polygon=polygon,
            center_lat=41.51,
            center_lon=1.9,
        )
        result = normalize_zone_geometry(zone)
        self.assertEqual(polygon, original)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["polygon"][0], [1.87, 41.49])
        self.assertEqual(result["polygon"][-1], result["polygon"][0])
        self.assertEqual(result["source_format"]["polygon"], "latitude_longitude")
        self.assertEqual(result["boundary"]["type"], "Polygon")

    def test_keeps_geojson_polygon_and_derives_bbox(self):
        zone = SimpleNamespace(
            bbox="",
            bounds_polygon=[[-3.1, 40.0], [-3.0, 40.0], [-3.0, 40.1], [-3.1, 40.1]],
            center_lat=40.05,
            center_lon=-3.05,
        )
        result = normalize_zone_geometry(zone)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["bbox"], [-3.1, 40.0, -3.0, 40.1])
        self.assertEqual(result["source_format"]["polygon"], "longitude_latitude")

    def test_does_not_guess_ambiguous_bbox(self):
        bbox, source_format, status = normalize_bbox("1,2,3,4", (None, None))
        self.assertIsNone(bbox)
        self.assertIsNone(source_format)
        self.assertEqual(status, "ambiguous")

    def test_reports_missing_geometry(self):
        zone = SimpleNamespace(bbox="", bounds_polygon=[], center_lat=None, center_lon=None)
        self.assertEqual(normalize_zone_geometry(zone)["status"], "missing")

    def test_does_not_guess_ambiguous_polygon(self):
        zone = SimpleNamespace(
            bbox="-1,-2,1,2",
            bounds_polygon=[[-2, -1], [2, -1], [2, 1], [-2, 1]],
            center_lat=0,
            center_lon=0,
        )
        result = normalize_zone_geometry(zone)
        self.assertIsNone(result["polygon"])
        self.assertEqual(result["status"], "bbox_only")

    def test_keeps_geojson_multipolygon(self):
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [[[[-3.1, 40.0], [-3.0, 40.0], [-3.0, 40.1], [-3.1, 40.0]]]],
        }
        zone = SimpleNamespace(bbox="", bounds_polygon=geometry, center_lat=40.05, center_lon=-3.05)
        result = normalize_zone_geometry(zone)
        self.assertEqual(result["boundary"], geometry)
        self.assertEqual(result["source_format"]["polygon"], "geojson")


if __name__ == "__main__":
    unittest.main()
