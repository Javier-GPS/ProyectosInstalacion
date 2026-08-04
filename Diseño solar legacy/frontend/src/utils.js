export const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

// ── Timezone offsets per country ──────────────────────────────────────────────
// [std_offset_h, dst_offset_h, dst_first_month, dst_last_month]  (0-based months, inclusive)
// dst_first = -1 → no DST
// Northern hem. pattern: month >= dstFirst && month <= dstLast
// Southern hem. pattern: month >= dstFirst || month <= dstLast  (wraps over Jan)
const COUNTRY_TZ = {
  ES: [ 1, 2, 2, 9],   // CET/CEST  (Mar–Oct)
  FR: [ 1, 2, 2, 9],
  DE: [ 1, 2, 2, 9],
  IT: [ 1, 2, 2, 9],
  PT: [ 0, 1, 2, 9],   // WET/WEST
  MA: [ 1, 1,-1,-1],   // +01:00, sin DST desde 2019
  DZ: [ 1, 1,-1,-1],
  TN: [ 1, 1,-1,-1],
  SN: [ 0, 0,-1,-1],
  EG: [ 2, 2,-1,-1],
  NG: [ 1, 1,-1,-1],
  KE: [ 3, 3,-1,-1],
  ZA: [ 2, 2,-1,-1],
  SA: [ 3, 3,-1,-1],
  IN: [ 5.5, 5.5,-1,-1],
  BR: [-3,-2, 9, 2],   // BRT/BRST — DST Oct–Feb (hem. sur)
  MX: [-6,-5, 3,10],   // CST/CDT
}

/**
 * Offset to add to solar time → local wall-clock time.
 *   clock_time = solar_time + solarToLocalOffset(country, lon, month)
 *
 * Solar time: sun crosses meridian at 12:00.
 * UTC = solar_time – lon/15
 * Local = UTC + tz_offset  (std or dst)
 * → offset = tz_offset – lon/15
 */
export function solarToLocalOffset(country, lon, month) {
  const tz = COUNTRY_TZ[country]
  if (!tz) return -(lon / 15)          // fallback: UTC
  const [std, dst, dstFirst, dstLast] = tz
  let tzOffset = std
  if (dst !== std && dstFirst >= 0) {
    const inDst = dstFirst <= dstLast
      ? month >= dstFirst && month <= dstLast     // hem. norte
      : month >= dstFirst || month <= dstLast     // hem. sur (wraps)
    if (inDst) tzOffset = dst
  }
  return tzOffset - lon / 15
}

