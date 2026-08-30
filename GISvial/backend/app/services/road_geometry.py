"""Road geometry resolution from multiple sources.

A *profile* is a flat dict of geometry attributes produced by one source.
Each profile carries its source name under the ``__source__`` key. Profiles
from different sources are reconciled attribute-by-attribute, letting the most
authoritative source win per attribute while provenance is recorded so the UI
can show where every measurement came from.

Source priority (low → high):

    osm  ......... OpenStreetMap / Overpass (global, sparse attributes)
    mapillary .... Mapillary imagery ML inference (global, fills gaps)
    ign_rt ....... IGN IGR-RT / TRAM (Spain, authoritative carriageway geometry)
    catastro ..... Catastro / building-edge inference (Spain)
    survey ....... Field survey (highest trust)

A *tramo* is a street stretch with a stable geometry signature. Consecutive
segments of the same street whose signature differs are reported as distinct
tramos (``tramoSeq`` / ``tramoOf``).
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

SOURCE_PRIORITY = {
    "osm": 0,
    "overture": 1,
    "mapillary": 2,
    "ign_rt": 3,
    "osm_buildings": 4,  # facade-to-facade from OSM footprints (real)
    "catastro": 5,        # legacy facade-to-facade (source retired, kept for cache)
    "survey": 6,
}

# ponytail: urban lane standard; upgrade to per-country/per-road-type table
LANE_WIDTH_M = 3.0

DEFAULT_WIDTHS = {
    "motorway": 10.5, "trunk": 9.0, "primary": 7.0, "secondary": 6.0,
    "tertiary": 5.5, "residential": 4.5, "living_street": 4.0,
    "service": 3.5, "pedestrian": 3.0, "footway": 2.0, "path": 2.0,
    "cycleway": 2.0,
}

# Attributes that define a geometry "tramo" — a change in any splits the street.
TRAMO_ATTRS = (
    "width", "lanes", "lanesForward", "lanesBackward", "sidewalk",
    "sidewalkWidthLeft", "sidewalkWidthRight", "median", "medianWidth",
    "dual", "cyclewayWidth", "parking", "shoulderWidth",
)

_ALL_ATTRS = TRAMO_ATTRS + (
    "platformWidth", "surface", "lit", "maxspeed", "highway", "widthSrc",
    "functionalClass", "formOfWay",
)


def _num(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    return float(match.group(0).replace(",", ".")) if match else None


def _tag(tags: Mapping, *keys: str) -> str | None:
    for key in keys:
        value = tags.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def osm_profile(tags: Mapping) -> dict[str, Any]:
    """Build a geometry profile from raw OSM tags."""
    tags = tags if isinstance(tags, Mapping) else {}
    p: dict[str, Any] = {"__source__": "osm"}
    highway = _tag(tags, "highway") or "unclassified"
    p["highway"] = highway

    width = (
        _num(_tag(tags, "width:carriageway"))
        or _num(_tag(tags, "width"))
        or _num(_tag(tags, "est_width"))
    )
    width_src = None
    if width is not None:
        width_src = "osm_width"
    else:
        lanes = _num(_tag(tags, "lanes"))
        if lanes is not None:
            has_bike = str(tags.get("cycleway") or "").lower() in {
                "lane", "track", "separate", "yes", "true", "1",
            }
            width = (lanes - (1 if has_bike else 0)) * LANE_WIDTH_M
            width_src = "lanes"
        else:
            width = DEFAULT_WIDTHS.get(highway, 4.0)
            width_src = "default"
    p["width"] = round(width, 2)
    p["widthSrc"] = width_src

    lanes = _num(_tag(tags, "lanes"))
    if lanes is not None:
        p["lanes"] = int(lanes)
    lf = _num(_tag(tags, "lanes:forward"))
    lb = _num(_tag(tags, "lanes:backward"))
    if lf is not None:
        p["lanesForward"] = int(lf)
    if lb is not None:
        p["lanesBackward"] = int(lb)

    sidewalk = _tag(tags, "sidewalk")
    if sidewalk:
        p["sidewalk"] = sidewalk
    swl = _num(_tag(tags, "sidewalk:left:width")) or _num(_tag(tags, "sidewalk:both:width"))
    swr = _num(_tag(tags, "sidewalk:right:width")) or _num(_tag(tags, "sidewalk:both:width"))
    swt = _tag(tags, "sidewalk:width")
    if swl is None and swr is None and swt:
        swl = swr = _num(swt)
    if swl is not None:
        p["sidewalkWidthLeft"] = round(swl, 2)
    if swr is not None:
        p["sidewalkWidthRight"] = round(swr, 2)

    median = str(tags.get("median") or "").lower() in {"yes", "true", "1"}
    median_w = _num(_tag(tags, "median:width"))
    dual = str(tags.get("dual_carriageway") or "").lower() in {"yes", "true", "1", "separate"}
    if median:
        dual = True
        p["median"] = True
    if median_w is not None:
        p["medianWidth"] = round(median_w, 2)
    if dual:
        p["dual"] = True

    cw = _num(_tag(tags, "cycleway:width")) or _num(_tag(tags, "cycleway:lane:width"))
    if cw is not None:
        p["cyclewayWidth"] = round(cw, 2)

    parking = _tag(tags, "parking:lane:both", "parking:lane", "parking")
    if parking:
        p["parking"] = parking

    shoulder = str(tags.get("shoulder") or "").lower() in {"yes", "true", "1"}
    shoulder_w = _num(_tag(tags, "shoulder:width"))
    if shoulder or shoulder_w is not None:
        p["shoulderWidth"] = round(shoulder_w, 2) if shoulder_w is not None else None

    if _tag(tags, "surface"):
        p["surface"] = _tag(tags, "surface")
    if _tag(tags, "lit"):
        p["lit"] = _tag(tags, "lit")
    maxspeed = _num(_tag(tags, "maxspeed"))
    if maxspeed is not None:
        p["maxspeed"] = int(maxspeed)
    return p


def ign_rt_profile(props: Mapping) -> dict[str, Any]:
    """Build a profile from IGN IGR-RT data.

    Accepts both the OGC API ``roadlink`` properties (numberoflanes,
    formofway_href, functionalclass, surfacecategory) and the classic CNIG
    shapefile/GeoPackage field names (num_carriles, anchocalzada, ancho_mediana)
    for when the full inventory is loaded from download.
    """
    props = props if isinstance(props, Mapping) else {}
    p: dict[str, Any] = {"__source__": "ign_rt"}

    def first(*names: str) -> Any:
        lowered = {str(k).lower(): v for k, v in props.items()}
        for name in names:
            if name in lowered and lowered[name] not in (None, "", -998, -997):
                return lowered[name]
        return None

    lanes = first("numberoflanes", "num_carriles", "carriles", "n_carriles", "nlcarriles")
    lanes_int = _num(str(lanes)) if lanes is not None else None
    # Only trust IGN lane counts that are at least 2 — the API fills 1 on
    # most links without data (junk that would beat OSM's real 2-lane data).
    if lanes_int is not None and lanes_int >= 2:
        p["lanes"] = int(lanes_int)

    width = _num(str(first("anchocalzada", "ancho_calzada", "width")))
    if width is not None:
        p["width"] = round(width, 2)
        p["widthSrc"] = "ign_rt"
    platform = _num(str(first("anchoplataforma", "ancho_plataforma")))
    if platform is not None:
        p["platformWidth"] = round(platform, 2)
    median_w = _num(str(first("anchomediana", "ancho_mediana")))
    if median_w is not None:
        p["median"] = True
        p["medianWidth"] = round(median_w, 2)

    form_of_way = str(first("formofway", "formofway_href", "formo_fway") or "")
    if form_of_way:
        fow = form_of_way.rsplit("/", 1)[-1].lower()
        p["formOfWay"] = fow
        if fow in {"dualcarriageway", "dualmotorway", "motorway"}:
            p["dual"] = True
        elif fow in {"singlecarriageway", "sliproad"}:
            p["dual"] = False

    functional_class = str(first("functionalclass", "functional_class") or "")
    if functional_class and functional_class.lower() not in {"-998", "-997", "none", "null"}:
        p["functionalClass"] = functional_class.rsplit("/", 1)[-1].lower()

    surface = first("surfacecategory", "surface")
    if surface and str(surface).lower() in {"paved", "unpaved"}:
        p["surface"] = str(surface).lower()

    sentido = first("sentido", "sentidocirculacion", "sentido_circulacion")
    if sentido is not None:
        p["dual"] = str(sentido).lower() in {"dos", "doble", "2", "bidireccional", "both", "dual", "dualcarriageway"}
    return p


def mapillary_profile(props: Mapping) -> dict[str, Any]:
    """Build a profile from Mapillary imagery ML inference properties."""
    props = props if isinstance(props, Mapping) else {}
    p: dict[str, Any] = {"__source__": "mapillary"}

    def first(*names: str) -> Any:
        lowered = {str(k).lower(): v for k, v in props.items()}
        for name in names:
            if name in lowered and lowered[name] not in (None, ""):
                return lowered[name]
        return None

    lanes = _num(str(first("lane_count", "lanes", "n_lanes")))
    if lanes is not None:
        p["lanes"] = int(lanes)
    width = _num(str(first("road_width_m", "width_m", "road_width")))
    if width is not None:
        p["width"] = round(width, 2)
        p["widthSrc"] = "mapillary"
    median_w = _num(str(first("median_width_m", "median_width")))
    if median_w is not None:
        p["median"] = True
        p["medianWidth"] = round(median_w, 2)
    return p


def reconcile(profiles: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    """Merge profiles attribute-by-attribute, highest source priority wins.

    Returns ``(merged, sources)`` where ``sources`` maps each attribute to the
    name of the source that provided its value (provenance for the UI).
    """
    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for attr in _ALL_ATTRS:
        best_val: Any = None
        best_src: str | None = None
        best_rank = -1
        for prof in profiles:
            if not isinstance(prof, Mapping):
                continue
            if attr in prof and prof[attr] is not None:
                src = prof.get("__source__", "osm")
                rank = SOURCE_PRIORITY.get(src, 0)
                if rank > best_rank:
                    best_rank = rank
                    best_val = prof[attr]
                    best_src = src
        if best_val is not None:
            merged[attr] = best_val
            if best_src:
                sources[attr] = best_src
    return merged, sources


def geometry_signature(merged: Mapping) -> tuple:
    """Stable signature of the geometry-relevant attributes for a tramo."""
    def round_val(value: Any) -> Any:
        return round(value, 1) if isinstance(value, float) else value
    return tuple(round_val(merged.get(attr)) for attr in TRAMO_ATTRS)


def catastro_profile(section_width: float | None, source: str = "osm_buildings") -> dict[str, Any]:
    """Profile from building-footprint inference (facade-to-facade).

    This is a *total section* width (calzada + aceras), so it maps to
    ``platformWidth`` and never overrides a direct OSM carriageway ``width``.
    ``source`` records where the footprints came from (osm_buildings/catastro).
    """
    if section_width is None:
        return {}
    return {
        "__source__": source,
        "platformWidth": round(float(section_width), 2),
    }


def overture_profile(props: Mapping) -> dict[str, Any]:
    """Build a profile from an Overture segment's physical properties.

    ``width`` is the edge-to-edge carriageway width in metres (TomTom and
    other authoritative sources), ``class`` the road class, plus surface and
    max speed. Overture class helps when OSM lacks it.
    """
    props = props if isinstance(props, Mapping) else {}
    p: dict[str, Any] = {"__source__": "overture"}
    width = props.get("width")
    if isinstance(width, (int, float)) and 1.0 <= width <= 60.0:
        p["width"] = round(float(width), 2)
        p["widthSrc"] = "overture"
    road_class = props.get("class")
    if isinstance(road_class, str) and road_class not in {"", "unknown"}:
        p["highway"] = road_class
    if props.get("surface"):
        p["surface"] = str(props["surface"])
    maxspeed = props.get("maxspeed")
    if isinstance(maxspeed, (int, float)) and maxspeed > 0:
        p["maxspeed"] = int(maxspeed)
    lanes = props.get("laneCount")
    if isinstance(lanes, int) and lanes > 0:
        p["lanes"] = lanes
    return p


def resolve_way(record: Mapping) -> dict[str, Any]:
    """Resolve the authoritative geometry for one way across all sources.

    Reads the raw OSM tags plus optional enrichment profiles attached to the
    record (``ignProfile`` from IGR-RT, ``sectionWidth`` from building
    footprints) and merges them attribute-by-attribute with per-attr
    provenance.

    Returns ``{"merged": {...}, "sources": {...}}`` — merged geometry without
    ``__source__`` keys, sources = attr → source name.
    """
    tags = record.get("tags") if isinstance(record.get("tags"), Mapping) else {}
    if tags:
        base = osm_profile(tags)
    else:
        # Legacy cached records without raw tags: keep precomputed values
        base = {
            "__source__": "osm",
            "width": record.get("estWidth"),
            "widthSrc": record.get("widthSrc") or "default",
            "lanes": record.get("lanes"),
            "dual": record.get("dual"),
            "median": record.get("median"),
        }
        if base["width"] is None:
            base.pop("width")
        base = {k: v for k, v in base.items() if v is not None or k in ("__source__",)} | {"__source__": "osm"}

    profiles: list[dict[str, Any]] = [base]

    ign = record.get("ignProfile")
    if isinstance(ign, Mapping) and ign:
        profiles.append(ign_rt_profile(ign))

    overture = record.get("overtureProfile")
    if isinstance(overture, Mapping) and overture:
        # A direct OSM width measurement beats Overture's modeled width:
        # drop width from the overture profile so the merge keeps the tag.
        if base.get("widthSrc") == "osm_width":
            overture = {k: v for k, v in overture.items() if k != "width"} | {"widthSrc": None}
        profiles.append(overture_profile(overture))

    section_width = record.get("sectionWidth")
    section_src = record.get("sectionWidthSrc")
    if section_width is None and record.get("widthSrc") == "catastro":
        est = record.get("estWidth")
        section_width = est if isinstance(est, (int, float)) else None
        if section_width is not None:
            section_src = "catastro"
    if isinstance(section_width, (int, float)):
        profiles.append(catastro_profile(section_width, section_src or "osm_buildings"))

    merged, sources = reconcile(profiles)
    return {"merged": merged, "sources": sources}


def assign_tramos(targets: list[dict]) -> dict[str, dict[str, int]]:
    """Return ``target_ref -> {tramoSeq, tramoOf}`` within each street.

    Segments of the same street are ordered by ``source_index`` (OSM edit
    order, an approximation of topology) and a new tramo is opened whenever
    the geometry signature changes.
    """
    by_street: dict[str, list[dict]] = {}
    for target in targets:
        key = target.get("osmName") or target.get("name") or f"__{target.get('target_ref')}"
        by_street.setdefault(key, []).append(target)

    out: dict[str, dict[str, int]] = {}
    for items in by_street.values():
        items.sort(key=lambda t: t.get("source_index", 0))
        seq = 0
        prev_sig: tuple | None = None
        for index, target in enumerate(items):
            sig = geometry_signature(target.get("geom", {}))
            if index == 0 or sig != prev_sig:
                seq += 1
            prev_sig = sig
            out[target["target_ref"]] = {"tramoSeq": seq, "tramoOf": len(items)}
    return out
