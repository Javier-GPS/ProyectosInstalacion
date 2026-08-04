import pytest

from road_ldt_designer.road_ldt.domain import LuminairePlacement
from road_ldt_designer.road_ldt.periodic import repeat_luminaire_pattern


def test_periodic_pattern_translates_luminaire_and_support_together():
    pattern = (
        LuminairePlacement(
            x_m=0.0,
            y_m=-1.0,
            mounting_height_m=8.0,
            flux_lm=1000.0,
            support_x_m=0.0,
            support_y_m=-3.0,
            arm_length_m=2.0,
            arm_azimuth_deg=90.0,
            label="left",
        ),
    )

    repeated = repeat_luminaire_pattern(
        pattern,
        20.0,
        x_min_m=-20.0,
        x_max_m=40.0,
    )

    assert [item.x_m for item in repeated] == pytest.approx(
        [-20.0, 0.0, 20.0, 40.0]
    )
    assert [item.support_x_m for item in repeated] == pytest.approx(
        [-20.0, 0.0, 20.0, 40.0]
    )
    assert all(item.y_m == pytest.approx(-1.0) for item in repeated)


def test_periodic_pattern_rejects_invalid_period():
    with pytest.raises(ValueError, match="period_m"):
        repeat_luminaire_pattern(
            (LuminairePlacement(0.0, 0.0, 8.0, 1000.0),),
            0.0,
            x_min_m=0.0,
            x_max_m=20.0,
        )
