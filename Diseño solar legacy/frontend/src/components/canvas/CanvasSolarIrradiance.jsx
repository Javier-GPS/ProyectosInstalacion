import { useRef, useEffect, useCallback } from 'react'
import { useApp } from '../../context/AppContext'
import { MONTHS, solarToLocalOffset, npHHMM } from '../../utils'

// ── Constants ────────────────────────────────────────────────────────────────
const G_DNI  = 800   // Direct Normal Irradiance at surface, clear sky (W/m²)
const G_DIF  = 100   // Isotropic diffuse (W/m²)
const N_PTS  = 180   // samples (5-minute resolution)

const PAD_L  = 50, PAD_R = 16, PAD_T = 28, PAD_B = 80

// ── Panel type definitions ────────────────────────────────────────────────────
const PANELS = [
  { id: 'horizontal',    label: 'Horizontal',               color: '#22C55E', dash: '' },
  { id: 'cylinder',      label: 'Cilíndrico vertical (SIL)', color: '#3B82F6', dash: '' },
  { id: 'optimal_tilt',  label: 'Inclinado óptimo',          color: '#F59E0B', dash: '' },
  { id: 'vertical_south',label: 'Vertical sur',              color: '#EF4444', dash: '5,4' },
]

// ── Solar math ────────────────────────────────────────────────────────────────
function dayOfYear(month) {
  return [15,46,75,106,136,167,197,228,258,289,319,350][month]
}

function declination(month) {
  const d = dayOfYear(month)
  return -23.45 * Math.cos((360 / 365 * (d + 10)) * Math.PI / 180) * Math.PI / 180
}

/**
 * Compute irradiance curve for a panel type over a full day.
 * Returns array of {solarHour, G} objects.
 */
function computeDayCurve(lat, month, panelType) {
  const decl = declination(month)
  const latR  = lat * Math.PI / 180
  const beta  = panelType === 'optimal_tilt'
    ? Math.max(0, lat) * Math.PI / 180
    : panelType === 'vertical_south' ? Math.PI / 2
    : 0  // horizontal / cylinder don't use beta in the same way

  // Sunrise/sunset hour angle
  const cosHs = -Math.tan(latR) * Math.tan(decl)
  if (cosHs >= 1)  return []               // polar night
  const Hs = Math.acos(Math.max(-1, Math.min(1, cosHs)))

  const points = []
  for (let i = 0; i <= N_PTS; i++) {
    const H = -Hs + (2 * Hs) * (i / N_PTS)
    const solarHour = 12 + (H * 180 / Math.PI) / 15

    const sinAlpha = Math.sin(latR) * Math.sin(decl) +
                     Math.cos(latR) * Math.cos(decl) * Math.cos(H)
    const cosAlpha = Math.sqrt(Math.max(0, 1 - sinAlpha * sinAlpha))

    if (sinAlpha <= 0.015) {
      points.push({ solarHour, G: 0 })
      continue
    }

    let G = 0

    if (panelType === 'horizontal') {
      G = G_DNI * sinAlpha + G_DIF

    } else if (panelType === 'cylinder') {
      // Vertical-axis cylinder: average irradiance on exposed curved half
      // G_direct = G_DNI × 2cosα/π (integrated over exposed half-cylinder)
      // G_diffuse = G_DIF × 0.5 (half sky visible from curved surface)
      G = G_DNI * (2 * cosAlpha / Math.PI) + G_DIF * 0.5

    } else if (panelType === 'optimal_tilt' || panelType === 'vertical_south') {
      // Solar azimuth from south (positive = west)
      // sin(Az) = cos(δ)sin(H) / cos(α)
      // cos(Az) = [sin(α)sin(φ) − sin(δ)] / [cos(α)cos(φ)]
      const sinAz = (cosAlpha > 0.01)
        ? (Math.cos(decl) * Math.sin(H)) / cosAlpha
        : 0
      const Az = Math.asin(Math.max(-1, Math.min(1, sinAz)))
      // Angle of incidence on south-facing panel at tilt beta
      // cos(θ) = sin(α)cos(β) + cos(α)sin(β)cos(Az_from_south)
      const cosTheta = sinAlpha * Math.cos(beta) + cosAlpha * Math.sin(beta) * Math.cos(Az)
      G = G_DNI * Math.max(0, cosTheta) + G_DIF * (1 + Math.cos(beta)) / 2
    }

    points.push({ solarHour, G: Math.max(0, G) })
  }
  return points
}

