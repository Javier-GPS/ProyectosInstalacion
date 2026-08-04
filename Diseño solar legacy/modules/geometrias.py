#!/usr/bin/env python3
"""Soiling factors for Salvi geometries."""

SOILING_ENV_BASE = {
    'verde_lluviosa': 0.04,
    'urbana_normal': 0.07,
    'polvo_medio': 0.10,
    'desierto_alto': 0.20,
}

SOILING_GEOMETRY_FACTOR = {
    'sil_horizontal': 1.25,
    'sil_independent': 1.00,
    'double_vertical_eo': 0.60,
    'double_vertical_ns': 0.60,
    'cylinder_250': 0.50,
    'cylinder_300': 0.50,
    'cylinder_350': 0.50,
    'custom_orientable': 1.00,  # panel fijo inclinado, suciedad estándar
}

SOILING_ENV_LABELS = {
    'verde_lluviosa': 'Verde / lluviosa',
    'urbana_normal': 'Urbana normal',
    'polvo_medio': 'Polvo medio',
    'desierto_alto': 'Desierto / polvo alto',
}

def get_soiling_loss(environment: str, geometry_type: str) -> float:
    """Returns soiling loss as fraction (0-1)."""
    base = SOILING_ENV_BASE.get(environment, 0.07)
    geo_key = geometry_type if geometry_type in SOILING_GEOMETRY_FACTOR else 'sil_horizontal'
    factor = SOILING_GEOMETRY_FACTOR.get(geo_key, 1.0)
    return min(base * factor, 0.40)

def apply_soiling(hourly_wh: list, soiling_loss: float) -> list:
    """Apply (1 - soiling_loss) to all hourly values."""
    factor = 1.0 - soiling_loss
    return [v * factor for v in hourly_wh]
