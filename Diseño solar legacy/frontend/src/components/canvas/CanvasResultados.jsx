import { useRef, useEffect, useState } from 'react'
import { Chart } from 'chart.js/auto'
import { useApp } from '../../context/AppContext'
import { MONTHS, formatEur, calcConsumoLive } from '../../utils'
import { downloadFile } from '../../utils'
import { showToast } from '../Toast'

const SCENARIO_BADGE_CFG = {
  recommended:     { label: '★ Recomendada',     cls: 'scenario-recommended' },
  low_capex:       { label: '💰 Bajo CAPEX',      cls: 'scenario-lowcapex' },
  max_reliability: { label: '🛡 Máx. Fiabilidad', cls: 'scenario-maxrel' },
  hybrid:          { label: '⚡ Híbrida',          cls: 'scenario-hybrid' },
}

function ScenarioBadges({ c }) {
  const tags = c.scenario_tags || (c.recommended ? ['recommended'] : [])
  if (!tags.length) return null
  return (
    <div className="scenario-badges-row">
      {tags.map(tag => {
        const cfg = SCENARIO_BADGE_CFG[tag]
        if (!cfg) return null
        return <span key={tag} className={`scenario-badge ${cfg.cls}`}>{cfg.label}</span>
      })}
    </div>
  )
}

function ResultRow({ c, onDetail, onSelect, isSelected, showShadingColumn }) {
  if (c.error) {
    return (
      <tr className="row-unreliable">
        <td colSpan={showShadingColumn ? 11 : 9} style={{ padding: '8px 12px' }}>
          <strong>{c.product_name || c.product_id}</strong>
          <span style={{ marginLeft: '8px', color: 'var(--state-danger)', fontSize: '11px' }}>
            ⚠ Error: {c.error}
          </span>
        </td>
      </tr>
    )
  }

  const failPct = c.annual_failure_rate_pct || 0
  const relPct = 100 - failPct
  const relClass = relPct >= 98 ? 'good' : relPct >= 95 ? 'warn' : 'bad'
  const y10fail = c.annual_failure_rate_pct_y10 != null ? (100 - c.annual_failure_rate_pct_y10).toFixed(1) + '%' : '–'

  return (
    <tr
      className={`${c.recommended ? 'row-recommended' : ''} ${c.meets_reliability === false ? 'row-unreliable' : ''} ${isSelected ? 'row-chart-selected' : ''}`}
      onClick={() => onSelect(c.product_id)}
      style={{ cursor: 'pointer' }}
    >
      <td>
        <strong>{c.product_name || c.product_id}</strong>
        {c.n_units && c.n_units > 1 && (
          <span style={{ display:'inline-block',marginLeft:'5px',padding:'1px 6px',background:'#1E1E1E',color:'#FCF9F5',borderRadius:'4px',fontSize:'10px',fontWeight:'700',verticalAlign:'middle' }}>×{c.n_units}</span>
        )}
        {c.is_custom_sized && (
          <span style={{ display:'inline-block',marginLeft:'5px',padding:'1px 6px',background:'var(--state-info)',color:'#fff',borderRadius:'4px',fontSize:'10px',fontWeight:'600',verticalAlign:'middle' }}>⚙ a medida</span>
        )}
        <ScenarioBadges c={c} />
        {c.meets_reliability === false && (
          <div style={{ marginTop: '3px' }}><span className="badge badge-warn">⚠ Baja fiabilidad</span></div>
        )}
      </td>
      <td>{c.pv_peak_power_wp || '–'}</td>
      <td>{c.battery_nominal_wh || '–'}</td>
      <td>{c.weight_kg || '–'}</td>
      {showShadingColumn && (
        <>
          <td>
            {c.shading_comparison ? (
              <span>{c.shading_comparison.base_case.annual_production_kwh.toFixed(0)} kWh</span>
            ) : c.annual_production_wh != null ? (
              <span>{(c.annual_production_wh / 1000).toFixed(0)} kWh</span>
            ) : '–'}
          </td>
          <td>
            {c.shading_comparison ? (
              <div title={`Pérdida por sombra: ${c.shading?.annual_total_shadow_loss_pct?.toFixed(1)}% anual · ${c.shading?.critical_month_shadow_loss_pct?.toFixed(1)}% mes crítico`}>
                <strong style={{ color: 'var(--state-warning)' }}>
                  {c.shading_comparison.corrected_case.annual_production_kwh.toFixed(0)} kWh
                </strong>
                <div className="cost-note">🌥 −{c.shading.annual_total_shadow_loss_pct?.toFixed(1)}%</div>
              </div>
            ) : '–'}
          </td>
        </>
      )}
      <td>
        <span className={`reliability-badge ${relClass}`}>{relPct.toFixed(1)}%</span>
        <div className="failure-nights">{failPct.toFixed(1)}% noches fallo</div>
      </td>
      <td>
        {c.tco_10y_sale != null ? (
          <>
            <strong>{formatEur(c.tco_10y_sale)}</strong>
            <div className="cost-note">{c.tco_10y_cost != null ? formatEur(c.tco_10y_cost) + ' coste' : ''}</div>
          </>
        ) : '–'}
      </td>
      <td>{c.co2_saved_10y_kg != null ? Math.round(c.co2_saved_10y_kg) + ' kg' : '–'}</td>
      <td>{y10fail}</td>
      <td>
        <button className="btn-sm btn-secondary" onClick={e => { e.stopPropagation(); onDetail(c.product_id) }}>
          Ver
        </button>
      </td>
    </tr>
  )
}

