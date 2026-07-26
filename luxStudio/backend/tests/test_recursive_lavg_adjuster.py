"""Tests for the recursive LAVG-only power adjuster.

Covers the "ajustar potencia" flow that:
  1. Estimates a new target flux from the LAVG ratio,
  2. Finds the SMALLEST PCB in the gama that can deliver that flux,
  3. Recalculates and checks LAVG,
  4. Recurses with +10 % flux until LAVG passes (or iterations run out).

The recursive adjuster optimizes LAVG while still respecting the user's
``lm_w_min`` PCB filter.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from conftest import create_test_engine

from app.database import Base
from app.models import (
    Difusor,
    Gama,
    GamaPCB,
    LED,
    Lente,
    LedType,
    LuminaireLED,
    PCB,
    TSCoefficient,
)
from app.schemas.models import (
    CalculationConfig,
    CalculationResult,
    CriterionResult,
    FluxDetail,
    FotometriaInfo,
)
from app.services.optimizer import _optimize_flux_for_config
from app.services.pcb_selector import select_pcb_for_config, select_pcb_for_flux


# ---------------------------------------------------------------------------
# Fixture: isolated DB schema with a gama that has 2 PCBs of different sizes
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    """Fresh PostgreSQL schema seeded with a gama that has two PCBs.

    PCB_A: 7 LEDs, 0.7 A I_max (smaller, less efficient at I_max)
    PCB_B: 18 LEDs, 1.2 A I_max (bigger, more flux overall)

    A HE_PLUS_6V LED is mapped to the 4-tuple so the V2 model has
    something to evaluate.
    """
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTesting()

    gama = Gama(name="ATENEA")
    dif = Difusor(name="PMMA LC", eficiencia=0.92)
    lente = Lente(name="F151", eficiencia=0.93)
    led_type = LedType(name="LUXEON HOP 5050")
    led = LED(
        led_ref="L150-4070500600HH0",
        led_desc_corta="Luxeon 5050 HE Plus 6V",
        family="HE_PLUS_6V",
        flux_ref_lm=746,
        cct=4000,
        cri=70,
        pmax_ajustada=200.0,
        i_max_led=1.2,
    )
    pcb_a = PCB(
        pcb_ref="PCB-A-SMALL",
        pcb_no_led=7,
        pcb_v_nominal=6.0,
        pcb_imax_led=0.7,
        pcb_descripcion="7-LED small PCB",
    )
    pcb_b = PCB(
        pcb_ref="PCB-B-BIG",
        pcb_no_led=18,
        pcb_v_nominal=6.0,
        pcb_imax_led=1.2,
        pcb_descripcion="18-LED bigger PCB",
    )
    session.add_all([gama, dif, lente, led_type, led, pcb_a, pcb_b])
    session.flush()
    session.add_all([
        GamaPCB(gama_id=gama.id, pcb_id=pcb_a.id),
        GamaPCB(gama_id=gama.id, pcb_id=pcb_b.id),
        LuminaireLED(
            gama_id=gama.id,
            difusor_id=dif.id,
            lente_id=lente.id,
            led_type_id=led_type.id,
            led_id=led.id,
            pcb_id=pcb_a.id,
            n_pcbs=1,
            n_leds_per_pcb=7,
        ),
        TSCoefficient(
            gama_id=gama.id,
            difusor_id=dif.id,
            coef_led_c_per_w=0.3,
        ),
    ])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# ignore_lm_w_min
# ---------------------------------------------------------------------------


def test_select_pcb_returns_none_when_lm_w_min_filters_everything(db):
    """Sanity check: a high lm_w_min that no PCB can meet yields None.

    The user's bug was: ``select_pcb_for_flux`` returned None for a
    valid 4-tuple because ``lm_w_min`` excluded every PCB.  The
    recursive adjuster needs the bypass to work, but first we want
    to confirm the filter is still active by default.
    """
    # lm_w_min far above what a small 7-LED PCB can deliver at I_max
    out = select_pcb_for_flux(
        db, "ATENEA", "PMMA LC", "F151", "LUXEON HOP 5050",
        target_flux=2000.0, lm_w_min=10000.0,
    )
    assert out is None


def test_select_pcb_with_ignore_lm_w_min_finds_smallest_pcb(db):
    """With ``ignore_lm_w_min=True``, the lm_w filter is bypassed.

    Even with a wildly high lm_w_min that no PCB meets, the function
    still returns the smallest PCB that can deliver the target flux.
    This is the behaviour the recursive LAVG adjuster relies on.
    """
    out = select_pcb_for_flux(
        db, "ATENEA", "PMMA LC", "F151", "LUXEON HOP 5050",
        target_flux=2000.0, lm_w_min=10000.0,
        ignore_lm_w_min=True,
    )
    assert out is not None
    # Among the two PCBs in the gama, the smaller one (7 LEDs) is
    # selected because it is enough to reach the target flux.
    assert out.pcb_ref == "PCB-A-SMALL"
    assert out.total_n_leds == 7


def test_select_pcb_ignore_lm_w_min_picks_bigger_pcb_when_target_too_high(db):
    """When the target flux exceeds the small PCB, ignore_lm_w_min
    still picks the next size up — keeping the "smallest that fits"
    rule intact.
    """
    # A target well above the 7-LED PCB's I_max flux
    out = select_pcb_for_flux(
        db, "ATENEA", "PMMA LC", "F151", "LUXEON HOP 5050",
        target_flux=9000.0, lm_w_min=10000.0,
        ignore_lm_w_min=True,
    )
    assert out is not None
    assert out.pcb_ref == "PCB-B-BIG"
    assert out.total_n_leds == 18


def test_select_pcb_for_flux_can_dim_below_same_drive_current(db):
    """Low-flow bilateral cases must not saturate at same-drive current."""
    out = select_pcb_for_flux(
        db, "ATENEA", "PMMA LC", "F151", "LUXEON HOP 5050",
        target_flux=1200.0, lm_w_min=None,
    )

    assert out is not None
    assert out.i_op_ma < 360.0
    assert 1150.0 <= out.flux <= 1250.0


def test_select_pcb_returns_none_when_no_pcb_can_deliver_flux(db):
    """If the target flux is above what every PCB in the gama can
    deliver, both the filtered and the bypass paths return None — no
    PCB exists that meets the request.  The recursive adjuster
    handles this by increasing the flux only when a PCB IS available
    and otherwise terminates gracefully.
    """
    out = select_pcb_for_flux(
        db, "ATENEA", "PMMA LC", "F151", "LUXEON HOP 5050",
        target_flux=10_000_000.0, lm_w_min=None, ignore_lm_w_min=True,
    )
    assert out is None


def test_select_pcb_for_config_filters_lm_w_after_actual_current(db, monkeypatch):
    """lm/w must be checked at the calculated Iop, not at PCB Imax.

    Regression for the UI case: a PCB can be below the lm/W threshold
    at Imax but above it at the lower current required by target_flux.
    """
    optical_eff = 0.92 * 0.93
    driver_eff = 0.9

    def fake_led_point(_led, current_a, **_kwargs):
        flux_lm = current_a * 1400.0
        system_eff = 140.0 if current_a >= 0.69 else 150.0
        power_w = flux_lm * optical_eff * driver_eff / system_eff
        return type("Point", (), {
            "flux_lm": flux_lm,
            "power_w": power_w,
            "vf_v": 6.0,
            "efficacy_lm_w": flux_lm / power_w,
            "kt": 1.0,
            "tj_c": 55.0,
        })()

    monkeypatch.setattr("app.services.pcb_selector.led_point", fake_led_point)
    config = _base_config(target_flux=3000.0, lm_w_min=145.0, driver_eficiencia=driver_eff)

    out = select_pcb_for_config(db, config)

    assert out is not None
    assert out.pcb_ref == "PCB-A-SMALL"
    assert out.lm_w_ok is True
    assert out.efficiency * out.driver_eficiencia >= 145.0


def test_select_pcb_for_config_solves_iop_for_target_flux(db, monkeypatch):
    """Target flux must use the V2 curve, not a linear Imax ratio."""
    optical_eff = 0.92 * 0.93

    def fake_led_point(_led, current_a, **_kwargs):
        flux_lm = 2000.0 * (current_a ** 0.8)
        return type("Point", (), {
            "flux_lm": flux_lm,
            "power_w": max(current_a * 6.0, 0.001),
            "vf_v": 6.0,
            "efficacy_lm_w": flux_lm / max(current_a * 6.0, 0.001),
            "kt": 1.0,
            "tj_c": 55.0,
        })()

    monkeypatch.setattr("app.services.pcb_selector.led_point", fake_led_point)
    config = _base_config(target_flux=8000.0, driver_eficiencia=0.9)

    out = select_pcb_for_config(db, config)

    assert out is not None
    assert abs(out.flux - 8000.0) <= 1.0


def test_flux_detail_efficiency_chain_matches_electrical_power(db):
    config = _base_config(
        target_flux=3000.0,
        driver_eficiencia=0.9,
        power=0.0,
    )

    out = select_pcb_for_config(db, config)

    assert out is not None
    optical_led_efficiency = (
        out.led_efficacy
        * out.thermal_derating
        * (out.lente_eficiencia or 1.0)
        * (out.difusor_eficiencia or 1.0)
    )
    assert out.efficiency == pytest.approx(optical_led_efficiency, abs=0.2)

    system_power = out.p_total / out.driver_eficiencia
    system_efficiency = out.efficiency * out.driver_eficiencia
    assert out.flux / system_power == pytest.approx(system_efficiency, abs=0.2)


# ---------------------------------------------------------------------------
# _optimize_flux_for_config — convergence with a mocked calc engine
# ---------------------------------------------------------------------------


def _base_config(**overrides) -> CalculationConfig:
    base = dict(
        road_width=7.0,
        sidewalk_left=0.0,
        sidewalk_right=0.0,
        lanes=2,
        arrangement="Lineal",
        height=9.0,
        spacing=30.0,
        arm_length=1.5,
        pole_offset=0.0,
        pole_side="left",
        tilt=5.0,
        optic_family="F151",
        power=80.0,
        ldt_id="ldt-mock",
        manufacturer="Salvi",
        model_family="ATENEA",
        gama="ATENEA",
        difusor="PMMA LC",
        lente="F151",
        led_type="LUXEON HOP 5050",
        lighting_class="M3",
        mf=0.85,
        pavement="R3",
        cct=4000,
        cri=70,
        language="es",
        target_flux=10_000.0,
    )
    base.update(overrides)
    return CalculationConfig(**base)


def _mock_pcb_for_flux(monkeypatch):
    """Replace ``select_pcb_for_flux`` with a deterministic stub.

    Returns a FluxDetail whose ``p_total`` scales with the requested
    flux so we can reason about the loop deterministically.  The
    relationship is intentionally non-linear (sqrt) so the linear
    estimate alone cannot nail the target — the binary search has
    to do real work.
    """
    def _stub(db, gama, dif, lnt, lt, target_flux, **kwargs):
        assert kwargs.get("ignore_lm_w_min") is False
        flux = float(target_flux)
        # p_total = 0.05 W/lm * flux^0.8 (mildly sub-linear)
        p_total = round(0.05 * (flux ** 0.8), 2)
        return FluxDetail(
            gama=gama, difusor=dif, lente=lnt, led_type=lt,
            pcb_ref="MOCK-PCB", pcb_descripcion="mock",
            pcb_v_nominal=24.0, pcb_imax_led=1.0, pcb_no_led=18,
            n_pcbs=1, n_leds_per_pcb=18, total_n_leds=18,
            led_ref="MOCK-LED",
            flux=flux, efficiency=round(flux / p_total, 1) if p_total else 0,
            led_efficacy=180.0, lente_eficiencia=0.93, difusor_eficiencia=0.92,
            thermal_derating=1.0, v_f=24.0,
            p_led=round(p_total / 18, 3), p_total=p_total,
            i_op_ma=700.0, user_i_op_ma=None, user_lm_w_min=None,
            i_op_ok=True, lm_w_ok=True,
            driver_eficiencia=kwargs.get("driver_eficiencia") or 1.0,
            available_pcbs=[],
        )

    monkeypatch.setattr("app.services.optimizer.select_pcb_for_flux", _stub)


def _mock_run_calculation(monkeypatch, lavg_fn):
    """Replace ``run_calculation`` with a function that returns a result
    whose ``Lavg`` is the value of ``lavg_fn(flux)`` and whose
    ``config.target_flux`` / ``config.power`` mirror the inputs.

    The relationship can be whatever we want; the test sets it to
    ``lavg_fn = lambda flux: flux / 5000`` (a linear 5 klm → 1 cd/m2)
    so the math is easy to reason about.
    """
    def _stub(config, ldt_id, **kwargs):
        flux = float(config.target_flux or 0)
        result_lavg = lavg_fn(flux)
        return CalculationResult(
            config=config,
            compliant=True,
            mode="ME",
            luminaire=FotometriaInfo(
                id=ldt_id, filename="mock.ldt", luminaire_name="mock",
                manufacturer="Salvi", model_family="ATENEA", cct=4000, cri=70,
                optic_family="F151", power=config.power, flux=flux,
                efficiency=100.0, LORL=1.0, isym=1,
            ),
            criteria=[
                CriterionResult(name="LAVG (cd/m2)", value=result_lavg, required=1.0, passed=result_lavg >= 1.0),
            ],
            Lavg=result_lavg, Uo=0.4, Ul=0.6, TI=10, SR=0.5,
        )

    monkeypatch.setattr("app.services.optimizer.run_calculation", _stub)


def test_optimize_flux_converges_above_target_for_m3(db, monkeypatch):
    """Starting above M3 (lavg=1.0), nail the smallest flux with Lavg >= 1.0.

    Mock Lavg = flux / 5000.  Starting at 10 000 lm → Lavg = 2.0.
    The optimiser should drop flux to 5 000 lm → Lavg = 1.0 exactly
    (or just above, within the binary-search precision).
    """
    _mock_pcb_for_flux(monkeypatch)
    _mock_run_calculation(monkeypatch, lambda flux: flux / 5000.0)

    config = _base_config(target_flux=10_000.0, power=80.0)
    feasible, checked, result, failures, optimized = _optimize_flux_for_config(
        db, config, "ldt-mock", target_lavg=1.0,
    )

    assert feasible is True
    assert failures == "none"
    assert result.Lavg is not None and result.Lavg >= 1.01
    # The flux is as low as the binary search can push it while keeping
    # Lavg >= 1.0.  With Lavg = flux/5000 the exact answer is 5000 lm;
    # the binary search converges within 0.5 % of the high bound.
    final_flux = float(optimized.target_flux or 0)
    assert 5000 <= final_flux <= 5150, f"expected just above 5000 lm, got {final_flux}"
    # The derived power is the PCB selector's output for the chosen flux.
    expected_power = round(0.05 * (final_flux ** 0.8), 2)
    assert abs(float(optimized.power) - expected_power) < 1.0


def test_optimize_flux_uses_led_power_and_driver_efficiency(db, monkeypatch):
    _mock_pcb_for_flux(monkeypatch)
    _mock_run_calculation(monkeypatch, lambda flux: flux / 5000.0)

    config = _base_config(target_flux=10_000.0, power=80.0, driver_eficiencia=0.9)
    feasible, _checked, _result, _failures, optimized = _optimize_flux_for_config(
        db, config, "ldt-mock", target_lavg=1.0,
    )

    assert feasible is True
    final_flux = float(optimized.target_flux or 0)
    expected_led_power = round(0.05 * (final_flux ** 0.8), 2)
    assert float(optimized.power) == pytest.approx(expected_led_power / 0.9, abs=0.01)


def test_optimize_flux_increases_flux_when_below_target(db, monkeypatch):
    """When the user is below the Lavg target, the optimiser must increase flux.

    Mock Lavg = flux / 10 000.  Start at 5 000 lm → Lavg = 0.5.
    The optimiser should push flux up to 10 000 lm → Lavg = 1.0.
    """
    _mock_pcb_for_flux(monkeypatch)
    _mock_run_calculation(monkeypatch, lambda flux: flux / 10_000.0)

    config = _base_config(target_flux=5_000.0, power=40.0)
    feasible, checked, result, failures, optimized = _optimize_flux_for_config(
        db, config, "ldt-mock", target_lavg=1.0,
    )

    assert feasible is True
    assert result.Lavg is not None and result.Lavg >= 1.01
    final_flux = float(optimized.target_flux or 0)
    assert 10_000 <= final_flux <= 10_300, f"expected just above 10 000 lm, got {final_flux}"


def test_optimize_flux_returns_infeasible_when_even_max_flux_fails(db, monkeypatch):
    """When the maximum flux the PCB can deliver still fails Lavg,
    the optimiser reports infeasibility with the failing criteria.
    """
    _mock_pcb_for_flux(monkeypatch)
    # Lavg never reaches 1.0 even at 200 000 lm
    _mock_run_calculation(monkeypatch, lambda flux: flux / 500_000.0)

    config = _base_config(target_flux=5_000.0, power=40.0)
    feasible, checked, result, failures, optimized = _optimize_flux_for_config(
        db, config, "ldt-mock", target_lavg=1.0,
    )

    assert feasible is False
    assert failures == "max_flux_insufficient"
    # The result is the best we could produce (highest flux tried).
    assert result.Lavg is not None
    assert result.Lavg < 1.0


def test_optimize_flux_uses_seeded_linear_estimate(db, monkeypatch):
    """The linear estimate should drive the binary search close to the
    target on the first probe — verified by counting the number of
    calculation calls.  Pure binary search would take ~17 iterations
    (log2(200000/100) / log2(1/0.995)); the seeded search needs fewer.
    """
    _mock_pcb_for_flux(monkeypatch)
    _mock_run_calculation(monkeypatch, lambda flux: flux / 5000.0)

    config = _base_config(target_flux=20_000.0, power=120.0)
    feasible, checked, result, failures, optimized = _optimize_flux_for_config(
        db, config, "ldt-mock", target_lavg=1.0,
    )

    assert feasible is True
    # 24-iter budget, but the linear estimate puts us within ~25 % on
    # the first probe, so the binary search converges in <10 steps.
    assert checked < 15, f"expected <15 calc calls (linear seed), got {checked}"
    final_flux = float(optimized.target_flux or 0)
    assert 4900 <= final_flux <= 5100
