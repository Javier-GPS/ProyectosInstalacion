from __future__ import annotations

import json

from pydantic import ValidationError, TypeAdapter

from app.schemas.models import CalculationConfig, TramoBulkImportItem, TramoBulkImportRequest


def _valid_config() -> dict:
    return {
        "road_width": 7.0,
        "height": 9.0,
        "spacing": 30.0,
        "power": 80.0,
        "optic_family": "F151",
        "arrangement": "Lineal",
        "lighting_class": "M3",
        "mf": 0.85,
        "pavement": "R3",
        "cct": 4000,
    }


def test_bulk_import_accepts_1200_items():
    """Regression: the endpoint must accept at least 1200 rows (user file)."""
    items = [
        TramoBulkImportItem(name=f"Tramo {i}", config=_valid_config())
        for i in range(1200)
    ]
    request = TramoBulkImportRequest(items=items)
    assert len(request.items) == 1200


def test_bulk_import_rejects_over_5000_items():
    """The 5000 safety limit must still be enforced."""
    items = [
        TramoBulkImportItem(name=f"Tramo {i}", config=_valid_config())
        for i in range(5001)
    ]
    try:
        TramoBulkImportRequest(items=items)
        assert False, "Expected ValidationError"
    except ValidationError as exc:
        errors = exc.errors()
        assert any("max_length" in str(e) for e in errors), str(errors)


def test_bulk_import_rejects_empty():
    try:
        TramoBulkImportRequest(items=[])
        assert False, "Expected ValidationError"
    except ValidationError:
        pass


def test_bulk_import_item_config_validates():
    """Each item's config must be a valid CalculationConfig."""
    item = TramoBulkImportItem(name="Test", config={"road_width": -1, "height": 9, "spacing": 30, "power": 80, "optic_family": "F151"})
    try:
        CalculationConfig.model_validate(item.config)
        assert False, "Expected ValidationError"
    except ValidationError:
        pass


def test_bulk_import_item_config_defaults():
    """Missing non-required fields should get defaults."""
    config = _valid_config()
    validated = CalculationConfig.model_validate(config)
    assert validated.mf == 0.85
    assert validated.sidewalk_left == 0.0
    assert validated.cct == 4000


