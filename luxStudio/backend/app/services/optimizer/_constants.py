"""Shared constants for the optimizer sub-package."""

OPTIMIZATION_OBJECTIVE = "Minimize luminaire power while satisfying all active EN 13201 criteria"
ADVANCED_OPTIMIZATION_OBJECTIVE = "Fit the solution close to the EN 13201 limits while staying compliant"
ADVANCED_OBJECTIVE_LABELS = {
    "technical_limits": "Fit the solution close to the EN 13201 limits while staying compliant",
    "min_power": "Minimize luminaire power while satisfying all active EN 13201 criteria",
    "max_spacing": "Maximize pole spacing while satisfying all active EN 13201 criteria",
}
OPTIMIZATION_MIN_POWER = 1.0
OPTIMIZATION_MAX_POWER = 500.0
OPTIMIZATION_PRECISION = 0.1
SPACING_CANDIDATES = [60.0, 55.0, 50.0, 45.0, 40.0, 35.0, 30.0, 25.0, 20.0, 15.0, 10.0, 5.0]
HEIGHT_CANDIDATES = [4.0, 6.0, 8.0, 9.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 25.0, 30.0, 35.0, 40.0]
ARM_LENGTH_CANDIDATES = [0.0, 0.5, 1.0, 1.5, 2.0]
ARM_TILT_CANDIDATES = [0.0, 5.0, 10.0, 15.0]
OPTIMIZATION_FIXED_PARAMETERS = [
    "road_width",
    "sidewalk_left",
    "sidewalk_right",
    "lanes",
    "pavement",
    "lighting_class",
    "maintenance_factor",
    "arrangement",
    "spacing",
    "height",
    "armLength",
    "pole_offset",
    "pole_side",
    "armTiltAngle",
    "power",
    "manufacturer",
    "model_family",
    "optic_family",
    "cct",
    "cri",
]
