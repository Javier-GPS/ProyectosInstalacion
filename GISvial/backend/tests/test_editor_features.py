"""Tests para editor_features: alturas y bases de edificios OSM."""
from app.services.editor_features import _base, _height, _kind, _num


def test_num_parsing():
    assert _num("12.5") == 12.5
    assert _num("12,5") == 12.5
    assert _num("abc") is None
    assert _num(None) is None
    assert _num("nivel 4") == 4


def test_height_precedence():
    tags = {"height": "21.5", "building:height": "18", "building:levels": "6"}
    assert _height(tags) == 21.5
    assert _height({"building:height": "18"}) == 18
    assert _height({"building:levels": "6"}) == 6 * 3.2
    assert _height({}) is None


def test_base_from_min_level():
    assert _base({"building:min_level": "2"}) == 2 * 3.2
    assert _base({"building:min_level": "abc"}) is None
    assert _base({}) is None


def test_kind_building_part():
    assert _kind({"building:part": "yes"}) == "building"
    assert _kind({"building": "yes"}) == "building"
    assert _kind({"building:name": "Casa"}) == "building"
    assert _kind({"landuse": "grass"}) == "green"
    assert _kind({"natural": "water"}) == "water"
    assert _kind({"highway": "residential"}) is None