"""Independent Flask API for the SALVI Road LDT Designer frontend."""
from __future__ import annotations

from dataclasses import asdict, replace
from math import ceil

from flask import Flask, jsonify, request

from .road_ldt import (
    AdjacentBuilding,
    ArrangementType,
    EvaluationOptions,
    IntrusionLimits,
    LuminaireArrangement,
    LuminairePlacement,
    OptimizationConfig,
    OptimizationRequest,
    PhotometricCandidate,
    QualityTargets,
    RoadGeometry,
    StreetBand,
    angular_residual_map,
    candidate_from_ldt_text,
    candidate_to_ldt,
    compare_photometries,
    compensate_target,
    describe_photometry,
    evaluate_candidate,
    get_m_lighting_class,
    list_m_lighting_classes,
    optimize_candidate,
)

app = Flask(__name__)


@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


def _number(data: dict, key: str, default: float) -> float:
    return float(data.get(key, default))


def _build_bands(data: dict) -> tuple[StreetBand, ...]:
    bands: list[StreetBand] = []
    for side in ("left", "right"):
        width = _number(data, f"sidewalk_{side}_m", 0.0)
        if width > 0:
            bands.append(
                StreetBand(
                    name=f"acera {side}",
                    side=side,
                    width_m=width,
                    elevation_m=_number(data, "sidewalk_elevation_m", 0.15),
                    target_illuminance_min_lx=(
                        float(data["sidewalk_target_min_lx"])
                        if data.get("sidewalk_target_min_lx") is not None
                        else None
                    ),
                )
            )
    return tuple(bands)


def _build_buildings(data: dict, intrusion_enabled: bool) -> tuple[AdjacentBuilding, ...]:
    if not intrusion_enabled:
        return ()
    buildings: list[AdjacentBuilding] = []
    for side in ("left", "right"):
        if not bool(data.get(f"building_{side}_enabled", False)):
            continue
        height = _number(data, f"building_{side}_height_m", 12.0)
        window_top = min(
            _number(data, f"building_{side}_window_top_m", height),
            height,
        )
        buildings.append(
            AdjacentBuilding(
                name=f"edificio {side}",
                side=side,
                setback_m=_number(data, f"building_{side}_setback_m", 5.0),
                facade_height_m=height,
                length_m=_number(data, "calculation_length_m", 30.0),
                window_bottom_m=_number(
                    data,
                    f"building_{side}_window_bottom_m",
                    1.0,
                ),
                window_top_m=window_top,
                max_vertical_illuminance_lx=(
                    float(data["facade_limit_lx"])
                    if data.get("facade_limit_lx") is not None
                    else None
                ),
                max_window_illuminance_lx=(
                    float(data["window_limit_lx"])
                    if data.get("window_limit_lx") is not None
                    else None
                ),
            )
        )
    return tuple(buildings)


def _placement(
    *,
    x_m: float,
    support_y_m: float,
    toward_positive_y: bool,
    height_m: float,
    flux_lm: float,
    overhang_m: float,
    tilt_deg: float,
    label: str,
) -> LuminairePlacement:
    orientation = 0.0 if toward_positive_y else 180.0
    if overhang_m <= 0:
        return LuminairePlacement(
            x_m=x_m,
            y_m=support_y_m,
            mounting_height_m=height_m,
            flux_lm=flux_lm,
            orientation_deg=orientation,
            tilt_deg=tilt_deg,
            label=label,
        )
    azimuth = 90.0 if toward_positive_y else 270.0
    y_m = support_y_m + (overhang_m if toward_positive_y else -overhang_m)
    return LuminairePlacement(
        x_m=x_m,
        y_m=y_m,
        mounting_height_m=height_m,
        flux_lm=flux_lm,
        orientation_deg=orientation,
        tilt_deg=tilt_deg,
        support_x_m=x_m,
        support_y_m=support_y_m,
        arm_length_m=overhang_m,
        arm_azimuth_deg=azimuth,
        label=label,
    )


