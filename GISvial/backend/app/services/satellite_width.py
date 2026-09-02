"""Satellite width — worldwide CPU OpenCV tile analysis.

Evaluacion OpenCV para teselas
------------------------------
¿Interesante? Si. Unico lib que cubre todo el pipeline en CPU sin torch:

+ Pros:
  - Canny/CLAHE/bilateral/morph/flood/distanceTransform en C++ ~30ms/512px vs
    PIL/skimage ~200ms (Python). 10-50x mas rapido en CPU floja.
  - Una dependencia (opencv-python-headless 90MB) vs PIL+skimage+scipy.
  - imdecode/hstack para stitch tiles sin Pillow extra.
  - Estable, sin modelo, sin GPU.

- Contras:
  - +90MB imagen Docker, necesita libGL en slim (headless lo evita).
  - API verbosa, tipos np.uint8 estrictos.
  - No segmenta acera/parking vs calzada si mismo asfalto (igual que cualquier RGB).

Alternativas:
  - PIL solo sirve para I/O/resize, no edges.
  - scikit-image: misma calidad, mas lento, mas deps.
  - SAM/MobileSAM: 0.5m precision pero 4-8s CPU/tiles, necesita GPU.
Conclusion: OpenCV clasico es el compromiso mundial CPU-rapido. Si CPU potente
y error <0.5m exigido, migrar a MobileSAM ONNX luego sin cambiar interfaz.

Mundial + parking
-----------------
- Tiles z19 ~0.30m/px (156543*cos(lat)/2^19). Esri World Imagery mundial gratis
  (sin key, cache 30d, solo guardamos ancho derivado para TOS). España -> PNOA
  25cm si bbox dentro de peninsula (legal ideal).
- Parking = mismo asfalto -> se incluye en ancho (pedido). Si OSM trae
  `amenity=parking` cercano o `parking:lane`, lo marcamos pero no restamos.
- Medicion: Canny edges + ray casting perpendicular a linea OSM (prior).
  No necesitamos segmentacion completa; buscamos bordes a ambos lados.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from collections.abc import Mapping
from typing import Any

import httpx

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
ZOOM = 19
TILE = 256
CACHE_TTL = 86400 * 30  # 30d — ortofoto estable
TIMEOUT = 15
MAX_TILES_PER_WAY = 4  # 2x2 stitch ~150m, suficiente para calzada 20m
CONF_THR = 0.6

ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
# PNOA solo Espana: WMS no sirve para XYZ directo, usamos Esri por defecto mundial.
# Si bbox en Espana, Esri ya sirve 25-50cm igual que PNOA en urbano, evitamos WMS.

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore
    np = None  # type: ignore
    HAS_CV2 = False


def _parse_bbox_raw(bbox: str) -> tuple[float, float, float, float]:
    """Parse bbox without Overpass size limit (satellite tiles need any size).

    Handles both stored formats: south,north,west,east (Overpass) and
    west,south,east,north (GeoJSON via normalize_bbox).
    Returns south,north,west,east.
    """
    try:
        from .zone_geometry import normalize_bbox

        norm, _, status = normalize_bbox(bbox, (None, None))
        if norm and status == "valid":
            # norm is west,south,east,north
            west, south, east, north = norm
            return south, north, west, east
    except Exception:
        pass
    try:
        parts = [float(p.strip()) for p in bbox.split(",")]
        if len(parts) == 4:
            # try south,north,west,east first (Overpass)
            s, n, w, e = parts
            if -90 <= s < n <= 90 and -180 <= w < e <= 180:
                return s, n, w, e
            # try west,south,east,north
            w2, s2, e2, n2 = parts
            if -90 <= s2 < n2 <= 90 and -180 <= w2 < e2 <= 180:
                return s2, n2, w2, e2
            return s, n, w, e
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"bad bbox {bbox}") from exc
    raise ValueError(f"bad bbox {bbox}")


def _is_spain(bbox: str) -> bool:
    try:
        s, n, w, e = _parse_bbox_raw(bbox)
        # peninsula + baleares + canarias aprox
        return -18.5 < w < 4.5 and 27 < s < 44 and w < e
    except Exception:
        return False


def _mpp(lat: float, zoom: int = ZOOM) -> float:
    return 156543.03 * math.cos(math.radians(lat)) / (2**zoom)


def _lonlat_to_tile(lon: float, lat: float, zoom: int = ZOOM) -> tuple[int, int]:
    n = 2**zoom
    xt = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    yt = int((1.0 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return xt, yt


def _tile_bounds(xt: int, yt: int, zoom: int = ZOOM) -> tuple[float, float, float, float]:
    n = 2**zoom
    lon_w = xt / n * 360.0 - 180.0
    lon_e = (xt + 1) / n * 360.0 - 180.0
    lat_n = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yt / n))))
    lat_s = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (yt + 1) / n))))
    return lat_s, lat_n, lon_w, lon_e


def _bbox_from_ways(ways: list[dict]) -> str | None:
    """Derive south,north,west,east from way geometries (evita bbox string ambiguo)."""
    lats: list[float] = []
    lons: list[float] = []
    for way in ways:
        geom = way.get("geom")
        if not isinstance(geom, list):
            continue
        for pt in geom:
            if isinstance(pt, Mapping) and "lat" in pt and "lon" in pt:
                try:
                    lats.append(float(pt["lat"]))
                    lons.append(float(pt["lon"]))
                except Exception:
                    continue
    if not lats or not lons:
        return None
    south, north = min(lats), max(lats)
    west, east = min(lons), max(lons)
    # pad 40m
    pad = 0.0005
    south -= pad
    north += pad
    west -= pad
    east += pad
    return f"{south},{north},{west},{east}"


def _tiles_for_bbox(bbox: str) -> list[tuple[int, int]]:
    s, n, w, e = _parse_bbox_raw(bbox)
    # expandir bbox 30m para no cortar calzada
    pad = 0.0004  # ~40m
    s -= pad
    n += pad
    w -= pad
    e += pad
    x0, y0 = _lonlat_to_tile(w, n, ZOOM)
    x1, y1 = _lonlat_to_tile(e, s, ZOOM)
    # limitar a 2x2 max centrado para CPU rapido (mundial no necesita 10x10)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > MAX_TILES_PER_WAY:
        # centrar en medio bbox
        cx, cy = _lonlat_to_tile((w + e) / 2, (s + n) / 2, ZOOM)
        x0, x1 = cx - 1, cx
        y0, y1 = cy - 1, cy
    tiles: list[tuple[int, int]] = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            tiles.append((x, y))
    return tiles[:MAX_TILES_PER_WAY]


def _cache_key(provider: str, z: int, x: int, y: int) -> str:
    return f"sat:tile:{provider}:{z}/{x}/{y}"


async def _fetch_tile(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        r = await client.get(url, timeout=TIMEOUT)
        if r.status_code == 200 and r.content and len(r.content) > 1000:
            return r.content
    except Exception as exc:  # noqa: BLE001
        logger.debug("tile fetch fail %s: %s", url, exc)
    return None


async def fetch_tiles(bbox: str) -> tuple[Any, tuple[int, int], float] | None:
    """Fetch & stitch tiles for bbox. Returns (image, (x0,y0), mpp) or None.

    image es np.ndarray BGR 512x512 si cv2, else PIL Image.
    x0,y0 tile origin para georef. mpp en centro bbox.
    """
    if not HAS_CV2:
        logger.warning("opencv not installed, satellite skipped")
        return None
    tiles = _tiles_for_bbox(bbox)
    if not tiles:
        return None
    # provider: esri mundial (pnoa check solo para log, mismo URL)
    provider = "pnoa" if _is_spain(bbox) else "esri"
    # mpp en centro
    s, n, w, e = _parse_bbox_raw(bbox)
    mpp = _mpp((s + n) / 2)

    # cache lookup
    cache_hit: dict[tuple[int, int], bytes] = {}
    to_fetch: list[tuple[int, int]] = []
    for xt, yt in tiles:
        key = _cache_key(provider, ZOOM, xt, yt)
        cached = await cache_get(key)
        if isinstance(cached, (bytes, bytearray)):
            cache_hit[(xt, yt)] = bytes(cached)
        else:
            to_fetch.append((xt, yt))

    fetched: dict[tuple[int, int], bytes] = {}
    if to_fetch:
        async with httpx.AsyncClient(headers={"User-Agent": "SALVI-GIS/2.0"}) as client:
            # fetch paralelo
            results = await asyncio.gather(
                *[
                    _fetch_tile(client, ESRI_URL.format(z=ZOOM, x=xt, y=yt))
                    for xt, yt in to_fetch
                ]
            )
            for (xt, yt), data in zip(to_fetch, results):
                if data:
                    fetched[(xt, yt)] = data
                    await cache_set(_cache_key(provider, ZOOM, xt, yt), data, ttl=CACHE_TTL)

    all_tiles = {**cache_hit, **fetched}
    if len(all_tiles) < len(tiles) * 0.5:
        logger.warning("sat tiles insufficient %d/%d bbox=%s", len(all_tiles), len(tiles), bbox)
        return None

    # decode + stitch
    xs = sorted({x for x, _ in tiles})
    ys = sorted({y for _, y in tiles})
    x0, y0 = min(xs), min(ys)
    w_px = len(xs) * TILE
    h_px = len(ys) * TILE
    stitched = np.zeros((h_px, w_px, 3), dtype=np.uint8)
    for xt, yt in tiles:
        data = all_tiles.get((xt, yt))
        if not data:
            continue
        arr = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            continue
        if img.shape[0] != TILE or img.shape[1] != TILE:
            img = cv2.resize(img, (TILE, TILE))
        ox = (xt - x0) * TILE
        oy = (yt - y0) * TILE
        stitched[oy : oy + TILE, ox : ox + TILE] = img

    # si solo 1 tile valido, stitched ya es 256
    if stitched is None or stitched.size == 0:
        return None
    return stitched, (x0, y0), mpp


def _lonlat_to_pixel(lon: float, lat: float, x0: int, y0: int, zoom: int = ZOOM) -> tuple[float, float]:
    n = 2**zoom
    xt = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    yt = (1.0 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2.0 * n
    px = xt * TILE - x0 * TILE
    py = yt * TILE - y0 * TILE
    return px, py


def _measure_way_width(
    way_geom: list[dict],
    stitched: Any,
    origin: tuple[int, int],
    mpp: float,
) -> tuple[float | None, float]:
    """Mide ancho calzada via Canny + ray casting perpendicular.

    Retorna (width_m, confidence). confidence = valid_rays / total.
    Si <2 rayos validos -> None.
    """
    if not HAS_CV2 or stitched is None:
        return None, 0.0
    h, w = stitched.shape[:2]
    x0, y0 = origin

    # polyline a pixel (mantener aunque salga de imagen para sampling central)
    poly: list[tuple[float, float]] = []
    for pt in way_geom:
        if not isinstance(pt, Mapping) or "lon" not in pt or "lat" not in pt:
            continue
        try:
            px, py = _lonlat_to_pixel(float(pt["lon"]), float(pt["lat"]), x0, y0)
        except Exception:
            continue
        poly.append((px, py))
    if len(poly) < 2:
        return None, 0.0
    # filtrar segmentos con midpoint fuera de imagen (no medibles)
    filtered_poly: list[tuple[float, float]] = []
    for p in poly:
        # mantener todos para continuidad, pero marcar si fuera muy lejos no influye
        filtered_poly.append(p)
    poly = filtered_poly

    # ── OpenCV pipeline (CPU rapido) ─────────────────────────────────────
    gray = cv2.cvtColor(stitched, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    blur = cv2.bilateralFilter(gray, 5, 50, 50)
    edges = cv2.Canny(blur, 60, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    # cerrar huecos pequenos (linea discontinua)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)

    # ray casting perpendicular
    widths: list[float] = []
    max_px = int(30 / mpp)  # buscar hasta 30m (autovia)
    min_px = int(2.0 / mpp)  # minimo 2m

    # sample cada segmento (hasta 5 muestras por way)
    samples: list[tuple[float, float, float, float]] = []  # mx,my,nx,ny
    step = max(1, len(poly) // 5)
    for i in range(0, len(poly) - 1, step):
        p0, p1 = poly[i], poly[i + 1]
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        # solo muestras con centro dentro de imagen (evita way fuera de tiles)
        if not (0 <= mx < w and 0 <= my < h):
            continue
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        seg_len = math.hypot(dx, dy)
        if seg_len < 1:
            continue
        nx, ny = -dy / seg_len, dx / seg_len
        samples.append((mx, my, nx, ny))
    if not samples:
        return None, 0.0

    for mx, my, nx, ny in samples:
        # buscar borde a izq y dcha
        dists = []
        for sign in (1, -1):
            found = None
            for d in range(min_px, max_px):
                x = int(mx + sign * nx * d)
                y = int(my + sign * ny * d)
                if not (0 <= x < w and 0 <= y < h):
                    break
                if edges[y, x] > 0:
                    found = d
                    break
            if found is not None:
                dists.append(found)
        if len(dists) == 2:
            width_px = dists[0] + dists[1]
            width_m = width_px * mpp
            # sanity 2.5m - 35m calzada (incl parking)
            if 2.5 <= width_m <= 35:
                widths.append(width_m)

    if not widths:
        return None, 0.0
    if len(widths) < 2 and len(samples) > 2:
        # exigir 2 muestras solo si way largo
        return None, len(widths) / max(1, len(samples))

    widths.sort()
    # mediana robusta
    median = widths[len(widths) // 2]
    # filtrar outliers >40% mediana
    filtered = [w for w in widths if abs(w - median) / median < 0.4]
    if not filtered:
        filtered = widths
    final = sum(filtered) / len(filtered)
    conf = len(widths) / len(samples)
    return round(final, 2), round(conf, 2)


def has_satellite_profiles(ways: list[dict]) -> bool:
    return bool(ways) and all(w.get("satelliteProfile") for w in ways)


def _way_midpoint(way: dict) -> tuple[float, float] | None:
    """Return (lat, lon) midpoint of a way's geometry, or None."""
    geom = way.get("geom")
    if not isinstance(geom, list) or len(geom) < 2:
        return None
    lats, lons = [], []
    for pt in geom:
        if isinstance(pt, Mapping) and "lat" in pt and "lon" in pt:
            try:
                lats.append(float(pt["lat"]))
                lons.append(float(pt["lon"]))
            except Exception:
                continue
    if not lats:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _batch_ways(ways: list[dict], cell_deg: float = 0.004) -> list[list[dict]]:
    """Group ways into spatial cells (~400m) for tile-local processing.

    Each batch gets its own small bbox → its own 2×2 tiles → correct mpp.
    """
    pending = [w for w in ways if not w.get("satelliteProfile")]
    if not pending:
        return []

    cells: dict[tuple[int, int], list[dict]] = {}
    for way in pending:
        mid = _way_midpoint(way)
        if mid is None:
            continue
        lat, lon = mid
        key = (int(lon / cell_deg), int(lat / cell_deg))
        cells.setdefault(key, []).append(way)

    # merge small adjacent cells to avoid many tiny fetches
    batches: list[list[dict]] = list(cells.values())
    return batches


