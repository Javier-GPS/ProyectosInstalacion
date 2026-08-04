#!/usr/bin/env python3
"""Battery SOC simulation."""

def build_night_map(annual_schedule: list) -> dict:
    """Pre-build hour->day_index map from schedule. Call once and pass to simular_bateria_anual."""
    night_map = {}
    if not annual_schedule:
        return night_map
    for entry in annual_schedule:
        d = entry['day_of_year'] - 1
        on_h  = entry['on_hour']
        off_h = entry['off_hour']
        for h_off in range(int(on_h), int(off_h) + 2):
            actual_h = d * 24 + h_off
            if 0 <= actual_h < 8760:
                night_map[actual_h] = d
    return night_map


def simular_bateria_anual(solar_hourly_wh: list, consumo_hourly_wh: list,
                           bat_nominal_wh: float, dod_max: float = 0.85,
                           min_soc_pct: float = 0.15,
                           charge_eff: float = 0.97,
                           discharge_eff: float = 0.97,
                           smartec_protection: bool = True,
                           annual_schedule: list = None,
                           prebuilt_night_map: dict = None) -> dict:
    """
    Hourly SOC simulation for 8760 hours.
    Returns separate results for new battery and year-10 battery (70% residual).
    Pass prebuilt_night_map (from build_night_map) to avoid rebuilding it on every call.
    """
    night_map = prebuilt_night_map if prebuilt_night_map is not None else build_night_map(annual_schedule)

    def _sim(bat_nom):
        bat_usable = bat_nom * dod_max
        min_soc_wh = bat_nom * min_soc_pct
        protection_threshold = bat_usable * 0.5

        soc = bat_nom
        soc_hourly = []
        critical_flags = [False] * 365
        protection_night_flags = [False] * 365  # nights where Smartec protection activated
        night_start_soc = {}                     # day_idx → SOC_wh at first night hour (dusk)
        protected_hours = 0

        for h in range(8760):
            pv = solar_hourly_wh[h] if h < len(solar_hourly_wh) else 0
            load = consumo_hourly_wh[h] if h < len(consumo_hourly_wh) else 0

            # Track SOC at dusk (first hour of each night)
            if load > 0:
                prev_load = consumo_hourly_wh[h - 1] if h > 0 else 0
                if prev_load == 0:
                    d = night_map.get(h, -1)
                    if d >= 0 and d not in night_start_soc:
                        night_start_soc[d] = soc  # SOC before night consumption starts

            if smartec_protection and load > 0 and soc < protection_threshold:
                factor = max(0.2, soc / protection_threshold)
                load = load * factor
                protected_hours += 1
                d = night_map.get(h, -1)
                if d >= 0:
                    protection_night_flags[d] = True

            net = pv * charge_eff - load / discharge_eff
            new_soc = max(0.0, min(bat_nom, soc + net))

            if new_soc < min_soc_wh and load > 0:
                if h in night_map:
                    critical_flags[night_map[h]] = True

            soc_hourly.append(new_soc)
            soc = new_soc

        critical_nights = sum(critical_flags)
        annual_failure_rate = critical_nights / 365 * 100

        monthly_failures = [0] * 12
        monthly_soc_sum = [0.0] * 12

        if annual_schedule:
            for i, entry in enumerate(annual_schedule):
                if i < 365 and critical_flags[i]:
                    monthly_failures[entry['month'] - 1] += 1

        days_per_month = [31,28,31,30,31,30,31,31,30,31,30,31]
        monthly_soc_min = [100.0] * 12
        h = 0
        for m, days in enumerate(days_per_month):
            m_hours = days * 24
            if h + m_hours <= 8760:
                m_soc = soc_hourly[h:h+m_hours]
                if m_soc and bat_nom > 0:
                    avg_soc_pct  = sum(m_soc) / len(m_soc) / bat_nom * 100
                    _min_soc_val = min(m_soc) / bat_nom * 100
                else:
                    avg_soc_pct  = 0
                    _min_soc_val = 0
                monthly_soc_sum[m] = round(avg_soc_pct, 1)
                monthly_soc_min[m] = round(_min_soc_val, 1)
            h += m_hours

        # Monthly dusk SOC averages + protection night counts
        monthly_soc_dusk_sum = [0.0] * 12
        monthly_soc_dusk_cnt = [0] * 12
        monthly_protection_nights = [0] * 12
        if annual_schedule:
            for i, entry in enumerate(annual_schedule):
                if i < 365:
                    m = entry['month'] - 1
                    if i in night_start_soc and bat_nom > 0:
                        monthly_soc_dusk_sum[m] += night_start_soc[i] / bat_nom * 100
                        monthly_soc_dusk_cnt[m] += 1
                    # Protection nights = Smartec activated but no critical failure
                    if protection_night_flags[i] and not critical_flags[i]:
                        monthly_protection_nights[m] += 1

        monthly_soc_dusk_avg_pct = [
            round(monthly_soc_dusk_sum[m] / monthly_soc_dusk_cnt[m], 1)
            if monthly_soc_dusk_cnt[m] > 0 else 0.0
            for m in range(12)
        ]

        return {
            'soc_hourly': soc_hourly,
            'critical_nights': critical_nights,
            'annual_failure_rate_pct': round(annual_failure_rate, 2),
            'monthly_failures': monthly_failures,
            'monthly_soc_avg_pct': monthly_soc_sum,
            'monthly_soc_min_pct': monthly_soc_min,
            'monthly_soc_dusk_avg_pct': monthly_soc_dusk_avg_pct,
            'monthly_protection_nights': monthly_protection_nights,
            'protected_mode_hours': protected_hours,
        }

    new_result = _sim(bat_nominal_wh)
    y10_result = _sim(bat_nominal_wh * 0.70)

    return {'new': new_result, 'year10': y10_result}


