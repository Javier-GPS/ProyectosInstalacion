"""Validación de entradas del proyecto antes de ejecutar el motor.

Esta capa no calcula ni modifica parámetros; únicamente evita lanzar una
ejecución con una definición de túnel incompleta o incoherente.
"""

from __future__ import annotations

from typing import Any


def _number(params: dict[str, Any], key: str, default: float | None = None) -> float | None:
    value = params.get(key, default)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_tunnel_params(params: dict[str, Any]) -> dict[str, list[str] | bool]:
    """Return a stable, UI-friendly validation result for direct tunnel input."""
    errors: list[str] = []
    warnings: list[str] = []

    required_positive = {
        "length_m": "La longitud del túnel",
        "width_m": "El ancho interior",
        "height_m": "La altura libre",
        "speed_kmh": "La velocidad de diseño",
    }
    for key, label in required_positive.items():
        value = _number(params, key)
        if value is None or value <= 0:
            errors.append(f"{label} debe ser un número mayor que cero.")

    lanes = _number(params, "num_lanes")
    lane_width = _number(params, "lane_width_m")
    width = _number(params, "width_m")
    if lanes is None or int(lanes) < 1:
        errors.append("El número de carriles debe ser al menos 1.")
    if lane_width is None or lane_width <= 0:
        errors.append("El ancho de carril debe ser mayor que cero.")
    if lanes is not None and lane_width is not None and width is not None:
        carriageway = int(lanes) * lane_width
        if carriageway > width:
            errors.append("La calzada no puede ser más ancha que el túnel.")

    traffic_direction = params.get("traffic_direction", "one_way")
    if traffic_direction not in {"one_way", "two_way"}:
        errors.append("El sentido de circulación no es válido.")

    orientation = params.get("portal_orientation", "S")
    if orientation not in {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}:
        errors.append("La orientación del portal A no es válida.")

    for key, label, low, high in (
        ("wall_reflectance", "La reflectancia de paredes", 0.05, 0.95),
        ("rho_wall", "La reflectancia de paredes (radiosidad)", 0.05, 0.95),
        ("rho_ceiling", "La reflectancia del techo", 0.05, 0.95),
        ("maintenance_factor", "El factor de mantenimiento", 0.01, 1.0),
    ):
        value = _number(params, key)
        if value is not None and not low <= value <= high:
            errors.append(f"{label} debe estar entre {low:g} y {high:g}.")

    if _number(params, "length_m") is not None and _number(params, "speed_kmh") is not None:
        if _number(params, "length_m") < 30:
            warnings.append("La longitud es muy corta; revisa que CIE 88 sea aplicable al proyecto.")

    return {"valid": not errors, "errors": errors, "warnings": warnings}

