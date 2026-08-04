"""End-to-end demonstration; not a production lens specification."""
from __future__ import annotations

import argparse
from pathlib import Path

from road_ldt_designer.road_ldt import (
    LuminaireArrangement,
    LuminairePlacement,
    OptimizationConfig,
    OptimizationRequest,
    RoadGeometry,
    get_m_lighting_class,
    optimize_candidate,
)


def build_demo_request() -> OptimizationRequest:
    geometry = RoadGeometry(
        carriageway_width_m=7.0,
        lane_widths_m=(3.5, 3.5),
        calculation_length_m=30.0,
        longitudinal_points=10,
        transverse_points_per_lane=3,
    )
    arrangement = LuminaireArrangement(
        placements=(
            LuminairePlacement(
                x_m=0.0,
                y_m=-1.0,
                mounting_height_m=8.0,
                flux_lm=10000.0,
            ),
        ),
        nominal_spacing_m=30.0,
    )
    return OptimizationRequest(
        geometry=geometry,
        arrangement=arrangement,
        targets=get_m_lighting_class("M4").quality_targets(),
        candidate_name="SALVI_M4_demo",
        max_candidates=70,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("SALVI_M4_demo.ldt"),
    )
    args = parser.parse_args()

    result = optimize_candidate(
        build_demo_request(),
        config=OptimizationConfig(
            samples_per_stage=(40, 20, 10),
            mutation_scales=(1.0, 0.20, 0.08),
            elite_count=5,
            random_seed=13201,
        ),
    )
    args.output.write_text(result.ldt_text, encoding="latin-1")
    metrics = result.export_evaluation.metrics
    print(f"LDT: {args.output.resolve()}")
    print(f"Candidatos evaluados: {result.evaluated_candidates}")
    print(f"Cumplimiento: {result.export_evaluation.compliance.compliant}")
    print(
        f"Lavg={metrics.luminance_avg_cd_m2:.3f} cd/m2; "
        f"Uo={metrics.uo:.3f}; Ul={metrics.ul:.3f}; "
        f"TI={metrics.ti_pct:.2f}%; REI={metrics.rei:.3f}"
    )


if __name__ == "__main__":
    main()
