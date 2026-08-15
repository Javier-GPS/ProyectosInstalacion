"""Electrical, thermal and luminous-flux model for LUXEON HL2X 3535.

The structure follows SALVI's existing model: current determines ``KI`` and
``Vf``; electrical power determines the thermal state; junction temperature
determines ``KT`` and therefore flux. The curve points are versioned and can
later be replaced by a more precise digitisation for the exact HL2X bin.
"""
from __future__ import annotations

from dataclasses import dataclass


HL2X_CURRENT_MAX_MA = 2000.0
HL2X_CURRENT_STEP_MA = 50.0
HL2X_REFERENCE_CURRENT_MA = 700.0
HL2X_REFERENCE_TJ_C = 85.0
HL2X_CURVE_VERSION = "DS288-HL2X-2026-provisional-digitisation-v1"
HL2X_TJ_MAX_C = 135.0
HL2X_MAX_INPUT_POWER_W = 30.0
HL2X_VF_TEMP_COEFF_V_PER_C = -0.0016
HL2X_CCT_FLUX_LM: dict[int, dict[int, float]] = {
    70: {2200: 306, 2700: 342, 3000: 355, 3500: 363, 4000: 375, 5000: 379, 5700: 379, 6500: 372},
    80: {2200: 251, 2700: 289, 3000: 314, 4000: 333, 5000: 339, 5700: 344},
    90: {2700: 247, 3000: 263, 3500: 271, 4000: 282, 5000: 298, 5700: 300},
}

# Normalised curves at Tj=85 C. These points are deliberately data, not a
# hidden power-law approximation, and are replaced when measured HL2X data is
# available.
HL2X_KI_POINTS = ((0.0, 0.0), (250.0, 0.38), (500.0, 0.73), (700.0, 1.0), (1000.0, 1.38), (1500.0, 1.92), (2000.0, 2.45))
HL2X_VF25_POINTS = ((250.0, 2.63), (500.0, 2.72), (700.0, 2.77), (1000.0, 2.84), (1500.0, 2.97), (2000.0, 3.12))
HL2X_KT_POINTS = ((25.0, 1.09), (85.0, 1.0), (125.0, 0.92), (135.0, 0.90))


@dataclass(frozen=True)
class Hl2xModel:
    reference_group_flux_lm: float
    reference_cct_k: int = 4000
    reference_cri: int = 70
    reference_current_ma: float = HL2X_REFERENCE_CURRENT_MA
    reference_tj_c: float = HL2X_REFERENCE_TJ_C
    ambient_temperature_c: float = 25.0
    ts_coefficient_c_per_w: float = 0.3
    rth_junction_to_solder_c_per_w: float = 1.1
    driver_efficiency: float = 0.9
    leds_per_group: int = 3
    group_count: int = 8
    max_input_power_w: float = HL2X_MAX_INPUT_POWER_W
    multiplexing_mode: str = "simultaneous"

    def __post_init__(self) -> None:
        if self.reference_group_flux_lm <= 0:
            raise ValueError("reference_group_flux_lm must be positive")
        if not 0 < self.driver_efficiency <= 1:
            raise ValueError("driver_efficiency must be in (0, 1]")
        if self.ts_coefficient_c_per_w < 0 or self.rth_junction_to_solder_c_per_w < 0:
            raise ValueError("thermal coefficients cannot be negative")
        if self.max_input_power_w <= 0:
            raise ValueError("max_input_power_w must be positive")
        if self.multiplexing_mode not in {"simultaneous", "time_multiplexed"}:
            raise ValueError("multiplexing_mode must be simultaneous or time_multiplexed")
        self._published_flux(self.reference_cct_k, self.reference_cri)

    @staticmethod
    def _published_flux(cct_k: int, cri: int) -> float:
        try:
            return HL2X_CCT_FLUX_LM[cri][cct_k]
        except KeyError as exc:
            raise ValueError(f"HL2X datasheet has no published combination {cct_k}K/{cri}CRI") from exc

    @staticmethod
    def _interpolate(points: tuple[tuple[float, float], ...], x: float) -> float:
        if x <= points[0][0]:
            return points[0][1]
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x <= x1:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return points[-1][1]

    def _ki(self, current_ma: float) -> float:
        return self._interpolate(HL2X_KI_POINTS, current_ma) / self._interpolate(HL2X_KI_POINTS, self.reference_current_ma)

    def _vf25(self, current_ma: float) -> float:
        return self._interpolate(HL2X_VF25_POINTS, current_ma)

    def _kt(self, tj_c: float) -> float:
        return self._interpolate(HL2X_KT_POINTS, tj_c) / self._interpolate(HL2X_KT_POINTS, self.reference_tj_c)

    def _published_ratio(self, cct_k: int, cri: int) -> float:
        return self._published_flux(cct_k, cri) / self._published_flux(self.reference_cct_k, self.reference_cri)

    def point(self, current_ma: float, cct_k: int, cri: int, *, tj_c: float = HL2X_REFERENCE_TJ_C, group_tj_ref_c: float | None = None) -> "Hl2xPoint":
        if current_ma < 0 or current_ma > HL2X_CURRENT_MAX_MA:
            raise ValueError(f"current must be between 0 and {HL2X_CURRENT_MAX_MA:g} mA")
        cct_ratio = self._published_ratio(cct_k, cri)
        if current_ma == 0:
            return Hl2xPoint(current_ma=0.0, tj_c=tj_c, vf_v=0.0, led_power_w=0.0, group_power_w=0.0, led_flux_lm=0.0, group_flux_lm=0.0, ki=0.0, kt=self._kt(tj_c), driver_power_w=0.0)
        vf = self._vf25(current_ma) + HL2X_VF_TEMP_COEFF_V_PER_C * (tj_c - 25.0)
        led_power = current_ma / 1000.0 * vf
        kt = self._kt(tj_c)
        # ``reference_group_flux_lm`` is the measured/declared LDT flux for
        # all three LED plus lens. Use it as the absolute anchor instead of
        # replacing the optical assembly with an LED-only datasheet estimate.
        reference_kt = self._kt(self.reference_tj_c)
        group_flux = self.reference_group_flux_lm * cct_ratio * self._ki(current_ma) * kt / reference_kt
        led_flux = group_flux / self.leds_per_group
        group_power = self.leds_per_group * led_power
        return Hl2xPoint(current_ma, tj_c, vf, led_power, group_power, led_flux, group_flux, self._ki(current_ma), kt, group_power / self.driver_efficiency)


