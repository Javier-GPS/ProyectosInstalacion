from app.services.building_width import _compute_segment_width, enrich_widths

LAT0 = 41.1162  # road runs along lon at this latitude
D = 0.00015  # ~16.5 m per 100 m? no — 0.00015 deg lat ≈ 16.7 m


def _square(cx, cy, half=0.00005):
    return [
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half],
        [cx - half, cy - half],
    ]


def test_compute_width_facade_to_facade():
    # Road axis along lon at lat LAT0; buildings flank the midpoint exactly.
    buildings = [
        (_square(1.245, LAT0 + 0.0001), (1.245, LAT0 + 0.0001)),
        (_square(1.245, LAT0 - 0.0001), (1.245, LAT0 - 0.0001)),
    ]
    way = [{"lat": LAT0, "lon": 1.2445}, {"lat": LAT0, "lon": 1.2455}]
    width = _compute_segment_width(way, buildings)
    assert width is not None
    assert 5 <= width <= 60


def test_enrich_widths_skips_direct_osm_width():
    buildings = [
        {"geometry": {"type": "Polygon", "coordinates": [[*_square(1.245, LAT0 + 0.0001)]]}},
        {"geometry": {"type": "Polygon", "coordinates": [[*_square(1.245, LAT0 - 0.0001)]]}},
    ]
    ways = [
        {"id": 1, "geom": [{"lat": LAT0, "lon": 1.2445}, {"lat": LAT0, "lon": 1.2455}], "tags": {"highway": "residential"}},
        {"id": 2, "geom": [{"lat": LAT0, "lon": 1.2445}, {"lat": LAT0, "lon": 1.2455}], "tags": {"highway": "residential"}, "width": "9.0", "widthSrc": "osm_width"},
    ]
    enrich_widths(ways, buildings)
    assert ways[0].get("sectionWidth") is not None
    assert ways[0].get("sectionWidthSrc") == "osm_buildings"
    assert ways[1].get("sectionWidth") is None
