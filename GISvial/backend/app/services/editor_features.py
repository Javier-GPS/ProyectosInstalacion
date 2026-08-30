"""Editor features: buildings (con altura), zonas verdes y agua vía Overpass.

Para el editor de ciudad se piden las features de la sección seleccionada
(ej. parques en verde, ríos en azul, edificios extruidos con altura real).
"""
import logging
import re

import httpx
from typing import Any, Mapping

from .overpass import parse_bbox

logger = logging.getLogger(__name__)

GREEN = {
    "grass", "meadow", "forest", "village_green", "recreation_ground",
    "park", "cemetery", "allotments", "wood", "grassland",
}
WATER = {"water", "river", "stream", "canal", "reservoir", "basin", "lake", "pond", "dock"}

_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)


def _num(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _height(tags: Mapping) -> float | None:
    h = _num(tags.get("building:height"))
    if h is None and _num(tags.get("building:levels")):
        h = _num(tags.get("building:levels")) * 3.2
    return h


def _kind(tags: Mapping) -> str | None:
    landuse = str(tags.get("landuse", "") or "")
    natural = str(tags.get("natural", "") or "")
    waterway = str(tags.get("waterway", "") or "")
    leisure = str(tags.get("leisure", "") or "")
    if tags.get("building") or tags.get("building:part") or tags.get("building:name"):
        return "building"
    if waterway or natural == "water" or tags.get("water") or landuse in ("reservoir", "basin"):
        return "water"
    if landuse in GREEN or natural == "wood" or natural == "grassland" or leisure == "park":
        return "green"
    return None


async def _overpass(query: str) -> Any:
    body: Any = None
    last_err: Exception | None = None
    async with httpx.AsyncClient(
        timeout=150, headers={"User-Agent": "SALVI-GIS/2.0"}, follow_redirects=True,
    ) as client:
        for url in _MIRRORS:
            try:
                resp = await client.post(url, content=query)
                resp.raise_for_status()
                body = resp.json()
                break
            except Exception as exc:  # noqa: BLE001 — probar siguiente espejo
                last_err = exc
                logger.warning("Overpass mirror failed for editor features: %s", url)
    if body is None:
        raise RuntimeError(f"No Overpass mirror available: {last_err}")
    return body


async def fetch_editor_features(bbox: str) -> list[dict]:
    """Devuelve [{'kind': 'building'|'green'|'water', 'ring', 'height'?}] para el bbox."""
    south, north, west, east = parse_bbox(bbox)
    query = (
        f"[out:json][timeout:120];\n"
        f"way[\"building\"]({south},{west},{north},{east});\n"
        f"way[\"leisure\"=\"park\"]({south},{west},{north},{east});\n"
        f"way[\"natural\"~\"water|wood|grassland\"]({south},{west},{north},{east});\n"
        f"way[\"waterway\"]({south},{west},{north},{east});\n"
        f"way[\"landuse\"~\"grass|meadow|forest|village_green|recreation_ground|park|cemetery|allotments|reservoir|basin\"]"
        f"({south},{west},{north},{east});\n"
        f"out tags geom;"
    )
    body = await _overpass(query)

    out: list[dict] = []
    for el in body.get("elements", []):
        if el.get("type") != "way":
            continue
        ring_raw = el.get("geometry") or []
        pts: list[list[float]] = []
        for pt in ring_raw:
            if isinstance(pt, Mapping) and isinstance(pt.get("lon"), (int, float)) and isinstance(pt.get("lat"), (int, float)):
                pts.append([float(pt["lon"]), float(pt["lat"])])
        if len(pts) < 3:
            continue
        if pts[0] != pts[-1]:
            pts.append(list(pts[0]))
        tags = el.get("tags") or {}
        kind = _kind(tags)
        if kind is None:
            continue
        item: dict = {"kind": kind, "ring": pts}
        if kind == "building":
            item["height"] = _height(tags)
        out.append(item)
    return out
