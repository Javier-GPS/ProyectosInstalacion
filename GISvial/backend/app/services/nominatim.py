"""Nominatim proxy — forward geocoding to OpenStreetMap."""
import json
import ssl
import urllib.error as _ue
import urllib.parse as _up
import urllib.request as _ur
from typing import Optional

_NOM_HEADERS = {"User-Agent": "SalviGIS/1.0 (contact@salvi.es)", "Accept-Language": "es,en"}


def _ssl_ctx():
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()


def search(q: str, featuretype: Optional[str] = None) -> list:
    params = f"q={_up.quote(q)}&format=json&addressdetails=1&polygon_geojson=1&limit=10"
    if featuretype:
        params += f"&featuretype={featuretype}"
    req = _ur.Request(f"https://nominatim.openstreetmap.org/search?{params}", headers=_NOM_HEADERS)
    with _ur.urlopen(req, timeout=12, context=_ssl_ctx()) as resp:
        return json.loads(resp.read())


def reverse(lat: float, lon: float, zoom: int = 14) -> dict:
    params = f"lat={lat}&lon={lon}&format=json&polygon_geojson=1&zoom={zoom}"
    req = _ur.Request(f"https://nominatim.openstreetmap.org/reverse?{params}", headers=_NOM_HEADERS)
    with _ur.urlopen(req, timeout=12, context=_ssl_ctx()) as resp:
        return json.loads(resp.read())
