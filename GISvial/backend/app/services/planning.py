"""Pure planning inventory helpers over the legacy OSM JSON."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping
from typing import Any

from .overpass import road_role
from .road_geometry import assign_tramos, resolve_way
from .street_merge import merge_streets


ADAPTER_VERSION = 2
PROJECTION_FIELDS = (
    "id", "type", "highway", "name", "ref", "noname", "officialName",
    "altName", "locName", "nameState", "roadRole", "lit", "len", "geom", "startPt", "endPt",
    "estWidth", "width", "widthSrc", "lanes", "dual", "surface",
    "sidewalk", "tunnel", "sidewalkWidthLeft", "sidewalkWidthRight",
    "median", "medianWidth",
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
    return f"s:{source_index}:{hashlib.md5(projection).hexdigest()}"


def group_ref(road_type: str | None) -> str:
    digest = hashlib.md5(canonical_json({"road_type": road_type})).hexdigest()
    return f"g:{digest}"


def base_inventory_hash(records: list[object]) -> str:
    digest = hashlib.md5()
    digest.update(b"[")
    for index, record in enumerate(records):
        if index:
            digest.update(b",")
        digest.update(record_projection(record))
    digest.update(b"]")
    return f"md5:{digest.hexdigest()}"


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


def _record_name_fields(record: Mapping) -> tuple[str | None, str | None, str, str]:
    """Read current OSM fields while tolerating legacy cached records."""
    osm_name = _label(record.get("osmName")) or _label(record.get("name"))
    osm_ref = _label(record.get("osmRef")) or _label(record.get("ref"))
    state = _label(record.get("nameState"))
    legacy = "nameState" not in record and "osmName" not in record and "osmRef" not in record
    if not state:
        if legacy and osm_name:
            state = "legacy"
        elif osm_name:
            state = "named"
        elif osm_ref:
            state = "ref_only"
        elif _label(record.get("noname")) in {"yes", "true", "1"}:
            state = "explicit_noname"
        elif any(_label(record.get(key)) for key in ("officialName", "altName", "locName")):
            state = "variant_only"
        else:
            state = "unnamed"
    highway = _label(record.get("highway")) or (_label(record.get("type")) if record.get("type") != "tunnel" else None)
    return osm_name, osm_ref, state, _label(record.get("roadRole")) or road_role(highway)


def inventory_counts(records: list[object]) -> dict:
    """Lightweight counts over raw ways — no projections, no street merging.

    Mirrors the ``counts`` block of :func:`normalize_inventory` so summaries
    can be served from a persisted JSONB column instead of re-normalizing.
    """
    geometry_available = invalid_length_count = unnamed_segment_count = 0
    explicit_noname_count = ref_only_count = variant_only_count = legacy_name_count = 0
    named_way_count = 0
    name_state_counts: dict[str, int] = {}
    road_role_counts: dict[str, int] = {}
    global_streets: set[str] = set()
    source_needs_refresh = False

    for raw in records:
        record = raw if isinstance(raw, Mapping) else {}
        name, ref, state, role = _record_name_fields(record)
        source_needs_refresh = source_needs_refresh or "nameState" not in record
        if _geometry(record.get("geom")) is not None:
            geometry_available += 1
        segment_length = length_m(record.get("len"))
        if segment_length is None:
            invalid_length_count += 1
        if name is None:
            unnamed_segment_count += 1
        else:
            named_way_count += 1
            global_streets.add(name)
        if state == "explicit_noname":
            explicit_noname_count += 1
        elif state == "ref_only":
            ref_only_count += 1
        elif state == "variant_only":
            variant_only_count += 1
        elif state == "legacy":
            legacy_name_count += 1
        name_state_counts[state] = name_state_counts.get(state, 0) + 1
        road_role_counts[role] = road_role_counts.get(role, 0) + 1

    segment_count = len(records)
    return {
        "counts": {
            "segment_count": segment_count,
            "named_street_count": len(global_streets),
            "distinct_name_count": len(global_streets),
            "named_way_count": named_way_count,
            "unnamed_segment_count": unnamed_segment_count,
            "without_osm_name_count": unnamed_segment_count,
            "explicit_noname_count": explicit_noname_count,
            "ref_only_count": ref_only_count,
            "variant_only_count": variant_only_count,
            "legacy_name_count": legacy_name_count,
            "geometry_available": geometry_available,
            "geometry_unavailable": segment_count - geometry_available,
            "invalid_length_count": invalid_length_count,
        },
        "name_state_counts": name_state_counts,
        "road_role_counts": road_role_counts,
        "source_needs_refresh": source_needs_refresh,
    }


def normalize_inventory(zone_id: str, records: list[object]) -> dict[str, Any]:
    """Return one authoritative planning projection without mutating ``records``."""
    inventory_digest = hashlib.md5()
    inventory_digest.update(b"[")
    groups_by_ref: dict[str, dict[str, Any]] = {}
    group_streets: dict[str, set[str]] = {}
    global_streets: set[str] = set()
    targets: list[dict[str, Any]] = []
    geometry_available = invalid_length_count = unnamed_segment_count = 0
    explicit_noname_count = ref_only_count = variant_only_count = legacy_name_count = 0
    name_state_counts: dict[str, int] = {}
    road_role_counts: dict[str, int] = {}
    source_needs_refresh = False

    for source_index, raw in enumerate(records):
        record = raw if isinstance(raw, Mapping) else {}
        diagnostics: list[str] = []
        road_type = _label(record.get("type"))
        name, ref, state, role = _record_name_fields(record)
        source_needs_refresh = source_needs_refresh or "nameState" not in record
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
        if state == "explicit_noname":
            explicit_noname_count += 1
        elif state == "ref_only":
            ref_only_count += 1
        elif state == "variant_only":
            variant_only_count += 1
        elif state == "legacy":
            legacy_name_count += 1
        name_state_counts[state] = name_state_counts.get(state, 0) + 1
        road_role_counts[role] = road_role_counts.get(role, 0) + 1

        group = groups_by_ref.setdefault(gref, {
            "group_ref": gref,
            "road_type": road_type,
            "road_role": role,
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

        resolved = resolve_way(record)
        geom = resolved["merged"]
        geom_sources = resolved["sources"]

        est_width = geom.get("width")
        width_src = geom.get("widthSrc")
        lanes_val = geom.get("lanes")
        lanes_fwd = geom.get("lanesForward")
        lanes_bwd = geom.get("lanesBackward")
        sw = geom.get("sidewalk")
        sw_left = geom.get("sidewalkWidthLeft")
        sw_right = geom.get("sidewalkWidthRight")
        median = geom.get("median")
        median_w = geom.get("medianWidth")
        dual = geom.get("dual")
        surface = geom.get("surface")
        cycleway_w = geom.get("cyclewayWidth")
        parking = geom.get("parking")
        shoulder_w = geom.get("shoulderWidth")
        maxspeed = geom.get("maxspeed")
        platform_w = geom.get("platformWidth")
        functional_class = geom.get("functionalClass")
        form_of_way = geom.get("formOfWay")

        targets.append({
            "target_ref": target_ref(source_index, projection),
            "group_ref": gref,
            "source_index": source_index,
            "name": name,
            "highway": _label(record.get("highway")),
            "osmName": name,
            "osmRef": ref,
            "noname": _label(record.get("noname")),
            "officialName": _label(record.get("officialName")),
            "altName": _label(record.get("altName")),
            "locName": _label(record.get("locName")),
            "nameState": state,
            "roadRole": role,
            "osmWayId": record.get("id"),
            "displayLabel": name or (f"Ref. {ref}" if ref else None),
            "lit": _label(record.get("lit")),
            "length_m": segment_length,
            "geometry": geometry,
            "diagnostics": diagnostics,
            "estWidth": est_width,
            "widthSrc": width_src,
            "lanes": lanes_val,
            "lanesForward": lanes_fwd,
            "lanesBackward": lanes_bwd,
            "sidewalk": sw,
            "sidewalkWidthLeft": sw_left,
            "sidewalkWidthRight": sw_right,
            "median": median,
            "medianWidth": median_w,
            "dual": dual,
            "cyclewayWidth": cycleway_w,
            "parking": parking,
            "shoulderWidth": shoulder_w,
            "maxspeed": maxspeed,
            "platformWidth": platform_w,
            "functionalClass": functional_class,
            "formOfWay": form_of_way,
            "surface": surface,
            "geomSources": geom_sources,
            "geom": geom,
        })

    # Per-street tramo numbering: a new tramo opens when geometry changes.
    tramo_map = assign_tramos(targets)
    for target in targets:
        entry = tramo_map.get(target["target_ref"])
        if entry:
            target["tramoSeq"] = entry["tramoSeq"]
            target["tramoOf"] = entry["tramoOf"]

    groups = list(groups_by_ref.values())
    inventory_digest.update(b"]")
    inventory_hash = f"md5:{inventory_digest.hexdigest()}"
    for group in groups:
        group["street_count"] = len(group_streets[group["group_ref"]])

    # Build merged street geometries for efficient frontend rendering
    streets = merge_streets(targets, groups, simplify_tolerance=0.0005)

    return {
        "schema_version": 1,
        "adapter_version": ADAPTER_VERSION,
        "zone_id": zone_id,
        "base_inventory_hash": inventory_hash,
        "counts": {
            "segment_count": len(targets),
            "named_street_count": len(global_streets),
            "distinct_name_count": len(global_streets),
            "named_way_count": sum(1 for target in targets if target["osmName"]),
            "unnamed_segment_count": unnamed_segment_count,
            "without_osm_name_count": unnamed_segment_count,
            "explicit_noname_count": explicit_noname_count,
            "ref_only_count": ref_only_count,
            "variant_only_count": variant_only_count,
            "legacy_name_count": legacy_name_count,
            "geometry_available": geometry_available,
            "geometry_unavailable": len(targets) - geometry_available,
            "invalid_length_count": invalid_length_count,
        },
        "name_state_counts": name_state_counts,
        "road_role_counts": road_role_counts,
        "source_needs_refresh": source_needs_refresh,
        "groups": groups,
        "targets": targets,
        "streets": streets,
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
