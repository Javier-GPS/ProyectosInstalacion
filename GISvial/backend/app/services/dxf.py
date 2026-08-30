"""DXF export service."""
import math
from typing import Any

# DXF colour/lw lookup tables
_DXF_CLR = {
    'motorway': 1, 'motorway_link': 1, 'trunk': 14, 'trunk_link': 14,
    'primary': 30, 'primary_link': 30, 'secondary': 2, 'secondary_link': 2,
    'tertiary': 3, 'tertiary_link': 3, 'residential': 4, 'unclassified': 9,
    'living_street': 8, 'pedestrian': 6, 'service': 8, 'tunnel': 5, 'trees': 82,
}
_DXF_LW = {
    'motorway': 50, 'trunk': 40, 'primary': 35, 'secondary': 30,
    'tertiary': 25, 'residential': 18, 'tunnel': 30,
}


def _dxf_ldef(name: str, color: int, lw: int = 18, lt: str = 'CONTINUOUS') -> list[str]:
    return ["0", "LAYER", "2", name, "70", "0", "62", str(color), "6", lt, "370", str(lw)]


def _object_ring(obj: dict) -> list[tuple[float, float]]:
    """Footprint corners (lon, lat) of a rotated rectangle, matching the frontend editor."""
    lng, lat = obj.get('lng'), obj.get('lat')
    if lng is None or lat is None:
        return []
    w = float(obj.get('width') or 1)
    l = float(obj.get('length') or 1)
    deg = float(obj.get('rotation') or 0)
    lat_rad = math.radians(float(lat))
    d_lat = 1 / 111320
    d_lng = 1 / (111320 * math.cos(lat_rad) if math.cos(lat_rad) else 111320 * 0.001)
    hw, hl = w / 2, l / 2
    rad = math.radians(deg)
    cos, sin = math.cos(rad), math.sin(rad)
    corners = [(-hw, -hl), (hw, -hl), (hw, hl), (-hw, hl)]
    ring = []
    for x, y in corners:
        rx = x * cos - y * sin
        ry = x * sin + y * cos
        ring.append((lng + rx * d_lng, lat + ry * d_lat))
    return ring


def _perp_off(lon1: float, lat1: float, lon2: float, lat2: float, half_m: float):
    mid = math.radians((lat1 + lat2) / 2)
    cos_mid = math.cos(mid) or 0.001
    dlat_m = (lat2 - lat1) * 111320
    dlon_m = (lon2 - lon1) * 111320 * cos_mid
    dist = math.sqrt(dlat_m ** 2 + dlon_m ** 2)
    if dist < 0.01:
        return 0.0, 0.0
    return (-dlon_m / dist * half_m / 111320,
            dlat_m / dist * half_m / (111320 * cos_mid))


