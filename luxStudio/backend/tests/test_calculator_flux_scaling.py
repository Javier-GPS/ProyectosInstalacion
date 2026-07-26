from __future__ import annotations

from app.schemas.models import CalculationConfig, CriterionResult, ElementResult
from app.salvi_lighting.calc import _me_compliance
from app.services.calculator import _build_criteria, _target_luminaire_info


class DummyPhotometry:
    power = 17.5
    flux = 2158.6
    eff = flux / power
    d = {"lamp_sets": [{"color": "4000"}]}


def _config(**overrides) -> CalculationConfig:
    base = dict(
        road_width=7.0,
        sidewalk_left=1.5,
        sidewalk_right=1.5,
        lanes=2,
        arrangement="Lineal",
        height=9.0,
        spacing=30.0,
        arm_length=1.5,
        pole_offset=0.0,
        pole_side="left",
        tilt=5.0,
        optic_family="F2M2",
        power=120.0,
        ldt_id="catalog-ldt",
        manufacturer="Salvi",
        model_family="CLAP S",
        gama="CLAP S",
        difusor="VDR SPUW",
        lente="F2M2",
        led_type="LUXEON HOP 5050",
        lighting_class="M3",
        mf=0.85,
        pavement="R3",
        cct=4000,
        cri=70,
        language="es",
    )
    base.update(overrides)
    return CalculationConfig(**base)


def test_catalog_selection_scales_reference_flux_linearly_to_selected_power(monkeypatch):
    monkeypatch.setattr("app.services.calculator.get_all_ldts", lambda: [])
    info = _target_luminaire_info(
        _config(),
        DummyPhotometry(),
        {
            "id": "catalog-ldt",
            "filename": "241002-Clap-S-7-LEds-F2M2.txt",
            "luminaire_name": "CLAP S 7 LEDs F2M2",
            "manufacturer": "Salvi",
            "model_family": "CLAP S",
            "optic_family": "F2M2",
            "power": 17.5,
            "flux": 2158.6,
            "efficiency": 123.3,
            "cri": 70,
        },
    )

    assert info["power"] == 120.0
    assert info["flux"] == 2158.6 * (120.0 / 17.5)
    assert info["efficiency"] == round(info["flux"] / 120.0, 1)


def test_target_flux_efficacy_does_not_apply_driver_loss_twice(monkeypatch):
    monkeypatch.setattr("app.services.calculator.get_all_ldts", lambda: [])
    info = _target_luminaire_info(
        _config(target_flux=6700.0, power=43.29, driver_eficiencia=0.9),
        DummyPhotometry(),
        {
            "power": 100.0,
            "flux": 15478.0,
            "efficiency": 154.78,
            "cct": 4000,
            "cri": 70,
        },
    )

    assert info["efficiency"] == round(6700.0 / 43.29, 1)


def test_catalog_selection_scales_flux_for_target_cct_even_when_cri_matches(monkeypatch):
    monkeypatch.setattr("app.services.calculator.get_all_ldts", lambda: [])
    info = _target_luminaire_info(
        _config(cct=3000, cri=70),
        DummyPhotometry(),
        {
            "id": "catalog-ldt",
            "filename": "241002-Clap-S-7-LEds-F2M2.txt",
            "luminaire_name": "CLAP S 7 LEDs F2M2",
            "manufacturer": "Salvi",
            "model_family": "CLAP S",
            "optic_family": "F2M2",
            "power": 17.5,
            "flux": 2158.6,
            "efficiency": 123.3,
            "cct": 4000,
            "cri": 70,
        },
    )

    expected = 2158.6 * (120.0 / 17.5) * (667.0 / 693.0)
    assert info["flux"] == expected
    assert info["efficiency"] == round(expected / 120.0, 1)


def test_legacy_selection_without_4tuple_keeps_existing_flux_estimation(monkeypatch):
    monkeypatch.setattr("app.services.calculator.get_all_ldts", lambda: [])
    info = _target_luminaire_info(
        _config(gama=None, difusor=None, lente=None, led_type=None),
        DummyPhotometry(),
        {
            "id": "legacy-ldt",
            "filename": "legacy.ldt",
            "luminaire_name": "Legacy",
            "manufacturer": "Salvi",
            "model_family": "CLAP S",
            "optic_family": "F2M2",
            "power": 17.5,
            "flux": 2158.6,
            "efficiency": 123.3,
            "cri": 70,
        },
    )

    assert info["power"] == 120.0
    assert info["flux"] == 120.0 * 123.3


def test_visualization_only_fields_are_preserved_by_calculation_config():
    """Visual-only fields must be preserved in the model so they round-trip
    through API save/load without being dropped."""
    baseline = _config()
    assert baseline.median_width == 0.0
    assert baseline.illuminance_scale_mode == "auto"
    assert baseline.illuminance_scale_min == 0.0
    assert baseline.illuminance_scale_max == 50.0
    assert baseline.photometric_display_unit == "lux"
    assert baseline.generate_buildings is False
    assert baseline.building_height == 12.0
    assert baseline.buildings_as_obstacles is False

    with_visual_settings = _config(
        median_width=1.2,
        illuminance_scale_mode="manual",
        illuminance_scale_min=2.0,
        illuminance_scale_max=25.0,
        photometric_display_unit="candela",
        generate_buildings=True,
        building_height=18.0,
        buildings_as_obstacles=False,
    )
    dumped = with_visual_settings.model_dump()
    assert dumped["median_width"] == 1.2
    assert dumped["illuminance_scale_mode"] == "manual"
    assert dumped["illuminance_scale_min"] == 2.0
    assert dumped["illuminance_scale_max"] == 25.0
    assert dumped["photometric_display_unit"] == "candela"
    assert dumped["generate_buildings"] is True
    assert dumped["building_height"] == 18.0
    assert dumped["buildings_as_obstacles"] is False


def test_build_criteria_treats_missing_metric_values_as_zero():
    criteria = _build_criteria(
        {
            "mode": "ME",
            "req": {"L": None, "Uo": 0.4},
            "Lavg": None,
            "Uo": None,
        }
    )

    assert criteria[0].name == "Lavg (cd/m²)"
    assert criteria[0].value == 0
    assert criteria[0].required == 0
    assert criteria[1].name == "Uo"
    assert criteria[1].value == 0
    assert criteria[1].required == 0.4


def test_metric_values_are_serialized_to_two_decimals():
    criterion = CriterionResult(name="Uo", value=0.4237, required=0.4, passed=True)
    element = ElementResult(index=0, type="carriageway", Lavg=1.2349, Uo=0.4237, TI=9.876)

    assert criterion.model_dump(mode="json")["value"] == 0.42
    assert element.model_dump(mode="json")["Lavg"] == 1.23
    assert element.model_dump(mode="json")["Uo"] == 0.42
    assert element.model_dump(mode="json")["TI"] == 9.88


def test_me_compliance_uses_the_normative_presented_precision():
    requirements = {"L": 1.0, "Uo": 0.4, "Ul": 0.6, "TI": 15, "SR": 0.5}
    values = {"Lavg": 1.004, "Uo": 0.396, "Ul": 0.596, "TI": 15.49, "SR": 0.496}

    assert all(_me_compliance(values, requirements).values())

    values["Ul"] = 0.594
    assert _me_compliance(values, requirements)["ok_Ul"] is False
