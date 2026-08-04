"""Compliance checks shared by the calculator and optimizer."""
from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    CalculationMetrics,
    IntrusionLimits,
    NormativeProfile,
    QualityTargets,
    RoadGeometry,
)


@dataclass(frozen=True)
class ComplianceResult:
    compliant: bool
    checks: dict[str, bool]
    failures: tuple[str, ...] = ()


def evaluate_compliance(
    metrics: CalculationMetrics,
    targets: QualityTargets,
    profile: NormativeProfile = NormativeProfile.EN13201_2015,
    *,
    geometry: RoadGeometry | None = None,
    intrusion_limits: IntrusionLimits | None = None,
    intrusion_evaluated: bool = False,
) -> ComplianceResult:
    """Evaluate hard constraints without rounding the calculated values."""

    checks: dict[str, bool] = {}

    def minimum(name: str, actual: float | None, required: float) -> None:
        checks[name] = actual is not None and actual >= required

    def maximum(name: str, actual: float | None, limit: float | None) -> None:
        if limit is not None:
            checks[name] = actual is not None and actual <= limit

    minimum("Uo", metrics.uo, targets.uo_min)
    minimum("Ul", metrics.ul, targets.ul_min)
    maximum("TI", metrics.ti_pct, targets.ti_max_pct)

    if targets.luminance_avg_min_cd_m2 is not None:
        minimum("L_avg", metrics.luminance_avg_cd_m2, targets.luminance_avg_min_cd_m2)

    # EN 13201-2:2015 uses EIR/REI. The legacy profile can require SR.
    if profile == NormativeProfile.EN13201_2003:
        if targets.sr_min is not None:
            minimum("SR", metrics.sr, targets.sr_min)
    else:
        if targets.rei_min is not None:
            minimum("REI", metrics.rei, targets.rei_min)
        elif targets.sr_min is not None:
            # Explicit compatibility request: evaluate historical SR even in
            # the current profile, but keep the field name visible in output.
            minimum("SR", metrics.sr, targets.sr_min)

    if geometry is not None:
        for band in geometry.side_bands:
            actual = metrics.band_illuminance_lx.get(band.name)
            if band.target_illuminance_min_lx is not None:
                minimum(
                    f"band:{band.name}:min",
                    actual,
                    band.target_illuminance_min_lx,
                )
            if band.target_illuminance_max_lx is not None:
                maximum(
                    f"band:{band.name}:max",
                    actual,
                    band.target_illuminance_max_lx,
                )

    if intrusion_evaluated and geometry is not None:
        for building in geometry.buildings:
            if building.max_vertical_illuminance_lx is not None:
                maximum(
                    f"facade:{building.name}",
                    metrics.building_vertical_illuminance_lx.get(building.name),
                    building.max_vertical_illuminance_lx,
                )
            if building.max_window_illuminance_lx is not None:
                maximum(
                    f"window:{building.name}",
                    metrics.building_window_illuminance_lx.get(building.name),
                    building.max_window_illuminance_lx,
                )

    if intrusion_evaluated and intrusion_limits is not None:
        if metrics.building_vertical_illuminance_lx:
            maximum(
                "intrusion:vertical",
                max(metrics.building_vertical_illuminance_lx.values()),
                intrusion_limits.max_vertical_illuminance_lx,
            )
        if metrics.building_window_illuminance_lx:
            maximum(
                "intrusion:window",
                max(metrics.building_window_illuminance_lx.values()),
                intrusion_limits.max_window_illuminance_lx,
            )

    failures = tuple(name for name, passed in checks.items() if not passed)
    return ComplianceResult(
        compliant=not failures,
        checks=checks,
        failures=failures,
    )
