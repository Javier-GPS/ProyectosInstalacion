"""Tests for the 4-tuple -> LED power cap (services/luminaire_catalog.py).

The service is the safety net that prevents a tramo from being
calculated at a power the LED cannot support.  The cases covered here
match the contract documented in the service module's docstring:

1. Known 4-tuple returns its ``pmax_ajustada``.
2. ``clamp_power_to_pmax`` returns the config unchanged when
   ``power`` is below the cap.
3. ``clamp_power_to_pmax`` raises an HTTP 400 when ``power`` is
   above the cap, and the message references the LED_REF and the
   cap value.
4. ``clamp_power_to_pmax`` passes through unchanged when the
   4-tuple is not in the catalog (e.g. a brand-new luminaire whose
   LDT was just uploaded).
5. ``clamp_power_to_pmax`` raises an HTTP 400 when ``ldt_id``
   starts with ``temp-`` (external LDTs are no longer supported).
6. ``max_power_for_optimizer`` honours a user-supplied limit when
   it is below the cap, and falls back to the cap otherwise.

The tests use a fresh isolated PostgreSQL schema created from the models.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from conftest import create_test_engine

from app.database import Base
from app.models import (
    Difusor,
    Driver,
    Gama,
    LED,
    Lente,
    LedType,
    LuminaireLED,
    PCB,
    ValidCombination,
)
from app.schemas.models import CalculationConfig
from app.services import luminaire_catalog


@pytest.fixture()
def db():
    """Fresh PostgreSQL schema with the catalog seeded for the tests."""
    engine = create_test_engine()
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTesting()

    gama = Gama(name="ATENEA")
    dif = Difusor(name="PMMA LC")
    lente = Lente(name="F151")
    led_type = LedType(name="LUXEON HO 5050")
    fallback_led_type = LedType(name="WICOP Y22")
    led = LED(
        led_ref="M18",
        led_desc_corta="18 Luxeon 5050 HO+ serie d205mm",
        pmax_lum=125.0,
        i_max_led=1.2,
        pmax_ajustada=110.0,
    )
    fallback_led = LED(
        led_ref="06Y",
        led_desc_corta="3X2Y22",
        led_tipo="WICOP Y22",
        pmax_ajustada=25.0,
    )
    fallback_led_higher = LED(
        led_ref="16T",
        led_desc_corta="16TS",
        led_tipo="WICOP Y22",
        pmax_ajustada=60.0,
    )
    session.add_all([gama, dif, lente, led_type, fallback_led_type, led, fallback_led, fallback_led_higher])
    session.flush()
    session.add(LuminaireLED(
        gama_id=gama.id,
        difusor_id=dif.id,
        lente_id=lente.id,
        led_type_id=led_type.id,
        led_id=led.id,
    ))
    session.add(ValidCombination(
        gama_id=gama.id,
        difusor_id=dif.id,
        lente_id=lente.id,
        led_type_id=fallback_led_type.id,
    ))
    legacy_gama = Gama(name="CLAP M")
    legacy_dif = Difusor(name="W")
    legacy_led = LED(
        led_ref="28B",
        led_desc_corta="28 WICOP HE 5050",
        pmax_ajustada=100.0,
    )
    session.add_all([legacy_gama, legacy_dif, legacy_led])
    session.flush()
    session.add(LuminaireLED(
        gama_id=legacy_gama.id,
        difusor_id=legacy_dif.id,
        lente_id=lente.id,
        led_type_id=led_type.id,
        led_id=legacy_led.id,
    ))
    # Add a spare LED with a lower pmax and no 4-tuple binding; it
    # must not affect the exact cap.
    session.add(LED(led_ref="M18LITE", pmax_ajustada=90.0))
    # A PCB and Driver so the table creation is covered end-to-end.
    session.add(PCB(pcb_ref="1ME2432", pcb_no_led=18, pcb_v_nominal=5.9))
    session.add(Driver(dr_ref="MSN032NPAL001", dr_pot_max_driver=120.0))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


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
        optic_family="F151",
        power=80.0,
        ldt_id="some-id",
        manufacturer="Salvi",
        model_family="ATENEA",
        gama="ATENEA",
        difusor="PMMA LC",
        lente="F151",
        led_type="LUXEON HO 5050",
        lighting_class="M3",
        mf=0.85,
        pavement="R3",
        cct=4000,
        cri=70,
        language="es",
    )
    base.update(overrides)
    return CalculationConfig(**base)


# ---------------------------------------------------------------------------
# 1. Known 4-tuple → pmax_ajustada
# ---------------------------------------------------------------------------


def test_get_pmax_for_known_tuple_returns_cap(db):
    info = luminaire_catalog.get_pmax_for_selection(
        db, "ATENEA", "PMMA LC", "F151", "LUXEON HO 5050",
    )
    assert info is not None
    assert info["led_ref"] == "M18"
    assert info["pmax_ajustada"] == 110.0
    assert info["pmax_lum"] == 125.0
    assert info["i_max_led"] == 1.2
    assert info["source"] == "exact"


# ---------------------------------------------------------------------------
# 2. Below the cap: passthrough
# ---------------------------------------------------------------------------


def test_clamp_power_below_cap_is_passthrough(db):
    config = _config(power=80.0)
    out = luminaire_catalog.clamp_power_to_pmax(db, config)
    assert out is config  # identity, no copy


# ---------------------------------------------------------------------------
# 3. Above the cap: HTTP 400 with a useful message
# ---------------------------------------------------------------------------


def test_clamp_power_above_cap_raises_400(db):
    config = _config(power=150.0)
    with pytest.raises(HTTPException) as exc:
        luminaire_catalog.clamp_power_to_pmax(db, config)
    assert exc.value.status_code == 400
    # Message references both the requested power and the cap, so the
    # FE can display a useful toast.
    assert "150" in exc.value.detail
    assert "110" in exc.value.detail
    assert "M18" in exc.value.detail


# ---------------------------------------------------------------------------
# 4. Unknown 4-tuple: passthrough (no enforcement)
# ---------------------------------------------------------------------------


def test_clamp_power_unknown_tuple_is_passthrough(db):
    config = _config(power=999.0, gama="DOES_NOT_EXIST")
    out = luminaire_catalog.clamp_power_to_pmax(db, config)
    assert out is config


def test_clamp_power_incomplete_tuple_is_passthrough(db):
    config = _config(power=999.0, lente="")
    out = luminaire_catalog.clamp_power_to_pmax(db, config)
    assert out is config


# ---------------------------------------------------------------------------
# 5. External LDT (temp-): now raises 400 (no longer supported)
# ---------------------------------------------------------------------------


def test_clamp_power_external_ldt_raises_400(db):
    config = _config(power=999.0, ldt_id="temp-foobar")
    with pytest.raises(HTTPException) as exc:
        luminaire_catalog.clamp_power_to_pmax(db, config)
    assert exc.value.status_code == 400
    assert "LDTs externos" in exc.value.detail


# ---------------------------------------------------------------------------
# 6. Optimizer ceiling helper
# ---------------------------------------------------------------------------


def test_max_power_for_optimizer_falls_back_to_cap(db):
    config = _config(power=80.0)
    assert luminaire_catalog.max_power_for_optimizer(db, config) == 110.0


def test_max_power_for_optimizer_honours_lower_user_limit(db):
    config = _config(power=80.0)
    assert luminaire_catalog.max_power_for_optimizer(db, config, user_supplied=50.0) == 50.0


def test_max_power_for_optimizer_caps_user_limit(db):
    config = _config(power=80.0)
    # User asked for 500 W but the LED caps at 110 W.
    assert luminaire_catalog.max_power_for_optimizer(db, config, user_supplied=500.0) == 110.0


def test_max_power_for_optimizer_unknown_tuple_returns_user_limit(db):
    config = _config(power=80.0, gama="DOES_NOT_EXIST")
    assert luminaire_catalog.max_power_for_optimizer(db, config, user_supplied=200.0) == 200.0


def test_max_power_for_optimizer_external_ldt_raises_400(db):
    config = _config(power=80.0, ldt_id="temp-foobar")
    with pytest.raises(HTTPException) as exc:
        luminaire_catalog.max_power_for_optimizer(db, config, user_supplied=200.0)
    assert exc.value.status_code == 400
    assert "LDTs externos" in exc.value.detail


# ---------------------------------------------------------------------------
# 7. pmax_by_combo map for the FE
# ---------------------------------------------------------------------------


def test_build_pmax_by_combo_contains_known_tuple(db):
    mapping = luminaire_catalog.build_pmax_by_combo(db)
    # Keys are upper-cased, pipe-joined.
    assert mapping.get("ATENEA|PMMA LC|F151|LUXEON HO 5050") == 110.0
    # M18LITE has no 4-tuple binding, so it must not appear in the map.
    assert "M18LITE" not in mapping


def test_legacy_difusor_code_resolves_descriptive_selection(db):
    info = luminaire_catalog.get_pmax_for_selection(
        db, "CLAP M", "VDR SPUW", "F151", "LUXEON HO 5050",
    )
    assert info is not None
    assert info["led_ref"] == "28B"
    assert info["pmax_ajustada"] == 100.0


def test_build_pmax_by_combo_expands_legacy_difusor_codes(db):
    mapping = luminaire_catalog.build_pmax_by_combo(db)
    assert mapping.get("CLAP M|W|F151|LUXEON HO 5050") == 100.0
    assert mapping.get("CLAP M|VDR SPUW|F151|LUXEON HO 5050") == 100.0


def test_missing_4tuple_binding_falls_back_to_highest_led_type_cap(db):
    info = luminaire_catalog.get_pmax_for_selection(
        db, "ATENEA", "PMMA LC", "F151", "WICOP Y22",
    )
    assert info is not None
    assert info["led_ref"] == "16T"
    assert info["pmax_ajustada"] == 60.0
    assert info["source"] == "led_type_fallback"


def test_build_pmax_by_combo_fills_valid_combo_from_led_type_fallback(db):
    mapping = luminaire_catalog.build_pmax_by_combo(db)
    assert mapping.get("ATENEA|PMMA LC|F151|WICOP Y22") == 60.0


def test_build_pmax_maps_marks_fallback_sources(db):
    mapping, sources = luminaire_catalog.build_pmax_maps(db)
    assert mapping.get("ATENEA|PMMA LC|F151|LUXEON HO 5050") == 110.0
    assert sources.get("ATENEA|PMMA LC|F151|LUXEON HO 5050") == "exact"
    assert mapping.get("ATENEA|PMMA LC|F151|WICOP Y22") == 60.0
    assert sources.get("ATENEA|PMMA LC|F151|WICOP Y22") == "led_type_fallback"
