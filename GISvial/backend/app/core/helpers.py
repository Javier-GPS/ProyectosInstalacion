"""Shared helpers — deduplicated _fval, _sval, _parse_json."""
import json
from typing import Any


def fval(v: Any) -> float | None:
    """Parse to float, return None on failure."""
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def sval(v: Any) -> str | None:
    """Parse to stripped string, return None on failure."""
    return str(v).strip() if v is not None else None


def parse_json(v: Any, default: Any = None) -> Any:
    """Parse JSON string, list, or dict. Return default on failure."""
    if v is None:
        return default if default is not None else ({} if isinstance(default, dict) else [])
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return default if default is not None else ({} if default is None else [])
    return v
