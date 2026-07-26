from app.schemas.models import CalculationConfig
from app.services.geometry import effective_overhang, luminaire_mounting_height


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
        pole_offset=0.5,
        pole_side="left",
        tilt=0.0,
        optic_family="F2M2",
        power=80.0,
        ldt_id="some-id",
        manufacturer="Salvi",
        model_family="CLAP S",
        gama="CLAP S",
        difusor="VDR SPUW",
        lente="F2M2",
        led_type="LUXEON 5050",
        lighting_class="M3",
        mf=0.85,
        pavement="R3",
        cct=4000,
        cri=70,
        language="es",
    )
    base.update(overrides)
    return CalculationConfig(**base)


def test_effective_overhang_subtracts_pole_offset_from_entered_arm():
    assert effective_overhang(_config(arm_length=1.5, pole_offset=0.5, tilt=30.0)) == 1.0


def test_mounting_height_is_entered_pole_height():
    assert luminaire_mounting_height(_config(height=9.0, arm_length=1.0, tilt=30.0)) == 9.0
