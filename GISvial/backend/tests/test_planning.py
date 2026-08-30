import copy
import math
import unittest

from pydantic import ValidationError

from app.schemas.zones import GisPlanningDraftPut, GisRoadScopePut
from app.services.overpass import clip_geometry, normalize_element, parse_bbox, parse_overpass_payload
from app.services.planning import (
    base_inventory_hash,
    compact_payload,
    group_ref,
    inventory_counts,
    length_m,
    normalize_inventory,
)
from app.services.road_scope import calculate_route, normalize_scope_boundary
from app.services.street_merge import merge_streets


class PlanningInventoryTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {
                "type": "residential", "name": "Calle Mayor", "len": 1.25,
                "geom": [{"lat": 40.0, "lon": -3.0}, {"lat": 40.1, "lon": -3.1}],
            },
            {"type": "residential", "name": "Calle Mayor", "len": True, "startPt": "a", "endPt": "b"},
            {"type": "primary", "name": None, "len": 0},
        ]

    def test_normalizes_without_mutating_and_keeps_missing_geometry(self):
        original = copy.deepcopy(self.records)
        result = normalize_inventory("z1", self.records)

        self.assertEqual(self.records, original)
        self.assertEqual(result["counts"]["segment_count"], 3)
        self.assertEqual(result["counts"]["geometry_available"], 1)
        self.assertEqual(result["counts"]["geometry_unavailable"], 2)
        self.assertEqual(result["targets"][0]["geometry"], [[-3.0, 40.0], [-3.1, 40.1]])
        self.assertIsNone(result["targets"][1]["geometry"])
        self.assertRegex(result["targets"][0]["target_ref"], r"^s:0:[0-9a-f]{32}$")
        self.assertEqual(result["base_inventory_hash"], base_inventory_hash(self.records))

    def test_counts_streets_segments_and_metres(self):
        result = normalize_inventory("z1", self.records)
        residential = next(g for g in result["groups"] if g["road_type"] == "residential")

        self.assertEqual(result["counts"]["named_street_count"], 1)
        self.assertEqual(result["counts"]["unnamed_segment_count"], 1)
        self.assertEqual(residential["street_count"], 1)
        self.assertEqual(residential["target_count"], 2)
        self.assertEqual(residential["length_m"], 1250.0)
        self.assertEqual(residential["invalid_length_count"], 1)
        self.assertEqual(residential["group_ref"], group_ref("residential"))

    def test_source_order_changes_snapshot_hash(self):
        self.assertNotEqual(base_inventory_hash(self.records), base_inventory_hash(list(reversed(self.records))))

    def test_length_is_strict_and_uses_kilometres(self):
        self.assertEqual(length_m(1.25), 1250.0)
        self.assertEqual(length_m(0), 0.0)
        for value in (True, "1", -1, math.nan, math.inf):
            self.assertIsNone(length_m(value))

    def test_compaction_preserves_explicit_null(self):
        payload = {
            "group_defaults": {"g:1": {"lighting_class": None, "luxParams": {}}},
            "target_overrides": {"s:1": {}},
        }
        self.assertEqual(compact_payload(payload), {
            "group_defaults": {"g:1": {"lighting_class": None}},
            "target_overrides": {},
        })

    def test_separates_osm_name_from_reference_and_tracks_absence_state(self):
        result = normalize_inventory("z1", [
            {"id": 1, "type": "primary", "highway": "primary", "name": None, "ref": "N-1", "nameState": "ref_only", "roadRole": "main", "len": 0.1, "geom": [{"lat": 40, "lon": -3}, {"lat": 40.001, "lon": -3.001}]},
            {"id": 2, "type": "service", "highway": "service", "name": None, "noname": "yes", "nameState": "explicit_noname", "roadRole": "auxiliary", "len": 0.1, "geom": [{"lat": 40, "lon": -3}, {"lat": 40.001, "lon": -3.001}]},
        ])

        self.assertIsNone(result["targets"][0]["osmName"])
        self.assertEqual(result["targets"][0]["osmRef"], "N-1")
        self.assertEqual(result["targets"][0]["nameState"], "ref_only")
        self.assertEqual(result["targets"][1]["nameState"], "explicit_noname")
        self.assertEqual(result["counts"]["without_osm_name_count"], 2)
        self.assertEqual(result["counts"]["ref_only_count"], 1)
        self.assertEqual(result["counts"]["explicit_noname_count"], 1)
        self.assertEqual(result["road_role_counts"], {"main": 1, "auxiliary": 1})
        self.assertFalse(result["source_needs_refresh"])

    def test_merged_streets_do_not_invent_names_for_unnamed_targets(self):
        result = merge_streets([
            {"target_ref": "named", "group_ref": "g", "name": "Calle", "geometry": [[0, 0], [1, 0]], "length_m": 10},
            {"target_ref": "unnamed", "group_ref": "g", "name": None, "geometry": [[0, 1], [1, 1]], "length_m": 10},
        ], [{"group_ref": "g", "road_type": "residential"}])

        self.assertEqual([street["street"] for street in result], ["Calle"])

    def test_inventory_counts_matches_normalize_inventory_counts(self):
        counts = inventory_counts(self.records)["counts"]
        expected = normalize_inventory("z1", self.records)["counts"]
        self.assertEqual(counts, expected)