def build_dxf(
    ways: list[dict],
    luminaires: list[Any],
    inventory: list[Any],
    tree_data: list[dict],
    boundary: list,
    objects: list[dict] | None = None,
) -> bytes:
    """Build a DXF file from GIS data. Returns raw bytes."""
    objects = objects or []
    rtypes = sorted({w.get('type', 'road') for w in ways})

    # Build layer list
    layers = [("0", 7, 18, "CONTINUOUS")]
    for rt in rtypes:
        layers.append((f"STREETS_{rt.upper()}", _DXF_CLR.get(rt, 7), _DXF_LW.get(rt, 18), "CONTINUOUS"))
        layers.append((f"WIDTH_{rt.upper()}", _DXF_CLR.get(rt, 7), 9, "DASHED"))

    seen_names = set()
    for w in ways:
        nm = w.get('name')
        if nm and nm not in seen_names:
            seen_names.add(nm)
            layers.append(("STREET_LABELS", 7, 13, "CONTINUOUS"))
            break

    for rt in sorted({getattr(r, 'road_type', None) or 'GEN' for r in luminaires}):
        layers.append((f"LUM_{rt.upper()}", 50, 18, "CONTINUOUS"))
    if inventory:
        layers.append(("INVENTORY", 140, 18, "CONTINUOUS"))
    if boundary:
        layers.append(("ZONE_BOUNDARY", 7, 25, "CONTINUOUS"))
    if tree_data:
        layers.append(("TREES", 82, 18, "CONTINUOUS"))
    if objects:
        layers.append(("OBJECTS", 30, 18, "CONTINUOUS"))

    # Build DXF
    L: list[str] = []
    L += ["0", "SECTION", "2", "HEADER", "0", "ENDSEC"]
    L += ["0", "SECTION", "2", "TABLES"]
    L += ["0", "TABLE", "2", "LTYPE", "70", "2"]
    L += ["0", "LTYPE", "2", "CONTINUOUS", "70", "0", "3", "Solid", "72", "65", "73", "0", "40", "0.0"]
    L += ["0", "LTYPE", "2", "DASHED", "70", "0", "3", "__ __", "72", "65", "73", "2", "40", "0.75",
          "49", "0.5", "74", "0", "49", "-0.25", "74", "0"]
    L += ["0", "ENDTAB"]
    L += ["0", "TABLE", "2", "LAYER", "70", str(len(layers))]
    for nm, clr, lw, lt in layers:
        L += _dxf_ldef(nm, clr, lw, lt)
    L += ["0", "ENDTAB", "0", "ENDSEC"]
    L += ["0", "SECTION", "2", "ENTITIES"]

    # Centerlines
    for w in ways:
        geom = w.get("geom", [])
        if len(geom) < 2:
            continue
        rt = w.get('type', 'road')
        lnm = f"STREETS_{rt.upper()}"
        clr = _DXF_CLR.get(rt, 7)
        for i in range(len(geom) - 1):
            p0, p1 = geom[i], geom[i + 1]
            L += ["0", "LINE", "8", lnm, "62", str(clr),
                  "10", f"{p0['lon']:.6f}", "20", f"{p0['lat']:.6f}", "30", "0.0",
                  "11", f"{p1['lon']:.6f}", "21", f"{p1['lat']:.6f}", "31", "0.0"]

    # Width polygons
    for w in ways:
        geom = w.get("geom", [])
        if len(geom) < 2:
            continue
        rt = w.get('type', 'road')
        lnm = f"WIDTH_{rt.upper()}"
        clr = _DXF_CLR.get(rt, 7)
        half = (w.get('estWidth') or 6.0) / 2.0
        for i in range(len(geom) - 1):
            p0, p1 = geom[i], geom[i + 1]
            dlat, dlon = _perp_off(p0['lon'], p0['lat'], p1['lon'], p1['lat'], half)
            if not dlat and not dlon:
                continue
            for s in (1, -1):
                L += ["0", "LINE", "8", lnm, "62", str(clr), "370", "9",
                      "10", f"{p0['lon'] + s * dlon:.6f}", "20", f"{p0['lat'] + s * dlat:.6f}", "30", "0.0",
                      "11", f"{p1['lon'] + s * dlon:.6f}", "21", f"{p1['lat'] + s * dlat:.6f}", "31", "0.0"]

    # Street labels
    seen = set()
    for w in ways:
        nm = w.get('name')
        if not nm or nm in seen:
            continue
        seen.add(nm)
        geom = w.get("geom", [])
        if not geom:
            continue
        mid = geom[len(geom) // 2]
        L += ["0", "TEXT", "8", "STREET_LABELS", "62", "7",
              "10", f"{mid['lon']:.6f}", "20", f"{mid['lat']:.6f}", "30", "0.0",
              "40", "0.000045", "1", nm[:63]]

    # Luminaires
    for r in luminaires:
        rt = getattr(r, 'road_type', None) or 'GEN'
        L += ["0", "POINT", "8", f"LUM_{rt.upper()}", "62", "50",
              "10", f"{r.lon:.6f}", "20", f"{r.lat:.6f}", "30", "0.0"]

    # Inventory
    for r in inventory:
        L += ["0", "POINT", "8", "INVENTORY", "62", "140",
              "10", f"{r.lon:.6f}", "20", f"{r.lat:.6f}", "30", "0.0"]

    # Boundary
    n = len(boundary)
    for i in range(n):
        p0 = boundary[i]
        p1 = boundary[(i + 1) % n]
        lat0, lon0 = (p0[0], p0[1]) if isinstance(p0, list) else (p0.get('lat'), p0.get('lon'))
        lat1, lon1 = (p1[0], p1[1]) if isinstance(p1, list) else (p1.get('lat'), p1.get('lon'))
        L += ["0", "LINE", "8", "ZONE_BOUNDARY", "62", "7", "370", "25",
              "10", f"{lon0:.6f}", "20", f"{lat0:.6f}", "30", "0.0",
              "11", f"{lon1:.6f}", "21", f"{lat1:.6f}", "31", "0.0"]

    # Trees
    for t in tree_data:
        L += ["0", "POINT", "8", "TREES", "62", "82",
              "10", f"{t.get('lon', 0):.6f}", "20", f"{t.get('lat', 0):.6f}", "30", "0.0"]

    # Editor objects: rotated footprint + center point + label
    for obj in objects:
        ring = _object_ring(obj)
        if len(ring) < 3:
            continue
        for i in range(len(ring)):
            p0 = ring[i]
            p1 = ring[(i + 1) % len(ring)]
            L += ["0", "LINE", "8", "OBJECTS", "62", "30", "370", "18",
                  "10", f"{p0[0]:.6f}", "20", f"{p0[1]:.6f}", "30", "0.0",
                  "11", f"{p1[0]:.6f}", "21", f"{p1[1]:.6f}", "31", "0.0"]
        L += ["0", "POINT", "8", "OBJECTS", "62", "30",
              "10", f"{obj.get('lng', 0):.6f}", "20", f"{obj.get('lat', 0):.6f}", "30", "0.0"]
        lbl = obj.get('label') or obj.get('type')
        if lbl:
            L += ["0", "TEXT", "8", "OBJECTS", "62", "30",
                  "10", f"{obj.get('lng', 0):.6f}", "20", f"{obj.get('lat', 0):.6f}", "30", "0.0",
                  "40", "0.000045", "1", str(lbl)[:63]]

    L += ["0", "ENDSEC", "0", "EOF"]
    return "\n".join(L).encode("utf-8")