@dataclass(frozen=True)
class Hl2xPoint:
    current_ma: float
    tj_c: float
    vf_v: float
    led_power_w: float
    group_power_w: float
    led_flux_lm: float
    group_flux_lm: float
    ki: float
    kt: float
    driver_power_w: float


@dataclass(frozen=True)
class LuminaireOperatingPoint:
    currents_ma: tuple[float, ...]
    groups: tuple[Hl2xPoint, ...]
    solder_temperature_c: float
    total_led_power_w: float
    total_driver_power_w: float
    total_flux_lm: float
    converged: bool
    power_limit_ok: bool


def _validate_currents(currents_ma: tuple[float, ...], model: Hl2xModel) -> None:
    if len(currents_ma) != model.group_count:
        raise ValueError(f"expected {model.group_count} group currents")
    for current in currents_ma:
        if current < 0 or current > HL2X_CURRENT_MAX_MA:
            raise ValueError("group current is outside 0..2000 mA")
        if abs(current / HL2X_CURRENT_STEP_MA - round(current / HL2X_CURRENT_STEP_MA)) > 1e-9:
            raise ValueError("group current must use 50 mA steps")


def calculate_luminaire_operating_point(currents_ma: list[float] | tuple[float, ...], model: Hl2xModel, cct_k: int, cri: int) -> LuminaireOperatingPoint:
    currents = tuple(float(value) for value in currents_ma)
    _validate_currents(currents, model)
    tjs = [HL2X_REFERENCE_TJ_C for _ in currents]
    solder = model.ambient_temperature_c
    converged = False
    for _ in range(30):
        points = [model.point(current, cct_k, cri, tj_c=tj) for current, tj in zip(currents, tjs)]
        total_led_power = sum(point.group_power_w for point in points)
        new_solder = model.ambient_temperature_c + model.ts_coefficient_c_per_w * total_led_power
        new_tjs = [new_solder + model.rth_junction_to_solder_c_per_w * point.led_power_w for point in points]
        if max([abs(new_solder - solder), *(abs(a - b) for a, b in zip(new_tjs, tjs))]) < 0.01:
            solder, tjs, converged = new_solder, new_tjs, True
            break
        solder, tjs = new_solder, new_tjs
    points = tuple(model.point(current, cct_k, cri, tj_c=tj) for current, tj in zip(currents, tjs))
    if any(point.tj_c > HL2X_TJ_MAX_C for point in points):
        raise ValueError("HL2X junction temperature exceeds the 2 A operating limit")
    total_driver_power = sum(point.driver_power_w for point in points)
    return LuminaireOperatingPoint(
        currents, points, solder, sum(point.group_power_w for point in points),
        total_driver_power, sum(point.group_flux_lm for point in points),
        converged, total_driver_power <= model.max_input_power_w + 1e-9,
    )
