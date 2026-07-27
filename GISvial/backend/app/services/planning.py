"""Pure planning inventory helpers over the legacy OSM JSON."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping
from typing import Any


ADAPTER_VERSION = 1
PROJECTION_FIELDS = (
    "id", "type", "name", "len", "geom", "startPt", "endPt",
    "estWidth", "width", "widthSrc", "lanes", "dual", "surface",
    "sidewalk", "tunnel",
)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def record_projection(record: object) -> bytes:
    if not isinstance(record, Mapping):
        return canonical_json({"raw": record})
    return canonical_json({key: record.get(key) for key in PROJECTION_FIELDS})


def target_ref(source_index: int, projection: bytes) -> str:
    return f"s:{source_index}:{hashlib.sha256(projection).hexdigest()}"


def group_ref(road_type: str | None) -> str:
    digest = hashlib.sha256(canonical_json({"road_type": road_type})).hexdigest()
    return f"g:{digest}"


def base_inventory_hash(records: list[object]) -> str:
    digest = hashlib.sha256()
    digest.update(b"[")
    for index, record in enumerate(records):
        if index:
            digest.update(b",")
        digest.update(record_projection(record))
    digest.update(b"]")
    return f"sha256:{digest.hexdigest()}"


def length_m(value: object) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    return float(value) * 1000.0


def _geometry(value: object) -> list[list[float]] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    result: list[list[float]] = []
    for point in value:
        if not isinstance(point, Mapping):
            return None
        lat, lon = point.get("lat"), point.get("lon")
        if (
            type(lat) not in (int, float) or type(lon) not in (int, float)
            or not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180
        ):
            return None
        result.append([float(lon), float(lat)])
    return result


def _label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFC", value.strip())
    return normalized or None


def normalize_inventory(zone_id: str, records: list[object]) -> dict[str, Any]:
    """Return one authoritative planning projection without mutating ``records``."""
    inventory_digest = hashlib.sha256()
    inventory_digest.update(b"[")
    groups_by_ref: dict[str, dict[str, Any]] = {}
    group_streets: dict[str, set[str]] = {}
    global_streets: set[str] = set()
    targets: list[dict[str, Any]] = []
    geometry_available = invalid_length_count = unnamed_segment_count = 0

    for source_index, raw in enumerate(records):
        record = raw if isinstance(raw, Mapping) else {}
        diagnostics: list[str] = []
        road_type = _label(record.get("type"))
        name = _label(record.get("name"))
        geometry = _geometry(record.get("geom"))
        segment_length = length_m(record.get("len"))
        projection = record_projection(raw)
        if source_index:
            inventory_digest.update(b",")
        inventory_digest.update(projection)
        gref = group_ref(road_type)

        if not isinstance(raw, Mapping):
            diagnostics.append("invalid_record")
        if geometry is None:
            diagnostics.append("geometry_unavailable")
        else:
            geometry_available += 1
        if segment_length is None:
            diagnostics.append("invalid_length")
            invalid_length_count += 1
        if name is None:
            unnamed_segment_count += 1

        group = groups_by_ref.setdefault(gref, {
            "group_ref": gref,
            "road_type": road_type,
            "street_count": 0,
            "target_count": 0,
            "length_m": 0.0,
            "invalid_length_count": 0,
        })
        streets = group_streets.setdefault(gref, set())
        if name is not None:
            streets.add(name)
            global_streets.add(name)
        group["target_count"] += 1
        if segment_length is None:
            group["invalid_length_count"] += 1
        else:
            group["length_m"] += segment_length

        targets.append({
            "target_ref": target_ref(source_index, projection),
            "group_ref": gref,
            "source_index": source_index,
            "name": name,
            "length_m": segment_length,
            "geometry": geometry,
            "diagnostics": diagnostics,
        })

    groups = list(groups_by_ref.values())
    inventory_digest.update(b"]")
    inventory_hash = f"sha256:{inventory_digest.hexdigest()}"
    for group in groups:
        group["street_count"] = len(group_streets[group["group_ref"]])

    return {
        "schema_version": 1,
        "adapter_version": ADAPTER_VERSION,
        "zone_id": zone_id,
        "base_inventory_hash": inventory_hash,
        "counts": {
            "segment_count": len(targets),
            "named_street_count": len(global_streets),
            "unnamed_segment_count": unnamed_segment_count,
            "geometry_available": geometry_available,
            "geometry_unavailable": len(targets) - geometry_available,
            "invalid_length_count": invalid_length_count,
        },
        "groups": groups,
        "targets": targets,
    }


def compact_payload(payload: Mapping[str, object]) -> dict[str, dict[str, Any]]:
    """Drop empty sparse patches while preserving explicit ``null`` values."""
    def compact(value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        result = {key: compact(item) for key, item in value.items()}
        return {key: item for key, item in result.items() if item != {}}

    result: dict[str, dict[str, Any]] = {}
    for key in ("group_defaults", "target_overrides"):
        source = payload.get(key, {})
        compacted = compact(source)
        result[key] = compacted if isinstance(compacted, dict) else {}
    return result
