from app.services.calculator import _build_criteria


def test_multi_sidewalk_criteria_keep_cross_section_indices():
    criteria = _build_criteria({
        "mode": "P",
        "sidewalk_e0_class": "P4",
        "sidewalk_e0_Eavg": 5,
        "sidewalk_e0_Emin": 2,
        "sidewalk_e0_req": {"Eavg": 3, "Emin": 1},
        "sidewalk_e0_ok_Eavg": True,
        "sidewalk_e0_ok_Emin": True,
        "sidewalk_e2_class": "P4",
        "sidewalk_e2_Eavg": 4,
        "sidewalk_e2_Emin": 1,
        "sidewalk_e2_req": {"Eavg": 3, "Emin": 1},
        "sidewalk_e2_ok_Eavg": True,
        "sidewalk_e2_ok_Emin": True,
    })

    assert [criterion.name for criterion in criteria] == [
        "Eavg (lux)",
        "Emin (lux)",
        "Acera SW 1 - Eavg (lux)",
        "Acera SW 1 - Emin (lux)",
        "Acera SW 3 - Eavg (lux)",
        "Acera SW 3 - Emin (lux)",
    ]
