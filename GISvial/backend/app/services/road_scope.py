"""Validate a manual road scope and route through the current OSM snapshot."""
from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence

EARTH_M = 6371008.8
EPS = 1e-10


def geometry_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "md5:" + hashlib.md5(raw.encode()).hexdigest()


def _point(value: object) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError("INVALID_BOUNDARY")
    try:
        point = float(value[0]), float(value[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_BOUNDARY") from exc
    if not all(math.isfinite(item) for item in point) or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
        raise ValueError("INVALID_BOUNDARY")
    return point


def _cross(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _on_segment(point, first, second) -> bool:
    edge = second[0] - first[0], second[1] - first[1]
    offset = point[0] - first[0], point[1] - first[1]
    length = math.hypot(*edge)
    projection = offset[0] * edge[0] + offset[1] * edge[1]
    return bool(length) and abs(_cross(edge, offset)) <= 1e-12 * length and -1e-12 * length <= projection <= length * length + 1e-12 * length


def _on_ring(point, ring) -> bool:
    return any(_on_segment(point, first, second) for first, second in zip(ring, ring[1:]))


def _in_ring(point, ring) -> bool:
    inside = False
    for first, second in zip(ring, ring[1:]):
        if (first[1] > point[1]) != (second[1] > point[1]) and point[0] < (second[0] - first[0]) * (point[1] - first[1]) / (second[1] - first[1]) + first[0]:
            inside = not inside
    return inside


def _in_polygon(point, polygon) -> bool:
    return bool(polygon and (_on_ring(point, polygon[0]) or _in_ring(point, polygon[0])) and not any(not _on_ring(point, ring) and _in_ring(point, ring) for ring in polygon[1:]))


def point_in_boundary(point, boundary: Mapping) -> bool:
    polygons = boundary["coordinates"] if boundary["type"] == "MultiPolygon" else [boundary["coordinates"]]
    return any(_in_polygon(point, polygon) for polygon in polygons)


def _intersection_measures(first, second, ring) -> list[float]:
    edge = second[0] - first[0], second[1] - first[1]
    edge_len2 = edge[0] ** 2 + edge[1] ** 2
    measures: list[float] = []
    for start, end in zip(ring, ring[1:]):
        boundary_edge = end[0] - start[0], end[1] - start[1]
        offset = start[0] - first[0], start[1] - first[1]
        denominator = _cross(edge, boundary_edge)
        if abs(denominator) > 1e-12:
            t = _cross(offset, boundary_edge) / denominator
            u = _cross(offset, edge) / denominator
            if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
                measures.append(max(0.0, min(1.0, t)))
        elif edge_len2 and abs(_cross(offset, edge)) <= 1e-12 * math.sqrt(edge_len2):
            for point in (start, end):
                t = ((point[0] - first[0]) * edge[0] + (point[1] - first[1]) * edge[1]) / edge_len2
                measures.append(max(0.0, min(1.0, t)))
    return measures


def clip_segment(first, second, boundaries: Sequence[Mapping]) -> list[tuple[float, float]]:
    measures = [0.0, 1.0]
    for boundary in boundaries:
        polygons = boundary["coordinates"] if boundary["type"] == "MultiPolygon" else [boundary["coordinates"]]
        for polygon in polygons:
            for ring in polygon:
                measures.extend(_intersection_measures(first, second, ring))
    measures.sort()
    unique = [value for index, value in enumerate(measures) if index == 0 or abs(value - measures[index - 1]) > EPS]
    return [
        (start, end) for start, end in zip(unique, unique[1:])
        if end - start > EPS and all(point_in_boundary((first[0] + (start + end) / 2 * (second[0] - first[0]), first[1] + (start + end) / 2 * (second[1] - first[1])), boundary) for boundary in boundaries)
    ]


def _segments_intersect(a, b, c, d) -> bool:
    def orientation(first, second, third):
        return _cross((second[0] - first[0], second[1] - first[1]), (third[0] - first[0], third[1] - first[1]))
    values = orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)
    if values[0] * values[1] < -EPS and values[2] * values[3] < -EPS:
        return True
    return any(abs(value) <= EPS and _on_segment(point, first, second) for value, point, first, second in (
        (values[0], c, a, b), (values[1], d, a, b), (values[2], a, c, d), (values[3], b, c, d),
    ))


def normalize_scope_boundary(value: object, zone_boundary: Mapping) -> dict:
    if not isinstance(value, Mapping) or value.get("type") != "Polygon":
        raise ValueError("INVALID_BOUNDARY")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, Sequence) or isinstance(coordinates, (str, bytes)) or len(coordinates) != 1:
        raise ValueError("INVALID_BOUNDARY")
    raw_ring = coordinates[0]
    if not isinstance(raw_ring, Sequence) or isinstance(raw_ring, (str, bytes)) or not 3 <= len(raw_ring) <= 201:
        raise ValueError("INVALID_BOUNDARY")
    ring = [_point(value) for value in raw_ring]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    if len(set(ring[:-1])) < 3:
        raise ValueError("INVALID_BOUNDARY")
    segment_count = len(ring) - 1
    for first_index in range(segment_count):
        for second_index in range(first_index + 1, segment_count):
            if second_index in {first_index, first_index + 1} or (first_index == 0 and second_index == segment_count - 1):
                continue
            if _segments_intersect(ring[first_index], ring[first_index + 1], ring[second_index], ring[second_index + 1]):
                raise ValueError("INVALID_BOUNDARY")
    boundary = {"type": "Polygon", "coordinates": [[list(point) for point in ring]]}
    if any(not clip_segment(first, second, [zone_boundary]) or sum(end - start for start, end in clip_segment(first, second, [zone_boundary])) < 1 - EPS for first, second in zip(ring, ring[1:])):
        raise ValueError("BOUNDARY_OUTSIDE_ZONE")
    zone_polygons = zone_boundary["coordinates"] if zone_boundary["type"] == "MultiPolygon" else [zone_boundary["coordinates"]]
    if any(point_in_boundary(tuple(hole[0]), boundary) for polygon in zone_polygons for hole in polygon[1:]):
        raise ValueError("BOUNDARY_OUTSIDE_ZONE")
    return boundary


def _distance(first, second) -> float:
    lat1, lat2 = math.radians(first[1]), math.radians(second[1])
    dlat, dlon = lat2 - lat1, math.radians(second[0] - first[0])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_M * 2 * math.asin(math.sqrt(value))


def _coordinate(first, second, measure: float):
    if measure <= EPS:
        return first
    if measure >= 1 - EPS:
        return second
    return first[0] + measure * (second[0] - first[0]), first[1] + measure * (second[1] - first[1])


def calculate_route(inventory: Mapping, zone_boundary: Mapping, scope_boundary: Mapping, allowed_groups: set[str], anchor_a: Mapping, anchor_b: Mapping) -> dict:
    if not allowed_groups:
        raise ValueError("INVALID_GROUP_REFS")
    known_groups = {group["group_ref"] for group in inventory["groups"]}
    if not allowed_groups.issubset(known_groups):
        raise ValueError("GROUP_REF_UNKNOWN")
    targets = {target["target_ref"]: target for target in inventory["targets"] if target["group_ref"] in allowed_groups and target.get("geometry")}
    anchors = {"a": anchor_a, "b": anchor_b}
    for name, anchor in anchors.items():
        target = targets.get(anchor["target_ref"])
        index = anchor["segment_index"]
        if target is None or index >= len(target["geometry"]) - 1:
            raise ValueError(f"INVALID_ANCHOR_{name.upper()}")

    graph = defaultdict(list)
    anchor_nodes = {}
    edge_count = 0
    for target in targets.values():
        geometry = [tuple(point) for point in target["geometry"]]
        for index, (first, second) in enumerate(zip(geometry, geometry[1:])):
            for start, end in clip_segment(first, second, [scope_boundary]):
                cuts = [start, end]
                for name, anchor in anchors.items():
                    if anchor["target_ref"] == target["target_ref"] and anchor["segment_index"] == index and start - EPS <= anchor["segment_t"] <= end + EPS:
                        measure = max(start, min(end, anchor["segment_t"]))
                        cuts.append(measure)
                        anchor_nodes[name] = _coordinate(first, second, measure)
                cuts = sorted(set(cuts))
                for from_t, to_t in zip(cuts, cuts[1:]):
                    start_node, end_node = _coordinate(first, second, from_t), _coordinate(first, second, to_t)
                    weight = _distance(start_node, end_node)
                    if weight <= 0:
                        continue
                    edge = {"target_ref": target["target_ref"], "segment_index": index, "from_t": from_t, "to_t": to_t, "length_m": weight, "_from_node": start_node}
                    graph[start_node].append((end_node, weight, edge))
                    graph[end_node].append((start_node, weight, edge))
                    edge_count += 1
                    if edge_count > 100000:
                        raise ValueError("GRAPH_LIMIT_EXCEEDED")
    if "a" not in anchor_nodes or "b" not in anchor_nodes:
        raise ValueError("ANCHOR_OUTSIDE_SCOPE")
    start_node, end_node = anchor_nodes["a"], anchor_nodes["b"]
    if start_node == end_node:
        raise ValueError("ZERO_LENGTH_ROUTE")

    distances = {start_node: 0.0}
    previous = {}
    queue = [(0.0, start_node)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if node == end_node:
            break
        for neighbour, weight, edge in sorted(graph[node], key=lambda item: (item[0], item[2]["target_ref"], item[2]["segment_index"])):
            candidate = distance + weight
            if candidate + 1e-8 < distances.get(neighbour, math.inf):
                distances[neighbour] = candidate
                previous[neighbour] = node, edge
                heapq.heappush(queue, (candidate, neighbour))
    if end_node not in distances:
        raise ValueError("NO_ROUTE")

    nodes = [end_node]
    traversed = []
    while nodes[-1] != start_node:
        prior, edge = previous[nodes[-1]]
        traversed.append((prior, nodes[-1], edge))
        nodes.append(prior)
    nodes.reverse()
    traversed.reverse()
    members = []
    for first, second, edge in traversed:
        forward = first == edge["_from_node"]
        members.append({
            "from_t": edge["from_t"] if forward else edge["to_t"],
            "to_t": edge["to_t"] if forward else edge["from_t"],
            "target_ref": edge["target_ref"],
            "segment_index": edge["segment_index"],
            "length_m": round(edge["length_m"], 3),
            "geometry": [list(first), list(second)],
        })
    return {
        "path": [list(node) for node in nodes],
        "length_m": round(distances[end_node], 3),
        "members": members,
        "topology_basis": "exact-coordinate",
        "topology_limitations": ["osm-node-ids-and-layers-unavailable", "oneway-not-enforced"],
    }
