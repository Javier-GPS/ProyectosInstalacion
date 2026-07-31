"""Fetch building footprints from Catastro INSPIRE WFS and compute street widths.

The Spanish Catastro (Dirección General del Catastro) publishes building
footprints under the INSPIRE directive via a public WFS endpoint. This
service queries those footprints and computes facade-to-facade distances
for each road segment, giving us an accurate total street section width
(calzada + both aceras) even where OSM has no width tag.

Future: add more WFS sources per country (France: BDTOPO, UK: OS MasterMap,
Germany: ALKIS, etc.) so building_width.py becomes the multi-backend
street width resolver for any region.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from ..core.redis import cache_get, cache_set
from .overpass import parse_bbox

logger = logging.getLogger(__name__)

CATASTRO_CACHE_TTL = 86400  # 24h — building footprints change very slowly

# ── Catastro INSPIRE WFS ────────────────────────────────────────────────────
# Public WFS serving building footprints for all of Spain (EPSG:4326).
CATASTRO_WFS = "https://ovc.catastro.meh.es/Inspire/DownloadWFS.aspx"


def _build_wfs_url(bbox: str) -> str:
    """Build WFS GetFeature URL for building footprints (GeoJSON output)."""
    south, north, west, east = parse_bbox(bbox)
    return (
        f"{CATASTRO_WFS}"
        f"?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
        f"&TYPENAMES=BU:Building"
        f"&BBOX={south},{west},{north},{east},urn:ogc:def:crs:EPSG::4326"
        f"&OUTPUTFORMAT=application/json"
        f"&COUNT=5000"
    )


def _building_cache_key(bbox: str) -> str:
    h = hashlib.md5(bbox.encode()).hexdigest()
    return f"buildings:catastro:{h}"


async def fetch_buildings(bbox: str) -> list[dict]:
    """Fetch building footprints from Catastro INSPIRE WFS.

    Returns a list of GeoJSON Feature objects, each with a Polygon geometry
    in [lon, lat] coordinates (EPSG:4326). Results are cached in Redis for 24h.
    """
    # Try cache first
    cache_key = _building_cache_key(bbox)
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, list):
        logger.info("Building footprints served from cache: bbox=%s", bbox)
        return cached

    url = _build_wfs_url(bbox)
    logger.info("Fetching building footprints from Catastro WFS: bbox=%s", bbox)
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        body = resp.json()
    features = body.get("features") if isinstance(body, Mapping) else body
    if not isinstance(features, list):
        logger.warning("Catastro WFS returned unexpected format: %s", type(body).__name__)
        return []

    # Store in cache
    await cache_set(cache_key, features, ttl=CATASTRO_CACHE_TTL)
    logger.info("Catastro returned %d building footprints (cached %dh)", len(features), CATASTRO_CACHE_TTL // 3600)
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
    import math
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
      4. Distance between the two facade edges = street width.

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

    # Find nearest building roughly opposite side (bearing difference > 90°)
    import math
    bearing_to_c0 = (math.degrees(math.atan2(
        c0_lon - mid_lon, c0_lat - mid_lat)) + 360) % 360
    i1 = None
    for d, idx in scored[1:]:
        ring1, (c1_lon, c1_lat) = buildings[idx]
        bearing_to_c1 = (math.degrees(math.atan2(
            c1_lon - mid_lon, c1_lat - mid_lat)) + 360) % 360
        diff = abs(bearing_to_c1 - bearing_to_c0)
        if diff > 90 and diff < 270:
            i1 = idx
            break

    if i1 is None:
        return None

    ring1, _ = buildings[i1]

    # Compute min distance from midpoint to each building's facade
    d0 = min(_point_to_segment_distance(mid_lon, mid_lat, ring[i][0], ring[i][1],
                                         ring[(i + 1) % len(ring)][0],
                                         ring[(i + 1) % len(ring)][1])
             for i in range(len(ring0) - 1))
    d1 = min(_point_to_segment_distance(mid_lon, mid_lat, ring[i][0], ring[i][1],
                                         ring[(i + 1) % len(ring)][0],
                                         ring[(i + 1) % len(ring)][1])
             for i in range(len(ring1) - 1))

    # Total width = distance to facade on left + right
    total = d0 + d1

    # Sanity: roads wider than 60m are probably wrong (avenues max ~40m)
    if total > 60 or total < 2:
        return None

    return round(total, 1)


def enrich_widths(ways: list[dict], buildings: list[dict]) -> list[dict]:
    """Update OSM ways with facade-to-facade width from building footprints.

    For each way that doesn't already have an ``osm_width`` source, compute
    the street section width and store it as ``estWidth`` with
    ``widthSrc="catastro"``.

    Returns the (mutated) ways list.
    """
    if not buildings:
        return ways

    # Pre-process buildings: extract rings + centroids
    parsed: list[tuple[list[list[float]], tuple[float, float]]] = []
    for feat in buildings:
        geom = feat.get("geometry") if isinstance(feat, Mapping) else None
        ring = _validate_coords(geom)
        if ring is None:
            continue
        parsed.append((ring, _building_center(ring)))

    if len(parsed) < 2:
        logger.warning("Too few buildings (%d) to compute widths", len(parsed))
        return ways

    updated = 0
    for way in ways:
        # Skip ways that already have a direct OSM width measurement
        if way.get("widthSrc") == "osm_width" and way.get("width") is not None:
            continue
        geom = way.get("geom")
        if not isinstance(geom, list) or len(geom) < 2:
            continue
        width = _compute_segment_width(geom, parsed)
        if width is not None:
            way["estWidth"] = width
            way["widthSrc"] = "catastro"
            way["width"] = None  # clear raw width, we use computed
            updated += 1

    if updated:
        logger.info("Building widths computed for %d/%d ways", updated, len(ways))
    return ways
