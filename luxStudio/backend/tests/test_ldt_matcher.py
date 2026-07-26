from app.schemas.models import CalculationConfig
from app.services import ldt_matcher


def test_exact_4tuple_wins_over_stale_ldt_id(monkeypatch):
    stale = {
        "id": "stale", "manufacturer": "Salvi", "gama": "CLAP S",
        "difusor": "PMMA AMBAR", "lente": "F151", "led_type": "LUXEON 5050",
        "optic_family": "F151", "power": 31.0, "cct": 4000, "cri": 70,
    }
    exact = {
        "id": "exact", "manufacturer": "Salvi", "gama": "CLAP S",
        "difusor": "VIDRIO ULTRAWHITE TRANSP PLANO", "lente": "F151",
        "led_type": "LUXEON HOP 5050", "optic_family": "F151",
        "power": 31.0, "cct": 4000, "cri": 70,
    }
    monkeypatch.setattr(ldt_matcher, "get_all_ldts", lambda: [stale, exact])
    monkeypatch.setattr(ldt_matcher, "get_ldt_by_id", lambda _id: stale)

    config = CalculationConfig(
        road_width=9.0, optic_family="F151", power=46.21, ldt_id="stale",
        manufacturer="Salvi", gama="CLAP S",
        difusor="VIDRIO ULTRAWHITE TRANSP PLANO", lente="F151",
        led_type="LUXEON HOP 5050",
    )

    ldt_id, ldt = ldt_matcher.find_ldt_for_config(config)
    assert ldt_id == "exact"
    assert ldt is exact
