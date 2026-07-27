"""Fetch and normalize OSM roads from public Overpass mirrors."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping

import httpx


OVERPASS_URLS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
DEFAULT_WIDTHS = {
    "motorway": 10.5, "trunk": 9.0, "primary": 7.0, "secondary": 6.0,
    "tertiary": 5.5, "residential": 4.5, "living_street": 4.0,
    "service": 3.5, "pedestrian": 3.0, "footway": 2.0, "path": 2.0,
    "cycleway": 2.0,
}


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        south, north, west, east = (float(part.strip()) for part in value.split(","))
    except (TypeError, ValueError) as exc:
        raise ValueError("Zone has no valid bbox") from exc
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise ValueError("Zone bbox is outside coordinate bounds")
    if (north - south) * (east - west) > 2:
        raise ValueError("Zone bbox is too large for one Overpass request")
    return south, north, west, east


def _number(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", value)
    return float(match.group(0).replace(",", ".")) if match else None


def _haversine_km(points: list[dict]) -> float:
    total = 0.0
    for first, second in zip(points, points[1:]):
        lat1, lon1 = math.radians(first["lat"]), math.radians(first["lon"])
        lat2, lon2 = math.radians(second["lat"]), math.radians(second["lon"])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        total += 6371.0088 * 2 * math.asin(math.sqrt(a))
    return total


def _clip_segment(first: dict, second: dict, bounds: tuple[float, float, float, float]) -> tuple[dict, dict] | None:
    south, north, west, east = bounds
    x1, y1, x2, y2 = first["lon"], first["lat"], second["lon"], second["lat"]
    dx, dy = x2 - x1, y2 - y1
    start, end = 0.0, 1.0
    for p, q in ((-dx, x1 - west), (dx, east - x1), (-dy, y1 - south), (dy, north - y1)):
        if p == 0:
            if q < 0:
                return None
            continue
        ratio = q / p
        if p < 0:
            start = max(start, ratio)
        else:
            end = min(end, ratio)
        if start > end:
            return None
    return (
        {"lat": y1 + start * dy, "lon": x1 + start * dx},
        {"lat": y1 + end * dy, "lon": x1 + end * dx},
    )


def clip_geometry(points: list[dict], bounds: tuple[float, float, float, float]) -> list[list[dict]]:
    """Clip a polyline to the request bbox, preserving disjoint pieces."""
    parts: list[list[dict]] = []
    current: list[dict] = []
    for first, second in zip(points, points[1:]):
        clipped = _clip_segment(first, second, bounds)
        if clipped is None:
            if len(current) >= 2:
                parts.append(current)
            current = []
            continue
        clipped_first, clipped_second = clipped
        if current and current[-1] == clipped_first:
            if current[-1] != clipped_second:
                current.append(clipped_second)
        else:
            if len(current) >= 2:
                parts.append(current)
            current = [clipped_first, clipped_second]
    if len(current) >= 2:
        parts.append(current)
    return parts


def normalize_element(element: Mapping) -> dict | None:
    tags = element.get("tags") if isinstance(element.get("tags"), Mapping) else {}
    geometry = element.get("geometry")
    if not isinstance(geometry, list) or len(geometry) < 2:
        return None
    points: list[dict[str, float]] = []
    for point in geometry:
        if not isinstance(point, Mapping):
            return None
        lat, lon = point.get("lat"), point.get("lon")
        if type(lat) not in (int, float) or type(lon) not in (int, float):
            return None
        points.append({"lat": float(lat), "lon": float(lon)})

    highway = str(tags.get("highway") or "unclassified")
    is_tunnel = str(tags.get("tunnel") or "").lower() in {"yes", "true", "1", "culvert"}
    road_type = "tunnel" if is_tunnel else highway
    width = _number(tags.get("width"))
    lanes = _number(tags.get("lanes"))
    if width is not None:
        estimated_width, width_source = width, "osm_width"
    elif lanes is not None:
        estimated_width, width_source = lanes * 3.5, "lanes"
    else:
        estimated_width, width_source = DEFAULT_WIDTHS.get(highway, 4.0), "default"

    return {
        "id": element.get("id"),
        "type": road_type,
        "name": tags.get("name") or tags.get("ref"),
        "len": round(_haversine_km(points), 6),
        "geom": points,
        "estWidth": estimated_width,
        "width": width,
        "widthSrc": width_source,
        "lanes": lanes,
        "dual": str(tags.get("oneway") or "").lower() in {"yes", "true", "1"},
        "surface": tags.get("surface"),
        "sidewalk": tags.get("sidewalk"),
        "tunnel": is_tunnel,
    }


def parse_overpass_payload(payload: object, bounds: tuple[float, float, float, float]) -> list[dict]:
    if not isinstance(payload, Mapping):
        raise ValueError("Overpass response root is invalid")
    if payload.get("remark"):
        raise ValueError(f"Overpass returned an incomplete response: {payload['remark']}")
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise ValueError("Overpass response has no elements list")

    ways: list[dict] = []
    for element in elements:
        if not isinstance(element, Mapping):
            raise ValueError("Overpass returned an invalid element")
        way = normalize_element(element)
        if way is None:
            raise ValueError("Overpass returned a way without valid geometry")
        for part_index, geometry in enumerate(clip_geometry(way["geom"], bounds)):
            clipped = {**way, "geom": geometry, "len": round(_haversine_km(geometry), 6)}
            if part_index:
                clipped["clipPart"] = part_index
            ways.append(clipped)
    return ways


async def fetch_roads(bbox: str) -> tuple[list[dict], str]:
    bounds = parse_bbox(bbox)
    south, north, west, east = bounds
    query = (
        f'[out:json][timeout:60];way["highway"]'
        f"({south},{west},{north},{east});out tags geom;"
    )
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=90, headers={"User-Agent": "SALVI-GIS/1.0"}) as client:
        for url in OVERPASS_URLS:
            try:
                response = await client.post(url, content=query)
                response.raise_for_status()
                ways = parse_overpass_payload(response.json(), bounds)
                return ways, url
            except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
                errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors) or "No Overpass mirror available")