def _build_arrangement(data: dict, carriageway_width_m: float) -> LuminaireArrangement:
    arrangement = ArrangementType(data.get("arrangement_type", "unilateral"))
    spacing = _number(data, "spacing_m", 30.0)
    height = _number(data, "mounting_height_m", 8.0)
    flux = _number(data, "flux_lm", 10000.0)
    setback = _number(data, "pole_setback_m", 1.0)
    overhang = _number(data, "overhang_m", 1.0)
    tilt = _number(data, "tilt_deg", 0.0)

    left = lambda x, label: _placement(
        x_m=x,
        support_y_m=-setback,
        toward_positive_y=True,
        height_m=height,
        flux_lm=flux,
        overhang_m=overhang,
        tilt_deg=tilt,
        label=label,
    )
    right = lambda x, label: _placement(
        x_m=x,
        support_y_m=carriageway_width_m + setback,
        toward_positive_y=False,
        height_m=height,
        flux_lm=flux,
        overhang_m=overhang,
        tilt_deg=tilt,
        label=label,
    )

    if arrangement == ArrangementType.UNILATERAL:
        placements = (
            right(0.0, "unilateral right")
            if data.get("unilateral_side") == "right"
            else left(0.0, "unilateral left"),
        )
    elif arrangement == ArrangementType.BILATERAL_OPPOSITE:
        placements = (left(0.0, "left"), right(0.0, "right"))
    elif arrangement == ArrangementType.BILATERAL_STAGGERED:
        placements = (
            left(0.0, "left"),
            right(spacing / 2.0, "right staggered"),
        )
    elif arrangement == ArrangementType.CENTRAL_DOUBLE:
        central_arm = max(overhang, 0.1)
        placements = (
            _placement(
                x_m=0.0,
                support_y_m=carriageway_width_m / 2.0,
                toward_positive_y=True,
                height_m=height,
                flux_lm=flux,
                overhang_m=central_arm,
                tilt_deg=tilt,
                label="central right",
            ),
            _placement(
                x_m=0.0,
                support_y_m=carriageway_width_m / 2.0,
                toward_positive_y=False,
                height_m=height,
                flux_lm=flux,
                overhang_m=central_arm,
                tilt_deg=tilt,
                label="central left",
            ),
        )
    else:
        raise ValueError("la API inicial no admite disposición custom")
    return LuminaireArrangement(
        placements=placements,
        arrangement_type=arrangement,
        nominal_spacing_m=spacing,
    )


def _build_request(data: dict) -> tuple[OptimizationRequest, EvaluationOptions]:
    geometry_data = data.get("geometry", {})
    installation_data = data.get("installation", {})
    requirements_data = data.get("requirements", {})
    optimizer_data = data.get("optimizer", {})

    lane_widths = tuple(
        float(value) for value in geometry_data.get("lane_widths_m", (3.5, 3.5))
    )
    carriageway_width = sum(lane_widths)
    intrusion_enabled = bool(requirements_data.get("evaluate_intrusion", False))
    geometry = RoadGeometry(
        carriageway_width_m=carriageway_width,
        lane_widths_m=lane_widths,
        calculation_length_m=_number(
            geometry_data,
            "calculation_length_m",
            _number(installation_data, "spacing_m", 30.0),
        ),
        r_table=str(geometry_data.get("r_table", "R2")),
        longitudinal_points=int(geometry_data.get("longitudinal_points", 10)),
        transverse_points_per_lane=int(
            geometry_data.get("transverse_points_per_lane", 3)
        ),
        side_bands=_build_bands(geometry_data),
        buildings=_build_buildings(geometry_data, intrusion_enabled),
    )
    arrangement = _build_arrangement(installation_data, carriageway_width)
    lighting_class_code = str(
        requirements_data.get("lighting_class", "M4")
    ).upper()
    include_rei = bool(requirements_data.get("include_rei", True))
    if lighting_class_code == "CUSTOM":
        custom_data = requirements_data.get("custom_targets", {})
        if not isinstance(custom_data, dict):
            raise ValueError("custom_targets debe ser un objeto")
        targets = QualityTargets(
            luminance_avg_min_cd_m2=_number(
                custom_data,
                "luminance_avg_min_cd_m2",
                0.75,
            ),
            uo_min=_number(custom_data, "uo_min", 0.40),
            ul_min=_number(custom_data, "ul_min", 0.60),
            ti_max_pct=_number(custom_data, "ti_max_pct", 15.0),
            rei_min=(
                _number(custom_data, "rei_min", 0.30)
                if include_rei
                else None
            ),
        )
    else:
        lighting_class = get_m_lighting_class(lighting_class_code)
        targets = lighting_class.quality_targets(include_rei=include_rei)
    max_candidates = int(optimizer_data.get("max_candidates", 70))
    optimization_request = OptimizationRequest(
        geometry=geometry,
        arrangement=arrangement,
        targets=targets,
        intrusion_limits=IntrusionLimits(
            max_vertical_illuminance_lx=(
                float(requirements_data["facade_limit_lx"])
                if requirements_data.get("facade_limit_lx") is not None
                else None
            ),
            max_window_illuminance_lx=(
                float(requirements_data["window_limit_lx"])
                if requirements_data.get("window_limit_lx") is not None
                else None
            ),
        ),
        candidate_name=str(data.get("project_name", "SALVI road candidate")),
        max_candidates=max_candidates,
    )
    options = EvaluationOptions(
        maintenance_factor=_number(requirements_data, "maintenance_factor", 0.8),
        evaluate_edge_metrics=include_rei,
        evaluate_side_bands=True,
        evaluate_intrusion=intrusion_enabled,
        calculation_backend="numpy",
    )
    return optimization_request, options


