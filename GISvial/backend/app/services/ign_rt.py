"""Fetch IGN IGR-RT (Redes de Transporte) road links from the IDEE OGC API.

The official IGR-RT road network service (https://api-features.idee.es,
collection ``roadlink``) exposes INSPIRE Road Link features for Spain with:

    - numberoflanes      : number of lanes (authoritative, may be null)
    - formofway_href     : single/dual carriageway, motorway, slipRoad...
    - functionalclass    : mainRoad, firstClass, secondClass, ...
    - surfacecategory    : paved / unpaved
    - fictitious         : "true" for non-physical links (ferries, etc.)
    - id_tramo           : TR tramo identifier

It does NOT carry width/median/sidewalk — those live in the CNIG download
(anchocalzada, anchomediana, etc.). This module is the official-source
complement to OSM attributes; values are reconciled in road_geometry.py.

Matching strategy: each IGN link is stored in a coarse spatial grid keyed by
nearest cell; OSM ways sample their midpoint and take the nearest link within
tolerance (default 25 m). Results are cached in Redis.
"""
from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from ..core.redis import cache_get, cache_set
from .overpass import parse_bbox

logger = logging.getLogger(__name__)

IGN_RT_ITEMS_URL = "https://api-features.idee.es/collections/roadlink/items"
IGN_RT_CACHE_TTL = 604800  # 7 days — IGR-RT publishes ~2x/year
IGN_RT_MAX_LINKS = 8000  # hard cap per bbox
IGN_RT_PAGE_LIMIT = 500
IGN_RT_TIMEOUT = 60
MATCH_TOLERANCE_M = 25.0
GRID_CELL = 0.003  # ~300 m — fine enough for street-level matching


def _cache_key(bbox: str) -> str:
    h = hashlib.md5(bbox.encode()).hexdigest()
    return f"ign:roadlink:{h}"


def _bbox_param(bbox: str) -> str:
    """OGC API bbox: minLon,minLat,maxLon,maxLat."""
    south, north, west, east = parse_bbox(bbox)
    return f"{west},{south},{east},{north}"


async def _fetch_page(
    client: httpx.AsyncClient, url: str
) -> tuple[list[dict], str | None]:
    resp = await client.get(url)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, Mapping):
        return [], None
    features = body.get("features")
    if not isinstance(features, list):
        return [], None
    next_href = None
    for link in body.get("links") or []:
        if isinstance(link, Mapping) and link.get("rel") == "next":
            next_href = link.get("href")
            break
    return features, next_href


async def fetch_ign_roadlinks(bbox: str) -> list[dict]:
    """Fetch IGR-RT road links intersecting ``bbox`` (paginated, cached).

    Returns raw GeoJSON features. Raises on network errors (callers decide
    whether to fall back silently to OSM-only data).
    """
    cache_key = _cache_key(bbox)
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, list):
        logger.info("IGN-RT road links served from cache: bbox=%s", bbox)
        return cached

    params = {"bbox": _bbox_param(bbox), "limit": IGN_RT_PAGE_LIMIT}
    url = f"{IGN_RT_ITEMS_URL}?f=json&bbox={params['bbox']}&limit={IGN_RT_PAGE_LIMIT}"
    features: list[dict] = []
    async with httpx.AsyncClient(
        timeout=IGN_RT_TIMEOUT,
        headers={"User-Agent": "SALVI-GIS/2.0"},
        follow_redirects=True,
    ) as client:
        current: str | None = url
        pages = 0
        while current and pages < 20:
            page, current = await _fetch_page(client, current)
            features.extend(page)
            pages += 1
            if len(features) >= IGN_RT_MAX_LINKS or not current:
                break

    if len(features) >= IGN_RT_MAX_LINKS:
        logger.warning("IGN-RT link count truncated at %d for bbox=%s", IGN_RT_MAX_LINKS, bbox)
    features = features[:IGN_RT_MAX_LINKS]
    await cache_set(cache_key, features, ttl=IGN_RT_CACHE_TTL)
    logger.info("Fetched %d IGN-RT road links for bbox=%s (cached %dd)", len(features), bbox, IGN_RT_CACHE_TTL // 86400)
    return features


# ── Spatial matching ────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371008.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_to_segment_m(
    lon: float, lat: float, ax: float, ay: float, bx: float, by: float
) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return _haversine_m(lat, lon, ay, ax)
    t = max(0.0, min(1.0, ((lon - ax) * dx + (lat - ay) * dy) / length_sq))
    return _haversine_m(lat, lon, ay + t * dy, ax + t * dx)


def _link_geometry(feature: Mapping) -> list[list[float]]:
    geom = feature.get("geometry")
    coords = geom.get("coordinates") if isinstance(geom, Mapping) else None
    if not isinstance(coords, list) or len(coords) < 2:
        return []
    result: list[list[float]] = []
    for point in coords[:5]:  # sample capped for speed
        if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) >= 2:
            result.append([float(point[0]), float(point[1])])
    return result


