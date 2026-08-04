#!/usr/bin/env python3
"""
Shadowmap local-shading correction (Phase 1 — single point per project).

Architecture (per integration spec): PVGIS/JRC remains the primary source of
climatic irradiance and production. Shadowmap — or the mock provider below,
until real API credentials exist — is a secondary geometric-correction source
that indicates whether direct sunlight reaches a specific point/hour due to
local 3D obstacles (buildings, trees, terrain). It never replaces PVGIS and
never blocks the solar calculation: on any failure or missing data, the
correction factor defaults to 1.0 (no penalty) and PVGIS-only results stand.

Sun-below-horizon hours are NOT handled here: they're already zero in the
PVGIS-derived hourly_direct_wh (Gb(i) is 0 at night), so no extra rule is
needed to satisfy "shading below the horizon" — it falls out of using real
irradiance components as input.
"""
import hashlib

DEFAULT_CONFIDENCE_THRESHOLD = 0.75

# Default diffuse/reflected retention factors by environment context, used only
# when the provider doesn't return its own sky-view-factor / indirect-light data.
DIFFUSE_FACTOR_BY_CONTEXT = {
    'open_area':         1.00,
    'isolated_obstacle': 0.85,
    'urban_street':      0.75,
    'urban_canyon':      0.60,
    'dense_trees':       0.65,
    'low_confidence':    0.80,
}
REFLECTED_FACTOR_BY_CONTEXT = {
    'open_area':         1.00,
    'building_shadow':   0.70,
    'urban_canyon':      0.60,
    'dense_trees':       0.50,
    'low_confidence':    0.70,
}


class ShadowmapProvider:
    """Abstract local-shading provider interface. A real provider (once credentials
    exist) implements the same signature and is a drop-in replacement for the mock."""

    def check_direct_sunlight(self, lat, lon, hour_of_day, month, panel_height_m):
        """Return a dict: {is_in_direct_sunlight: bool|None, confidence: float|None,
        height_mode: 'panel_center_height'|'ground_level_proxy'|'unknown',
        status: 'ok'|'no_data'|'low_confidence'|'error'}. Must not raise."""
        raise NotImplementedError


def _mock_hash(lat, lon, month, hour):
    return int(hashlib.sha256(f'{lat:.3f}|{lon:.3f}|{month}|{hour}'.encode()).hexdigest()[:8], 16)


class MockShadowmapProvider(ShadowmapProvider):
    """Deterministic mock for development (per integration spec §32-33) — no network
    calls, no randomness (so results are reproducible in tests).

    Scenarios: open_area, urban_canyon, tree_shading, morning_shadow,
    afternoon_shadow, no_data, low_confidence."""

    SCENARIOS = ('open_area', 'urban_canyon', 'tree_shading',
                 'morning_shadow', 'afternoon_shadow', 'no_data', 'low_confidence')

    def __init__(self, scenario='open_area'):
        if scenario not in self.SCENARIOS:
            raise ValueError(f'Unknown mock scenario: {scenario!r}. Choices: {self.SCENARIOS}')
        self.scenario = scenario

    def check_direct_sunlight(self, lat, lon, hour_of_day, month, panel_height_m):
        if self.scenario == 'no_data':
            return {'is_in_direct_sunlight': None, 'confidence': None,
                    'height_mode': 'unknown', 'status': 'no_data'}
        if self.scenario == 'low_confidence':
            return {'is_in_direct_sunlight': True, 'confidence': 0.4,
                    'height_mode': 'panel_center_height' if panel_height_m else 'ground_level_proxy',
                    'status': 'low_confidence'}

        height_mode = 'panel_center_height' if panel_height_m else 'ground_level_proxy'
        confidence  = 0.91 if panel_height_m else 0.65

        if self.scenario == 'open_area':
            in_sun = True
        elif self.scenario == 'urban_canyon':
            # tall buildings block low-sun-angle hours (early morning / late afternoon)
            in_sun = 9 <= hour_of_day <= 17
        elif self.scenario == 'tree_shading':
            # deterministic per-location/month/hour pattern instead of randomness
            in_sun = (_mock_hash(lat, lon, month, hour_of_day) % 10) >= 3
        elif self.scenario == 'morning_shadow':
            in_sun = hour_of_day >= 11
        elif self.scenario == 'afternoon_shadow':
            in_sun = hour_of_day <= 15
        else:
            in_sun = True

        return {'is_in_direct_sunlight': in_sun, 'confidence': confidence,
                'height_mode': height_mode, 'status': 'ok'}


