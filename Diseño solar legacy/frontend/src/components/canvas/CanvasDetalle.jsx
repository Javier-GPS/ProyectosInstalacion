import { useRef, useEffect, useState } from 'react'
import { Chart } from 'chart.js/auto'
import { useApp } from '../../context/AppContext'
import { MONTHS, formatEur, calcConsumoLive, npNightHours, npHHMM } from '../../utils'

// ── TCO breakdown modal ──────────────────────────────────────────────────────
function TcoModal({ c, onClose }) {
  if (!c) return null
  const cb = c.capex_breakdown || {}
  const tb = c.tco_breakdown   || {}
  const margin = c.capex_cost > 0
    ? Math.round((1 - c.capex_cost / c.capex_sale) * 100)
    : 62

  const Row = ({ label, cost, sale, note, bold, accent }) => (
    <tr style={{ background: bold ? 'var(--bg-hover, #F5F5F5)' : undefined }}>
      <td style={{ fontWeight: bold ? 700 : 400, color: accent || 'inherit' }}>{label}</td>
      <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: bold ? 700 : 400 }}>
        {cost != null && cost > 0 ? formatEur(cost) : '—'}
      </td>
      <td style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: bold ? 700 : 400,
        color: bold ? 'var(--salvi-black)' : 'var(--salvi-grey)' }}>
        {sale != null && sale > 0 ? formatEur(sale) : '—'}
      </td>
      {note && <td style={{ fontSize: 10, color: 'var(--salvi-muted)', paddingLeft: 8 }}>{note}</td>}
    </tr>
  )

  const saleCapex   = cb.panel > 0 ? cb.panel   / (1 - margin/100) : null
  const saleBat     = cb.battery > 0 ? cb.battery / (1 - margin/100) : null
  const saleCtrl    = cb.controller > 0 ? cb.controller / (1 - margin/100) : null
  const saleInst    = cb.installation > 0 ? cb.installation / (1 - margin/100) : null
  const saleStruct  = cb.structure > 0 ? cb.structure / (1 - margin/100) : null
  const saleSmartec = cb.smartec_node > 0 ? cb.smartec_node / (1 - margin/100) : null

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 9000,
      background: 'rgba(0,0,0,0.45)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: '#fff', borderRadius: 14,
        width: 'min(620px, 95vw)', maxHeight: '90vh',
        overflow: 'auto', boxShadow: '0 8px 40px rgba(0,0,0,0.25)',
        padding: '24px 28px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 18, letterSpacing: -0.5 }}>Desglose TCO 10 años</div>
            <div style={{ fontSize: 12, color: 'var(--salvi-grey)', marginTop: 2 }}>
              {c.product_name || c.product_id}
              {c.n_units > 1 ? ` · ×${c.n_units} unidades` : ''}
            </div>
          </div>
          <button onClick={onClose} style={{
            border: 'none', background: 'var(--bg-hover, #F0F0F0)',
            borderRadius: 8, width: 32, height: 32, cursor: 'pointer',
            fontSize: 18, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>×</button>
        </div>

        {/* CAPEX table */}
        <div style={{ fontWeight: 700, fontSize: 11, color: 'var(--salvi-muted)', textTransform: 'uppercase',
          letterSpacing: '0.06em', marginBottom: 6 }}>
          CAPEX — Inversión inicial
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 20, fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--salvi-line, #E8E8E8)' }}>
              <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600, color: 'var(--salvi-grey)', fontSize: 11 }}>Componente</th>
              <th style={{ textAlign: 'right', paddingBottom: 6, fontWeight: 600, color: 'var(--salvi-grey)', fontSize: 11 }}>Coste</th>
              <th style={{ textAlign: 'right', paddingBottom: 6, fontWeight: 600, color: 'var(--salvi-grey)', fontSize: 11 }}>PVP</th>
              <th style={{ paddingBottom: 6, paddingLeft: 8 }}></th>
            </tr>
          </thead>
          <tbody style={{ lineHeight: 2 }}>
            <Row label="☀ Panel fotovoltaico" cost={cb.panel} sale={saleCapex}
              note={c.pv_peak_power_wp ? `${c.pv_peak_power_wp} Wp` : ''} />
            <Row label="🔋 Batería" cost={cb.battery} sale={saleBat}
              note={c.battery_nominal_wh ? `${c.battery_nominal_wh} Wh` : ''} />
            <Row label="⚡ Controlador / electrónica" cost={cb.controller} sale={saleCtrl} />
            <Row label="🏗 Estructura / soporte" cost={cb.structure} sale={saleStruct} />
            <Row label="🔧 Instalación" cost={cb.installation} sale={saleInst} />
            {cb.smartec_node > 0 && <Row label="📡 Nodo Smartec" cost={cb.smartec_node} sale={saleSmartec} />}
            {cb.sensor > 0 && <Row label="👁 Sensor de presencia" cost={cb.sensor} sale={cb.sensor / (1 - margin/100)} />}
            <Row label="Total CAPEX" cost={c.capex_cost} sale={c.capex_sale} bold accent="var(--salvi-black)" />
          </tbody>
        </table>

        {/* OPEX table */}
        <div style={{ fontWeight: 700, fontSize: 11, color: 'var(--salvi-muted)', textTransform: 'uppercase',
          letterSpacing: '0.06em', marginBottom: 6 }}>
          OPEX — Costes operativos 10 años
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 20, fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--salvi-line, #E8E8E8)' }}>
              <th style={{ textAlign: 'left', paddingBottom: 6, fontWeight: 600, color: 'var(--salvi-grey)', fontSize: 11 }}>Concepto</th>
              <th style={{ textAlign: 'right', paddingBottom: 6, fontWeight: 600, color: 'var(--salvi-grey)', fontSize: 11 }}>Coste</th>
              <th style={{ textAlign: 'right', paddingBottom: 6, fontWeight: 600, color: 'var(--salvi-grey)', fontSize: 11 }}>PVP</th>
              <th style={{ paddingBottom: 6, paddingLeft: 8 }}></th>
            </tr>
          </thead>
          <tbody style={{ lineHeight: 2 }}>
            <Row label="🧹 Limpieza (10 años)" cost={tb.cleaning_10y}
              sale={tb.cleaning_10y ? tb.cleaning_10y / (1 - margin/100) : null}
              note="25 €/año × 10" />
            <Row label="🔩 Mantenimiento (10 años)" cost={tb.maintenance_10y}
              sale={tb.maintenance_10y ? tb.maintenance_10y / (1 - margin/100) : null}
              note="25 €/año × 10" />
            {tb.battery_replacement > 0 && (
              <Row label="🔋 Sustitución batería" cost={tb.battery_replacement}
                sale={tb.battery_replacement / (1 - margin/100)}
                note="degradación > 20% en año 10" />
            )}
            {tb.grid_energy_10y > 0 && (
              <Row label="⚡ Energía red (10 años)" cost={tb.grid_energy_10y}
                sale={tb.grid_energy_10y / (1 - margin/100)} />
            )}
          </tbody>
        </table>

        {/* Total summary */}
        <div style={{
          background: 'var(--salvi-black, #1E1E1E)', color: '#fff',
          borderRadius: 10, padding: '14px 18px',
          display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center',
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, opacity: 0.6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              TCO Coste total 10 años
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: -1 }}>
              {c.tco_10y_cost != null ? formatEur(c.tco_10y_cost) : '—'}
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, opacity: 0.6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              TCO Precio venta (margen {margin}%)
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: -1 }}>
              {c.tco_10y_sale != null ? formatEur(c.tco_10y_sale) : '—'}
            </div>
          </div>
          <div style={{ fontSize: 11, opacity: 0.55, alignSelf: 'flex-end' }}>
            Precio venta = coste / (1 − margen)
          </div>
        </div>

      </div>
    </div>
  )
}