def simular_bateria_batch_numpy(solar_hourly_wh: list, consumo_hourly_wh: list,
                                bat_sizes_wh: list,
                                dod_max: float = 0.85,
                                min_soc_pct: float = 0.15,
                                charge_eff: float = 0.97,
                                discharge_eff: float = 0.97,
                                prebuilt_night_map: dict = None) -> list:
    """
    Vectorized battery simulation for N battery sizes with the same solar+consumption arrays.
    Runs the 8760-hour loop once, updating all N batteries simultaneously via numpy.
    Skips smartec_protection to allow pre-computed net energy array (conservative sizing).

    Returns list of annual_failure_rate_pct, one per battery size.
    About 40-100x faster than calling simular_bateria_anual N times.
    """
    import numpy as np

    N = len(bat_sizes_wh)
    if N == 0:
        return []

    bat      = np.asarray(bat_sizes_wh, dtype=np.float64)   # (N,)
    min_soc  = bat * min_soc_pct                              # (N,)

    solar    = np.asarray(solar_hourly_wh,   dtype=np.float64)  # (8760,)
    load_arr = np.asarray(consumo_hourly_wh, dtype=np.float64)  # (8760,)

    # Pre-compute net energy; identical for all N batteries (no smartec feedback)
    net = solar * charge_eff - load_arr / discharge_eff  # (8760,)

    # Build hour->day_index lookup, -1 = not a night hour
    day_of_hour = np.full(8760, -1, dtype=np.int32)
    if prebuilt_night_map:
        for h, d in prebuilt_night_map.items():
            if 0 <= h < 8760:
                day_of_hour[h] = d

    # Track which days went critical for each battery: shape (N, 365)
    critical_days = np.zeros((N, 365), dtype=bool)

    soc = bat.copy()  # all batteries start fully charged

    for h in range(8760):
        new_soc = np.clip(soc + net[h], 0.0, bat)   # (N,)
        d = int(day_of_hour[h])
        if d >= 0 and load_arr[h] > 0.0:
            critical_days[:, d] |= new_soc < min_soc
        soc = new_soc

    critical_nights = critical_days.sum(axis=1)  # (N,)
    return (critical_nights / 365.0 * 100.0).tolist()


def calcular_autonomia_equivalente(bat_nominal_wh: float, dod_max: float,
                                    min_soc_pct: float,
                                    avg_night_consumption_wh: float) -> dict:
    """Secondary indicator: can the battery support 2 or 3 nights with minimal solar (5%)."""""
    bat_usable = bat_nominal_wh * dod_max
    min_soc_wh = bat_nominal_wh * min_soc_pct

    results = {}
    for days in [2, 3]:
        soc = bat_nominal_wh
        viable = True
        for _ in range(days):
            pv_night = avg_night_consumption_wh * 0.05
            soc = max(0, soc + pv_night - avg_night_consumption_wh)
            if soc < min_soc_wh:
                viable = False
                break
        results[f'days_{days}_viable'] = viable

    return results