def build_monthly_shadow_pattern(provider, lat, lon, panel_height_m):
    """Query the provider once per (month, hour-of-day) representative day —
    12 x 24 = 288 calls max, instead of once per each of the 8760 annual hours
    (per integration spec §12, sampling discipline applies even to a mock/free
    provider). Returns {month(1-12): {hour(0-23): result_dict}}."""
    pattern = {}
    for month in range(1, 13):
        pattern[month] = {
            hour: provider.check_direct_sunlight(lat, lon, hour, month, panel_height_m)
            for hour in range(24)
        }
    return pattern


def apply_shadow_correction(hourly_direct_wh, hourly_diffuse_wh, hourly_reflected_wh,
                             shadow_pattern, environment_context='urban_street',
                             confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD):
    """
    Apply local-shading correction to the three PVGIS-derived irradiance components
    (spec §6-9). Rules:
      - Direct: factor 1.0 if sunlit, 0.0 if shaded — but ONLY when the provider
        result has status 'ok' and confidence >= threshold. Otherwise factor stays
        1.0 (never penalize on unverified/low-confidence data).
      - Diffuse/reflected: never zeroed automatically. Reduced by a context-based
        retention factor only on hours actually found in shadow.
    Returns (corrected_hourly_wh: list[8760], stats: dict) — stats includes annual/
    monthly shadow-loss %, whether correction was applied, and any warnings.
    """
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    diffuse_f   = DIFFUSE_FACTOR_BY_CONTEXT.get(environment_context, 0.75)
    reflected_f = REFLECTED_FACTOR_BY_CONTEXT.get(environment_context, 0.70)

    corrected = []
    base_direct_wh = sum(hourly_direct_wh)
    base_total_wh  = base_direct_wh + sum(hourly_diffuse_wh) + sum(hourly_reflected_wh)
    shadow_loss_direct_wh = 0.0
    shadow_loss_total_wh  = 0.0
    monthly_base_wh = [0.0] * 12
    monthly_loss_wh = [0.0] * 12
    confidence_sum, confidence_n = 0.0, 0
    any_applied = False
    any_low_confidence = False

    h = 0
    n = len(hourly_direct_wh)
    for m_idx, days in enumerate(days_in_month):
        month = m_idx + 1
        for _d in range(days):
            for hour in range(24):
                if h >= n:
                    break
                gb, gd, gr = hourly_direct_wh[h], hourly_diffuse_wh[h], hourly_reflected_wh[h]
                base = gb + gd + gr
                monthly_base_wh[m_idx] += base

                r = shadow_pattern.get(month, {}).get(hour)
                f_direct = f_diffuse = f_reflected = 1.0
                if r and r.get('status') == 'ok' and r.get('confidence') is not None \
                        and r['confidence'] >= confidence_threshold:
                    any_applied = True
                    confidence_sum += r['confidence']; confidence_n += 1
                    if r['is_in_direct_sunlight'] is False:
                        f_direct, f_diffuse, f_reflected = 0.0, diffuse_f, reflected_f
                elif r and r.get('status') == 'low_confidence':
                    any_low_confidence = True
                # status in ('no_data', 'error') or missing → factors stay 1.0

                corr_total = gb * f_direct + gd * f_diffuse + gr * f_reflected
                corrected.append(corr_total)

                loss = base - corr_total
                shadow_loss_direct_wh += gb * (1 - f_direct)
                shadow_loss_total_wh  += loss
                monthly_loss_wh[m_idx] += loss
                h += 1

    annual_direct_pct = round(shadow_loss_direct_wh / base_direct_wh * 100, 2) if base_direct_wh > 0 else 0.0
    annual_total_pct  = round(shadow_loss_total_wh  / base_total_wh  * 100, 2) if base_total_wh  > 0 else 0.0
    monthly_loss_pct = [
        round(monthly_loss_wh[i] / monthly_base_wh[i] * 100, 2) if monthly_base_wh[i] > 0 else 0.0
        for i in range(12)
    ]
    critical_month_pct = max(monthly_loss_pct) if monthly_loss_pct else 0.0
    avg_confidence = round(confidence_sum / confidence_n, 2) if confidence_n else None

    warnings = []
    if not any_applied:
        warnings.append('No se aplicó corrección de sombra: sin datos o confianza '
                         'insuficiente para las horas consultadas.')
    if any_low_confidence:
        warnings.append(f'Algunas horas tienen confianza baja (< {confidence_threshold:.0%}) '
                         'y no se corrigieron por defecto.')

    stats = {
        'confidence':                      avg_confidence,
        'annual_direct_shadow_loss_pct':   annual_direct_pct,
        'annual_total_shadow_loss_pct':    annual_total_pct,
        'monthly_shadow_loss_pct':         monthly_loss_pct,
        'critical_month_shadow_loss_pct':  critical_month_pct,
        'shadow_correction_applied':       any_applied,
        'warnings':                        warnings,
    }
    return corrected, stats
