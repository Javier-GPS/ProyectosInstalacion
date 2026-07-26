from types import SimpleNamespace

from app.services.pdf_generator import env, renderIsoLinesSvg


class _Translations(dict):
    def __missing__(self, key):
        return key


def test_report_template_renders_professional_cover():
    template = env.get_template("report.html")
    cfg = SimpleNamespace(
        lighting_class="M3",
        arrangement="Unilateral",
        spacing=30.0,
        road_width=7.0,
        height=9.0,
        mf=0.85,
        pavement="R3",
        cct=4000,
        cri=70,
        sidewalk_left=1.5,
        sidewalk_right=1.5,
        pole_side="left",
        pole_offset=0.0,
        arm_length=1.0,
        tilt=5.0,
        lanes=2,
    )
    luminaire = SimpleNamespace(
        luminaire_name="SALVI TEST",
        manufacturer="SALVI",
        optic_family="F151",
        power=75.0,
        flux=9000.0,
        efficiency=120.0,
        cri=70,
        LORL=100.0,
    )

    html = template.render(
        language="es",
        project=None,
        tr=_Translations({"report.title": "Informe de alumbrado vial", "report.overall_result": "Resultado global"}),
        title="Informe",
        date="01/01/2026 12:00",
        standard="CIE 140 / EN 13201",
        compliant=True,
        compliant_label="CUMPLE",
        compliant_color="#10b981",
        luminaire=luminaire,
        cfg=cfg,
        mf_efectivo=0.85,
        total_width=10.0,
        effective_arm_overhang=1.0,
        luminaire_mounting_height=9.0,
        mini_section_svg="<svg></svg>",
        road_plan_svg="<svg></svg>",
        road_section_svg="<svg></svg>",
        polar_svg="<svg></svg>",
        iso_luminance_svg="<svg></svg>",
        iso_illuminance_svg="",
        results_table="<table></table>",
        point_table="<table></table>",
        sidewalk_left_point_table="",
        sidewalk_right_point_table="",
        Lavg="1.20",
        Uo="0.420",
        Ul="0.720",
        TI="9.5",
        SR="0.510",
        EIR="-",
        Eavg="12.30",
        Emin="4.50",
        Emax="24.00",
        criteria_map={},
    )

    assert "page" in html
    assert "1 / 2" in html
    assert "2 / 2" in html
    assert "SALVI TEST" in html
    assert "Vista en planta" in html
    assert "Secci" in html  # Sección transversal
    assert "report-module" in html
    assert "Estudio luminotécnico" in html
    assert "CUMPLE" in html


class _FakePhotometry:
    flux = 10000.0
    housing_height_m = 0.0

    def intensity(self, *_args):
        return 100.0


def test_isoline_svg_marks_luminaires_and_worst_observer():
    cfg = SimpleNamespace(
        language="es",
        arrangement="Lineal",
        spacing=30.0,
        road_width=7.0,
        height=9.0,
        mf=0.85,
        pavement="R3",
        sidewalk_left=1.5,
        sidewalk_right=1.5,
        pole_side="left",
        pole_offset=0.0,
        arm_length=1.0,
        tilt=0.0,
        lanes=2,
        lighting_class="M3",
    )
    grid = {
        "title": "Luminancia",
        "unit": "cd/m²",
        "xs": [5.0, 15.0, 25.0],
        "ys": [1.75, 5.25],
        "values": [[1.0, 0.8], [1.2, 0.7], [1.1, 0.9]],
        "avg": 0.95,
        "zone": "observer",
        "observer": (-60.0, 5.25),
        "pavement": "R3",
    }

    svg = renderIsoLinesSvg(grid, cfg, _FakePhotometry())

    assert ">L</text>" in svg
    assert 'cy="78.0"' in svg
    assert "Peor observ." in svg
    assert "#dc2626" in svg
