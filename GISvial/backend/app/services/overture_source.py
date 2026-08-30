"""Source adapter: Overture Maps transportation segments (global, free).

Overture merges OSM with TomTom and other authoritative sources into
global GeoParquet on S3/Azure. Road segments carry ``width_rules`` — the
edge-to-edge carriageway width in metres (linearly scoped), plus ``class``,
``road_surface`` and ``speed_limits``. That is real measured width where
available (TomTom/licensed sources), complementing OSM's sparse tags.

Access: ``overturemaps`` python client streams only the bbox requested
(cloud-native GeoParquet + STAC). No API key.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from collections.abc import Mapping, Sequence
from typing import Any

from ..core.redis import cache_get, cache_set
from .overpass import parse_bbox

logger = logging.getLogger(__name__)

OVERTURE_CACHE_TTL = 604800  # 7 days
OVERTURE_TIMEOUT = 120  # client fetch is local; server side streaming bounded
# ponytail: only road subtype; rail/water skipped at source
GRID_CELL = 0.003
MATCH_TOLERANCE_M = 18.0


def _cache_key(bbox: str) -> str:
    h = hashlib.md5(bbox.encode()).hexdigest()
    return f"overture:segments:{h}"


async def fetch_overture_segments(bbox: str) -> list[dict]:
    """Fetch Overture road segments for bbox (cached 7 days, no key required).

    Returns list of flat dicts with the fields we consume:
    id, geometry (as [[lon, lat]]), width (m), class, road_surface, maxspeed.
    """
    cache_key = _cache_key(bbox)
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, list):
        logger.info("Overture segments served from cache: bbox=%s", bbox)
        return cached

    try:
        import overturemaps
    except ImportError as exc:
        logger.warning("overturemaps not installed; source unavailable")
        raise RuntimeError("overturemaps client missing") from exc

    # overturemaps extracts with pyarrow batches; client buffers locally,
    # then we convert the table to plain Python and release the buffer.
    south, north, west, east = parse_bbox(bbox)

    def _extract() -> list[dict]:
        table = overturemaps.record_batch_reader(
            "segment", (west, south, east, north)
        ).read_all()
        out: list[dict] = []
        for row in table.to_pylist():
            if row.get("subtype") != "road":
                continue
            geometry = row.get("geometry")
            coords = _coords(geometry)
            if len(coords) < 2:
                continue
            width = _width_from_rules(row.get("width_rules"))
            surface = _surface(row.get("road_surface"))
            maxspeed = _maxspeed(row.get("speed_limits"))
            out.append({
                "id": str(row.get("id", "")),
                "geometry": coords,
                "width": width,
                "class": row.get("class"),
                "surface": surface,
                "maxspeed": maxspeed,
                "laneCount": _lanes(row.get("subclass_rules"), row.get("class")),
            })
        return out

    # Blocking pyarrow extract: run in executor so the event loop stays free
    loop = asyncio.get_running_loop()
    try:
        segments = await loop.run_in_executor(None, _extract)
    except Exception as exc:
        logger.warning("Overture fetch failed: %s", exc)
        raise

    await cache_set(cache_key, segments, ttl=OVERTURE_CACHE_TTL)
    logger.info("Overture returned %d road segments for bbox=%s", len(segments), bbox)
    return segments


def _coords(geometry: Any) -> list[list[float]]:
    if geometry is None:
        return []
    if isinstance(geometry, (bytes, bytearray, memoryview)):
        return _wkb_coords(bytes(geometry))
    text = geometry.to_wkt() if hasattr(geometry, "to_wkt") else geometry
    if isinstance(text, str):
        return _wkt_coords(text)
    coords = geometry.get("coordinates") if isinstance(geometry, Mapping) else None
    if not isinstance(coords, list):
        return []
    result: list[list[float]] = []
    for point in coords:
        if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) >= 2:
            result.append([float(point[0]), float(point[1])])
    return result


def _wkb_coords(data: bytes) -> list[list[float]]:
    """Parse WKB LineString (little-endian) → [[x(lon), y(lat)], ...].

    Overture returns geometry as raw WKB bytes via pyarrow pylist.
    Supports Point/LineString (types 1/2), both endians.
    """
    import struct

    def read(offset: int, fmt: str):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, data[offset:offset + size])[0], offset + size

    if len(data) < 5:
        return []
    endian = data[0]
    fmt_byte = "<" if endian == 1 else ">"
    geom_type, offset = read(1, fmt_byte + "I")
    if geom_type == 1:  # Point
        lon, offset = read(offset, fmt_byte + "d")
        lat, _ = read(offset, fmt_byte + "d")
        return [[lon, lat]]
    if geom_type != 2:  # LineString
        return []
    count, offset = read(offset, fmt_byte + "I")
    result: list[list[float]] = []
    for _ in range(count):
        lon, offset = read(offset, fmt_byte + "d")
        lat, offset = read(offset, fmt_byte + "d")
        result.append([lon, lat])
    return result


def _wkt_coords(text: str) -> list[list[float]]:
    """Parse minimal WKT: LINESTRING (x y, x y, ...) → [[x, y], ...]."""
    start = text.find("(")
    if start < 0:
        return []
    body = text[start + 1:]
    end = body.find(")")
    if end < 0:
        return []
    segs = [s.strip() for s in body[:end].split(",") if s.strip()]
    result: list[list[float]] = []
    for seg in segs:
        parts = seg.split()
        if len(parts) >= 2:
            try:
                result.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return result


def _width_from_rules(rules: Any) -> float | None:
    """width_rules → metres edge-to-edge (first global-or-scoped value)."""
    if not isinstance(rules, list):
        return None
    for rule in rules:
        value = rule.get("value") if isinstance(rule, Mapping) else None
        if isinstance(value, (int, float)) and 1.0 <= value <= 60.0:
            return round(float(value), 2)
    return None


def _surface(surface_rules: Any) -> str | None:
    if not isinstance(surface_rules, list):
        return None
    for rule in surface_rules:
        value = rule.get("value") if isinstance(rule, Mapping) else None
        if isinstance(value, str):
            return value
    return None


def _maxspeed(speed_limits: Any) -> int | None:
    if not isinstance(speed_limits, list):
        return None
    for rule in speed_limits:
        if not isinstance(rule, Mapping):
            continue
        value = rule.get("value")
        limit = None
        if isinstance(value, Mapping):
            max_speed = value.get("max_speed") or {}
            limit = (max_speed.get("value") if isinstance(max_speed, Mapping) else None)
        if isinstance(limit, (int, float)) and limit > 0:
            return int(limit)
    return None


def _lanes(subclass_rules: Any, road_class: Any) -> int | None:
    """Estimate lane count from Overture subclass (dual carriageway → 2).

    Not authoritative; used only as a hint when no other source has lanes.
    """
    if not isinstance(subclass_rules, list):
        return None
    for rule in subclass_rules:
        value = rule.get("value") if isinstance(rule, Mapping) else None
        if isinstance(value, str) and "dual" in value.lower():
            return 2
    return None


# ── Spatial matching → OSM ways ─────────────────────────────────────────────

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


def match_overture_to_ways(ways: list[dict], segments: list[dict], tolerance_m: float = MATCH_TOLERANCE_M) -> int:
    """Attach ``overtureProfile`` to the nearest OSM way.

    Mutates ways in place: ``overtureProfile`` = {width, class, surface,
    maxspeed} and ``overtureRef``. Returns number of ways enriched.
    """
    if not ways or not segments:
        return 0

    usable: list[tuple[list[list[float]], dict[str, Any], str]] = []
    for seg in segments:
        coords = seg.get("geometry")
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        props = {k: seg.get(k) for k in ("width", "class", "surface", "maxspeed", "laneCount") if seg.get(k) is not None}
        if not props:
            continue
        usable.append((coords, props, str(seg.get("id", ""))))

    grid: dict[tuple[int, int], list[int]] = {}
    for index, coords in enumerate(u[0] for u in usable):
        for lon, lat in coords:
            cell = (math.floor(lon / GRID_CELL), math.floor(lat / GRID_CELL))
            grid.setdefault(cell, []).append(index)

    radius_cells = math.ceil(tolerance_m / (GRID_CELL * 111_000)) + 1
    enriched = 0
    for way in ways:
        if way.get("overtureProfile"):
            continue
        geom = way.get("geom")
        if not isinstance(geom, list) or len(geom) < 2:
            continue
        samples: list[tuple[float, float]] = []
        for frac in (0.25, 0.5, 0.75):
            idx = int(frac * (len(geom) - 1))
            point = geom[idx]
            if isinstance(point, Mapping) and "lon" in point and "lat" in point:
                samples.append((float(point["lon"]), float(point["lat"])))
        if not samples:
            continue
        best_index, best_dist = -1, math.inf
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
            _coords, props, localid = usable[best_index]
            way["overtureProfile"] = props
            if localid:
                way["overtureRef"] = localid
            enriched += 1

    if enriched:
        logger.info("Overture matched %d/%d ways (tolerance %.0fm)", enriched, len(ways), tolerance_m)
    return enriched


def has_overture_profiles(ways: list[dict]) -> bool:
    return bool(ways) and all(way.get("overtureProfile") for way in ways)


async def enrich_overture(ways: list[dict], bbox: str) -> int:
    """Ensure ways carry Overture profiles; safe no-op on failure."""
    if has_overture_profiles(ways):
        return 0
    try:
        segments = await fetch_overture_segments(bbox)
    except Exception as exc:  # noqa: BLE001 — remote, OSM stays fallback
        logger.warning("Overture fetch skipped (%s)", exc)
        return 0
    try:
        return match_overture_to_ways(ways, segments)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Overture matching failed (%s)", exc)
        return 0
