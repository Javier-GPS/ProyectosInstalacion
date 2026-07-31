"""Redis cache client — async, graceful degradation when unavailable."""
from __future__ import annotations

import json
import logging
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

_redis = None  # Redis | None


async def init_redis() -> None:
    """Initialize the async Redis client if a URL is configured."""
    global _redis
    if not settings.redis_url:
        logger.info("No REDIS_URL configured — cache disabled")
        _redis = None
        return
    try:
        from redis.asyncio import Redis

        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await _redis.ping()
        logger.info("Redis connected at %s", settings.redis_url)
    except Exception as exc:
        logger.warning("Redis unavailable — cache disabled: %s", exc)
        _redis = None


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        except Exception:
            pass
        _redis = None


async def cache_get(key: str) -> Any | None:
    """Get value from cache. Returns parsed JSON or None."""
    if _redis is None:
        return None
    try:
        data = await _redis.get(key)
        if data is None:
            return None
        return json.loads(data)
    except Exception as exc:
        logger.debug("Cache GET error for %s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    """Set value in cache with TTL in seconds. Gracefully ignores errors."""
    if _redis is None:
        return
    try:
        data = json.dumps(value, default=str, separators=(",", ":"), ensure_ascii=False)
        await _redis.setex(key, ttl, data)
    except Exception as exc:
        logger.debug("Cache SET error for %s: %s", key, exc)


async def cache_delete(key: str) -> None:
    """Delete a key from cache."""
    if _redis is None:
        return
    try:
        await _redis.delete(key)
    except Exception as exc:
        logger.debug("Cache DELETE error for %s: %s", key, exc)
