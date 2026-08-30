"""Compute street section widths (facade-to-facade) from building footprints.

Buildings come from OpenStreetMap (Overpass ``building`` ways) — real,
globally available and free. The Spanish Catastro INSPIRE WFS
(ovc.catastro.meh.es) used to serve this, but it returns 404 and is removed.

For each road way we sample its midpoint, find the nearest building centroid
on each side (>90° apart in bearing) and sum the facade-to-facade distance:
the total street *section* width (calzada + aceras). This is a real,
measured value where OSM has no width tag — stored as ``sectionWidth`` and
reconciled in road_geometry.py as ``platformWidth``.

Future: additional footprint sources per region could be plugged here
(e.g. Microsoft building footprints) — the computation only needs polygons.
"""
from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Mapping
from typing import Any

import httpx

from ..core.redis import cache_get, cache_set
from .overpass import parse_bbox

logger = logging.getLogger(__name__)

BUILDINGS_CACHE_TTL = 86400 * 7  # 7 days — footprints change slowly
BUILDINGS_COUNT_LIMIT = 6000


def _buildings_url(bbox: str) -> str:
    south, north, west, east = parse_bbox(bbox)
    return (
        f"[out:json][timeout:180];"
        f"way[\"building\"]({south},{west},{north},{east});out tags geom;"
    )


def _buildings_cache_key(bbox: str) -> str:
    h = hashlib.md5(bbox.encode()).hexdigest()
    return f"buildings:osm:{h}"


