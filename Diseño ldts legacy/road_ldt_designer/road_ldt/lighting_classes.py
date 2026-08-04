"""EN 13201-2:2015 M-class performance catalogue."""
from __future__ import annotations

from dataclasses import dataclass

from .domain import QualityTargets


@dataclass(frozen=True)
class MLightingClass:
    code: str
    luminance_avg_min_cd_m2: float
    uo_min: float
    ul_min: float
    wet_uo_min: float
    ti_max_pct: float
    rei_min: float

    def quality_targets(
        self,
        *,
        include_rei: bool = True,
    ) -> QualityTargets:
        """Convert the class into the dry-road targets used by the engine."""

        return QualityTargets(
            luminance_avg_min_cd_m2=self.luminance_avg_min_cd_m2,
            uo_min=self.uo_min,
            ul_min=self.ul_min,
            ti_max_pct=self.ti_max_pct,
            rei_min=self.rei_min if include_rei else None,
        )


M_LIGHTING_CLASSES: dict[str, MLightingClass] = {
    item.code: item
    for item in (
        MLightingClass("M1", 2.00, 0.40, 0.70, 0.15, 10.0, 0.35),
        MLightingClass("M2", 1.50, 0.40, 0.70, 0.15, 10.0, 0.35),
        MLightingClass("M3", 1.00, 0.40, 0.60, 0.15, 15.0, 0.30),
        MLightingClass("M4", 0.75, 0.40, 0.60, 0.15, 15.0, 0.30),
        MLightingClass("M5", 0.50, 0.35, 0.40, 0.15, 15.0, 0.30),
        MLightingClass("M6", 0.30, 0.35, 0.40, 0.15, 20.0, 0.30),
    )
}


def get_m_lighting_class(code: str) -> MLightingClass:
    name = str(code).upper()
    if name not in M_LIGHTING_CLASSES:
        raise ValueError(f"clase luminotécnica M no disponible: {code}")
    return M_LIGHTING_CLASSES[name]


def list_m_lighting_classes() -> tuple[str, ...]:
    return tuple(M_LIGHTING_CLASSES)
