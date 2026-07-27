"""Read-only normalization for mixed Legacy/current zone geometry formats."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


def _numbers(value: object, size: int) -> list[float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != size:
        return None
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(item) for item in result) else None


def _valid_bbox(bbox: list[float]) -> bool:
    west, south, east, north = bbox
    return -180 <= west < east <= 180 and -90 <= south < north <= 90


def normalize_bbox(value: object, center: tuple[float | None, float | None]) -> tuple[list[float] | None, str | None, str]:
    parts = _numbers(value.split(",") if isinstance(value, str) else value, 4)
    if parts is None:
        return None, None, "missing" if not value else "invalid"
    south, second, third, east = parts
    candidates = [
        ("south_west_north_east", [second, south, east, third]),
        ("south_north_west_east", [third, south, east, second]),
    ]
    valid = [(name, bbox) for name, bbox in candidates if _valid_bbox(bbox)]
    unique = {(tuple(bbox)): (name, bbox) for name, bbox in valid}
    valid = list(unique.values())
    if len(valid) == 1:
        name, bbox = valid[0]
        return bbox, name, "valid"
    lat, lon = center
    if len(valid) > 1 and lat is not None and lon is not None:
        containing = [item for item in valid if item[1][0] <= lon <= item[1][2] and item[1][1] <= lat <= item[1][3]]
        if len(containing) == 1:
            name, bbox = containing[0]
            return bbox, name, "valid"
    return None, None, "ambiguous" if valid else "invalid"


def _ring(value: object, swap: bool) -> list[list[float]] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    points: list[list[float]] = []
    for raw in value:
        point = _numbers(raw, 2)
        if point is None:
            return None
        x, y = (point[1], point[0]) if swap else point
        if not (-180 <= x <= 180 and -90 <= y <= 90):
            return None
        points.append([x, y])
    if len(points) < 3:
        return None
    if points[0] != points[-1]:
        points.append(points[0].copy())
    return points


def _contains(ring: list[list[float]], point: tuple[float, float]) -> bool:
    x, y = point
    inside = False
    for first, second in zip(ring, ring[1:]):
        x1, y1 = first
        x2, y2 = second
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def normalize_polygon(
    value: object,
    center: tuple[float | None, float | None],
    bbox: list[float] | None,
) -> tuple[list[list[float]] | None, str | None, str]:
    if not value:
        return None, None, "missing"
    candidates = [("longitude_latitude", _ring(value, False)), ("latitude_longitude", _ring(value, True))]
    valid = [(name, ring) for name, ring in candidates if ring is not None]
    unique = {tuple(tuple(point) for point in ring): (name, ring) for name, ring in valid}
    valid = list(unique.values())
    if len(valid) == 1:
        name, ring = valid[0]
        return ring, name, "valid"
    lat, lon = center
    target = (lon, lat) if lat is not None and lon is not None else None
    if target is None and bbox is not None:
        target = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    if len(valid) > 1 and target is not None:
        containing = [(name, ring) for name, ring in valid if _contains(ring, target)]
        if len(containing) == 1:
            name, ring = containing[0]
            return ring, name, "valid"
    return None, None, "ambiguous" if valid else "invalid"


def _geojson_boundary(value: object) -> dict | None:
    if not isinstance(value, Mapping) or value.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    geometry_type = value["type"]
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, Sequence) or isinstance(coordinates, (str, bytes)):
        return None
    polygons = coordinates if geometry_type == "MultiPolygon" else [coordinates]
    normalized: list[list[list[list[float]]]] = []
    for polygon in polygons:
        if not isinstance(polygon, Sequence) or isinstance(polygon, (str, bytes)) or not polygon:
            return None
        rings: list[list[list[float]]] = []
        for raw_ring in polygon:
            ring = _ring(raw_ring, False)
            if ring is None:
                return None
            rings.append(ring)
        normalized.append(rings)
    return {
        "type": geometry_type,
        "coordinates": normalized if geometry_type == "MultiPolygon" else normalized[0],
    }


def _boundary_points(boundary: dict) -> list[list[float]]:
    polygons = boundary["coordinates"] if boundary["type"] == "MultiPolygon" else [boundary["coordinates"]]
    return [point for polygon in polygons for ring in polygon for point in ring]


def normalize_zone_geometry(zone: object) -> dict:
    center = (getattr(zone, "center_lat", None), getattr(zone, "center_lon", None))
    bbox, bbox_format, bbox_status = normalize_bbox(getattr(zone, "bbox", ""), center)
    raw_boundary = getattr(zone, "bounds_polygon", [])
    boundary = _geojson_boundary(raw_boundary)
    if boundary:
        polygon = boundary["coordinates"][0] if boundary["type"] == "Polygon" else None
        polygon_format, polygon_status = "geojson", "valid"
    else:
        polygon, polygon_format, polygon_status = normalize_polygon(raw_boundary, center, bbox)
        boundary = {"type": "Polygon", "coordinates": [polygon]} if polygon else None
    if boundary and bbox is None:
        points = _boundary_points(boundary)
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    if boundary:
        status = "valid"
    elif bbox:
        status = "bbox_only"
    elif "ambiguous" in (bbox_status, polygon_status):
        status = "ambiguous"
    elif "invalid" in (bbox_status, polygon_status):
        status = "invalid"
    else:
        status = "missing"
    return {
        "bbox": bbox,
        "polygon": polygon,
        "boundary": boundary,
        "status": status,
        "source_format": {"bbox": bbox_format, "polygon": polygon_format},
    }