async def fetch_buildings(bbox: str) -> list[dict]:
    """Fetch building footprints from OpenStreetMap.

    Returns a list of GeoJSON Feature objects (Polygon rings in [lon, lat]).
    Cached in Redis for 7 days. Raises on network failure so callers can log
    and skip enrichment.
    """
    cache_key = _buildings_cache_key(bbox)
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, list):
        logger.info("Building footprints served from cache: bbox=%s", bbox)
        return cached

    query = _buildings_url(bbox)
    mirrors = (
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.openstreetmap.fr/api/interpreter",
    )
    body: Any = None
    last_error: Exception | None = None
    async with httpx.AsyncClient(
        timeout=200,
        headers={"User-Agent": "SALVI-GIS/2.0"},
        follow_redirects=True,
    ) as client:
        for url in mirrors:
            try:
                resp = await client.post(url, content=query)
                resp.raise_for_status()
                body = resp.json()
                break
            except Exception as exc:  # noqa: BLE001 — try next mirror
                last_error = exc
                logger.warning("Overpass mirror %s failed for buildings: %s", url, exc)
    if body is None:
        raise RuntimeError(f"No Overpass mirror available for buildings: {last_error}")

    elements = body.get("elements") if isinstance(body, Mapping) else None
    if not isinstance(elements, list):
        return []

    features: list[dict] = []
    for element in elements:
        if element.get("type") != "way" or not isinstance(element.get("geometry"), list):
            continue
        ring: list[list[float]] = []
        for pt in element["geometry"]:
            if isinstance(pt, Mapping) and type(pt.get("lon")) in (int, float) and type(pt.get("lat")) in (int, float):
                ring.append([float(pt["lon"]), float(pt["lat"])])
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0][:])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
        if len(features) >= BUILDINGS_COUNT_LIMIT:
            break

    await cache_set(cache_key, features, ttl=BUILDINGS_CACHE_TTL)
    logger.info("OSM returned %d building footprints (cached %dd)", len(features), BUILDINGS_CACHE_TTL // 86400)
    return features


# ── Geometry helpers ────────────────────────────────────────────────────────

def _validate_coords(geom: Any) -> list[list[float]] | None:
    """Extract outer ring coordinates from a GeoJSON Polygon geometry."""
    if not isinstance(geom, Mapping):
        return None
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return None
    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < 3:
        return None
    return ring


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two (lat, lon) points."""
    R = 6371008.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_to_segment_distance(lon: float, lat: float,
                               ax: float, ay: float,
                               bx: float, by: float) -> float:
    """Minimum distance from point (lon,lat) to segment AB in metres."""
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return _haversine(lat, lon, ay, ax)
    t = max(0, min(1, ((lon - ax) * dx + (lat - ay) * dy) / length_sq))
    proj_lon = ax + t * dx
    proj_lat = ay + t * dy
    return _haversine(lat, lon, proj_lat, proj_lon)


def _building_center(ring: list[list[float]]) -> tuple[float, float]:
    """Centroid of a polygon ring as (lon, lat)."""
    n = len(ring) - 1  # last == first
    lon = sum(pt[0] for pt in ring[:n]) / n
    lat = sum(pt[1] for pt in ring[:n]) / n
    return lon, lat


# ── Street width computation ────────────────────────────────────────────────

def _compute_segment_width(
    geom: list[dict],
    buildings: list[tuple[list[list[float]], tuple[float, float]]],
) -> float | None:
    """For a road segment, find facade-to-facade width via nearest buildings.

    Strategy:
      1. Compute the midpoint of the segment.
      2. Find the nearest building centroid overall — that's one side.
      3. Find the nearest building in roughly the opposite direction.
      4. Distance between the two facade edges = street section width.

    Returns width in metres, or None if <2 buildings found.
    """
    if len(geom) < 2 or len(buildings) < 2:
        return None

    # Midpoint of the segment
    mid_lat = sum(pt["lat"] for pt in geom) / len(geom)
    mid_lon = sum(pt["lon"] for pt in geom) / len(geom)

    # Sort buildings by distance from midpoint
    scored: list[tuple[float, int]] = []
    for idx, (ring, (clon, clat)) in enumerate(buildings):
        d = _haversine(mid_lat, mid_lon, clat, clon)
        scored.append((d, idx))
    scored.sort(key=lambda x: x[0])

    if len(scored) < 2:
        return None

    # Nearest building
    _, i0 = scored[0]
    ring0, (c0_lon, c0_lat) = buildings[i0]

    # Find nearest building roughly opposite side (bearing difference > 90°).
    # Lons/lats must be scaled by cos(lat) before the angle test, otherwise
    # near-vertical streets fail the "opposite side" gate spuriously.
    import math
    lon_scale = math.cos(math.radians(mid_lat))
    bearing_to_c0 = (math.degrees(math.atan2(
        (c0_lon - mid_lon) * lon_scale, c0_lat - mid_lat)) + 360) % 360
    i1 = None
    for d, idx in scored[1:]:
        ring1, (c1_lon, c1_lat) = buildings[idx]
        bearing_to_c1 = (math.degrees(math.atan2(
            (c1_lon - mid_lon) * lon_scale, c1_lat - mid_lat)) + 360) % 360
        diff = abs(bearing_to_c1 - bearing_to_c0)
        if 90 < diff < 270:
            i1 = idx
            break

    if i1 is None:
        return None

    ring1, _ = buildings[i1]

    # Compute min distance from midpoint to each building's facade
    d0 = min(_point_to_segment_distance(mid_lon, mid_lat, ring0[i][0], ring0[i][1],
                                         ring0[(i + 1) % len(ring0)][0],
                                         ring0[(i + 1) % len(ring0)][1])
             for i in range(len(ring0) - 1))
    d1 = min(_point_to_segment_distance(mid_lon, mid_lat, ring1[i][0], ring1[i][1],
                                         ring1[(i + 1) % len(ring1)][0],
                                         ring1[(i + 1) % len(ring1)][1])
             for i in range(len(ring1) - 1))

    # Total width = distance to facade on left + right
    total = d0 + d1

    # Sanity: roads wider than 60m are probably wrong (avenues max ~40m)
    if total > 60 or total < 2:
        return None

    return round(total, 1)


def enrich_widths(ways: list[dict], buildings: list[dict]) -> list[dict]:
    """Update OSM ways with facade-to-facade section width from footprints.

    For each way that doesn't already have a direct OSM width measurement,
    compute the street section width and store it as ``sectionWidth``.
    Returns the (mutated) ways list.
    """
    if not buildings:
        return ways

    # Pre-process buildings: extract rings + centroids
    parsed: list[tuple[list[list[float]], tuple[float, float]]] = []
    for feat in buildings:
        geom = feat.get("geometry") if isinstance(feat, Mapping) else None
        ring = _validate_coords(geom)
        if ring is None or len(ring) < 4 or not all(len(p) >= 2 for p in ring):
            continue
        # normalized: closed ring
        ring = [list(map(float, p[:2])) for p in ring]
        if ring[0] != ring[-1]:
            ring.append(ring[0][:])
        parsed.append((ring, _building_center(ring)))

    if len(parsed) < 2:
        logger.warning("Too few buildings (%d) to compute widths", len(parsed))
        return ways

    updated = 0
    for way in ways:
        # Skip ways that already have a direct OSM width measurement
        if way.get("widthSrc") == "osm_width" and way.get("width") is not None:
            continue
        if way.get("sectionWidth"):
            continue
        geom = way.get("geom")
        if not isinstance(geom, list) or len(geom) < 2:
            continue
        width = _compute_segment_width(geom, parsed)
        if width is not None:
            way["sectionWidth"] = width
            way["sectionWidthSrc"] = "osm_buildings"
            updated += 1

    if updated:
        logger.info("Building widths computed for %d/%d ways", updated, len(ways))
    return ways
