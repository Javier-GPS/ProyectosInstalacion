#!/usr/bin/env python3
"""TCO optimizer."""

def calcular_capex(product: dict, costs: dict, include_smartec=True, include_sensor=False) -> dict:
    margin = costs.get('gross_margin', 0.62)
    panel_c = product['pv_peak_power_wp'] * costs['panel_eur_wp']
    bat_c = product['battery_nominal_wh'] * costs['battery_eur_wh']
    ctrl_c = costs['controller_eur']
    inst_c = costs['installation_eur']
    struct_c = costs['structure_eur']
    smartec_c = costs['smartec_node_eur'] if include_smartec else 0
    sensor_c = costs['presence_sensor_eur'] if include_sensor else 0
    
    total_cost = panel_c + bat_c + ctrl_c + inst_c + struct_c + smartec_c + sensor_c
    sale_price = total_cost / (1 - margin)
    
    return {
        'cost': round(total_cost, 2),
        'sale_price': round(sale_price, 2),
        'breakdown': {
            'panel': round(panel_c, 2),
            'battery': round(bat_c, 2),
            'controller': ctrl_c,
            'installation': inst_c,
            'structure': struct_c,
            'smartec_node': smartec_c,
            'sensor': sensor_c,
        }
    }

def calcular_tco_10y(capex_cost: float, grid_energy_kwh_y: float = 0,
                      electricity_cost: float = 0.12, costs: dict = None,
                      battery_nominal_wh: float = 0,
                      residual_year10: float = 0.70,
                      gross_margin: float = 0.62) -> dict:
    if costs is None:
        costs = {}
    cleaning = costs.get('cleaning_annual_eur', 25) * 10
    maintenance = costs.get('maintenance_annual_eur', 25) * 10
    bat_replacement = costs.get('battery_replacement_eur', 200) if residual_year10 < 0.80 else 0
    grid_cost = grid_energy_kwh_y * electricity_cost * 10
    
    total_cost = capex_cost + cleaning + maintenance + bat_replacement + grid_cost
    sale_price = total_cost / (1 - gross_margin)
    
    return {
        'cost': round(total_cost, 2),
        'sale_price': round(sale_price, 2),
        'breakdown': {
            'capex': capex_cost,
            'cleaning_10y': cleaning,
            'maintenance_10y': maintenance,
            'battery_replacement': bat_replacement,
            'grid_energy_10y': round(grid_cost, 2),
        }
    }

def calcular_co2_evitado(annual_kwh_solar: float, country_co2_factor: float,
                          grid_energy_kwh_y: float = 0, years: int = 10) -> float:
    avoided = (annual_kwh_solar - grid_energy_kwh_y) * country_co2_factor * years
    return round(max(avoided, 0), 1)

def rankear_candidatos(candidates: list, objective: str = 'min_tco_10y',
                        max_failure_rate_pct: float = 2.0) -> list:
    valid = [c for c in candidates if c.get('annual_failure_rate_pct', 100) <= max_failure_rate_pct]
    invalid = [c for c in candidates if c.get('annual_failure_rate_pct', 100) > max_failure_rate_pct]

    if objective == 'min_tco_10y':
        valid.sort(key=lambda c: c.get('tco_10y_sale', float('inf')))
    elif objective == 'min_capex':
        valid.sort(key=lambda c: c.get('capex_sale', float('inf')))
    elif objective == 'max_reliability':
        valid.sort(key=lambda c: (c.get('annual_failure_rate_pct', 100), c.get('tco_10y_sale', float('inf'))))
    elif objective == 'min_grid':
        valid.sort(key=lambda c: c.get('grid_energy_kwh_y', float('inf')))

    # Identify scenario winners among valid candidates
    min_capex_pid = min(valid, key=lambda c: c.get('capex_sale', float('inf')))['product_id'] if valid else None
    min_fail_pid  = min(valid, key=lambda c: c.get('annual_failure_rate_pct', 100))['product_id'] if valid else None
    hybrid_pids   = {c['product_id'] for c in valid if c.get('grid_energy_kwh_y', 0) > 0}

    for i, c in enumerate(valid):
        c['rank'] = i + 1
        c['meets_reliability'] = True
        c['recommended'] = (i == 0)
        tags = []
        if i == 0:
            tags.append('recommended')
        # Only label low_capex / max_reliability if different from recommended
        if min_capex_pid and c['product_id'] == min_capex_pid and i != 0:
            tags.append('low_capex')
        if min_fail_pid and c['product_id'] == min_fail_pid and i != 0:
            tags.append('max_reliability')
        if c['product_id'] in hybrid_pids:
            tags.append('hybrid')
        c['scenario_tags'] = tags
        c['scenario_type'] = tags[0] if tags else 'alternative'

    for c in invalid:
        c['rank'] = len(valid) + 1
        c['meets_reliability'] = False
        c['recommended'] = False
        c['scenario_tags'] = []
        c['scenario_type'] = 'invalid'

    return valid + invalid
