#!/usr/bin/env python3
"""Consumption engine. Replicates the Excel calculation."""

def calcular_consumo_periodo(system_power_w: float, hours: float,
                              presence_ratio: float, dimming_presence: float,
                              dimming_no_presence: float) -> float:
    """E = P * h * (pres * dim_pres + (1-pres) * dim_no_pres)"""
    return system_power_w * hours * (
        presence_ratio * dimming_presence +
        (1 - presence_ratio) * dimming_no_presence
    )

def calcular_consumo_noche(system_power_w: float, night_duration_h: float,
                            periods: list, aux_wh: float = 0) -> dict:
    """
    periods: list of dicts with duration_pct (0-1) OR duration_h, 
             presence_ratio (0-1), dimming_presence (0-1), dimming_no_presence (0-1)
    Returns {'total_wh': float, 'periods': [{'duration_h', 'wh'}]}
    """
    result_periods = []
    total = 0
    for p in periods:
        if 'duration_h' in p and p['duration_h']:
            h = float(p['duration_h'])
        else:
            h = float(p.get('duration_pct', 0.333)) * night_duration_h
        wh = calcular_consumo_periodo(
            system_power_w, h,
            float(p.get('presence_ratio', 0.5)),
            float(p.get('dimming_presence', 1.0)),
            float(p.get('dimming_no_presence', 0.3))
        )
        total += wh
        result_periods.append({'duration_h': round(h, 2), 'wh': round(wh, 2)})
    total += aux_wh
    return {'total_wh': round(total, 2), 'periods': result_periods}

def build_hourly_consumption(annual_schedule: list, system_power_w: float,
                              periods_def: list, aux_wh_night: float = 0) -> list:
    """
    Build 8760-element list of Wh per hour.
    Night hours get consumption distributed across periods.
    Day hours = 0.
    """
    hourly = [0.0] * 8760
    
    for entry in annual_schedule:
        day_idx = entry['day_of_year'] - 1  # 0-indexed
        on_h = entry['on_hour']
        off_h = entry['off_hour']
        night_h = entry['duration_h']
        if night_h <= 0:
            continue
        
        result = calcular_consumo_noche(system_power_w, night_h, periods_def, aux_wh_night)
        total_wh = result['total_wh']
        
        wh_per_hour = total_wh / max(night_h, 1)
        
        start_h = int(on_h)
        end_h = int(off_h) + 1
        
        for h_offset in range(start_h, end_h + 1):
            actual_hour = day_idx * 24 + h_offset
            if 0 <= actual_hour < 8760:
                hourly[actual_hour] = wh_per_hour
    
    return hourly

def calcular_consumo_anual(system_power_w: float, lat: float, lon: float,
                            year: int, periods_def: list, aux_wh: float = 0,
                            margin_on: int = -15, margin_off: int = 15) -> dict:
    """Full annual consumption calculation."""
    from modules.geo import build_annual_schedule
    schedule = build_annual_schedule(lat, lon, year, margin_on, margin_off)
    
    daily = []
    monthly = [0.0] * 12
    
    for entry in schedule:
        result = calcular_consumo_noche(system_power_w, entry['duration_h'], periods_def, aux_wh)
        wh = result['total_wh']
        daily.append(wh)
        monthly[entry['month'] - 1] += wh
    
    annual = sum(monthly)
    avg_night = annual / len(daily) if daily else 0
    
    hourly = build_hourly_consumption(schedule, system_power_w, periods_def, aux_wh)
    
    return {
        'daily_wh': daily,
        'monthly_wh': monthly,
        'annual_wh': round(annual, 1),
        'avg_night_wh': round(avg_night, 1),
        'hourly_wh': hourly,
        'schedule': schedule,
    }