class PlanningSchemaTests(unittest.TestCase):
    def body(self, **patch):
        return {
            "mode": "update",
            "base_inventory_hash": "sha256:" + "0" * 64,
            "payload": {"group_defaults": {"g:1": patch}, "target_overrides": {}},
        }

    def test_accepts_current_une_families_and_legacy_distributions(self):
        for lighting_class in ("M1", "M6", "C0", "C5", "P1", "P7"):
            GisPlanningDraftPut.model_validate(self.body(lighting_class=lighting_class))
        for distribution in (
            "unilateral_r", "unilateral_l", "bilateral_pareado",
            "bilateral_tresbolillo", "centrada_mediana", "mediana_compartida",
        ):
            GisPlanningDraftPut.model_validate(self.body(distribution=distribution))

    def test_rejects_unknown_class_distribution_and_coerced_numbers(self):
        for patch in (
            {"lighting_class": "ME3"},
            {"distribution": "unknown"},
            {"spacing": "30"},
            {"spacing": True},
            {"spacing": -1},
            {"luxParams": {"cri": 101}},
        ):
            with self.assertRaises(ValidationError):
                GisPlanningDraftPut.model_validate(self.body(**patch))

    def test_recreate_requires_confirmation_and_empty_payload(self):
        body = self.body()
        body["mode"] = "recreate"
        with self.assertRaises(ValidationError):
            GisPlanningDraftPut.model_validate(body)

    def test_road_scope_rejects_client_route_and_invalid_anchor(self):
        body = {
            "base_inventory_hash": "sha256:" + "0" * 64,
            "boundary": {"type": "Polygon", "coordinates": []},
            "allowed_group_refs": ["g:1"],
            "a": {"target_ref": "s:1", "segment_index": 0, "segment_t": 0.2},
            "b": {"target_ref": "s:2", "segment_index": 0, "segment_t": 0.8},
        }
        GisRoadScopePut.model_validate(body)
        for patch in ({"path": []}, {"a": {**body["a"], "segment_t": 2}}, {"allowed_group_refs": ["g:1", "g:1"]}):
            with self.assertRaises(ValidationError):
                GisRoadScopePut.model_validate({**body, **patch})