export function formatEur(n) {
  return new Intl.NumberFormat('es-ES', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(n)
}

export function formatKWh(wh) {
  return (wh / 1000).toFixed(1) + ' kWh'
}

// Night hours (civil twilight, 6° below horizon) at given lat + month
export function npNightHours(lat, month) {
  const d = [15,46,75,106,136,167,197,228,258,289,319,350][month]
  const decl = -23.45 * Math.cos((360 / 365 * (d + 10)) * Math.PI / 180)
  const latR = lat * Math.PI / 180
  const declR = decl * Math.PI / 180
  const cosHA = (Math.sin(-6 * Math.PI / 180) - Math.sin(latR) * Math.sin(declR))
               / (Math.cos(latR) * Math.cos(declR))
  if (cosHA >= 1) return 24
  if (cosHA <= -1) return 0
  return 24 - Math.acos(Math.max(-1, Math.min(1, cosHA))) * 2 * 180 / (Math.PI * 15)
}

// Civil dusk (evening twilight) in decimal solar hours from midnight
// Civil dawn = 12 - ha/15  |  Civil dusk = 12 + ha/15
export function npCivilOnset(lat, month) {
  const d = [15,46,75,106,136,167,197,228,258,289,319,350][month]
  const decl = -23.45 * Math.cos((360 / 365 * (d + 10)) * Math.PI / 180)
  const latR = lat * Math.PI / 180
  const declR = decl * Math.PI / 180
  const cosHA = (Math.sin(-6 * Math.PI / 180) - Math.sin(latR) * Math.sin(declR))
               / (Math.cos(latR) * Math.cos(declR))
  const ha = Math.acos(Math.max(-1, Math.min(1, cosHA))) * 180 / Math.PI
  return 12 + ha / 15   // civil dusk (ocaso) — was: 12 - ha/15 (alba, wrong)
}

// Civil dawn (morning twilight) in decimal solar hours from midnight
export function npCivilDawn(lat, month) {
  const d = [15,46,75,106,136,167,197,228,258,289,319,350][month]
  const decl = -23.45 * Math.cos((360 / 365 * (d + 10)) * Math.PI / 180)
  const latR = lat * Math.PI / 180
  const declR = decl * Math.PI / 180
  const cosHA = (Math.sin(-6 * Math.PI / 180) - Math.sin(latR) * Math.sin(declR))
               / (Math.cos(latR) * Math.cos(declR))
  const ha = Math.acos(Math.max(-1, Math.min(1, cosHA))) * 180 / Math.PI
  return 12 - ha / 15   // civil dawn (alba)
}

export function npHHMM(h) {
  const h24 = ((h % 24) + 24) % 24
  const hh = Math.floor(h24)
  const mm = Math.round((h24 - hh) * 60)
  if (mm >= 60) return String(hh + 1).padStart(2, '0') + ':00'
  return String(hh).padStart(2, '0') + ':' + String(mm).padStart(2, '0')
}

export function calcConsumoLive(photometry, nightProfile, lat = 41.4, month = 5) {
  const P = photometry.system_power_w || 90
  const nightH = npNightHours(lat, month)
  let total = nightProfile.aux_wh || 0
  for (const p of (nightProfile.periods || [])) {
    const h = (p.duration_pct || 0.333) * nightH
    total += P * h * (
      (p.presence_ratio || 0) * (p.dimming_presence || 1.0) +
      (1 - (p.presence_ratio || 0)) * (p.dimming_no_presence || 0.2)
    )
  }
  return Math.round(total)
}

export function downloadFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const COUNTRY_DATA = {
  ES: { electricity_cost: 0.15, co2: 0.18 },
  FR: { electricity_cost: 0.14, co2: 0.05 },
  DE: { electricity_cost: 0.18, co2: 0.35 },
  IT: { electricity_cost: 0.20, co2: 0.23 },
  PT: { electricity_cost: 0.14, co2: 0.18 },
  MA: { electricity_cost: 0.12, co2: 0.62 },
  DZ: { electricity_cost: 0.04, co2: 0.57 },
  TN: { electricity_cost: 0.08, co2: 0.50 },
  SN: { electricity_cost: 0.18, co2: 0.62 },
  EG: { electricity_cost: 0.04, co2: 0.44 },
  NG: { electricity_cost: 0.05, co2: 0.40 },
  KE: { electricity_cost: 0.10, co2: 0.22 },
  ZA: { electricity_cost: 0.07, co2: 0.85 },
  SA: { electricity_cost: 0.04, co2: 0.65 },
  IN: { electricity_cost: 0.08, co2: 0.70 },
  BR: { electricity_cost: 0.08, co2: 0.09 },
  MX: { electricity_cost: 0.06, co2: 0.42 },
}

export const DEMO_PRODUCTS = [
  { id: 'SIL_M_60',  name: 'SIL M 60',  pv_peak_power_wp: 60,  battery_nominal_wh: 300,  weight_kg: 4.5 },
  { id: 'SIL_M_90',  name: 'SIL M 90',  pv_peak_power_wp: 90,  battery_nominal_wh: 500,  weight_kg: 5.8 },
  { id: 'SIL_L_200', name: 'SIL L 200', pv_peak_power_wp: 200, battery_nominal_wh: 900,  weight_kg: 10.2 },
  { id: 'SIL_L_260', name: 'SIL L 260', pv_peak_power_wp: 260, battery_nominal_wh: 1200, weight_kg: 12.4 },
  { id: 'IND_200',   name: 'IND 200',   pv_peak_power_wp: 200, battery_nominal_wh: 800,  weight_kg: 9.1 },
  { id: 'IND_300',   name: 'IND 300',   pv_peak_power_wp: 300, battery_nominal_wh: 1100, weight_kg: 11.5 },
]
