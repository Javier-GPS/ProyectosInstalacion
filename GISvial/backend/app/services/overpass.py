"""Fetch and normalize OSM roads from public Overpass mirrors."""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import Collection, Mapping, Sequence

import httpx

from ..core.redis import cache_get, cache_set

OVERPASS_URLS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

OVERPASS_TIMEOUT = 180  # HTTP client timeout (seconds)
OVERPASS_QUERY_TIMEOUT = 120  # Overpass query timeout (seconds)
OVERPASS_CACHE_TTL = 3600  # 1 hour cache for Overpass responses
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
        # Deduct 1 carril for bike lane if present, use 3.0m/lane urban standard
        has_bike = str(tags.get("cycleway") or "").lower() in {"yes", "true", "1", "lane", "track", "separate"}
        effective_lanes = lanes - (1 if has_bike else 0)
        estimated_width, width_source = effective_lanes * 3.0, "lanes"
    else:
        estimated_width, width_source = DEFAULT_WIDTHS.get(highway, 4.0), "default"

    # Sidewalk width from explicit OSM tags
    sw_left_tag = tags.get("sidewalk:left:width") or tags.get("sidewalk:both:width")
    sw_right_tag = tags.get("sidewalk:right:width") or tags.get("sidewalk:both:width")
    sw_width_tag = tags.get("sidewalk:width")
    sw_left = _number(sw_left_tag) if sw_left_tag else None
    sw_right = _number(sw_right_tag) if sw_right_tag else None
    if sw_left is None and sw_right is None and sw_width_tag:
        sw_left = sw_right = _number(sw_width_tag)

    # Median detection
    median_raw = str(tags.get("median") or "").lower()
    median = median_raw in {"yes", "true", "1"}
    median_width = _number(tags.get("median:width"))
    dual_carriageway = str(tags.get("dual_carriageway") or "").lower() in {"yes", "true", "1", "separate"}
    if not dual_carriageway and median:
        dual_carriageway = True

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
        "sidewalk": tags.get("sidewalk"),
        "sidewalkWidthLeft": sw_left,
        "sidewalkWidthRight": sw_right,
        "median": median,
        "medianWidth": median_width,
        "dual": dual_carriageway,
        "surface": tags.get("surface"),
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


def _point_in_ring(lon: float, lat: float, ring: Sequence) -> bool:
    inside = False
    for i in range(len(ring) - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if (y1 > lat) != (y2 > lat):
            x_intersect = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_intersect:
                inside = not inside
    return inside


def _point_in_polygon(lon: float, lat: float, polygon: Collection) -> bool:
    rings = polygon if polygon and isinstance(polygon[0][0], (list, tuple)) else [polygon]
    return _point_in_ring(lon, lat, rings[0]) and not any(
        _point_in_ring(lon, lat, ring) for ring in rings[1:]
    )


def _parse_bounds_polygon(raw: object) -> list | None:
    if isinstance(raw, dict) and raw.get("type") in ("Polygon", "MultiPolygon"):
        coords = raw["coordinates"]
        return coords[0] if raw["type"] == "Polygon" else coords[0][0]
    if isinstance(raw, (list, tuple)) and len(raw) >= 3:
        pt = raw[0]
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            return raw
    return None


def filter_ways_to_polygon(ways: list[dict], polygon: object) -> list[dict]:
    ring = _parse_bounds_polygon(polygon)
    if not ring:
        return ways
    filtered: list[dict] = []
    for way in ways:
        geom = way.get("geom")
        if not isinstance(geom, (list, tuple)) or len(geom) < 2:
            continue
        keep = any(
            _point_in_polygon(pt["lon"], pt["lat"], ring) for pt in geom
        )
        if keep:
            filtered.append(way)
    return filtered


def _build_query(bounds: tuple[float, float, float, float]) -> str:
    south, north, west, east = bounds
    return (
        f'[out:json][timeout:{OVERPASS_QUERY_TIMEOUT}];'
        f'way["highway"]'
        f"({south},{west},{north},{east});out tags geom;"
    )


def _cache_key(bounds: tuple[float, float, float, float]) -> str:
    raw = f"{bounds[0]:.6f},{bounds[1]:.6f},{bounds[2]:.6f},{bounds[3]:.6f}"
    h = hashlib.md5(raw.encode()).hexdigest()
    return f"overpass:roads:{h}"


async def _try_mirror(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    bounds: tuple[float, float, float, float],
) -> tuple[list[dict], str]:
    """Try a single Overpass mirror. Raises on failure."""
    response = await client.post(url, content=query)
    response.raise_for_status()
    ways = parse_overpass_payload(response.json(), bounds)
    return ways, url


async def fetch_roads(bbox: str) -> tuple[list[dict], str]:
    bounds = parse_bbox(bbox)
    query = _build_query(bounds)
    cache_key = _cache_key(bounds)

    # ── Try Redis cache first ──────────────────────────────────────────
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, list) and len(cached) == 2:
        return cached[0], cached[1]

    errors: list[str] = []
    async with httpx.AsyncClient(
        timeout=OVERPASS_TIMEOUT,
        headers={"User-Agent": "SALVI-GIS/2.0"},
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
    ) as client:
        # ── Parallel: try all mirrors concurrently, first wins ──────────
        tasks = [
            asyncio.create_task(_try_mirror(client, url, query, bounds))
            for url in OVERPASS_URLS
        ]
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
            timeout=OVERPASS_TIMEOUT,
        )

        # Cancel remaining in-flight requests
        for task in pending:
            task.cancel()

        # Process completed tasks
        for task in done:
            try:
                ways, source = task.result()
                # Cache in Redis
                await cache_set(cache_key, [ways, source], ttl=OVERPASS_CACHE_TTL)
                return ways, source
            except httpx.HTTPStatusError as exc:
                errors.append(f"{exc.response.url}: HTTP {exc.response.status_code}")
            except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
                errors.append(str(exc))

    raise RuntimeError("; ".join(errors) or "No Overpass mirror available")
