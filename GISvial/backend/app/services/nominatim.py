"""Nominatim proxy — forward geocoding to OpenStreetMap."""
from __future__ import annotations

from typing import Optional

import httpx

_NOM_HEADERS = {"User-Agent": "SalviGIS/1.0 (contact@salvi.es)", "Accept-Language": "es,en"}
_NOM_TIMEOUT = 12


async def search(q: str, featuretype: Optional[str] = None) -> list:
    params = {
        "q": q, "format": "json", "addressdetails": "1",
        "polygon_geojson": "1", "limit": "10",
    }
    if featuretype:
        params["featuretype"] = featuretype
    async with httpx.AsyncClient(headers=_NOM_HEADERS, timeout=_NOM_TIMEOUT) as client:
        resp = await client.get("https://nominatim.openstreetmap.org/search", params=params)
        resp.raise_for_status()
        return resp.json()


async def reverse(lat: float, lon: float, zoom: int = 14) -> dict:
    params = {
        "lat": str(lat), "lon": str(lon),
        "format": "json", "polygon_geojson": "1", "zoom": str(zoom),
    }
    async with httpx.AsyncClient(headers=_NOM_HEADERS, timeout=_NOM_TIMEOUT) as client:
        resp = await client.get("https://nominatim.openstreetmap.org/reverse", params=params)
        resp.raise_for_status()
        return resp.json()
