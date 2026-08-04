"""Small, dependency-free domain model for road LDT design.

The classes in this module intentionally do not perform photometric
calculations. They define the stable contract between the future UI, the
EN 13201 calculator, the optimizer and the EULUMDAT exporter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NormativeProfile(str, Enum):
    """Normative convention used to interpret and report the calculation."""

    EN13201_2015 = "EN13201-2015"
    EN13201_2003 = "EN13201-2003"
    PREN13201_2026 = "prEN13201-2026"


def _positive(name: str, value: float) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


def _non_negative(name: str, value: float) -> float:
    value = float(value)
    if value < 0:
        raise ValueError(f"{name} no puede ser negativo")
    return value


class ArrangementType(str, Enum):
    UNILATERAL = "unilateral"
    BILATERAL_OPPOSITE = "bilateral_opposite"
    BILATERAL_STAGGERED = "bilateral_staggered"
    CENTRAL_DOUBLE = "central_double"
    CUSTOM = "custom"


def _validate_side(side: str) -> str:
    side = str(side).lower()
    if side not in {"left", "right"}:
        raise ValueError("side debe ser 'left' o 'right'")
    return side


@dataclass(frozen=True)
class StreetBand:
    """Band beside the carriageway, such as sidewalk, cycleway or parking."""

    name: str
    side: str
    width_m: float
    offset_from_carriageway_m: float = 0.0
    elevation_m: float = 0.0
    surface: str = "sidewalk"
    target_illuminance_min_lx: float | None = None
    target_illuminance_max_lx: float | None = None

    def __post_init__(self) -> None:
        _validate_side(self.side)
        _positive("width_m", self.width_m)
        _non_negative("offset_from_carriageway_m", self.offset_from_carriageway_m)
        if self.target_illuminance_min_lx is not None:
            _non_negative("target_illuminance_min_lx", self.target_illuminance_min_lx)
        if self.target_illuminance_max_lx is not None:
            _non_negative("target_illuminance_max_lx", self.target_illuminance_max_lx)
        if (
            self.target_illuminance_min_lx is not None
            and self.target_illuminance_max_lx is not None
            and self.target_illuminance_max_lx < self.target_illuminance_min_lx
        ):
            raise ValueError("el máximo de iluminancia no puede ser menor que el mínimo")


@dataclass(frozen=True)
class AdjacentBuilding:
    """Facade parallel to the road used for light-intrusion evaluation."""

    name: str
    side: str
    setback_m: float
    facade_height_m: float
    length_m: float = 100.0
    facade_reflectance: float = 0.30
    window_bottom_m: float | None = None
    window_top_m: float | None = None
    max_vertical_illuminance_lx: float | None = None
    max_window_illuminance_lx: float | None = None

    def __post_init__(self) -> None:
        _validate_side(self.side)
        _non_negative("setback_m", self.setback_m)
        _positive("facade_height_m", self.facade_height_m)
        _positive("length_m", self.length_m)
        if not 0.0 <= self.facade_reflectance <= 1.0:
            raise ValueError("facade_reflectance debe estar entre 0 y 1")
        if (self.window_bottom_m is None) != (self.window_top_m is None):
            raise ValueError("window_bottom_m y window_top_m deben definirse juntos")
        if self.window_bottom_m is not None:
            _non_negative("window_bottom_m", self.window_bottom_m)
            _positive("window_top_m", self.window_top_m)
            if self.window_top_m <= self.window_bottom_m:
                raise ValueError("window_top_m debe ser mayor que window_bottom_m")
            if self.window_top_m > self.facade_height_m:
                raise ValueError("window_top_m no puede superar facade_height_m")
        for name in ("max_vertical_illuminance_lx", "max_window_illuminance_lx"):
            value = getattr(self, name)
            if value is not None:
                _non_negative(name, value)


@dataclass(frozen=True)
class RoadGeometry:
    """Street cross-section and roadside elements."""

    carriageway_width_m: float
    lane_width_m: float | None = None
    lanes: int | None = None
    lane_widths_m: tuple[float, ...] | None = None
    calculation_length_m: float = 100.0
    r_table: str = "R2"
    road_surface: str = "dry"
    longitudinal_points: int = 10
    transverse_points_per_lane: int = 3
    side_bands: tuple[StreetBand, ...] = ()
    buildings: tuple[AdjacentBuilding, ...] = ()

    def __post_init__(self) -> None:
        _positive("carriageway_width_m", self.carriageway_width_m)
        _positive("calculation_length_m", self.calculation_length_m)

        if self.lane_widths_m is not None:
            if not self.lane_widths_m or any(float(width) <= 0 for width in self.lane_widths_m):
                raise ValueError("lane_widths_m debe contener anchuras positivas")
            if self.lanes is not None and self.lanes != len(self.lane_widths_m):
                raise ValueError("lanes no coincide con el número de lane_widths_m")
            object.__setattr__(self, "lanes", len(self.lane_widths_m))
            if self.lane_width_m is None:
                object.__setattr__(self, "lane_width_m", sum(self.lane_widths_m) / len(self.lane_widths_m))
        else:
            if self.lane_width_m is None or self.lanes is None:
                raise ValueError("defina lane_width_m y lanes, o lane_widths_m")
            _positive("lane_width_m", self.lane_width_m)
            if int(self.lanes) != self.lanes or self.lanes < 1:
                raise ValueError("lanes debe ser un entero mayor o igual que uno")

        total_lane_width = sum(self.resolved_lane_widths_m)
        if abs(self.carriageway_width_m - total_lane_width) > 1e-6:
            raise ValueError(
                "carriageway_width_m debe coincidir con la suma de los carriles; "
                "modele aceras, arcenes y otras zonas como StreetBand"
            )
        if self.longitudinal_points < 2:
            raise ValueError("longitudinal_points debe ser al menos 2")
        if self.transverse_points_per_lane < 1:
            raise ValueError("transverse_points_per_lane debe ser al menos 1")

    @property
    def resolved_lane_widths_m(self) -> tuple[float, ...]:
        if self.lane_widths_m is not None:
            return tuple(float(width) for width in self.lane_widths_m)
        return tuple(float(self.lane_width_m) for _ in range(int(self.lanes)))


@dataclass(frozen=True)
class LuminairePlacement:
    """One installed luminaire in road coordinates."""

    x_m: float
    y_m: float
    mounting_height_m: float
    flux_lm: float
    orientation_deg: float = 0.0
    tilt_deg: float = 0.0
    rotation_deg: float = 0.0
    support_x_m: float | None = None
    support_y_m: float | None = None
    arm_length_m: float = 0.0
    arm_azimuth_deg: float = 0.0
    label: str = ""

    def __post_init__(self) -> None:
        _positive("mounting_height_m", self.mounting_height_m)
        _positive("flux_lm", self.flux_lm)
        _non_negative("arm_length_m", self.arm_length_m)
        if self.arm_length_m > 0 and (self.support_x_m is None or self.support_y_m is None):
            raise ValueError("un brazo requiere support_x_m y support_y_m")
        if self.arm_length_m > 0:
            arm_rad = math.radians(self.arm_azimuth_deg)
            expected_x = self.support_x_m + self.arm_length_m * math.cos(arm_rad)
            expected_y = self.support_y_m + self.arm_length_m * math.sin(arm_rad)
            if math.hypot(self.x_m - expected_x, self.y_m - expected_y) > 1e-6:
                raise ValueError(
                    "x_m e y_m deben coincidir con el extremo definido por "
                    "support_x_m, support_y_m, arm_length_m y arm_azimuth_deg"
                )


@dataclass(frozen=True)
class LuminaireArrangement:
    """Installed luminaire positions and optional layout metadata."""

    placements: tuple[LuminairePlacement, ...]
    arrangement_type: ArrangementType | str = ArrangementType.CUSTOM
    nominal_spacing_m: float | None = None

    def __post_init__(self) -> None:
        if not self.placements:
            raise ValueError("la disposición debe contener al menos una luminaria")
        if self.nominal_spacing_m is not None:
            _positive("nominal_spacing_m", self.nominal_spacing_m)


@dataclass(frozen=True)
class QualityTargets:
    """Hard quality constraints; all values are in maintained conditions."""

    uo_min: float = 0.40
    ul_min: float = 0.60
    ti_max_pct: float = 15.0
    sr_min: float | None = None
    rei_min: float | None = None
    luminance_avg_min_cd_m2: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.uo_min <= 1.0:
            raise ValueError("uo_min debe estar entre 0 y 1")
        if not 0.0 <= self.ul_min <= 1.0:
            raise ValueError("ul_min debe estar entre 0 y 1")
        _non_negative("ti_max_pct", self.ti_max_pct)
        for name in ("sr_min", "rei_min", "luminance_avg_min_cd_m2"):
            value = getattr(self, name)
            if value is not None:
                _non_negative(name, value)


@dataclass(frozen=True)
class PhotometricCandidate:
    """Parametric candidate represented by an EULUMDAT I-table.

    `intensity_cd_per_klm` is indexed as [C][gamma] and remains in the unit
    used by EULUMDAT. The actual flux used by the installation is declared
    separately in `flux_lm`.
    """

    c_angles_deg: tuple[float, ...]
    gamma_angles_deg: tuple[float, ...]
    intensity_cd_per_klm: tuple[tuple[float, ...], ...]
    flux_lm: float
    manufacturer: str = "SALVI"
    luminaire_name: str = "SALVI Optimized Road Distribution"
    symmetry: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _positive("flux_lm", self.flux_lm)
        if len(self.c_angles_deg) < 2 or len(self.gamma_angles_deg) < 2:
            raise ValueError("la tabla debe tener al menos 2 ángulos C y 2 ángulos gamma")
        if any(
            self.c_angles_deg[index + 1] <= self.c_angles_deg[index]
            for index in range(len(self.c_angles_deg) - 1)
        ):
            raise ValueError("los ángulos C deben ser estrictamente crecientes")
        if any(
            self.gamma_angles_deg[index + 1] <= self.gamma_angles_deg[index]
            for index in range(len(self.gamma_angles_deg) - 1)
        ):
            raise ValueError("los ángulos gamma deben ser estrictamente crecientes")
        if len(self.intensity_cd_per_klm) != len(self.c_angles_deg):
            raise ValueError("la matriz de intensidades no coincide con los planos C")
        gamma_count = len(self.gamma_angles_deg)
        for row in self.intensity_cd_per_klm:
            if len(row) != gamma_count:
                raise ValueError("cada fila de intensidades debe tener todos los ángulos gamma")
            if any(float(value) < 0 for value in row):
                raise ValueError("las intensidades no pueden ser negativas")
        if self.symmetry not in (0, 1, 2, 3, 4):
            raise ValueError("symmetry debe ser un código EULUMDAT entre 0 y 4")


@dataclass(frozen=True)
class CalculationMetrics:
    """Calculated quality metrics for one road layout."""

    luminance_avg_cd_m2: float | None = None
    uo: float | None = None
    ul: float | None = None
    ti_pct: float | None = None
    sr: float | None = None
    rei: float | None = None
    band_illuminance_lx: dict[str, float] = field(default_factory=dict)
    building_vertical_illuminance_lx: dict[str, float] = field(default_factory=dict)
    building_window_illuminance_lx: dict[str, float] = field(default_factory=dict)
    intrusion_max_lx: float | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class IntrusionLimits:
    """Project-wide optional limits for light sent to adjacent properties."""

    max_vertical_illuminance_lx: float | None = None
    max_window_illuminance_lx: float | None = None

    def __post_init__(self) -> None:
        for name in ("max_vertical_illuminance_lx", "max_window_illuminance_lx"):
            value = getattr(self, name)
            if value is not None:
                _non_negative(name, value)


@dataclass(frozen=True)
class OptimizationRequest:
    """Complete input contract for the future optimization endpoint."""

    geometry: RoadGeometry
    arrangement: LuminaireArrangement
    targets: QualityTargets
    intrusion_limits: IntrusionLimits = field(default_factory=IntrusionLimits)
    normative_profile: NormativeProfile = NormativeProfile.EN13201_2015
    candidate_name: str = "SALVI road LDT candidate"
    max_candidates: int = 5000
    require_longitudinal_symmetry: bool = True

    def __post_init__(self) -> None:
        if self.max_candidates < 1:
            raise ValueError("max_candidates debe ser mayor que cero")