def _optimizer_config(max_candidates: int) -> OptimizationConfig:
    coarse = max(1, ceil(max_candidates * 0.57))
    medium = max(1, ceil(max_candidates * 0.29))
    fine = max(1, max_candidates - coarse - medium)
    total = coarse + medium + fine
    if total > max_candidates:
        coarse = max(1, coarse - (total - max_candidates))
    return OptimizationConfig(
        samples_per_stage=(coarse, medium, fine),
        mutation_scales=(1.0, 0.20, 0.08),
        elite_count=min(5, coarse),
        random_seed=13201,
    )


def _photometry_payload(
    candidate: PhotometricCandidate,
    *,
    source: str,
) -> dict:
    descriptor = describe_photometry(candidate)
    return {
        "source": source,
        "declared_flux_lm": candidate.flux_lm,
        "c_step_deg": (
            candidate.c_angles_deg[1]
            - candidate.c_angles_deg[0]
        ),
        "gamma_step_deg": (
            candidate.gamma_angles_deg[1]
            - candidate.gamma_angles_deg[0]
        ),
        **asdict(descriptor),
        "c_angles_deg": candidate.c_angles_deg,
        "gamma_angles_deg": candidate.gamma_angles_deg,
        "intensity_cd_per_klm": candidate.intensity_cd_per_klm,
    }


def _metrics_payload(metrics) -> dict:
    return {
        "luminance_avg_cd_m2": metrics.luminance_avg_cd_m2,
        "uo": metrics.uo,
        "ul": metrics.ul,
        "ti_pct": metrics.ti_pct,
        "rei": metrics.rei,
        "sr": metrics.sr,
        "band_illuminance_lx": metrics.band_illuminance_lx,
        "intrusion_max_lx": metrics.intrusion_max_lx,
    }


def _result_payload(result) -> dict:
    metrics = result.export_evaluation.metrics
    preview_candidate = result.round_trip_candidate

    critical_observer = min(
        result.export_evaluation.luminance.observer_results,
        key=lambda item: item.luminance_avg_cd_m2,
    )
    return {
        "status": "complete",
        "compliant": result.export_evaluation.compliance.compliant,
        "failures": list(result.export_evaluation.compliance.failures),
        "metrics": _metrics_payload(metrics),
        "optimizer": {
            "evaluated_candidates": result.evaluated_candidates,
            "score": result.export_score.total,
            "maximum_violation": result.export_score.maximum_violation,
            "parameters": asdict(result.best_trial.parameters),
        },
        "photometry": _photometry_payload(
            preview_candidate,
            source="round_trip_ldt",
        ),
        "road_luminance": [
            {
                "x_m": item.point.x_m,
                "y_m": item.point.y_m,
                "lane_index": item.point.lane_index,
                "luminance_cd_m2": item.luminance_cd_m2,
            }
            for item in critical_observer.point_results
        ],
        "ldt_text": result.ldt_text,
    }


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "engine": "SALVI Road LDT Designer"})


