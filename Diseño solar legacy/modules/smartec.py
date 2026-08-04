#!/usr/bin/env python3
"""Smartec initial profile generator."""

def generar_perfil_smartec(night_profile: list, battery_nominal_wh: float,
                            dod_max: float = 0.85, min_soc_pct: float = 0.15,
                            hybrid_enabled: bool = False) -> dict:
    """Generate initial Smartec configuration."""
    dimming_profile = []
    for i, p in enumerate(night_profile):
        dimming_profile.append({
            'period': i + 1,
            'duration_pct': p.get('duration_pct', 0.333),
            'presence_ratio': p.get('presence_ratio', 0.5),
            'dim_with_presence_pct': int(p.get('dimming_presence', 1.0) * 100),
            'dim_no_presence_pct': int(p.get('dimming_no_presence', 0.3) * 100),
        })
    
    return {
        'version': 'Salvi Solar 2026.1',
        'dimming_profile': dimming_profile,
        'battery_thresholds': {
            'nominal_wh': battery_nominal_wh,
            'usable_wh': round(battery_nominal_wh * dod_max, 1),
            'min_soc_pct': int(min_soc_pct * 100),
            'protection_threshold_pct': 50,
            'grid_threshold_pct': 20 if hybrid_enabled else None,
        },
        'protection_mode': {
            'enabled': True,
            'strategy': 'progressive_dimming',
            'min_dim_with_presence_pct': 50,
            'min_dim_no_presence_pct': 0,
            'description': 'Reduce consumo progresivamente cuando SOC < 50% del util',
        },
        'alarms': [
            {'type': 'low_battery', 'threshold_pct': int(min_soc_pct * 100 + 5), 'action': 'alert'},
            {'type': 'low_production', 'threshold_vs_expected_pct': 30, 'action': 'alert'},
            {'type': 'possible_soiling', 'consecutive_low_days': 5, 'action': 'recommend_cleaning'},
        ],
        'hybrid_rules': {
            'source': 'grid_24v',
            'enable_threshold_pct': 20,
            'allow_grid_charge': True,
        } if hybrid_enabled else None,
    }
