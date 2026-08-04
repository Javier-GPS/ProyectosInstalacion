import { useRef, useEffect, useCallback } from 'react'
import { Chart } from 'chart.js/auto'
import { useApp } from '../../context/AppContext'
import { MONTHS, npNightHours, npCivilOnset, npHHMM, solarToLocalOffset, calcConsumoLive } from '../../utils'
// npCivilOnset now returns civil DUSK (evening); npCivilDawn available if needed

const NP_PAD_L = 50, NP_PAD_R = 88, NP_PAD_T = 18, NP_PAD_B = 58

export default function CanvasStep3() {
  const { state, dispatch } = useApp()
  const { nightProfile, project, photometry, npMonth } = state

  const svgRef = useRef(null)
  const dragRef = useRef(null)
  const chartRectRef = useRef(null)
  const sizeRef = useRef({ w: 640, h: 400, cw: 568, ch: 324 })
  const resizeObserverRef = useRef(null)
  const consCanvasRef = useRef(null)
  const consChartRef = useRef(null)

  // Derive chart state from nightProfile.periods
  const periods = nightProfile.periods
  const npPR = periods[0]?.presence_ratio ?? 0.5

  const npMo = npMonth ?? 5

  // Build breakpoints + dimming arrays from periods
  const getBP = () => {
    const bp = [0]
    let cum = 0
    for (const p of periods) {
      cum += p.duration_pct
      bp.push(Math.min(1, Math.round(cum * 10000) / 10000))
    }
    bp[bp.length - 1] = 1.0
    return bp
  }
  const getDP = () => periods.map(p => p.dimming_presence)
  const getDN = () => periods.map(p => p.dimming_no_presence)
  const getPR = () => periods.map(p => p.presence_ratio ?? npPR)

  const npX = (f, cw) => NP_PAD_L + f * cw
  const npY = (d, ch) => NP_PAD_T + (1 - d) * ch
  const npFrac = (px, cw) => Math.max(0, Math.min(1, (px - NP_PAD_L) / cw))
  const npDim  = (py, ch) => Math.max(0, Math.min(1, 1 - (py - NP_PAD_T) / ch))

  // `pr` is an array with one presence ratio per period (use getPR() to preserve the
  // existing per-period values — never collapse them to a single global value here).
  const syncToApp = (bp, dp, dn, pr) => {
    const N = dp.length
    const newPeriods = []
    for (let i = 0; i < N; i++) {
      newPeriods.push({
        duration_pct: Math.round((bp[i+1] - bp[i]) * 10000) / 10000,
        presence_ratio: pr[i],
        dimming_presence: Math.round(dp[i] * 100) / 100,
        dimming_no_presence: Math.round(dn[i] * 100) / 100,
      })
    }
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: { periods: newPeriods } })
  }

  const renderChart = useCallback(() => {
    const svg = svgRef.current
    if (!svg) return
    const bbox = svg.getBoundingClientRect()
    if (bbox.width < 50 || bbox.height < 50) {
      requestAnimationFrame(renderChart)
      return
    }
    const W = bbox.width, H = bbox.height
    const CW = W - NP_PAD_L - NP_PAD_R
    const CH = H - NP_PAD_T - NP_PAD_B
    sizeRef.current = { w: W, h: H, cw: CW, ch: CH }

    svg.setAttribute('viewBox', `0 0 ${W} ${H}`)

    const bp = getBP()
    const dp = getDP()
    const dn = getDN()
    const pr = getPR()
    const N = dp.length
    const lat    = project.lat || 41.4
    const lon    = project.lon || 2.17
    const nightH = npNightHours(lat, npMo)   // civil dusk → civil dawn (horas)
    const dusk   = npCivilOnset(lat, npMo)   // ocaso civil (horas solares)
    // Apply encendido/apagado offsets so X-axis reflects real switch-on/off times
    const moH    = (nightProfile.margin_on_min  ?? -15) / 60   // negativo = antes del ocaso
    const mofH   = (nightProfile.margin_off_min ??  15) / 60   // positivo = después del alba
    const onset  = dusk + moH                 // hora real de encendido (solar)
    const totalH = nightH - moH + mofH        // duración real iluminada
    // Convert solar time → local wall-clock time (timezone + DST)
    const tzOff  = solarToLocalOffset(project.country || 'ES', lon, npMo)
    const toLocal = h => h + tzOff            // helper: solar → local
    const showNoP = pr.some(v => v < 0.995)

    let s = ''
    s += `<rect x="${NP_PAD_L}" y="${NP_PAD_T}" width="${CW}" height="${CH}" fill="rgba(30,30,30,0.015)" rx="3"/>`

    // Y-axis scales
    const pW100  = photometry.system_power_w || 90          // watts at 100% dimming
    // Lux at 100%: designed for E_req at MF=0.75, so initial E = E_req / 0.75
    const CLASS_LUX_MAP = {
      ME1:30,ME2:15,'ME3a':10,'ME3b':10,'ME4a':7.5,'ME4b':7.5,ME5:5,ME6:3,
      CE0:50,CE1:30,CE2:20,CE3:15,CE4:10,CE5:7.5,
      S1:15,S2:10,S3:7.5,S4:5,S5:3,S6:2,M1:30,M2:15,M3:10,M4:7.5,M5:5,M6:3,
    }
    const eReq   = CLASS_LUX_MAP[photometry.lighting_class] || 7.5
    const lux100 = eReq / 0.75   // lux at 100% (MF=0.75 → initial illuminance is higher)
    const xW   = NP_PAD_L + CW + 6   // first right column: W
    const xLux = NP_PAD_L + CW + 48  // second right column: lux

    ;[0, 0.25, 0.5, 0.75, 1.0].forEach(v => {
      const y = npY(v, CH)
      s += `<line x1="${NP_PAD_L}" y1="${y}" x2="${NP_PAD_L+CW}" y2="${y}" stroke="rgba(30,30,30,${v===0||v===1?'0.14':'0.055'})" stroke-width="1"/>`
      // Left: %
      s += `<text x="${NP_PAD_L-5}" y="${y+4}" text-anchor="end" fill="#9A9A9A" font-size="10">${Math.round(v*100)}%</text>`
      // Right col 1: W
      s += `<text x="${xW}" y="${y+4}" text-anchor="start" fill="#5588CC" font-size="10">${Math.round(v*pW100)}W</text>`
      // Right col 2: lux
      const luxVal = v * lux100
      s += `<text x="${xLux}" y="${y+4}" text-anchor="start" fill="#CC8844" font-size="10">${luxVal < 1 ? luxVal.toFixed(1) : Math.round(luxVal)}lx</text>`
    })
    // Axis labels on right side
    s += `<text x="${xW+16}"  y="${NP_PAD_T-5}" text-anchor="middle" fill="#5588CC" font-size="9" font-weight="600">W</text>`
    s += `<text x="${xLux+14}" y="${NP_PAD_T-5}" text-anchor="middle" fill="#CC8844" font-size="9" font-weight="600">lux</text>`
    s += `<text x="12" y="${NP_PAD_T+CH/2}" text-anchor="middle" fill="#aaa" font-size="10" transform="rotate(-90,12,${NP_PAD_T+CH/2})">Dimming</text>`

    // X-axis — local clock times
    for (let t = 0; t <= 5; t++) {
      const frac = t / 5, x = npX(frac, CW)
      if (t > 0 && t < 5) s += `<line x1="${x}" y1="${NP_PAD_T}" x2="${x}" y2="${NP_PAD_T+CH}" stroke="rgba(30,30,30,0.045)" stroke-width="1" stroke-dasharray="3,4"/>`
      s += `<line x1="${x}" y1="${NP_PAD_T+CH}" x2="${x}" y2="${NP_PAD_T+CH+5}" stroke="#ccc" stroke-width="1"/>`
      s += `<text x="${x}" y="${NP_PAD_T+CH+18}" text-anchor="middle" fill="#555" font-size="10" font-weight="600">${npHHMM(toLocal(onset + frac * totalH))}</text>`
      s += `<text x="${x}" y="${NP_PAD_T+CH+32}" text-anchor="middle" fill="#b0b0b0" font-size="9">${Math.round(frac*100)}%</text>`
    }
    // Info footer: hora local encendido → apagado
    const moLabel  = moH  < 0 ? `${Math.round(-moH*60)} min antes ocaso` : moH  > 0 ? `+${Math.round(moH*60)} min` : 'ocaso'
    const mofLabel = mofH > 0 ? `+${Math.round(mofH*60)} min tras alba`  : mofH < 0 ? `${Math.round(mofH*60)} min` : 'alba'
    s += `<text x="${NP_PAD_L+CW/2}" y="${NP_PAD_T+CH+46}" text-anchor="middle" fill="#aaa" font-size="9">`
    s += `${MONTHS[npMo]} · ${totalH.toFixed(1)}h iluminadas · `
    s += `encendido ${npHHMM(toLocal(onset))} (${moLabel}) → apagado ${npHHMM(toLocal(onset+totalH))} (${mofLabel})`
    s += `</text>`

    // "Without presence" area
    if (showNoP) {
      let pathD = `M${npX(0,CW)},${npY(0,CH)}`
      for (let i = 0; i < N; i++) pathD += ` L${npX(bp[i],CW)},${npY(dn[i],CH)} L${npX(bp[i+1],CW)},${npY(dn[i],CH)}`
      pathD += ` L${npX(1,CW)},${npY(0,CH)} Z`
      s += `<path d="${pathD}" fill="rgba(183,121,31,0.13)" stroke="none"/>`
      let lineD = ''
      for (let i = 0; i < N; i++) {
        const x1=npX(bp[i],CW), x2=npX(bp[i+1],CW), y=npY(dn[i],CH)
        lineD += (i===0?`M${x1},${y}`:`L${x1},${y}`) + ` L${x2},${y}`
        if (i<N-1) lineD += ` L${x2},${npY(dn[i+1],CH)}`
      }
      s += `<path d="${lineD}" fill="none" stroke="rgba(183,121,31,0.85)" stroke-width="2" stroke-dasharray="6,4"/>`
    }

    // "With presence" area
    const presAlpha = showNoP ? 0.16 : 0.28
    let pathP = `M${npX(0,CW)},${npY(0,CH)}`
    for (let i = 0; i < N; i++) pathP += ` L${npX(bp[i],CW)},${npY(dp[i],CH)} L${npX(bp[i+1],CW)},${npY(dp[i],CH)}`
    pathP += ` L${npX(1,CW)},${npY(0,CH)} Z`
    s += `<path d="${pathP}" fill="rgba(31,122,77,${presAlpha})" stroke="none"/>`
    let lineP = ''
    for (let i = 0; i < N; i++) {
      const x1=npX(bp[i],CW), x2=npX(bp[i+1],CW), y=npY(dp[i],CH)
      lineP += (i===0?`M${x1},${y}`:`L${x1},${y}`) + ` L${x2},${y}`
      if (i<N-1) lineP += ` L${x2},${npY(dp[i+1],CH)}`
    }
    s += `<path d="${lineP}" fill="none" stroke="rgba(31,122,77,0.9)" stroke-width="2.5"/>`

    // Divider handles
    for (let i = 1; i < N; i++) {
      const x = npX(bp[i], CW)
      const tLabel = npHHMM(toLocal(onset + bp[i] * totalH))
      s += `<line x1="${x}" y1="${NP_PAD_T}" x2="${x}" y2="${NP_PAD_T+CH}" stroke="rgba(30,30,30,0.22)" stroke-width="1.5" stroke-dasharray="4,4"/>`
      s += `<text x="${x}" y="${NP_PAD_T-5}" text-anchor="middle" fill="#777" font-size="9">${tLabel}</text>`
      const midY = NP_PAD_T + CH * 0.48
      s += `<circle cx="${x}" cy="${midY}" r="9" fill="white" stroke="#999" stroke-width="1.5" class="np-handle" data-drag="divider" data-idx="${i}" style="cursor:ew-resize"/>`
      s += `<text x="${x}" y="${midY+4}" text-anchor="middle" fill="#999" font-size="10" pointer-events="none">⋮</text>`
      if (N > 1) {
        s += `<circle cx="${x}" cy="${NP_PAD_T+CH+6}" r="7" fill="#f0f0f0" stroke="#ccc" stroke-width="1" class="np-handle" data-action="remove-seg" data-idx="${i}" style="cursor:pointer"/>`
        s += `<text x="${x}" y="${NP_PAD_T+CH+10}" text-anchor="middle" fill="#bbb" font-size="9" pointer-events="none">✕</text>`
      }
    }

    // Dimming handles
    for (let i = 0; i < N; i++) {
      const xM = npX((bp[i]+bp[i+1])/2, CW)
      s += `<circle cx="${xM}" cy="${npY(dp[i],CH)}" r="9" fill="white" stroke="rgba(31,122,77,0.9)" stroke-width="2" class="np-handle" data-drag="presence" data-idx="${i}" style="cursor:ns-resize"/>`
      s += `<text x="${xM}" y="${npY(dp[i],CH)+4}" text-anchor="middle" fill="rgba(31,122,77,0.9)" font-size="10" font-weight="600" pointer-events="none">${Math.round(dp[i]*100)}</text>`
      if (showNoP) {
        s += `<circle cx="${xM}" cy="${npY(dn[i],CH)}" r="9" fill="white" stroke="rgba(183,121,31,0.9)" stroke-width="2" class="np-handle" data-drag="nopresence" data-idx="${i}" style="cursor:ns-resize"/>`
        s += `<text x="${xM}" y="${npY(dn[i],CH)+4}" text-anchor="middle" fill="rgba(183,121,31,0.9)" font-size="10" font-weight="600" pointer-events="none">${Math.round(dn[i]*100)}</text>`
      }
    }

    // Presence-ratio badge per period — centered horizontally over each segment
    for (let i = 0; i < N; i++) {
      const xM = npX((bp[i]+bp[i+1])/2, CW)
      const y = NP_PAD_T + 14
      const label = `👤 ${Math.round(pr[i]*100)}%`
      const bw = 15 + label.length * 5.6
      s += `<rect x="${xM - bw/2}" y="${y-11}" width="${bw}" height="16" rx="7" fill="rgba(255,255,255,0.92)" stroke="rgba(30,30,30,0.15)" stroke-width="1"/>`
      s += `<text x="${xM}" y="${y}" text-anchor="middle" fill="#555" font-size="10" font-weight="600" pointer-events="none">${label}</text>`
    }

    s += `<rect x="${NP_PAD_L}" y="${NP_PAD_T}" width="${CW}" height="${CH}" fill="none" stroke="rgba(30,30,30,0.1)" rx="2" stroke-width="1"/>`
    svg.innerHTML = s

    // Energy badge — uses each period's own presence ratio
    let weighted = 0
    for (let i = 0; i < N; i++) {
      const dur = bp[i+1] - bp[i]
      weighted += dur * (pr[i] * dp[i] + (1 - pr[i]) * dn[i])
    }
    const badge = document.getElementById('np-energy-badge')
    if (badge) badge.textContent = `⚡ ${Math.round((1 - weighted) * 100)}% ahorro energético`

    // Attach handlers
    svg.querySelectorAll('.np-handle').forEach(el => {
      if (el.dataset.action) {
        el.addEventListener('click', handleClick)
      } else {
        el.addEventListener('mousedown', handleMouseDown)
        el.addEventListener('touchstart', handleTouchStart, { passive: false })
      }
    })
  }, [periods, npPR, npMo, project.lat, project.lon, project.country, nightProfile.margin_on_min, nightProfile.margin_off_min, photometry.system_power_w, photometry.lighting_class])

  useEffect(() => {
    renderChart()
    const svg = svgRef.current
    if (!svg || resizeObserverRef.current) return
    resizeObserverRef.current = new ResizeObserver(() => renderChart())
    resizeObserverRef.current.observe(svg)
    return () => resizeObserverRef.current?.disconnect()
  }, [renderChart])

  // Monthly consumption chart — same night profile (periods/presence/dimming) applied
  // across all 12 months, only the night length (npNightHours) varies by month.
  useEffect(() => {
    if (!consCanvasRef.current) return
    const lat = project.lat || 41.4
    const monthlyWh = MONTHS.map((_, m) => calcConsumoLive(photometry, nightProfile, lat, m))

    if (consChartRef.current) { consChartRef.current.destroy(); consChartRef.current = null }
    consChartRef.current = new Chart(consCanvasRef.current, {
      type: 'bar',
      data: {
        labels: MONTHS,
        datasets: [{
          data: monthlyWh,
          backgroundColor: monthlyWh.map((_, i) => i === npMo ? 'rgba(30,30,30,0.85)' : 'rgba(30,30,30,0.35)'),
          borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => c.raw + ' Wh/noche' } } },
        scales: {
          y: { beginAtZero: true, ticks: { font: { size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' },
               title: { display: true, text: 'Wh/noche', font: { size: 10 } } },
          x: { ticks: { font: { size: 10 } }, grid: { display: false } },
        },
      },
    })
    return () => { consChartRef.current?.destroy(); consChartRef.current = null }
  }, [periods, npPR, npMo, project.lat, photometry.system_power_w, nightProfile.margin_on_min, nightProfile.margin_off_min, nightProfile.aux_wh])

  const handleClick = (e) => {
    if (e.currentTarget.dataset.action === 'remove-seg') {
      const bpIdx = parseInt(e.currentTarget.dataset.idx)
      const bp = getBP()
      const dp = getDP()
      const dn = getDN()
      if (dp.length <= 1) return
      const pr = getPR()
      const li = bpIdx - 1, ri = bpIdx
      const ll = bp[bpIdx] - bp[bpIdx-1], rl = bp[bpIdx+1] - bp[bpIdx], tot = ll + rl
      const avgP = (ll*dp[li]+rl*dp[ri])/tot
      const avgN = (ll*dn[li]+rl*dn[ri])/tot
      const avgPR = (ll*pr[li]+rl*pr[ri])/tot
      const newBP = [...bp.slice(0, bpIdx), ...bp.slice(bpIdx + 1)]
      const newDP = [...dp.slice(0, li), avgP, ...dp.slice(ri + 1)]
      const newDN = [...dn.slice(0, li), avgN, ...dn.slice(ri + 1)]
      const newPR = [...pr.slice(0, li), avgPR, ...pr.slice(ri + 1)]
      syncToApp(newBP, newDP, newDN, newPR)
    }
  }

  const handleMouseDown = (e) => {
    if (e.button !== 0) return
    e.preventDefault()
    e.stopPropagation()
    dragRef.current = { type: e.currentTarget.dataset.drag, idx: parseInt(e.currentTarget.dataset.idx) }
    chartRectRef.current = svgRef.current.getBoundingClientRect()
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  const handleTouchStart = (e) => {
    e.preventDefault()
    dragRef.current = { type: e.currentTarget.dataset.drag, idx: parseInt(e.currentTarget.dataset.idx) }
    chartRectRef.current = svgRef.current.getBoundingClientRect()
    document.addEventListener('touchmove', onTouchMove, { passive: false })
    document.addEventListener('touchend', onTouchEnd)
  }

  const getSVGXY = (cx, cy) => {
    const { w, h } = sizeRef.current
    const r = chartRectRef.current
    return { x: (cx - r.left) * w / r.width, y: (cy - r.top) * h / r.height }
  }

  const applyDrag = (cx, cy) => {
    if (!dragRef.current) return
    const { cw, ch } = sizeRef.current
    const { x, y } = getSVGXY(cx, cy)
    const { type, idx } = dragRef.current
    const bp = getBP()
    const dp = getDP()
    const dn = getDN()

    const pr = getPR()
    if (type === 'divider') {
      const lo = bp[idx-1] + 0.04, hi = bp[idx+1] - 0.04
      const newBP = [...bp]
      newBP[idx] = Math.max(lo, Math.min(hi, npFrac(x, cw)))
      syncToApp(newBP, dp, dn, pr)
    } else if (type === 'presence') {
      const newDP = [...dp]
      newDP[idx] = Math.max(0.01, Math.min(1, npDim(y, ch)))
      const newDN = [...dn]
      if (newDN[idx] > newDP[idx]) newDN[idx] = newDP[idx]
      syncToApp(bp, newDP, newDN, pr)
    } else if (type === 'nopresence') {
      const newDN = [...dn]
      newDN[idx] = Math.max(0, Math.min(dp[idx], npDim(y, ch)))
      syncToApp(bp, dp, newDN, pr)
    }
  }

  const onMouseMove = (e) => applyDrag(e.clientX, e.clientY)
  const onTouchMove = (e) => { e.preventDefault(); applyDrag(e.touches[0].clientX, e.touches[0].clientY) }
  const onMouseUp = () => { dragRef.current = null; document.removeEventListener('mousemove', onMouseMove); document.removeEventListener('mouseup', onMouseUp) }
  const onTouchEnd = () => { dragRef.current = null; document.removeEventListener('touchmove', onTouchMove); document.removeEventListener('touchend', onTouchEnd) }

  return (
    <div className="canvas-panel canvas-step-view" style={{ display: 'flex' }}>
      <div className="np-topbar">
        <span className="np-canvas-title">Perfil de Dimming Nocturno</span>
        <span style={{
          fontSize: 12, fontWeight: 600, color: '#888',
          background: 'rgba(0,0,0,0.05)', borderRadius: 5,
          padding: '2px 8px', letterSpacing: 0.3,
        }}>
          {MONTHS[npMo]}
        </span>
        <span id="np-energy-badge" className="np-energy-badge">⚡ –% ahorro</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        <svg
          ref={svgRef}
          xmlns="http://www.w3.org/2000/svg"
          id="np-chart"
          style={{ flex: '0 0 50%', minWidth: 0, display: 'block', width: '50%', height: '100%', cursor: 'default', touchAction: 'none', background: '#fff' }}
        />
        <div style={{ flex: '0 0 50%', minWidth: 0, borderLeft: '1px solid var(--salvi-line)', padding: '12px 16px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--salvi-grey)', marginBottom: 8 }}>
            Consumo mensual estimado <span style={{ fontWeight: 400, color: 'var(--salvi-muted)' }}>· según el perfil de dimming definido</span>
          </div>
          <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
            <canvas ref={consCanvasRef}></canvas>
          </div>
        </div>
      </div>
      <div className="np-legend-row">
        <span className="np-legend-pres">─── Con presencia</span>
        <span className="np-legend-nopres">- - - Sin presencia</span>
        <span className="np-legend-hint">Arrastra los puntos · ✕ elimina segmento</span>
      </div>
    </div>
  )
}
