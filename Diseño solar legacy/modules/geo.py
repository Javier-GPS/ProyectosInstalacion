#!/usr/bin/env python3
"""Civil twilight and night schedule. Uses astral library."""
import datetime
from astral import LocationInfo
from astral.sun import sun

def get_civil_twilight(lat: float, lon: float, date: datetime.date):
    """Returns (dusk, dawn) as UTC datetime objects (civil twilight evening/morning).
    Returns (None, None) for polar day/night."""
    try:
        loc = LocationInfo(latitude=lat, longitude=lon)
        s = sun(loc.observer, date=date, tzinfo=datetime.timezone.utc)
        return s['dusk'], s['dawn']
    except Exception:
        return None, None

def build_annual_schedule(lat: float, lon: float, year: int = 2024,
                           margin_on_min: int = -15,
                           margin_off_min: int = 15) -> list:
    """
    Returns list of 365 dicts. Skips Feb 29 for leap years.
    Each dict: {date, day_of_year, month, on_hour, off_hour, duration_h, is_polar_night, is_polar_day}
    on_hour/off_hour: float hours since midnight UTC (off_hour can be >24 if crosses midnight)
    margin_on_min: negative = turn on BEFORE dusk (default -15)
    margin_off_min: positive = turn off AFTER dawn (default +15)
    """
    schedule = []
    start = datetime.date(year, 1, 1)
    day_num = 0
    for i in range(366 if (year % 4 == 0) else 365):
        d = start + datetime.timedelta(days=i)
        # Skip Feb 29 for consistency
        if d.month == 2 and d.day == 29:
            continue
        day_num += 1
        dusk, dawn = get_civil_twilight(lat, lon, d)
        
        if dusk is None or dawn is None:
            # Polar case: estimate
            is_polar_night = (lat > 60 and 4 <= d.month <= 8) or (lat < -60 and (d.month <= 2 or d.month >= 10))
            schedule.append({
                'date': d.isoformat(),
                'day_of_year': day_num,
                'month': d.month,
                'on_hour': 18.0,
                'off_hour': 30.0,
                'duration_h': 12.0,
                'is_polar_night': is_polar_night,
                'is_polar_day': not is_polar_night,
            })
            continue
        
        # Apply margins
        on_dt = dusk + datetime.timedelta(minutes=margin_on_min)
        off_dt = dawn + datetime.timedelta(minutes=margin_off_min)
        
        # Convert to float hours since midnight UTC
        on_h = on_dt.hour + on_dt.minute / 60 + on_dt.second / 3600
        off_h = off_dt.hour + off_dt.minute / 60 + off_dt.second / 3600
        
        # If dawn is next day (typical for most locations)
        if off_h < on_h:
            off_h += 24
        
        duration_h = off_h - on_h
        if duration_h <= 0:
            duration_h = 0.1
            
        schedule.append({
            'date': d.isoformat(),
            'day_of_year': day_num,
            'month': d.month,
            'on_hour': round(on_h, 3),
            'off_hour': round(off_h, 3),
            'duration_h': round(duration_h, 3),
            'is_polar_night': False,
            'is_polar_day': False,
        })
    
    return schedule
