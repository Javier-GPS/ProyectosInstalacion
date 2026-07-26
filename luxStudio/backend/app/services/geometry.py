from ..schemas.models import CalculationConfig


def arm_projection(config: CalculationConfig) -> tuple[float, float]:
    length = max(float(config.arm_length), 0.0)
    # ponytail: tilt rotates the photometry/head; bracket dimensions stay as entered.
    return length, 0.0


def luminaire_mounting_height(config: CalculationConfig) -> float:
    return max(0.1, float(config.height))


def effective_overhang(config: CalculationConfig) -> float:
    return max(float(config.arm_length), 0.0) - config.pole_offset