def _valid_link_props(feature: Mapping) -> dict[str, Any]:
    """Keep only the IGR-RT attributes we can use."""
    props = feature.get("properties")
    props = props if isinstance(props, Mapping) else {}
    known = ("numberoflanes", "formofway_href", "functionalclass", "surfacecategory")
    return {key: props.get(key) for key in known if key in props}


def match_ign_to_ways(ways: list[dict], links: list[dict], tolerance_m: float = MATCH_TOLERANCE_M) -> int:
    """Attach IGR-RT ``ignProfile`` to the nearest matching OSM way.

    Mutates each way in place with ``ignProfile`` = validated raw properties
    and ``ignRef`` = IGN localid, when a link is found within tolerance of the
    way's midpoint (sampled at ¼, ½, ¾ to tolerate split ways).
    Returns the number of ways enriched.
    """
    if not links or not ways:
        return 0

    # Filter to genuinely inventoried road links only. The API marks most
    # municipality (non-classified) links as fictitious=true and fills
    # numberoflanes=1 on everything — junk for urban geometry. Require:
    # fictitious=false AND a real functionalclass AND paved.
    usable: list[tuple[list[list[float]], dict[str, Any], str]] = []
    for feature in links:
        props_in = feature.get("properties", {}) if isinstance(feature, Mapping) else {}
        if str(props_in.get("fictitious", "")).lower() == "true":
            continue
        if not props_in.get("functionalclass") or str(props_in.get("functionalclass")).lower() in {"-998", "-997"}:
            continue
        if str(props_in.get("surfacecategory", "")).lower() not in {"paved", ""}:
            continue
        coords = _link_geometry(feature)
        if len(coords) < 2:
            continue
        props = _valid_link_props(feature)
        if not props:
            continue
        usable.append((coords, props, str(feature.get("id", ""))))

    # Spatial grid: each cell holds links whose sampled geometry enters it
    grid: dict[tuple[int, int], list[int]] = {}
    for index, (coords, _props, _id) in enumerate(usable):
        for lon, lat in coords:
            cell = (math.floor(lon / GRID_CELL), math.floor(lat / GRID_CELL))
            grid.setdefault(cell, []).append(index)

    radius_cells = math.ceil(tolerance_m / (GRID_CELL * 111_000)) + 1
    enriched = 0
    for way in ways:
        geom = way.get("geom")
        if not isinstance(geom, list) or len(geom) < 2:
            continue
        # Sample the way
        samples: list[tuple[float, float]] = []
        for frac in (0.25, 0.5, 0.75):
            idx = int(frac * (len(geom) - 1))
            point = geom[idx]
            if isinstance(point, Mapping) and "lon" in point and "lat" in point:
                samples.append((float(point["lon"]), float(point["lat"])))
        if not samples:
            continue

        best_index = -1
        best_dist = math.inf
        for lon, lat in samples:
            cx, cy = math.floor(lon / GRID_CELL), math.floor(lat / GRID_CELL)
            seen: set[int] = set()
            for dx in range(-radius_cells, radius_cells + 1):
                for dy in range(-radius_cells, radius_cells + 1):
                    for index in grid.get((cx + dx, cy + dy), ()):
                        if index in seen:
                            continue
                        seen.add(index)
                        coords = usable[index][0]
                        d = min(
                            _point_to_segment_m(lon, lat, ax, ay, bx, by)
                            for (ax, ay), (bx, by) in zip(coords, coords[1:])
                        )
                        if d < best_dist:
                            best_dist = d
                            best_index = index
        if 0 <= best_index < len(usable) and best_dist <= tolerance_m:
            coords, props, localid = usable[best_index]
            way["ignProfile"] = props
            if localid:
                way["ignRef"] = localid
            enriched += 1

    if enriched:
        logger.info("IGN-RT matched %d/%d ways (tolerance %.0fm)", enriched, len(ways), tolerance_m)
    return enriched


def has_ign_profiles(ways: list[dict]) -> bool:
    """True when every way already carries its IGN profile (skip re-fetch)."""
    return bool(ways) and all(way.get("ignProfile") for way in ways)


async def enrich_ign_rt(ways: list[dict], bbox: str) -> int:
    """Ensure ways carry IGR-RT profiles; safe to call on every load.

    Returns number of ways enriched with IGN data (0 when already enriched).
    Any failure (network, schema) is logged and swallowed — OSM data is always
    the fallback.
    """
    if has_ign_profiles(ways):
        return 0
    try:
        links = await fetch_ign_roadlinks(bbox)
    except Exception as exc:  # noqa: BLE001 — remote source, never break load
        logger.warning("IGN-RT fetch skipped (%s)", exc)
        return 0
    try:
        return match_ign_to_ways(ways, links)
    except Exception as exc:  # noqa: BLE001
        logger.warning("IGN-RT matching failed (%s)", exc)
        return 0