/**
 * Integrate W/m² × hours → Wh/m²/day
 */
function dailyEnergy(points) {
  if (points.length < 2) return 0
  let wh = 0
  for (let i = 1; i < points.length; i++) {
    const dt = points[i].solarHour - points[i - 1].solarHour
    wh += ((points[i].G + points[i - 1].G) / 2) * dt
  }
  return Math.round(wh)
}

// ── Component ────────────────────────────────────────────────────────────────
export default function CanvasSolarIrradiance() {
  const { state, dispatch } = useApp()
  const { project, npMonth } = state
  const month = npMonth ?? 5
  const lat   = project.lat  || 41.4
  const lon   = project.lon  || 2.17

  const svgRef = useRef(null)
  const resizeObRef = useRef(null)

  const renderChart = useCallback(() => {
    const svg = svgRef.current
    if (!svg) return
    const bbox = svg.getBoundingClientRect()
    if (bbox.width < 60 || bbox.height < 60) {
      requestAnimationFrame(renderChart)
      return
    }
    const W  = bbox.width
    const H  = bbox.height
    const CW = W - PAD_L - PAD_R
    const CH = H - PAD_T - PAD_B
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`)

    const tzOff = solarToLocalOffset(project.country || 'ES', lon, month)
    const localH = h => h + tzOff

    // Compute all curves
    const curves = PANELS.map(p => ({
      ...p,
      points: computeDayCurve(lat, month, p.id),
    }))

    // X domain: local sunrise to sunset (add 1h padding each side)
    const allHs = curves.flatMap(c => c.points.map(pt => localH(pt.solarHour)))
    const xMin = Math.min(...allHs) - 0.5
    const xMax = Math.max(...allHs) + 0.5
    const yMax = 1050  // W/m² max axis

    const toX = h  => PAD_L + ((localH(h) - xMin) / (xMax - xMin)) * CW
    const toY = g  => PAD_T + (1 - g / yMax) * CH

    let s = ''
    s += `<rect x="${PAD_L}" y="${PAD_T}" width="${CW}" height="${CH}" fill="rgba(30,30,30,0.015)" rx="3"/>`

    // Y-axis grid + labels
    ;[0, 250, 500, 750, 1000].forEach(v => {
      const y = toY(v)
      if (v > 0 && v < yMax) {
        s += `<line x1="${PAD_L}" y1="${y}" x2="${PAD_L+CW}" y2="${y}" stroke="rgba(30,30,30,0.06)" stroke-width="1"/>`
      }
      s += `<text x="${PAD_L-5}" y="${y+4}" text-anchor="end" fill="#aaa" font-size="10">${v}</text>`
    })
    s += `<text x="11" y="${PAD_T+CH/2}" text-anchor="middle" fill="#bbb" font-size="10" transform="rotate(-90,11,${PAD_T+CH/2})">W/m²</text>`

    // X-axis: hourly ticks
    const firstH = Math.ceil(xMin)
    const lastH  = Math.floor(xMax)
    for (let h = firstH; h <= lastH; h++) {
      const x = PAD_L + ((h - xMin) / (xMax - xMin)) * CW
      s += `<line x1="${x}" y1="${PAD_T}" x2="${x}" y2="${PAD_T+CH}" stroke="rgba(30,30,30,0.05)" stroke-width="1" stroke-dasharray="3,4"/>`
      s += `<line x1="${x}" y1="${PAD_T+CH}" x2="${x}" y2="${PAD_T+CH+5}" stroke="#ddd" stroke-width="1"/>`
      s += `<text x="${x}" y="${PAD_T+CH+17}" text-anchor="middle" fill="#777" font-size="10" font-weight="600">${npHHMM(h)}</text>`
    }

    // Solar noon marker
    const noonX = PAD_L + ((localH(12) - xMin) / (xMax - xMin)) * CW
    s += `<line x1="${noonX}" y1="${PAD_T}" x2="${noonX}" y2="${PAD_T+CH}" stroke="rgba(255,180,0,0.35)" stroke-width="1.5" stroke-dasharray="4,3"/>`
    s += `<text x="${noonX}" y="${PAD_T-8}" text-anchor="middle" fill="#D4A017" font-size="9">☀ mediodía</text>`

    // Filled areas + lines
    curves.forEach(({ points, color, dash }) => {
      if (!points.length) return
      // Area fill (below line, to y=CH)
      let areaD = `M${toX(points[0].solarHour)},${toY(0)}`
      points.forEach(pt => { areaD += ` L${toX(pt.solarHour)},${toY(pt.G)}` })
      areaD += ` L${toX(points[points.length-1].solarHour)},${toY(0)} Z`
      s += `<path d="${areaD}" fill="${color}" fill-opacity="0.07" stroke="none"/>`

      // Line
      let lineD = ''
      points.forEach((pt, i) => {
        lineD += (i === 0 ? 'M' : 'L') + `${toX(pt.solarHour)},${toY(pt.G)}`
      })
      s += `<path d="${lineD}" fill="none" stroke="${color}" stroke-width="2" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`
    })

    // Legend — inside the chart, top-right, combined with the Wh/m²/día value per curve
    // (previously a separate footer row below the chart — hard to read, now removed).
    const legLineH = 16
    const legBoxW  = 210
    const legBoxH  = curves.length * legLineH + 10
    const legRight = PAD_L + CW - 8
    const legTop   = PAD_T + 6
    s += `<rect x="${legRight - legBoxW}" y="${legTop}" width="${legBoxW}" height="${legBoxH}" rx="5" fill="rgba(255,255,255,0.92)" stroke="rgba(30,30,30,0.12)" stroke-width="1"/>`
    curves.forEach(({ label, color, dash, points }, i) => {
      const y  = legTop + 15 + i * legLineH
      const wh = dailyEnergy(points)
      s += `<line x1="${legRight-legBoxW+10}" y1="${y-4}" x2="${legRight-legBoxW+26}" y2="${y-4}" stroke="${color}" stroke-width="2.5" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`
      s += `<text x="${legRight-legBoxW+31}" y="${y}" text-anchor="start" fill="#333" font-size="10">${label}</text>`
      s += `<text x="${legRight-6}" y="${y}" text-anchor="end" fill="#888" font-size="9.5" font-weight="600">${wh} Wh/m²/día</text>`
    })

    // Axis border
    s += `<rect x="${PAD_L}" y="${PAD_T}" width="${CW}" height="${CH}" fill="none" stroke="rgba(30,30,30,0.1)" rx="2" stroke-width="1"/>`

    svg.innerHTML = s
  }, [lat, lon, month, project.country])

  useEffect(() => {
    renderChart()
    const svg = svgRef.current
    if (!svg || resizeObRef.current) return
    resizeObRef.current = new ResizeObserver(() => renderChart())
    resizeObRef.current.observe(svg)
    return () => resizeObRef.current?.disconnect()
  }, [renderChart])

  return (
    <div className="canvas-panel canvas-step-view" style={{ display: 'flex', flexDirection: 'column' }}>

      {/* Header */}
      <div className="canvas-header">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span className="canvas-title">Irradiancia Solar por Tipo de Panel</span>
          <span style={{ fontSize: 12, color: 'var(--salvi-muted)' }}>cielo despejado · {Math.round(lat)}° lat</span>
        </div>

        {/* Month chips */}
        <div style={{ display: 'flex', gap: 4, marginTop: 8, flexWrap: 'wrap' }}>
          {MONTHS.map((m, i) => (
            <button key={i} onClick={() => dispatch({ type: 'SET_NP_MONTH', payload: i })}
              style={{
                padding: '2px 8px', borderRadius: 5, border: 'none', cursor: 'pointer',
                fontSize: 11, fontWeight: i === month ? 700 : 400,
                background: i === month ? 'var(--salvi-black, #1E1E1E)' : 'var(--bg-hover, #F0F0F0)',
                color: i === month ? '#fff' : 'var(--salvi-grey)',
                transition: 'all 0.1s',
              }}>
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <svg ref={svgRef}
        style={{ flex: 1, minHeight: 0, display: 'block', width: '100%', height: '100%', background: '#fff' }}
        xmlns="http://www.w3.org/2000/svg"
      />
    </div>
  )
}
