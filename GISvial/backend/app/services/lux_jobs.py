"""Pure helpers and state projections for the durable GIS/Lux workflow."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

from ..models import GisLuxJob, GisLuxJobItem


class JobItemError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _number(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def effective_patch(payload: dict, target: dict) -> dict:
    group = payload.get("group_defaults", {}).get(target.get("group_ref"), {}) or {}
    override = payload.get("target_overrides", {}).get(target.get("target_ref"), {}) or {}
    result = {**group, **override}
    group_lux = group.get("luxParams") or {}
    override_lux = override.get("luxParams") or {}
    result["luxParams"] = {**group_lux, **override_lux}
    return result


def build_lux_config(snapshot: dict) -> dict:
    target = snapshot["target"]
    params = snapshot.get("params") or {}
    lux = params.get("luxParams") or {}
    lighting_class = str(params.get("lighting_class") or "M3").upper()
    if not re.fullmatch(r"(?:M[1-6]|P[1-6])", lighting_class):
        raise JobItemError("UNSUPPORTED_CLASS", f"Lux no soporta la clase {lighting_class}")
    distribution = str(params.get("distribution") or "unilateral_r")
    arrangement = {
        "unilateral_r": "Lineal",
        "unilateral_l": "Lineal",
        "bilateral_pareado": "Bilateral",
        "bilateral_tresbolillo": "Bilateral Alternada",
        "centrada_mediana": "Central Doble",
        "mediana_compartida": "Central Doble",
    }.get(distribution, "Lineal")
    optic = str(lux.get("optic") or "F151")
    config = {
        "road_width": _number(target.get("estWidth"), 7.0),
        "sidewalk_left": _number(lux.get("sidewalkL"), _number(target.get("sidewalkWidthLeft"), 0.0)),
        "sidewalk_right": _number(lux.get("sidewalkR"), _number(target.get("sidewalkWidthRight"), 0.0)),
        "lanes": max(1, min(6, int(_number(target.get("lanes"), 2)))),
        "arrangement": arrangement,
        "height": max(4.0, min(40.0, _number(lux.get("poleH"), 9.0))),
        "spacing": max(5.0, min(60.0, _number(params.get("spacing"), 30.0))),
        "arm_length": max(0.0, min(5.0, _number(lux.get("armLen"), 1.5))),
        "tilt": max(-30.0, min(30.0, _number(lux.get("tilt"), 5.0))),
        "optic_family": optic,
        "power": max(0.0, _number(lux.get("power"), 100.0)),
        "lighting_class": lighting_class,
        "mf": max(0.5, min(1.0, _number(lux.get("maintFactor"), 0.85))),
        "pavement": "R3",
        "cct": max(1800, min(6500, int(_number(lux.get("colorTemp"), 4000)))),
        "cri": max(70, min(90, int(_number(lux.get("cri"), 70)))),
    }
    for source, destination in (("range", "gama"), ("diffuser", "difusor"), ("optic", "lente"), ("ledType", "led_type")):
        if lux.get(source):
            config[destination] = lux[source]
    return config


def _line_length_m(geometry: list[list[float]]) -> tuple[list[float], float]:
    cumulative = [0.0]
    for first, second in zip(geometry, geometry[1:]):
        lat = math.radians((first[1] + second[1]) / 2.0)
        dx = (second[0] - first[0]) * 111320.0 * math.cos(lat)
        dy = (second[1] - first[1]) * 110540.0
        cumulative.append(cumulative[-1] + math.hypot(dx, dy))
    return cumulative, cumulative[-1]


def materialization_points(snapshot: dict, result: dict) -> list[dict]:
    geometry = snapshot["target"].get("geometry") or []
    if len(geometry) < 2:
        raise JobItemError("GEOMETRY_UNAVAILABLE", "El tramo no tiene geometría materializable")
    config = result.get("config") or build_lux_config(snapshot)
    spacing = max(5.0, _number(config.get("spacing"), 30.0))
    cumulative, total = _line_length_m(geometry)
    if total <= 0:
        raise JobItemError("GEOMETRY_ZERO_LENGTH", "La geometría del tramo mide cero")
    distances = [min(total, spacing / 2.0 + index * spacing) for index in range(max(1, math.ceil(total / spacing)))]
    points: list[dict] = []
    for distance in distances:
        segment_index = next((i for i, end in enumerate(cumulative[1:]) if end >= distance), len(cumulative) - 2)
        start_distance = cumulative[segment_index]
        end_distance = cumulative[segment_index + 1]
        fraction = 0.0 if end_distance == start_distance else (distance - start_distance) / (end_distance - start_distance)
        first = geometry[segment_index]
        second = geometry[segment_index + 1]
        lon = first[0] + (second[0] - first[0]) * fraction
        lat = first[1] + (second[1] - first[1]) * fraction
        points.append({
            "lat": round(lat, 8),
            "lon": round(lon, 8),
            "watts": _number(config.get("power"), 100.0),
            "spacing": spacing,
            "tilt": _number(config.get("tilt"), 5.0),
            "height_m": _number(config.get("height"), 9.0),
            "arm_len": _number(config.get("arm_length"), 1.5),
            "lighting_class": config.get("lighting_class"),
            "distribution": config.get("arrangement"),
            "street_name": snapshot["target"].get("name") or "",
            "road_type": snapshot["target"].get("road_type") or "",
        })
    return points


def refresh_job(job: GisLuxJob, items: list[GisLuxJobItem]) -> None:
    job.total = len(items)
    job.succeeded = sum(item.state == "succeeded" for item in items)
    job.failed = sum(item.state in {"failed", "cancelled"} for item in items)
    job.blocked = sum(item.state in {"blocked", "stale"} for item in items)
    job.unknown = sum(item.state in {"unknown", "reconciling"} for item in items)
    active = sum(item.state in {"pending", "running", "materializing"} for item in items)
    if job.cancel_requested and active == 0:
        state = "cancelled"
    elif job.unknown:
        state = "unknown"
    elif active:
        state = "running"
    elif job.succeeded == job.total and job.total:
        state = "succeeded"
    elif job.succeeded:
        state = "partial"
    else:
        state = "failed"
    # The projection version must change for item-level progress too, not only
    # when the aggregate state changes; otherwise ETag polling hides progress.
    job.state_version += 1
    job.state = state
    job.updated_at = datetime.now(timezone.utc)
