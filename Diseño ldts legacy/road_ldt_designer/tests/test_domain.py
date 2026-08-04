from road_ldt_designer.road_ldt.compliance import evaluate_compliance
from road_ldt_designer.road_ldt.domain import (
    AdjacentBuilding,
    ArrangementType,
    CalculationMetrics,
    IntrusionLimits,
    LuminaireArrangement,
    LuminairePlacement,
    NormativeProfile,
    OptimizationRequest,
    QualityTargets,
    RoadGeometry,
    StreetBand,
)
from road_ldt_designer.road_ldt.eulumdat import write_ldt
from road_ldt_designer.road_ldt.domain import PhotometricCandidate


def _request_parts():
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_width_m=3.5,
        lanes=2,
    )
    arrangement = LuminaireArrangement(
        placements=(LuminairePlacement(0.0, 0.3, 8.0, 12000.0),),
    )
    return geometry, arrangement


def test_basic_road_domain_is_valid():
    geometry, arrangement = _request_parts()
    assert geometry.carriageway_width_m == 7.0
    assert arrangement.placements[0].mounting_height_m == 8.0


def test_current_profile_checks_rei_when_requested():
    metrics = CalculationMetrics(uo=0.45, ul=0.72, ti_pct=8.0, rei=0.36)
    targets = QualityTargets(uo_min=0.40, ul_min=0.70, ti_max_pct=10.0, rei_min=0.35)
    result = evaluate_compliance(metrics, targets, NormativeProfile.EN13201_2015)
    assert result.compliant is True


def test_legacy_profile_checks_sr():
    metrics = CalculationMetrics(uo=0.45, ul=0.72, ti_pct=8.0, sr=0.52)
    targets = QualityTargets(sr_min=0.50)
    result = evaluate_compliance(metrics, targets, NormativeProfile.EN13201_2003)
    assert result.compliant is True


def test_generated_ldt_contains_the_required_eulumdat_sections(tmp_path):
    c_angles = (0.0, 90.0, 180.0, 270.0)
    gamma_angles = (0.0, 30.0, 60.0, 90.0)
    matrix = tuple(tuple(float(c + g) for g in range(4)) for c in range(4))
    candidate = PhotometricCandidate(
        c_angles_deg=c_angles,
        gamma_angles_deg=gamma_angles,
        intensity_cd_per_klm=matrix,
        flux_lm=10000.0,
    )

    output = write_ldt(tmp_path / "candidate.ldt", candidate)
    lines = output.read_text(encoding="latin-1").splitlines()

    assert lines[0] == "SALVI"
    assert lines[3] == "4"
    assert lines[5] == "4"
    assert lines[-16:-12] == ["0", "1", "2", "3"]
    assert lines[-4:] == ["3", "4", "5", "6"]


def test_complete_street_supports_variable_lanes_sidewalks_buildings_and_arm():
    geometry = RoadGeometry(
        carriageway_width_m=10.5,
        lane_widths_m=(3.0, 3.5, 4.0),
        side_bands=(
            StreetBand("acera_izquierda", "left", 2.5, target_illuminance_min_lx=7.5),
            StreetBand("acera_derecha", "right", 3.0, target_illuminance_min_lx=7.5),
        ),
        buildings=(
            AdjacentBuilding(
                "fachada_derecha",
                "right",
                setback_m=5.0,
                facade_height_m=12.0,
                window_bottom_m=1.0,
                window_top_m=10.0,
                max_vertical_illuminance_lx=5.0,
                max_window_illuminance_lx=2.0,
            ),
        ),
    )
    luminaire = LuminairePlacement(
        x_m=0.0,
        y_m=1.25,
        mounting_height_m=9.0,
        flux_lm=14000.0,
        support_x_m=0.0,
        support_y_m=0.0,
        arm_length_m=1.25,
        arm_azimuth_deg=90.0,
    )
    arrangement = LuminaireArrangement(
        placements=(luminaire,),
        arrangement_type=ArrangementType.UNILATERAL,
        nominal_spacing_m=30.0,
    )
    request = OptimizationRequest(
        geometry=geometry,
        arrangement=arrangement,
        targets=QualityTargets(uo_min=0.40, ul_min=0.60, ti_max_pct=15.0),
        intrusion_limits=IntrusionLimits(max_vertical_illuminance_lx=5.0),
    )

    assert request.geometry.resolved_lane_widths_m == (3.0, 3.5, 4.0)
    assert request.geometry.buildings[0].window_top_m == 10.0
    assert request.arrangement.placements[0].arm_length_m == 1.25
