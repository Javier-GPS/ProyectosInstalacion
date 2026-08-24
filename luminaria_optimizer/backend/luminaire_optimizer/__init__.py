"""Independent core for the eight-group luminaire optimizer."""

from .hl2x import (
    HL2X_CCT_FLUX_LM,
    HL2X_CURRENT_MAX_MA,
    HL2X_CURRENT_STEP_MA,
    Hl2xModel,
    LuminaireOperatingPoint,
    calculate_luminaire_operating_point,
)
from .ldt import LdtPhotometry, parse_ldt, write_ldt
from .composition import DEFAULT_GROUP_ANGLES_DEG, compose_luminaire
from .r_tables import ReducedLuminanceTable, load_rtable
from .normative import M_CLASS_REQUIREMENTS, MClassRequirements, requirements_for
from .road import RoadCalculation, RoadMetrics, RoadScenario, calculate_reference_road, calculate_road
from .optimizer import OptimizationResult, optimize_currents, optimize_currents_and_tilt, optimize_currents_symmetric
from .config import DEFAULT_GROUP_FLUX_LM
from .rayset import Tm25Error, Tm25Header, Tm25RaySet, parse_tm25

__all__ = [
    "DEFAULT_GROUP_ANGLES_DEG",
    "DEFAULT_GROUP_FLUX_LM",
    "HL2X_CCT_FLUX_LM",
    "HL2X_CURRENT_MAX_MA",
    "HL2X_CURRENT_STEP_MA",
    "Hl2xModel",
    "LdtPhotometry",
    "LuminaireOperatingPoint",
    "M_CLASS_REQUIREMENTS",
    "MClassRequirements",
    "OptimizationResult",
    "RoadCalculation",
    "RoadMetrics",
    "RoadScenario",
    "ReducedLuminanceTable",
    "calculate_luminaire_operating_point",
    "compose_luminaire",
    "load_rtable",
    "calculate_road",
    "calculate_reference_road",
    "optimize_currents",
    "optimize_currents_and_tilt",
    "optimize_currents_symmetric",
    "parse_ldt",
    "write_ldt",
    "requirements_for",
    "Tm25Error",
    "Tm25Header",
    "Tm25RaySet",
    "parse_tm25",
]