class RoadScopeRoutingTests(unittest.TestCase):
    zone = {"type": "Polygon", "coordinates": [[[-2, -2], [2, -2], [2, 2], [-2, 2], [-2, -2]]]}
    scope = {"type": "Polygon", "coordinates": [[[-1.5, -1.5], [1.5, -1.5], [1.5, 1.5], [-1.5, 1.5], [-1.5, -1.5]]]}

    @staticmethod
    def inventory(targets):
        return {"groups": [{"group_ref": "g:road"}], "targets": [{"group_ref": "g:road", **target} for target in targets]}

    def test_routes_across_connected_targets_and_splits_anchors(self):
        inventory = self.inventory([
            {"target_ref": "t1", "geometry": [[0, 0], [1, 0]]},
            {"target_ref": "t2", "geometry": [[1, 0], [1, 1]]},
        ])
        route = calculate_route(
            inventory, self.zone, self.scope, {"g:road"},
            {"target_ref": "t1", "segment_index": 0, "segment_t": 0.2},
            {"target_ref": "t2", "segment_index": 0, "segment_t": 0.8},
        )
        self.assertEqual(route["path"], [[0.2, 0.0], [1, 0], [1.0, 0.8]])
        self.assertEqual({member["target_ref"] for member in route["members"]}, {"t1", "t2"})
        self.assertGreater(route["length_m"], 0)

    def test_clips_crossing_segment_to_scope(self):
        inventory = self.inventory([{"target_ref": "t", "geometry": [[-2, 0], [2, 0]]}])
        route = calculate_route(
            inventory, self.zone, self.scope, {"g:road"},
            {"target_ref": "t", "segment_index": 0, "segment_t": 0.2},
            {"target_ref": "t", "segment_index": 0, "segment_t": 0.7},
        )
        self.assertEqual(route["path"], [[-1.2, 0.0], [0.7999999999999998, 0.0]])

    def test_does_not_connect_visual_crossings(self):
        inventory = self.inventory([
            {"target_ref": "horizontal", "geometry": [[-1, 0], [1, 0]]},
            {"target_ref": "vertical", "geometry": [[0, -1], [0, 1]]},
        ])
        with self.assertRaisesRegex(ValueError, "NO_ROUTE"):
            calculate_route(
                inventory, self.zone, self.scope, {"g:road"},
                {"target_ref": "horizontal", "segment_index": 0, "segment_t": 0.2},
                {"target_ref": "vertical", "segment_index": 0, "segment_t": 0.8},
            )

    def test_rejects_invalid_or_outside_scope_boundary(self):
        with self.assertRaisesRegex(ValueError, "INVALID_BOUNDARY"):
            normalize_scope_boundary({"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]}, self.zone)
        with self.assertRaisesRegex(ValueError, "BOUNDARY_OUTSIDE_ZONE"):
            normalize_scope_boundary({"type": "Polygon", "coordinates": [[[0, 0], [3, 0], [3, 1], [0, 0]]]}, self.zone)
        zone_with_hole = {"type": "Polygon", "coordinates": [self.zone["coordinates"][0], [[-0.2, -0.2], [0.2, -0.2], [0.2, 0.2], [-0.2, 0.2], [-0.2, -0.2]]]}
        with self.assertRaisesRegex(ValueError, "BOUNDARY_OUTSIDE_ZONE"):
            normalize_scope_boundary({"type": "Polygon", "coordinates": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}, zone_with_hole)

class OverpassNormalizationTests(unittest.TestCase):
    def test_bbox_and_way_normalization(self):
        self.assertEqual(parse_bbox("40,41,-4,-3"), (40.0, 41.0, -4.0, -3.0))
        way = normalize_element({
            "id": 7,
            "tags": {"highway": "residential", "name": "Calle", "lanes": "2"},
            "geometry": [{"lat": 40.0, "lon": -3.0}, {"lat": 40.001, "lon": -3.001}],
        })
        self.assertEqual(way["type"], "residential")
        self.assertEqual(way["name"], "Calle")
        self.assertIsNone(way["ref"])
        self.assertEqual(way["nameState"], "named")
        self.assertEqual(way["roadRole"], "main")
        self.assertEqual(way["estWidth"], 6.0)  # 2 lanes × 3.0m (urban standard, no cycleway)
        self.assertGreater(way["len"], 0)

    def test_reference_is_not_promoted_to_name(self):
        way = normalize_element({
            "id": 8,
            "tags": {"highway": "primary", "ref": "N-1"},
            "geometry": [{"lat": 40.0, "lon": -3.0}, {"lat": 40.001, "lon": -3.001}],
        })
        self.assertIsNone(way["name"])
        self.assertEqual(way["ref"], "N-1")
        self.assertEqual(way["nameState"], "ref_only")

    def test_rejects_invalid_or_excessive_bbox(self):
        for bbox in ("", "41,40,-3,-4", "-90,90,-180,180"):
            with self.assertRaises(ValueError):
                parse_bbox(bbox)

    def test_clips_ways_to_bbox_and_rejects_remarks(self):
        bounds = (40.0, 41.0, -4.0, -3.0)
        parts = clip_geometry([
            {"lat": 40.5, "lon": -5.0},
            {"lat": 40.5, "lon": -3.5},
            {"lat": 40.5, "lon": -2.0},
        ], bounds)
        self.assertEqual(parts[0][0], {"lat": 40.5, "lon": -4.0})
        self.assertEqual(parts[0][-1], {"lat": 40.5, "lon": -3.0})
        with self.assertRaises(ValueError):
            parse_overpass_payload({"remark": "runtime error", "elements": []}, bounds)


if __name__ == "__main__":
    unittest.main()
