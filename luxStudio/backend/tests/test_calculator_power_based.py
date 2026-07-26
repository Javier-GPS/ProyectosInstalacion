from types import SimpleNamespace

import pytest

from app.schemas.models import CalculationConfig, CalculationResult, FotometriaInfo
from app.services import calculator
from app.services.led_calculator import LedCatalogEntry, compute_led_point
from app.services.electrical import total_system_power
from app.services.pcb_selector import _led_efficacy_before_thermal


def test_total_system_power_includes_driver_losses():
    assert total_system_power(37.878, 0.9) == pytest.approx(42.0867, abs=0.001)


def test_efficiency_chain_uses_the_actual_operating_point_once():
    point = compute_led_point(
        LedCatalogEntry(family="HE_PLUS_6V", flux_ref_lm=746),
        0.548792,
        t_amb_c=25.0,
        ts_coef_c_per_w=0.532,
        n_leds_total=12,
    )

    nominal_led_efficacy = _led_efficacy_before_thermal(point)
    system_efficacy = nominal_led_efficacy * point.kt * 0.94 * 0.95 * 0.9
    optical_flux = point.flux_lm * 12 * 0.94 * 0.95
    system_power = total_system_power(point.power_w * 12, 0.9)

    assert nominal_led_efficacy == pytest.approx(207.57, abs=0.05)
    assert system_efficacy == pytest.approx(optical_flux / system_power, abs=0.01)
    assert system_efficacy == pytest.approx(158.55, abs=0.1)


def test_calculate_config_replaces_stale_power_from_target_flux(monkeypatch):
    """A saved/LDT-derived wattage must not override the electrical point."""
    config = CalculationConfig(
        road_width=7.0,
        lanes=2,
        arrangement="Lineal",
        height=10.0,
        spacing=40.0,
        arm_length=2.0,
        pole_offset=1.0,
        optic_family="F151",
        power=53.95,
        target_flux=9038.3,
        gama="CLAP S",
        difusor="VIDRIO ULTRAWHITE TRANSP PLANO",
        lente="F151",
        led_type="LUXEON HOP 5050",
    )
    seen = {}

    monkeypatch.setattr(calculator, "get_eficiencia", lambda *_: (1.0, 1.0))
    monkeypatch.setattr(calculator, "require_ldt_for_config", lambda cfg: ("ldt-1", {}))
    monkeypatch.setattr(calculator, "clamp_power_to_pmax", lambda _db, cfg: cfg)
    monkeypatch.setattr(
        calculator,
        "select_pcb_for_config",
        lambda _db, cfg: SimpleNamespace(
            p_total=37.878,
            driver_eficiencia=0.9,
            flux=cfg.target_flux,
        ),
    )

    def fake_run_calculation(cfg, *_args, **_kwargs):
        seen["config"] = cfg
        return CalculationResult(
            config=cfg,
            compliant=True,
            mode="ME",
            luminaire=FotometriaInfo(
                id="ldt-1",
                filename="mock.ldt",
                luminaire_name="mock",
                optic_family="F151",
                power=cfg.power,
                flux=0,
                efficiency=0,
                LORL=100,
                isym=0,
            ),
            criteria=[],
        )

    monkeypatch.setattr(calculator, "run_calculation", fake_run_calculation)

    result = calculator.calculate_config(object(), config)

    assert seen["config"].power == 42.09
    assert seen["config"].target_flux == 9038.3
    assert result.config.target_flux == 9038.3


def test_catalog_ldt_flux_scaling_applies_optical_efficiency():
    """The reference LDT is a bare LED-module photometry (lens/diffuser
    losses not baked in), so the 4-tuple path must scale the flux by the
    selected lens AND diffuser efficiencies.  Dropping these factors
    over-estimates the luminance and under-reports the power required
    (DIALux needs ~29% more W for the same Lavg)."""

    class Photometry:
        power = 31.0
        flux = 3993.2

    config = CalculationConfig(
        road_width=7.0,
        lanes=2,
        arrangement="Lineal",
        height=10.0,
        spacing=40.0,
        arm_length=2.0,
        optic_family="F151",
        power=53.95,
        gama="CLAP S",
        difusor="VIDRIO ULTRAWHITE TRANSP PLANO",
        lente="F151",
        led_type="LUXEON HOP 5050",
        cct=4000,
        cri=70,
    )
    info = {"cri": 70, "cct": 4000, "power": 31.0, "flux": 3993.2}

    out = calculator._target_luminaire_info(
        config,
        Photometry(),
        info,
        lente_eficiencia=0.94,
        difusor_eficiencia=0.95,
    )

    expected = 3993.2 * (53.95 / 31.0) * 0.94 * 0.95
    assert abs(out["flux"] - expected) < 1e-6
