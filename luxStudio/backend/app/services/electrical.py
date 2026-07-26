"""Electrical conversions shared by calculation and optimization services."""

from __future__ import annotations


def total_system_power(led_power: float, driver_efficiency: float | None) -> float:
    """Convert total LED power to luminaire input power."""
    efficiency = 1.0 if driver_efficiency is None else float(driver_efficiency)
    return float(led_power) / max(efficiency, 0.01)