@app.get("/api/lighting-classes")
def lighting_classes():
    return jsonify(
        [
            asdict(get_m_lighting_class(code))
            for code in list_m_lighting_classes()
        ]
    )


@app.post("/api/optimize")
def optimize():
    try:
        optimization_request, options = _build_request(request.get_json(force=True))
        result = optimize_candidate(
            optimization_request,
            options=options,
            config=_optimizer_config(optimization_request.max_candidates),
        )
        return jsonify(_result_payload(result))
    except (TypeError, ValueError) as error:
        return jsonify({"status": "error", "message": str(error)}), 400


@app.post("/api/validate-ldt")
def validate_ldt():
    """Compare a simulated/measured physical LDT against the target LDT."""

    try:
        data = request.get_json(force=True)
        physical_text = str(data.get("physical_ldt_text", ""))
        target_text = str(data.get("target_ldt_text", ""))
        if not physical_text.strip():
            raise ValueError("seleccione un LDT físico para validar")
        if not target_text.strip():
            raise ValueError("falta el LDT objetivo de la optimización")

        optimization_request, options = _build_request(data)
        validation_request = replace(
            optimization_request,
            require_longitudinal_symmetry=False,
        )
        physical_candidate = candidate_from_ldt_text(physical_text)
        target_candidate = candidate_from_ldt_text(target_text)
        physical_evaluation = evaluate_candidate(
            validation_request,
            physical_candidate,
            options=options,
        )
        target_evaluation = evaluate_candidate(
            validation_request,
            target_candidate,
            options=options,
        )
        comparison = compare_photometries(
            target_candidate,
            physical_candidate,
        )
        residual_map = angular_residual_map(
            target_candidate,
            physical_candidate,
        )
        compensation = compensate_target(
            target_candidate,
            physical_candidate,
            correction_gain=float(data.get("correction_gain", 0.60)),
        )
        compensated_comparison = compare_photometries(
            target_candidate,
            compensation.candidate,
        )
        physical_metrics = physical_evaluation.metrics
        target_metrics = target_evaluation.metrics

        metric_deltas: dict[str, float | None] = {}
        for name in (
            "luminance_avg_cd_m2",
            "uo",
            "ul",
            "ti_pct",
            "rei",
            "sr",
            "intrusion_max_lx",
        ):
            physical_value = getattr(physical_metrics, name)
            target_value = getattr(target_metrics, name)
            metric_deltas[name] = (
                float(physical_value - target_value)
                if physical_value is not None and target_value is not None
                else None
            )

        return jsonify(
            {
                "status": "complete",
                "filename": str(data.get("physical_filename", "physical.ldt")),
                "compliant": physical_evaluation.compliance.compliant,
                "failures": list(physical_evaluation.compliance.failures),
                "metrics": _metrics_payload(physical_metrics),
                "target_metrics": _metrics_payload(target_metrics),
                "metric_deltas": metric_deltas,
                "comparison": asdict(comparison),
                "residual_map": asdict(residual_map),
                "compensation": {
                    "correction_gain": compensation.correction_gain,
                    "smoothing_passes": compensation.smoothing_passes,
                    "clipped_low_fraction": compensation.clipped_low_fraction,
                    "capped_high_fraction": compensation.capped_high_fraction,
                    "maximum_adjustment_pct_of_target_peak": (
                        compensation.maximum_adjustment_pct_of_target_peak
                    ),
                    "integrated_flux_lm_per_klm": (
                        compensation.integrated_flux_lm_per_klm
                    ),
                    "pre_distortion_rmse_pct": (
                        compensated_comparison.normalized_rmse_pct
                    ),
                    "filename": "SALVI_target_compensated.ldt",
                    "ldt_text": candidate_to_ldt(
                        compensation.candidate,
                        "SALVI_target_compensated.ldt",
                    ),
                    "photometry": _photometry_payload(
                        compensation.candidate,
                        source="compensated_target",
                    ),
                },
                "photometry": _photometry_payload(
                    physical_candidate,
                    source="physical_ldt",
                ),
            }
        )
    except (TypeError, ValueError) as error:
        return jsonify({"status": "error", "message": str(error)}), 400


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=False,
        use_reloader=False,
    )
