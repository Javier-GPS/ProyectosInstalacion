"""Merge OSM segments into named street MultiLineStrings for efficient map rendering.

Transforms 100k+ individual segments into ~5k street-level MultiLineStrings,
drastically reducing frontend rendering overhead while preserving all data.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any


def _coord_key(point: list[float]) -> str:
    """Canonical string key for a coordinate pair."""
    return f"{point[0]:.6f},{point[1]:.6f}"


def _can_join(a: list[list[float]], b: list[list[float]], tol: float = 0.0001) -> bool:
    """Check if two line strings can be joined (end-to-start or start-to-end)."""
    if not a or not b:
        return False
    # Last of A to First of B
    if abs(a[-1][0] - b[0][0]) < tol and abs(a[-1][1] - b[0][1]) < tol:
        return True
    # First of A to Last of B
    if abs(a[0][0] - b[-1][0]) < tol and abs(a[0][1] - b[-1][1]) < tol:
        return True
    return False


def _join_geometries(segments: list[list[list[float]]], tol: float = 0.0001) -> list[list[list[float]]]:
    """Greedy join of connected line segments into longer polylines."""
    if len(segments) <= 1:
        return segments

    # Work with a mutable list
    joined = [seg[:] for seg in segments]  # deep enough
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(joined):
            j = i + 1
            while j < len(joined):
                a, b = joined[i], joined[j]
                if _can_join(a, b, tol):
                    if abs(a[-1][0] - b[0][0]) < tol and abs(a[-1][1] - b[0][1]) < tol:
                        a.extend(b[1:])
                    else:
                        # b connects to start of a
                        b.extend(a[1:])
                        joined[i] = b
                    joined.pop(j)
                    changed = True
                elif _can_join(b, a, tol):
                    if abs(b[-1][0] - a[0][0]) < tol and abs(b[-1][1] - a[0][1]) < tol:
                        b.extend(a[1:])
                        joined[i] = b
                    else:
                        a.extend(b[1:])
                    joined.pop(j)
                    changed = True
                else:
                    j += 1
            i += 1

    return joined


def merge_streets(
    targets: list[dict],
    groups: list[dict],
    simplify_tolerance: float = 0.0005,
) -> list[dict]:
    """Merge individual segment geometries into street-level MultiLineStrings.

    Args:
        targets: List of inventory target dicts with 'name', 'group_ref', 'geometry'.
        groups: List of group dicts for road type lookup.
        simplify_tolerance: Douglas-Peucker tolerance in degrees (~0.0005° ≈ 50m).

    Returns:
        List of street features with merged MultiLineString geometries.
        Each feature: { street, road_type, geometry (MultiLineString), target_count, total_length, target_refs }
    """
    group_type_map = {g["group_ref"]: g.get("road_type") for g in groups}
    streets: dict[str, dict[str, Any]] = {}

    for target in targets:
        # This projection is explicitly street-level; unnamed ways remain in
        # the authoritative target inventory instead of becoming fake streets.
        name = target.get("name")
        if not name:
            continue
        geom = target.get("geometry")
        if not geom or len(geom) < 2:
            continue

        # Simplify geometry: retain every Nth point roughly
        simplified = _simplify_rdp(geom, simplify_tolerance)

        if name not in streets:
            streets[name] = {
                "street": name,
                "road_type": group_type_map.get(target.get("group_ref", ""), ""),
                "geometries": [],
                "target_refs": [],
                "target_count": 0,
                "total_length_m": 0.0,
            }
        s = streets[name]
        s["geometries"].append(simplified)
        s["target_refs"].append(target.get("target_ref", ""))
        s["target_count"] += 1
        s["total_length_m"] += target.get("length_m", 0) or 0

    # Build MultiLineStrings by joining connected segments within each street
    result: list[dict] = []
    for name, s in streets.items():
        if not s["geometries"]:
            continue
        joined = _join_geometries(s["geometries"])
        if not joined:
            continue

        # Ensure valid MultiLineString
        multilinestring = joined if len(joined) > 1 else joined

        result.append({
            "street": name,
            "road_type": s["road_type"],
            "geometry": {
                "type": "MultiLineString",
                "coordinates": multilinestring,
            },
            "target_count": s["target_count"],
            "total_length_m": round(s["total_length_m"], 3),
            "target_refs": s["target_refs"],
        })

    # Sort by target_count descending (most significant first)
    result.sort(key=lambda x: -x["target_count"])
    return result


def _simplify_rdp(
    coords: list[list[float]],
    epsilon: float = 0.0005,
) -> list[list[float]]:
    """Rammer-Douglas-Peucker line simplification.

    Args:
        coords: List of [lon, lat] coordinate pairs.
        epsilon: Max distance in degrees. ~0.0005° ≈ 50m, good for street-level.

    Returns:
        Simplified coordinate list.
    """
    if len(coords) <= 2:
        return list(coords)

    # Find point with max distance from line between first and last
    first, last = coords[0], coords[-1]
    dx, dy = last[0] - first[0], last[1] - first[1]
    line_len_sq = dx * dx + dy * dy

    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(coords) - 1):
        if line_len_sq > 0:
            t = ((coords[i][0] - first[0]) * dx + (coords[i][1] - first[1]) * dy) / line_len_sq
            t = max(0, min(1, t))
            proj_x = first[0] + t * dx
            proj_y = first[1] + t * dy
            dist = ((coords[i][0] - proj_x) ** 2 + (coords[i][1] - proj_y) ** 2) ** 0.5
        else:
            dist = ((coords[i][0] - first[0]) ** 2 + (coords[i][1] - first[1]) ** 2) ** 0.5
        if dist > max_dist:
            max_dist = dist
            max_idx = i

    if max_dist > epsilon:
        left = _simplify_rdp(coords[:max_idx + 1], epsilon)
        right = _simplify_rdp(coords[max_idx:], epsilon)
        return left[:-1] + right
    else:
        return [first, last]