function LossTree({ lt }) {
  if (!lt) return null

  // Build cumulative: each bar shows the remaining % after applying all losses up to that point
  const losses = [
    { label: '− Geometría / tilt',        loss: lt.geometry_loss_pct,           bar: 'bar-geometry'   },
    { label: '− Suciedad (soiling)',       loss: lt.soiling_loss_pct,            bar: 'bar-soiling'    },
    { label: '− Temperatura',             loss: lt.temperature_loss_pct,        bar: 'bar-temp'       },
    { label: '− Controlador / cableado',  loss: lt.controller_loss_pct,         bar: 'bar-controller' },
    { label: '− Batería (ida+vuelta)',     loss: lt.battery_roundtrip_loss_pct,  bar: 'bar-battery'    },
    { label: '− Degradación (prom.)',      loss: lt.degradation_loss_pct,        bar: 'bar-degradation'},
  ]

  // Cumulative remaining after each step
  let running = 100
  const rows = losses.map(l => {
    const before = running
    running = Math.max(0, running - (l.loss || 0))
    return { ...l, before, after: running }
  })

  const avail = lt.energy_available_pct ?? running

  return (
    <div>
      <div className="detail-section-title" style={{ marginBottom: '12px' }}>
        Árbol de pérdidas <span style={{ fontSize: '10px', fontWeight: '400', color: 'var(--salvi-muted)' }}>(estimado F1)</span>
      </div>
      <div className="loss-tree-wrap">
        {/* Base row */}
        <div className="loss-tree-row">
          <span className="loss-tree-label" style={{ fontWeight: '600' }}>Recurso PV teórico</span>
          <div className="loss-tree-bar-wrap">
            <div className="loss-tree-bar bar-available" style={{ width: '100%' }} />
          </div>
          <span className="loss-tree-val" style={{ color: 'var(--salvi-grey)' }}>100%</span>
        </div>

        {/* Loss rows — bar shows remaining after this loss (cumulative) */}
        {rows.map((r, i) => (
          <div key={i} className="loss-tree-row">
            <span className="loss-tree-label">{r.label}</span>
            <div className="loss-tree-bar-wrap">
              <div className={`loss-tree-bar ${r.bar}`} style={{ width: r.after + '%' }} />
            </div>
            <span className="loss-tree-val val-loss">−{(r.loss || 0).toFixed(1)}%</span>
          </div>
        ))}

        <hr className="loss-tree-divider" />

        {/* Result row */}
        <div className="loss-tree-row">
          <span className="loss-tree-label total-label">▶ Energía disponible útil</span>
          <div className="loss-tree-bar-wrap">
            <div className="loss-tree-bar bar-available" style={{ width: avail + '%' }} />
          </div>
          <span className="loss-tree-val val-avail">{avail.toFixed(1)}%</span>
        </div>
      </div>
    </div>
  )
}