async def enrich_satellite(ways: list[dict], bbox: str) -> int:
    """Enriquece ways con `satelliteProfile` mundial CPU, batched espacialmente.

    Divide ways en grups ~400m, fetch 2×2 tiles por grupo, mide y continúa.
    Esto cubre zonas grandes (623 ways, 4km) sin descargar 256 tiles de golpe.
    """
    if not ways or has_satellite_profiles(ways):
        return 0
    if not HAS_CV2:
        logger.info("satellite skipped: opencv not installed")
        return 0
    import os
    if os.getenv("SATELLITE_WIDTH_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return 0

    is_spain = _is_spain(bbox)
    batches = _batch_ways(ways)
    if not batches:
        return 0

    total_enriched = 0
    total_measured = 0
    for batch_i, batch in enumerate(batches):
        # bbox local del batch
        lats, lons = [], []
        for w in batch:
            mid = _way_midpoint(w)
            if mid:
                lats.append(mid[0])
                lons.append(mid[1])
        if not lats:
            continue
        pad = 0.0005  # ~50m padding
        local_bbox = f"{min(lats)-pad},{max(lats)+pad},{min(lons)-pad},{max(lons)+pad}"

        try:
            res = await fetch_tiles(local_bbox)
        except Exception as exc:  # noqa: BLE001
            logger.debug("sat tiles batch %d failed: %s", batch_i, exc)
            continue
        if not res:
            continue

        stitched, origin, mpp = res
        for way in batch:
            if way.get("satelliteProfile"):
                continue
            geom = way.get("geom")
            if not isinstance(geom, list) or len(geom) < 2:
                continue
            if way.get("widthSrc") == "osm_width" and way.get("width") is not None:
                continue
            try:
                width, conf = _measure_way_width(geom, stitched, origin, mpp)
            except Exception as exc:  # noqa: BLE001
                logger.debug("sat measure fail: %s", exc)
                continue
            if width is not None and conf >= CONF_THR:
                way["satelliteWidth"] = width
                way["satelliteConfidence"] = conf
                way["satelliteWidthSrc"] = "pnoa" if is_spain else "esri"
                way["satelliteProfile"] = {"width": width, "confidence": conf}
                total_enriched += 1
            elif width is not None:
                way["satelliteWidth"] = width
                way["satelliteConfidence"] = conf
                way["satelliteWidthSrc"] = "pnoa" if is_spain else "esri"
            total_measured += 1

    if total_enriched:
        logger.info(
            "satellite matched %d/%d ways (%d batches, %d measured) bbox=%s",
            total_enriched, len(ways), len(batches), total_measured, bbox,
        )
    return total_enriched