export default function CanvasResultados() {
  const { state, dispatch } = useApp()
  const { simulation, project, photometry, nightProfile, env } = state

  const [selectedChart, setSelectedChart] = useState('')
  const [sortField, setSortField] = useState(null)
  const [sortAsc, setSortAsc] = useState(true)

  const monthlyChartRef = useRef(null)
  const socChartRef = useRef(null)
  const monthlyCanvasRef = useRef(null)
  const socCanvasRef = useRef(null)

  const candidates = simulation?.candidates || []
  const hasShading = candidates.some(c => c.shading_comparison)

  // Auto-select recommended on mount
  useEffect(() => {
    const rec = candidates.find(c => c.recommended)
    if (rec) setSelectedChart(rec.product_id)
  }, [simulation])

  // Monthly + SOC charts
  useEffect(() => {
    if (!selectedChart || !monthlyCanvasRef.current || !socCanvasRef.current) return
    const candidate = candidates.find(c => c.product_id === selectedChart)
    if (!candidate) return

    const prodKwh = (candidate.monthly_production_wh || []).map(v => +(v / 1000).toFixed(2))
    const consKwh = (candidate.monthly_consumption_wh || []).map(v => +(v / 1000).toFixed(2))
    const socNew = candidate.monthly_soc_avg_pct || []
    const socY10 = candidate.monthly_soc_avg_pct_y10 || []

    // Fallback demo data
    const cons = calcConsumoLive(photometry, nightProfile, project.lat || 41.4, 5) / 1000
    const baseProduction = [0.8,1.0,1.4,1.8,2.1,2.3,2.2,2.0,1.6,1.2,0.9,0.7]
    const nightHours = [14.5,13.5,12.5,11.5,10.5,10.0,10.5,11.5,12.5,13.5,14.5,15.0]
    const pv = (candidate.pv_peak_power_wp || 90) / 90
    const demoMonthly = MONTHS.map((_, i) => ({
      production_kwh: +(baseProduction[i] * pv * 30).toFixed(1),
      consumption_kwh: +(cons * nightHours[i]).toFixed(1),
      soc_min_pct: Math.min(95, Math.max(15, 50 + (baseProduction[i] - 1.5) * 25)),
      soc_min_y10: Math.min(90, Math.max(10, 40 + (baseProduction[i] - 1.5) * 22)),
    }))

    if (monthlyChartRef.current) { monthlyChartRef.current.destroy(); monthlyChartRef.current = null }
    monthlyChartRef.current = new Chart(monthlyCanvasRef.current, {
      type: 'bar',
      data: {
        labels: MONTHS,
        datasets: [
          {
            label: 'Producción solar (kWh)',
            data: prodKwh.length ? prodKwh : demoMonthly.map(m => m.production_kwh),
            backgroundColor: 'rgba(31,122,77,0.7)', borderRadius: 3,
          },
          {
            label: 'Consumo (kWh)',
            data: consKwh.length ? consKwh : demoMonthly.map(m => m.consumption_kwh),
            backgroundColor: 'rgba(30,30,30,0.5)', borderRadius: 3,
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { font: { size: 11 }, boxWidth: 12 } } },
        scales: {
          y: { beginAtZero: true, ticks: { font: { size: 11 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
          x: { ticks: { font: { size: 11 } }, grid: { display: false } }
        }
      }
    })

    if (socChartRef.current) { socChartRef.current.destroy(); socChartRef.current = null }
    socChartRef.current = new Chart(socCanvasRef.current, {
      type: 'line',
      data: {
        labels: MONTHS,
        datasets: [
          {
            label: 'SOC mín. año 1',
            data: socNew.length ? socNew : demoMonthly.map(m => m.soc_min_pct),
            borderColor: 'rgba(31,122,77,0.9)', backgroundColor: 'rgba(31,122,77,0.1)',
            fill: true, tension: 0.4, pointRadius: 3,
          },
          {
            label: 'SOC mín. año 10',
            data: socY10.length ? socY10 : demoMonthly.map(m => m.soc_min_y10),
            borderColor: 'rgba(183,121,31,0.9)', backgroundColor: 'rgba(183,121,31,0.08)',
            fill: false, tension: 0.4, pointRadius: 3, borderDash: [4,4],
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { font: { size: 11 }, boxWidth: 12 } } },
        scales: {
          y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%', font: { size: 11 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
          x: { ticks: { font: { size: 11 } }, grid: { display: false } }
        }
      }
    })

    return () => {
      monthlyChartRef.current?.destroy()
      socChartRef.current?.destroy()
    }
  }, [selectedChart, simulation])

  const handleSort = (field) => {
    if (sortField === field) setSortAsc(a => !a)
    else { setSortField(field); setSortAsc(true) }
  }

  const getSortedCandidates = () => {
    if (!sortField) return candidates
    return [...candidates].sort((a, b) => {
      const av = a[sortField] ?? 0, bv = b[sortField] ?? 0
      return sortAsc ? av - bv : bv - av
    })
  }

  const showDetail = (productId) => {
    dispatch({ type: 'SET_SELECTED_PRODUCT', payload: productId })
    dispatch({ type: 'SET_STEP', payload: 8 })
  }

  const exportCSV = () => {
    if (!simulation?.candidates) { showToast('No hay datos', 'warning'); return }
    const headers = ['Producto','Panel Wp','Batería Wh','Peso kg','Fiabilidad %','TCO 10a €','CO2 10a kg','Recomendado']
    const rows = simulation.candidates.map(c => [
      c.product_name || c.product_id,
      c.pv_peak_power_wp || '',
      c.battery_nominal_wh || '',
      c.weight_kg || '',
      (100 - (c.annual_failure_rate_pct || 0)).toFixed(1),
      c.tco_10y_sale != null ? c.tco_10y_sale.toFixed(0) : '',
      c.co2_saved_10y_kg != null ? Math.round(c.co2_saved_10y_kg) : '',
      c.recommended ? 'Sí' : 'No',
    ])
    const csv = [headers, ...rows].map(r => r.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(',')).join('\n')
    downloadFile('SALVI_Solar_resultados.csv', csv, 'text/csv')
    showToast('CSV exportado', 'success')
  }

  const sorted = getSortedCandidates()
  const selectedCandidate = candidates.find(c => c.product_id === selectedChart)
  const loc = project.city ? ' · ' + project.city : ''

  return (
    <div id="canvas-results" className="canvas-panel" style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="results-toolbar">
        <span className="results-title">
          Comparativa de soluciones{loc}
        </span>
        <div className="results-actions">
          <button className="btn-secondary btn-sm" onClick={exportCSV}>CSV</button>
        </div>
      </div>

      <div className="table-container">
        <table className="results-table">
          <thead>
            <tr>
              <th>Producto</th>
              <th>Panel <small>Wp</small></th>
              <th>Batería <small>Wh</small></th>
              <th>Peso <small>kg</small></th>
              {hasShading && (
                <>
                  <th title="Producción anual estimada sin corregir por sombras (PVGIS puro).">Producción</th>
                  <th title="Producción anual corregida por sombras locales (Shadowmap). Compárala con la columna anterior.">
                    Producción<br /><small>con sombras</small>
                  </th>
                </>
              )}
              <th
                className={`sortable ${sortField === 'annual_failure_rate_pct' ? (sortAsc ? 'sorted-asc' : 'sorted-desc') : ''}`}
                onClick={() => handleSort('annual_failure_rate_pct')}
              >
                Fiabilidad
              </th>
              <th
                className={`sortable ${sortField === 'tco_10y_sale' ? (sortAsc ? 'sorted-asc' : 'sorted-desc') : ''}`}
                onClick={() => handleSort('tco_10y_sale')}
              >
                TCO 10a €
              </th>
              <th
                className={`sortable ${sortField === 'co2_saved_10y_kg' ? (sortAsc ? 'sorted-asc' : 'sorted-desc') : ''}`}
                onClick={() => handleSort('co2_saved_10y_kg')}
              >
                CO₂ 10a kg
              </th>
              <th title="Fiabilidad estimada en el año 10, con batería degradada">Fiab. año 10</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(c => (
              <ResultRow
                key={c.product_id}
                c={c}
                showShadingColumn={hasShading}
                onDetail={showDetail}
                onSelect={setSelectedChart}
                isSelected={selectedChart === c.product_id}
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="charts-row">
        <div className="chart-card">
          <div className="chart-title">
            Producción vs Consumo mensual
            {selectedCandidate ? ' – ' + (selectedCandidate.product_name || selectedChart) : ''}
          </div>
          <div style={{ position: 'relative', height: '200px' }}>
            <canvas ref={monthlyCanvasRef}></canvas>
          </div>
        </div>
        <div className="chart-card">
          <div className="chart-title">
            Estado de carga batería (SOC mensual)
            {selectedCandidate ? ' – ' + (selectedCandidate.product_name || selectedChart) : ''}
          </div>
          <div style={{ position: 'relative', height: '200px' }}>
            <canvas ref={socCanvasRef}></canvas>
          </div>
        </div>
      </div>
    </div>
  )
}