function SmartecSummary({ nightProfile, photometry }) {
  const periods = nightProfile.periods || []
  const presGlobal = periods[0]?.presence_ratio ?? 0
  const hasSensor = presGlobal < 0.995
  const mo = nightProfile.margin_on_min ?? -15
  const mof = nightProfile.margin_off_min ?? 15
  const lat = 41.4 // approximate
  const nightH = npNightHours(lat, 5)

  const moLabel = `${mo > 0 ? '+' : ''}${mo} min respecto al ocaso`
  const mofLabel = `+${mof} min respecto al alba`

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
        {hasSensor ? (
          <span className="scenario-badge scenario-recommended" style={{ fontSize: '11px' }}>
            🔆 Sensor presencia · ratio {Math.round(presGlobal * 100)}%
          </span>
        ) : (
          <span className="scenario-badge scenario-lowcapex" style={{ fontSize: '11px' }}>
            Sin sensor de presencia
          </span>
        )}
        <span style={{ fontSize: '11px', color: 'var(--salvi-grey)' }}>⏱ Encendido: {moLabel}</span>
        <span style={{ fontSize: '11px', color: 'var(--salvi-grey)' }}>⏱ Apagado: {mofLabel}</span>
      </div>
      <table className="detail-monthly-table" style={{ width: 'auto' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'center' }}>#</th>
            <th>Duración</th>
            <th>Con presencia</th>
            {hasSensor && <th>Sin presencia</th>}
            <th>Consumo</th>
          </tr>
        </thead>
        <tbody>
          {periods.map((p, i) => {
            const durH = (p.duration_pct * nightH).toFixed(1)
            const durPct = (p.duration_pct * 100).toFixed(0)
            const dpPct = (p.dimming_presence * 100).toFixed(0)
            const dnPct = (p.dimming_no_presence * 100).toFixed(0)
            const wh = Math.round((photometry.system_power_w || 90) * p.duration_pct * nightH
              * (presGlobal * p.dimming_presence + (1 - presGlobal) * p.dimming_no_presence))
            return (
              <tr key={i}>
                <td style={{ fontWeight: '700', color: 'var(--salvi-grey)', textAlign: 'center' }}>{i+1}</td>
                <td>{durPct}% <span style={{ color: 'var(--salvi-muted)', fontSize: '10px' }}>(~{durH}h)</span></td>
                <td style={{ color: 'rgba(31,122,77,0.9)', fontWeight: '600' }}>{dpPct}%</td>
                {hasSensor && <td style={{ color: 'rgba(183,121,31,0.9)', fontWeight: '600' }}>{dnPct}%</td>}
                <td style={{ color: 'var(--salvi-grey)' }}>{wh} Wh</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="result-note" style={{ marginTop: '8px' }}>
        ℹ️ Estos parámetros se envían al nodo Smartec para programar el dimming automático.
      </div>
    </div>
  )
}

// ── Smartec Intelligence panel ──────────────────────────────────────────────
function SmartecIntelligence({ monthly, batWh, socTarget, onSocTargetChange }) {
  if (!monthly || monthly.length === 0) return null

  const extras = monthly.map(m => {
    const dusk = m.soc_dusk_pct || 0
    const consWh = (m.consumption_kwh || 0) * 1000
    const headroomWh = Math.max(0, (dusk - socTarget) / 100 * batWh - consWh)
    const headroomPct = consWh > 0 ? Math.round(headroomWh / consWh * 100) : 0
    return { wh: Math.round(headroomWh), pct: headroomPct }
  })

  const totalProtNights = monthly.reduce((s, m) => s + (m.protection_nights || 0), 0)
  const minExtra = Math.min(...extras.map(e => e.wh))
  const avgExtra = Math.round(extras.reduce((s, e) => s + e.wh, 0) / 12)

  const kpiBox = { background: 'var(--salvi-surface)', border: '1px solid var(--salvi-line)', borderRadius: '8px', padding: '10px 14px', minWidth: '140px', flex: '1 1 140px' }
  const kpiLbl = { fontSize: '10px', color: 'var(--salvi-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }
  const kpiVal = { fontSize: '18px', fontWeight: '700', letterSpacing: '-0.02em', lineHeight: 1 }
  const kpiSub = { fontSize: '10px', color: 'var(--salvi-muted)', marginTop: '3px' }

  return (
    <div className="detail-section">
      <div className="detail-section-title" style={{ marginBottom: '12px' }}>
        Inteligencia Smartec — Gestión activa de energía
      </div>

      {/* SOC target slider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '12px', color: 'var(--salvi-grey)', whiteSpace: 'nowrap' }}>SOC objetivo fin de noche:</span>
        <input type="range" min="10" max="50" step="5" value={socTarget}
          onChange={e => onSocTargetChange(+e.target.value)}
          style={{ flex: '1', maxWidth: '180px', accentColor: '#1E1E1E', cursor: 'pointer' }} />
        <span style={{ fontWeight: '700', fontSize: '14px', minWidth: '34px' }}>{socTarget}%</span>
        <span style={{ fontSize: '10px', color: 'var(--salvi-muted)' }}>margen de seguridad reservado</span>
      </div>

      {/* KPI summary cards */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '14px', flexWrap: 'wrap' }}>
        <div style={kpiBox}>
          <div style={kpiLbl}>Noches protegidas / año</div>
          <div style={{ ...kpiVal, color: totalProtNights > 0 ? 'var(--state-warning)' : 'var(--state-success)' }}>
            {totalProtNights}
          </div>
          <div style={kpiSub}>Smartec redujo consumo para salvar batería</div>
        </div>
        <div style={kpiBox}>
          <div style={kpiLbl}>Extra mín. (mes peor)</div>
          <div style={{ ...kpiVal, color: minExtra > 0 ? 'var(--state-success)' : 'var(--salvi-muted)' }}>
            {minExtra > 0 ? `+${minExtra} Wh` : 'Sin margen'}
          </div>
          <div style={kpiSub}>capacidad de brillo adicional</div>
        </div>
        <div style={kpiBox}>
          <div style={kpiLbl}>Extra medio anual</div>
          <div style={{ ...kpiVal, color: avgExtra > 0 ? 'var(--state-success)' : 'var(--salvi-muted)' }}>
            {avgExtra > 0 ? `+${avgExtra} Wh` : '—'}
          </div>
          <div style={kpiSub}>energía aprovechable por noche</div>
        </div>
      </div>

      {/* Monthly breakdown table */}
      <table className="detail-monthly-table" style={{ width: '100%' }}>
        <thead>
          <tr>
            <th>Mes</th>
            <th title="SOC promedio al inicio de la noche (al anochecer)">SOC anochecer</th>
            <th title={`Energía extra disponible por noche manteniendo SOC final ≥ ${socTarget}%`}>Extra Smartec</th>
            <th title="Noches donde Smartec activó protección (redujo dimming para no llegar al SOC mínimo)">Noches protección</th>
          </tr>
        </thead>
        <tbody>
          {monthly.map((m, i) => {
            const dusk = m.soc_dusk_pct || 0
            const prot = m.protection_nights || 0
            const { wh, pct } = extras[i]
            const duskColor = dusk >= 70 ? 'var(--state-success)' : dusk >= 45 ? 'var(--salvi-grey)' : 'var(--state-warning)'
            return (
              <tr key={i}>
                <td style={{ fontWeight: '600' }}>{MONTHS[i]}</td>
                <td style={{ color: duskColor, fontWeight: '600' }}>{dusk.toFixed(0)}%</td>
                <td style={{ color: wh > 0 ? 'var(--state-success)' : 'var(--salvi-muted)', fontWeight: wh > 0 ? '600' : '400' }}>
                  {wh > 0 ? `+${wh} Wh (+${pct}% más luz)` : '—'}
                </td>
                <td style={{ color: prot > 0 ? 'var(--state-warning)' : 'var(--salvi-muted)' }}>
                  {prot > 0 ? prot + ' noches' : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className="result-note" style={{ marginTop: '8px' }}>
        ℹ️ En noches con poco sol (winter dip), Smartec reduce el dimming base para proteger la batería.
        En noches con excedente, puede ofrecer mayor intensidad luminosa sin comprometer el margen de seguridad seleccionado.
      </div>
    </div>
  )
}

// ── Local shading (Shadowmap) correction panel ──────────────────────────────
function ShadingCorrection({ shading, comparison, monthlyProductionWh, monthlyConsumptionWh }) {
  const chartRef = useRef(null)
  const canvasRef = useRef(null)

  const monthlyBaseWh = comparison?.monthly_production_base_wh

  useEffect(() => {
    if (!canvasRef.current || !monthlyBaseWh || !monthlyProductionWh) return
    if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null }
    chartRef.current = new Chart(canvasRef.current, {
      type: 'line',
      data: {
        labels: MONTHS,
        datasets: [
          {
            label: 'Producción sin sombra',
            data: monthlyBaseWh.map(v => +(v / 1000).toFixed(2)),
            borderColor: 'rgba(31,122,77,0.55)', backgroundColor: 'rgba(31,122,77,0.06)',
            borderDash: [5, 4], fill: false, tension: 0.35, pointRadius: 3,
          },
          {
            label: 'Producción con sombra',
            data: monthlyProductionWh.map(v => +(v / 1000).toFixed(2)),
            borderColor: 'rgba(183,121,31,0.9)', backgroundColor: 'rgba(183,121,31,0.10)',
            fill: true, tension: 0.35, pointRadius: 3, borderWidth: 2.5,
          },
          {
            label: 'Consumo',
            data: (monthlyConsumptionWh || []).map(v => +(v / 1000).toFixed(2)),
            borderColor: 'rgba(30,30,30,0.6)', backgroundColor: 'rgba(30,30,30,0)',
            borderDash: [2, 3], fill: false, tension: 0.35, pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 10 } } },
        scales: {
          y: { beginAtZero: true, ticks: { font: { size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' },
               title: { display: true, text: 'kWh/mes', font: { size: 10 } } },
          x: { ticks: { font: { size: 10 } }, grid: { display: false } },
        },
      },
    })
    return () => { chartRef.current?.destroy(); chartRef.current = null }
  }, [monthlyBaseWh, monthlyProductionWh, monthlyConsumptionWh])

  if (!shading || shading.status === 'not_supported_geometry') return null

  const applied = !!shading.shadow_correction_applied
  const box = { background: 'var(--salvi-surface)', border: '1px solid var(--salvi-line)', borderRadius: '8px', padding: '10px 14px', minWidth: '140px', flex: '1 1 140px' }
  const lbl = { fontSize: '10px', color: 'var(--salvi-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }
  const val = { fontSize: '18px', fontWeight: '700', letterSpacing: '-0.02em', lineHeight: 1 }

  return (
    <div className="detail-section">
      <div className="detail-section-title" style={{ marginBottom: '10px' }}>
        Corrección de sombras locales
        <span style={{ fontSize: '11px', color: 'var(--salvi-grey)', fontWeight: '400', marginLeft: '8px' }}>
          PVGIS/JRC + {shading.provider || 'Shadowmap'}
        </span>
      </div>

      {!applied && (
        <div className="result-note" style={{ marginBottom: '10px' }}>
          ⚠️ {shading.warnings?.[0] || 'No se aplicó corrección de sombra local.'}
        </div>
      )}

      <div style={{ display: 'flex', gap: '10px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <div style={box}>
          <div style={lbl}>Pérdida directa anual</div>
          <div style={{ ...val, color: 'var(--state-warning)' }}>
            {shading.annual_direct_shadow_loss_pct != null ? shading.annual_direct_shadow_loss_pct.toFixed(1) + '%' : '–'}
          </div>
        </div>
        <div style={box}>
          <div style={lbl}>Pérdida total anual</div>
          <div style={val}>
            {shading.annual_total_shadow_loss_pct != null ? shading.annual_total_shadow_loss_pct.toFixed(1) + '%' : '–'}
          </div>
        </div>
        <div style={box}>
          <div style={lbl}>Mes crítico</div>
          <div style={{ ...val, color: 'var(--state-danger)' }}>
            {shading.critical_month_shadow_loss_pct != null ? shading.critical_month_shadow_loss_pct.toFixed(1) + '%' : '–'}
          </div>
        </div>
        <div style={box}>
          <div style={lbl}>Confianza</div>
          <div style={val}>
            {shading.confidence != null ? Math.round(shading.confidence * 100) + '%' : '–'}
          </div>
        </div>
      </div>

      {comparison && (
        <table className="detail-monthly-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Escenario</th>
              <th>Producción anual</th>
              <th>Fiabilidad año 1</th>
            </tr>
          </thead>
          <tbody>
            {['base_case', 'corrected_case'].map(k => {
              const row = comparison[k]
              if (!row) return null
              return (
                <tr key={k}>
                  <td style={{ fontWeight: '600' }}>{row.label}</td>
                  <td>{row.annual_production_kwh?.toFixed(1)} kWh</td>
                  <td>{(100 - (row.annual_failure_rate_pct || 0)).toFixed(1)}%</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {monthlyBaseWh && monthlyProductionWh && (
        <div style={{ marginTop: '14px' }}>
          <div className="detail-section-title" style={{ fontSize: '12px', marginBottom: '8px' }}>
            Producción mensual — sin sombra vs. con sombra vs. consumo
          </div>
          <div style={{ position: 'relative', height: '200px' }}>
            <canvas ref={canvasRef}></canvas>
          </div>
        </div>
      )}

      {comparison?.base_case && comparison?.corrected_case && (() => {
        const prodDelta = comparison.corrected_case.annual_production_kwh - comparison.base_case.annual_production_kwh
        const prodDeltaPct = comparison.base_case.annual_production_kwh
          ? (prodDelta / comparison.base_case.annual_production_kwh) * 100 : 0
        const relBase = 100 - (comparison.base_case.annual_failure_rate_pct || 0)
        const relCorr = 100 - (comparison.corrected_case.annual_failure_rate_pct || 0)
        const relDelta = relCorr - relBase
        return (
          <div style={{
            display: 'flex', gap: '16px', marginTop: '10px', padding: '10px 14px',
            background: 'var(--salvi-cream)', border: '1px solid var(--salvi-line)', borderRadius: '8px',
          }}>
            <div style={{ fontSize: '12px' }}>
              <span style={{ color: 'var(--salvi-grey)' }}>Δ Producción anual: </span>
              <strong style={{ color: prodDelta < 0 ? 'var(--state-warning)' : 'var(--state-success)' }}>
                {prodDelta >= 0 ? '+' : ''}{prodDelta.toFixed(0)} kWh ({prodDeltaPct >= 0 ? '+' : ''}{prodDeltaPct.toFixed(1)}%)
              </strong>
            </div>
            <div style={{ fontSize: '12px' }}>
              <span style={{ color: 'var(--salvi-grey)' }}>Δ Fiabilidad: </span>
              <strong style={{ color: relDelta < 0 ? 'var(--state-warning)' : 'var(--state-success)' }}>
                {relDelta >= 0 ? '+' : ''}{relDelta.toFixed(1)} pp
              </strong>
            </div>
          </div>
        )
      })()}

      <div className="field-help" style={{ marginTop: '8px' }}>
        La corrección afecta principalmente a la irradiancia directa; la difusa y reflejada
        no se anulan automáticamente. Altura de panel: {shading.height_mode === 'panel_center_height' ? 'centro del panel' : 'proxy a nivel de suelo'}.
      </div>
    </div>
  )
}

export default function CanvasDetalle() {
  const { state, dispatch } = useApp()
  const { simulation, selectedProductId, photometry, nightProfile, project } = state

  const [socTarget, setSocTarget] = useState(30)
  const [showTco, setShowTco] = useState(false)

  const monthlyChartRef = useRef(null)
  const socChartRef = useRef(null)
  const monthlyCanvasRef = useRef(null)
  const socCanvasRef = useRef(null)

  const c = simulation?.candidates?.find(cc => cc.product_id === selectedProductId)

  const monthly = c?.monthly_data || []

  useEffect(() => {
    if (!c || !monthlyCanvasRef.current || !socCanvasRef.current) return

    if (monthlyChartRef.current) { monthlyChartRef.current.destroy(); monthlyChartRef.current = null }
    if (socChartRef.current) { socChartRef.current.destroy(); socChartRef.current = null }

    const t = setTimeout(() => {
      monthlyChartRef.current = new Chart(monthlyCanvasRef.current, {
        type: 'bar',
        data: {
          labels: MONTHS,
          datasets: [
            {
              label: 'Producción (kWh/día)',
              data: monthly.map(m => +((m.production_kwh || 0)).toFixed(3)),
              backgroundColor: 'rgba(30,30,30,0.75)', borderRadius: 3,
            },
            {
              label: 'Consumo (kWh/noche)',
              data: monthly.map(m => +((m.consumption_kwh || 0)).toFixed(3)),
              backgroundColor: 'rgba(107,107,107,0.45)', borderRadius: 3,
            }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 10 } } },
          scales: {
            y: { beginAtZero: true, ticks: { font: { size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
            x: { ticks: { font: { size: 10 } }, grid: { display: false } }
          }
        }
      })

      socChartRef.current = new Chart(socCanvasRef.current, {
        type: 'line',
        data: {
          labels: MONTHS,
          datasets: [
            {
              label: 'SOC al anochecer (promedio)',
              data: monthly.map(m => m.soc_dusk_pct || 0),
              borderColor: 'rgba(30,30,30,0.7)', backgroundColor: 'rgba(30,30,30,0.07)',
              fill: true, tension: 0.4, pointRadius: 3, borderDash: [2,2],
            },
            {
              label: 'SOC mín. año 1',
              data: monthly.map(m => m.soc_min_pct || 0),
              borderColor: 'rgba(31,122,77,0.9)', backgroundColor: 'rgba(31,122,77,0.1)',
              fill: true, tension: 0.4, pointRadius: 3,
            },
            {
              label: 'SOC mín. año 10',
              data: monthly.map(m => m.soc_min_y10 || 0),
              borderColor: 'rgba(183,121,31,0.9)', fill: false, tension: 0.4, pointRadius: 3, borderDash: [4,4],
            }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, boxWidth: 10 } } },
          scales: {
            y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%', font: { size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
            x: { ticks: { font: { size: 10 } }, grid: { display: false } }
          }
        }
      })
    }, 100)

    return () => {
      clearTimeout(t)
      monthlyChartRef.current?.destroy()
      socChartRef.current?.destroy()
    }
  }, [selectedProductId, simulation])

  if (!c) return null

  const reliabilityPct = 100 - (c.annual_failure_rate_pct || 0)
  const reliabilityClass = reliabilityPct >= 98 ? 'success' : reliabilityPct >= 95 ? 'warning' : 'danger'
  const consumption = calcConsumoLive(photometry, nightProfile, project.lat || 41.4, 5)

  return (
    <div id="canvas-detail" className="canvas-panel" style={{ display: 'block' }}>
      <div id="detail-content" style={{ padding: '16px' }}>
        <div
          className="detail-back"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--salvi-grey)', cursor: 'pointer', marginBottom: '16px' }}
          onClick={() => dispatch({ type: 'SET_STEP', payload: 7 })}
        >
          ← Volver a comparativa
        </div>

        <div className="detail-header">
          <div>
            <div className="detail-product-name">
              {c.product_name || c.product_id}
              {c.n_units && c.n_units > 1 && (
                <span style={{ display:'inline-block',marginLeft:'6px',padding:'2px 8px',background:'#1E1E1E',color:'#FCF9F5',borderRadius:'5px',fontSize:'12px',fontWeight:'700',verticalAlign:'middle' }}>
                  ×{c.n_units} unidades
                </span>
              )}
              {c.recommended && (
                <span className="badge badge-success" style={{ fontSize: '12px', verticalAlign: 'middle', marginLeft: '8px' }}>
                  ★ Recomendado
                </span>
              )}
            </div>
            <div className="detail-product-sub">
              {c.pv_peak_power_wp || '–'} Wp · {c.battery_nominal_wh || '–'} Wh · {c.weight_kg ? c.weight_kg + ' kg est.' : '–'}
            </div>
          </div>
          <button className="btn-secondary" onClick={() => dispatch({ type: 'SET_STEP', payload: 7 })}>
            ← Volver
          </button>
        </div>

        <div className="detail-kpis">
          <div className="detail-kpi">
            <div className="detail-kpi-label">Fiabilidad año 1</div>
            <div className={`detail-kpi-value ${reliabilityClass}`}>{reliabilityPct.toFixed(1)}%</div>
            <div className="detail-kpi-sub">{(c.annual_failure_rate_pct || 0).toFixed(1)}% noches con fallo</div>
          </div>
          <div className="detail-kpi" onClick={() => setShowTco(true)} style={{
            cursor: 'pointer', transition: 'box-shadow 0.15s',
            outline: 'none',
          }}
            onMouseEnter={e => e.currentTarget.style.boxShadow = '0 0 0 2px var(--salvi-black, #1E1E1E)'}
            onMouseLeave={e => e.currentTarget.style.boxShadow = ''}
            title="Ver desglose de costes"
          >
            <div className="detail-kpi-label" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              TCO 10 años (venta)
              <span style={{ fontSize: 10, opacity: 0.5 }}>↗</span>
            </div>
            <div className="detail-kpi-value">{c.tco_10y_sale != null ? formatEur(c.tco_10y_sale) : '–'}</div>
            <div className="detail-kpi-sub">{c.tco_10y_cost != null ? formatEur(c.tco_10y_cost) + ' coste' : ''}</div>
          </div>
          <div className="detail-kpi">
            <div className="detail-kpi-label">CO₂ evitado 10a</div>
            <div className="detail-kpi-value success">{c.co2_saved_10y_kg != null ? Math.round(c.co2_saved_10y_kg) + ' kg' : '–'}</div>
            <div className="detail-kpi-sub">vs red eléctrica</div>
          </div>
          <div className="detail-kpi">
            <div className="detail-kpi-label">Autonomía diseño</div>
            <div className="detail-kpi-value">{c.autonomy_days != null ? c.autonomy_days + ' días' : '–'}</div>
            <div className="detail-kpi-sub">sin sol</div>
          </div>
          <div className="detail-kpi">
            <div className="detail-kpi-label">Fiabilidad año 10</div>
            <div className={`detail-kpi-value ${c.annual_failure_rate_pct_y10 != null && (100 - c.annual_failure_rate_pct_y10) >= 95 ? 'success' : 'warning'}`}>
              {c.annual_failure_rate_pct_y10 != null ? (100 - c.annual_failure_rate_pct_y10).toFixed(1) + '%' : '–'}
            </div>
            <div className="detail-kpi-sub">degradación batería</div>
          </div>
          <div className="detail-kpi">
            <div className="detail-kpi-label">Consumo estimado</div>
            <div className="detail-kpi-value">{consumption} Wh</div>
            <div className="detail-kpi-sub">por noche (~12h)</div>
          </div>
        </div>

        <ShadingCorrection
          shading={c.shading}
          comparison={c.shading_comparison}
          monthlyProductionWh={c.monthly_production_wh}
          monthlyConsumptionWh={c.monthly_consumption_wh}
        />

        {/* Two-column: loss tree left, monthly table right */}
        <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-start', margin: '16px 0' }}>

          {/* Left: Loss tree — half width */}
          <div className="detail-section" style={{ flex: '0 0 50%', minWidth: 0, margin: 0 }}>
            <LossTree lt={c.loss_tree} />
          </div>

          {/* Right: Monthly table */}
          <div className="detail-section" style={{ flex: 1, minWidth: 0, margin: 0 }}>
            <div className="detail-section-title" style={{ marginBottom: '12px' }}>
              Balance diario medio por mes
              <span style={{ fontSize: '11px', color: 'var(--salvi-grey)', fontWeight: '400', marginLeft: '8px' }}>
                (kWh/día · kWh/noche · difusa · SOC mínimo)
              </span>
            </div>
            {monthly.length === 0 ? (
              <div style={{ color: 'var(--salvi-muted)', fontSize: '13px', padding: '12px 0' }}>
                Los datos mensuales se muestran tras ejecutar la simulación.
              </div>
            ) : (
            <table className="detail-monthly-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Mes</th>
                  <th title="Producción solar diaria media del mes">Prod. kWh/día</th>
                  <th title="Fracción de irradiancia difusa — el cilindro BC captura mejor la luz difusa" style={{ color: 'var(--salvi-muted)', fontSize: '10px' }}>Difusa</th>
                  <th title="Consumo nocturno medio del mes">Cons. kWh/noche</th>
                  <th title="Balance diario medio: producción − consumo">Balance</th>
                  <th title="SOC mínimo alcanzado en el mes (año 1 — batería nueva)">SOC mín. a1</th>
                  <th title="SOC mínimo alcanzado en el mes (año 10 — batería degradada)" style={{ color: 'var(--salvi-muted)' }}>SOC mín. a10</th>
                  <th title="Noches donde el SOC cayó por debajo del umbral mínimo">Noches críticas</th>
                </tr>
              </thead>
              <tbody>
                {monthly.map((m, i) => {
                  const prod = m.production_kwh || 0
                  const cons = m.consumption_kwh || 0
                  const bal  = prod - cons
                  const soc1 = m.soc_min_pct || 0
                  const soc10 = m.soc_min_y10 || 0
                  const fails = m.failures || 0
                  const socClass = soc1 >= 30 ? 'var(--state-success)' : soc1 >= 15 ? 'var(--state-warning)' : 'var(--state-danger)'
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: '600' }}>{MONTHS[i]}</td>
                      <td>{prod.toFixed(2)}</td>
                      <td style={{ color: 'var(--salvi-muted)', fontSize: '11px' }}>
                        {((m.diffuse_fraction || 0) * 100).toFixed(0)}%
                      </td>
                      <td>{cons.toFixed(2)}</td>
                      <td style={{ color: bal >= 0 ? 'var(--state-success)' : 'var(--state-danger)', fontWeight: '600' }}>
                        {bal >= 0 ? '+' : ''}{bal.toFixed(2)}
                      </td>
                      <td style={{ color: socClass, fontWeight: '600' }}>{soc1.toFixed(0)}%</td>
                      <td style={{ color: 'var(--salvi-muted)' }}>{soc10.toFixed(0)}%</td>
                      <td style={{ color: fails > 0 ? 'var(--state-danger)' : 'var(--salvi-muted)' }}>
                        {fails > 0 ? fails : '–'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            )}
          </div>

        </div>

        <div className="detail-section">
          <div className="detail-section-title">Perfil de control nocturno (Smartec)</div>
          <SmartecSummary nightProfile={nightProfile} photometry={photometry} />
        </div>

        <SmartecIntelligence
          monthly={monthly}
          batWh={c.battery_nominal_wh || 1200}
          socTarget={socTarget}
          onSocTargetChange={setSocTarget}
        />

        <div className="detail-charts-row">
          <div className="chart-card">
            <div className="chart-title">Producción vs Consumo mensual</div>
            <div style={{ position: 'relative', height: '160px' }}>
              <canvas ref={monthlyCanvasRef}></canvas>
            </div>
          </div>
          <div className="chart-card">
            <div className="chart-title">SOC mínimo mensual (batería)</div>
            <div style={{ position: 'relative', height: '160px' }}>
              <canvas ref={socCanvasRef}></canvas>
            </div>
          </div>
        </div>
      </div>

      {showTco && <TcoModal c={c} onClose={() => setShowTco(false)} />}
    </div>
  )
}
