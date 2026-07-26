"""JWKS client — OIDC key fetch and cache with stale-while-revalidate."""
import json
import time
from typing import Any

import httpx

JWKS_CACHE: dict[str, Any] = {}
_JWKS_LOADED_AT: float = 0
_JWKS_TTL = 300  # 5 minutos


async def _fetch_jwks(issuer_url: str) -> dict[str, Any]:
    """Fetch JWKS from OIDC issuer."""
    async with httpx.AsyncClient(timeout=5) as cl:
        r = await cl.get(f"{issuer_url.rstrip('/')}/.well-known/openid-configuration")
        r.raise_for_status()
        jwks_uri = r.json()["jwks_uri"]
        r2 = await cl.get(jwks_uri)
        r2.raise_for_status()
        return {k["kid"]: k for k in r2.json()["keys"]}


async def get_jwks_keys(issuer_url: str) -> dict[str, Any]:
    """Get cached JWKS keys, refreshing if stale."""
    global JWKS_CACHE, _JWKS_LOADED_AT
    now = time.time()
    if now - _JWKS_LOADED_AT > _JWKS_TTL or not JWKS_CACHE:
        try:
            JWKS_CACHE = await _fetch_jwks(issuer_url)
            _JWKS_LOADED_AT = now
        except Exception:
            if not JWKS_CACHE:
                raise
    return JWKS_CACHE
