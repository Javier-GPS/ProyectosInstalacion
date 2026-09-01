"""Automatic vector ↔ raster alignment.

Computes a global translation (dx, dy) that snaps OSM road vectors to the
satellite/ortho raster so both maps coincide.  Works automatically per zone:

* For Spain (bbox inside -18..5, 27..44) tries vector-vector against the
  official IGN Transport Network (WFS/OGC API, aligned with PNOA).
* Fallback / global: raster correlation — fetch a small window of Esri/PNOA
  tiles, rasterize OSM roads to a mask, and phase-correlate.

Result is a translation in degrees (and meters) stored in ``gis_zone_alignment``.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TILE_SIZE = 256
ZOOM_ALIGN = 18  # ~0.6 m/px, enough for 5-20 m offsets
WINDOW_TILES = 3  # 3×3 window around zone centre (~460 m at z18)
SEARCH_PX = 40  # ±40 px search window (~±24 m)

# IGN OGC API for road links (GeoJSON, ETRS89/WGS84)
IGN_API = "https://api-features.idee.es/collections/tn-ro:roadlink/items"


def _is_spain(bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bbox
    return west >= -18 and east <= 5 and south >= 27 and north <= 44


def _bbox_from_ways(ways: list[dict]) -> tuple[float, float, float, float] | None:
    lons: list[float] = []
    lats: list[float] = []
    for w in ways:
        for coord in w.get("geometry") or w.get("geom") or []:
            if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                lons.append(float(coord[0])); lats.append(float(coord[1]))
        for coord in w.get("nodes") or []:
            # some ways store lon/lat differently — ignore
            pass
    if not lons:
        return None
    return (min(lons), min(lats), max(lons), max(lats))


def _centre(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    west, south, east, north = bbox
    return ((west + east) / 2, (south + north) / 2)


def _lng_to_x(lng: float, z: int) -> float:
    return (lng + 180) / 360 * (2 ** z)


def _lat_to_y(lat: float, z: int) -> float:
    lat_rad = math.radians(lat)
    return (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * (2 ** z)


def _meters_per_pixel(lat: float, z: int) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / (2 ** z)


def _meters_to_deg(lat: float) -> tuple[float, float]:
    M_PER_DEG_LAT = 111320
    d_lat = 1 / M_PER_DEG_LAT
    d_lng = 1 / (M_PER_DEG_LAT * math.cos(math.radians(lat) or 1e-6))
    return d_lng, d_lat


# ── IGN vector-vector alignment ──────────────────────────────────────────
async def _fetch_ign_roads(bbox: tuple[float, float, float, float]) -> list[list[list[float]]]:
    west, south, east, north = bbox
    # Pad bbox a bit for context
    pad = 0.002  # ~200 m
    url = f"{IGN_API}?bbox={west-pad},{south-pad},{east+pad},{north+pad}&limit=1000&f=json"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
            if resp.status_code != 200:
                logger.warning("IGN API %s -> %s", url, resp.status_code)
                return []
            data = resp.json()
            geoms: list[list[list[float]]] = []
            for feat in data.get("features") or []:
                geom = feat.get("geometry") or {}
                if geom.get("type") == "LineString" and isinstance(geom.get("coordinates"), list):
                    geoms.append(geom["coordinates"])
                elif geom.get("type") == "MultiLineString":
                    for line in geom.get("coordinates") or []:
                        geoms.append(line)
            return geoms
    except Exception as exc:
        logger.warning("IGN fetch failed: %s", exc)
        return []


def _nearest_point_on_segments(px: float, py: float, geoms: list[list[list[float]]]) -> tuple[float, float] | None:
    best = None
    best_d2 = float("inf")
    for line in geoms:
        for i in range(len(line) - 1):
            x1, y1 = line[i][0], line[i][1]
            x2, y2 = line[i + 1][0], line[i + 1][1]
            dx, dy = x2 - x1, y2 - y1
            denom = dx * dx + dy * dy
            if denom == 0:
                continue
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / denom))
            cx, cy = x1 + t * dx, y1 + t * dy
            d2 = (px - cx) ** 2 + (py - cy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = (cx, cy)
    return best


def _vector_offset_osm_to_ign(osm_geoms: list[list[list[float]]], ign_geoms: list[list[list[float]]]) -> tuple[float, float, float] | None:
    if not osm_geoms or not ign_geoms:
        return None
    dxs: list[float] = []
    dys: list[float] = []
    for line in osm_geoms:
        # sample midpoint of each OSM segment
        for i in range(len(line) - 1):
            mx = (line[i][0] + line[i + 1][0]) / 2
            my = (line[i][1] + line[i + 1][1]) / 2
            nearest = _nearest_point_on_segments(mx, my, ign_geoms)
            if nearest is None:
                continue
            # only consider close matches (<50 m)
            d_lng, d_lat = _meters_to_deg(my)
            dist_m = math.hypot((mx - nearest[0]) / d_lng, (my - nearest[1]) / d_lat)
            if dist_m < 50:
                dxs.append(nearest[0] - mx)
                dys.append(nearest[1] - my)
    if len(dxs) < 5:
        return None
    dxs.sort(); dys.sort()
    # median robust to outliers
    mx = dxs[len(dxs) // 2]
    my = dys[len(dys) // 2]
    # confidence: fraction with |dx-mx|<5m and |dy-my|<5m
    d_lng, d_lat = _meters_to_deg(0)  # approximate, will be refined per point
    # Use 0.00005 deg ~5.5 m as threshold
    thr = 0.00005
    inliers = sum(1 for dx, dy in zip(dxs, dys) if abs(dx - mx) < thr and abs(dy - my) < thr)
    conf = inliers / len(dxs) if dxs else 0
    return mx, my, conf


# ── Raster correlation alignment (global fallback) ───────────────────────
def _phase_correlate(a: Any, b: Any) -> tuple[int, int, float]:
    """Phase correlation via numpy FFT. Returns (dx, dy, confidence) in pixels."""
    try:
        import numpy as np  # type: ignore
    except ImportError:
        return 0, 0, 0.0
    # a,b are 2D float arrays same shape
    # window to reduce edge effects
    try:
        import numpy as np

        # Use float32
        fa = np.fft.fft2(a)
        fb = np.fft.fft2(b)
        cross = fa * np.conj(fb)
        cross /= np.abs(cross) + 1e-8
        corr = np.fft.ifft2(cross)
        corr = np.abs(corr)
        # Find peak
        y, x = np.unravel_index(np.argmax(corr), corr.shape)
        h, w = corr.shape
        # Wrap-around
        if x > w // 2:
            x -= w
        if y > h // 2:
            y -= h
        peak = float(corr[y % h, x % w])
        # confidence: peak vs mean
        mean = float(np.mean(corr))
        conf = min(1.0, max(0.0, (peak - mean) / (peak + 1e-8)))
        # Clamp to search window
        if abs(x) > SEARCH_PX or abs(y) > SEARCH_PX:
            return 0, 0, 0.0
        return int(x), int(y), conf
    except Exception as exc:
        logger.warning("phase correlate failed: %s", exc)
        return 0, 0, 0.0


def _render_mask(geoms: list[list[list[float]]], bbox: tuple[float, float, float, float], size: int, width_px: int = 3) -> Any:
    try:
        from PIL import Image, ImageDraw  # type: ignore
        import numpy as np
    except ImportError:
        return None
    west, south, east, north = bbox
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    # Convert lng/lat to pixel
    def to_px(lng: float, lat: float) -> tuple[int, int]:
        x = (lng - west) / (east - west) * size if east != west else 0
        y = (1 - (lat - south) / (north - south)) * size if north != south else 0
        return int(round(x)), int(round(y))
    for line in geoms:
        if len(line) < 2:
            continue
        pts = [to_px(lng, lat) for lng, lat in line]
        draw.line(pts, fill=255, width=width_px, joint="round")
    return np.array(img, dtype=np.float32) / 255.0


async def _fetch_raster_window(bbox: tuple[float, float, float, float], zoom: int = ZOOM_ALIGN, source: str = "esri") -> tuple[Any, tuple[float, float, float, float]] | None:
    """Fetch a WINDOW_TILES×WINDOW_TILES window around bbox centre. Returns (PIL.Image, bbox_of_image)."""
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return None
    west, south, east, north = bbox
    clng, clat = _centre(bbox)
    cx, cy = _lng_to_x(clng, zoom), _lat_to_y(clat, zoom)
    # Integer tile range centred on centre
    half = WINDOW_TILES // 2
    tx0, ty0 = int(math.floor(cx)) - half, int(math.floor(cy)) - half
    # Pick source URL
    if source == "pnoa":
        # PNOA WMTS, same as CityEditor
        def tile_url(x: int, y: int, z: int) -> str:
            return f"https://www.ign.es/wmts/pnoa-ma?Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/jpeg&Layer=OI.OrthoimageCoverage&Style=default&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileCol={x}&TileRow={y}"
    else:
        def tile_url(x: int, y: int, z: int) -> str:
            return f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    # Fetch tiles
    tiles: dict[tuple[int, int], Any] = {}
    async with httpx.AsyncClient(timeout=15) as client:
        async def fetch_one(x: int, y: int):
            url = tile_url(x, y, zoom)
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    from PIL import Image
                    import io

                    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    tiles[(x, y)] = img
            except Exception:
                pass

        await asyncio.gather(*(fetch_one(tx0 + dx, ty0 + dy) for dx in range(WINDOW_TILES) for dy in range(WINDOW_TILES)))
    if not tiles:
        return None
    # Stitch
    size = TILE_SIZE * WINDOW_TILES
    stitched = Image.new("RGB", (size, size))
    for (x, y), img in tiles.items():
        px, py = (x - tx0) * TILE_SIZE, (y - ty0) * TILE_SIZE
        stitched.paste(img, (px, py))
    # Compute bbox of stitched image
    def tile_to_lng(x: float, z: int) -> float:
        return x / (2 ** z) * 360 - 180

    def tile_to_lat(y: float, z: int) -> float:
        n = math.pi - 2 * math.pi * y / (2 ** z)
        return math.degrees(math.atan(math.sinh(n)))

    img_west = tile_to_lng(tx0, zoom)
    img_north = tile_to_lat(ty0, zoom)
    img_east = tile_to_lng(tx0 + WINDOW_TILES, zoom)
    img_south = tile_to_lat(ty0 + WINDOW_TILES, zoom)
    return stitched, (img_west, img_south, img_east, img_north)


def _satellite_to_grayscale_mask(sat: Any) -> Any:
    """Convert satellite RGB PIL image to a road-enhanced grayscale mask (float 0-1)."""
    try:
        import numpy as np
        from PIL import Image

        arr = np.array(sat.convert("RGB"), dtype=np.float32)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        # Road: bright + low saturation
        maxc = np.maximum(np.maximum(r, g), b)
        minc = np.minimum(np.minimum(r, g), b)
        # Brightness 0-255, saturation 0-255
        brightness = maxc
        sat = (maxc - minc)
        # Road mask: bright (>170) and low sat (<35)
        road = ((brightness > 170) & (sat < 40)).astype(np.float32)
        # Also high-frequency edges: simple Sobel-like via PIL FIND_EDGES as fallback
        # Slight blur to thicken roads for correlation
        from PIL import ImageFilter

        # Dilate a bit
        road_img = Image.fromarray((road * 255).astype(np.uint8), mode="L")
        road_img = road_img.filter(ImageFilter.MaxFilter(3))
        return np.array(road_img, dtype=np.float32) / 255.0
    except Exception as exc:
        logger.warning("sat preprocess failed: %s", exc)
        return None


async def compute_raster_offset(osm_geoms: list[list[list[float]]], bbox: tuple[float, float, float, float]) -> tuple[float, float, float] | None:
    """Compute offset via raster correlation. Returns (dx_deg, dy_deg, conf) or None."""
    # Fetch satellite window
    sat_data = await _fetch_raster_window(bbox, zoom=ZOOM_ALIGN, source="esri")
    if sat_data is None:
        return None
    sat_img, img_bbox = sat_data
    # Render OSM mask at same bbox/size
    try:
        from PIL import Image

        size = sat_img.size[0]  # square
        mask = _render_mask(osm_geoms, img_bbox, size, width_px=4)
        if mask is None:
            return None
        sat_mask = _satellite_to_grayscale_mask(sat_img)
        if sat_mask is None:
            return None
        # Phase correlate
        dx_px, dy_px, conf = _phase_correlate(mask, sat_mask)
        if conf < 0.15:
            return None
        # Convert px to degrees
        west, south, east, north = img_bbox
        deg_per_px_x = (east - west) / size
        deg_per_px_y = (north - south) / size
        # Phase correlate gives shift of mask relative to satellite.
        # To align mask to satellite, shift mask by (dx,dy). Vector should move by that.
        dx_deg = dx_px * deg_per_px_x
        dy_deg = -dy_px * deg_per_px_y  # y is north->south in image
        if abs(dx_deg) > 0.0005 or abs(dy_deg) > 0.0005:  # > ~50 m, likely spurious
            return None
        return dx_deg, dy_deg, conf
    except Exception as exc:
        logger.warning("raster offset failed: %s", exc)
        return None


# ── Public API ───────────────────────────────────────────────────────────
async def auto_align_for_zone(zone_id: str, ways: list[dict], bbox_str: str | None) -> tuple[float, float, float, str] | None:
    """Compute automatic alignment for a zone. Returns (dx, dy, conf, source) or None."""
    # Parse bbox
    bbox: tuple[float, float, float, float] | None = None
    if bbox_str:
        try:
            # bbox stored as "west,south,east,north" or similar — try to parse
            parts = [p.strip() for p in bbox_str.replace(";", ",").split(",") if p.strip()]
            if len(parts) == 4:
                vals = [float(p) for p in parts]
                # Heuristic: detect order. Our bbox is often "south,north,west,east" in some places,
                # but zone.bbox is usually "west,south,east,north" as stored.
                # Try both: if first two are lat-like (|val|<=90) and last two lon-like, swap.
                # Simpler: assume west,south,east,north if west<east and south<north
                west, south, east, north = vals
                if west > east or south > north:
                    # try south,north,west,east
                    south, north, west, east = vals
                if west < east and south < north:
                    bbox = (west, south, east, north)
        except Exception:
            pass
    if bbox is None:
        bbox = _bbox_from_ways(ways)
    if bbox is None:
        return None
    # Extract OSM geoms as list of linestrings in lng/lat
    osm_geoms: list[list[list[float]]] = []
    for w in ways:
        geom = w.get("geometry") or w.get("geom")
        if isinstance(geom, list) and geom and isinstance(geom[0], (list, tuple)):
            # geom is list of [lng,lat]
            osm_geoms.append([[float(p[0]), float(p[1])] for p in geom if len(p) >= 2])
    if not osm_geoms:
        return None

    # Try IGN vector-vector for Spain
    if _is_spain(bbox):
        ign_geoms = await _fetch_ign_roads(bbox)
        if ign_geoms:
            vec = _vector_offset_osm_to_ign(osm_geoms, ign_geoms)
            if vec:
                dx, dy, conf = vec
                if abs(dx) < 0.001 and abs(dy) < 0.001 and conf > 0.3:
                    return dx, dy, conf, "ign-vector"

    # Fallback: raster correlation
    raster = await compute_raster_offset(osm_geoms, bbox)
    if raster:
        dx, dy, conf = raster
        return dx, dy, conf, "raster"

    return None
