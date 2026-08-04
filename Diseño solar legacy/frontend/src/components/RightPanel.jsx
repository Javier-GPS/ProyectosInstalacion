import { useApp } from '../context/AppContext'
import { calcConsumoLive, formatEur } from '../utils'

export default function RightPanel() {
  const { state, dispatch } = useApp()
  const { project, photometry, nightProfile, candidates, simulation } = state
  const hasSimulation = !!simulation

  const consumption = calcConsumoLive(photometry, nightProfile, project.lat || 41.4, 5)

  const checks = [
    { label: 'Nombre del proyecto', ok: !!project.name },
    { label: 'Coordenadas GPS', ok: !!(project.lat && project.lon) },
    { label: 'Potencia luminaria', ok: photometry.system_power_w > 0 },
    { label: 'Periodos nocturnos', ok: nightProfile.periods.length > 0 },
    { label: 'Candidatos seleccionados', ok: candidates.length > 0 },
  ]

  if (!hasSimulation) {
    return (
      <aside id="right-panel">
        <div className="rp-section">
          <div className="rp-title">Estado del proyecto</div>
          <div className="rp-checklist">
            {checks.map((c, i) => (
              <div key={i} className="rp-check-item">
                <div className={`rp-check-dot ${c.ok ? 'ok' : 'pending'}`}></div>
                <span>{c.label}</span>
              </div>
            ))}
          </div>
          <div className="rp-consumption">
            <div className="rp-label">Consumo estimado</div>
            <div className="rp-value">{consumption} Wh/noche</div>
          </div>
          <button
            className="btn-primary btn-block"
            style={{ marginTop: '8px' }}
            onClick={() => dispatch({ type: 'SET_STEP', payload: 6 })}
          >
            Ejecutar Simulación →
          </button>
        </div>
      </aside>
    )
  }

  // Post-simulation: recommended product
  const recommended = simulation.candidates?.find(c => c.recommended)

  return (
    <aside id="right-panel">
      <div className="rp-section">
        <div className="rp-title">★ Solución Recomendada</div>
        {recommended ? (
          <>
            <div className="rp-product-name">
              {recommended.product_name || recommended.product_id}
            </div>
            <div className="rp-specs">
              {[
                recommended.pv_peak_power_wp ? `${recommended.pv_peak_power_wp} Wp` : null,
                recommended.battery_nominal_wh ? `${recommended.battery_nominal_wh} Wh` : null,
                recommended.weight_kg ? `${recommended.weight_kg} kg` : null,
              ].filter(Boolean).join(' · ')}
            </div>
            <div className="rp-kpis">
              {(() => {
                const relPct = 100 - (recommended.annual_failure_rate_pct || 0)
                const relClass = relPct >= 98 ? 'success' : relPct >= 95 ? 'warning' : 'danger'
                const y10rel = recommended.annual_failure_rate_pct_y10 != null
                  ? (100 - recommended.annual_failure_rate_pct_y10).toFixed(1) + '%'
                  : '–'
                return (
                  <>
                    <div className="rp-kpi">
                      <div className="rp-kpi-label">Fiabilidad año 1</div>
                      <div className={`rp-kpi-value ${relClass}`}>{relPct.toFixed(1)}%</div>
                    </div>
                    <div className="rp-kpi">
                      <div className="rp-kpi-label">TCO 10 años</div>
                      <div className="rp-kpi-value">
                        {recommended.tco_10y_sale != null ? formatEur(recommended.tco_10y_sale) : '–'}
                      </div>
                    </div>
                    <div className="rp-kpi">
                      <div className="rp-kpi-label">CO₂ evitado</div>
                      <div className="rp-kpi-value success">
                        {recommended.co2_saved_10y_kg != null
                          ? `${Math.round(recommended.co2_saved_10y_kg)} kg`
                          : '–'}
                      </div>
                    </div>
                    <div className="rp-kpi">
                      <div className="rp-kpi-label">Batería año 10</div>
                      <div className="rp-kpi-value">{y10rel}</div>
                    </div>
                  </>
                )
              })()}
            </div>
          </>
        ) : (
          <div style={{ fontSize: '12px', color: 'var(--salvi-muted)', padding: '8px 0' }}>
            No hay solución recomendada en los resultados.
          </div>
        )}
        <button
          className="btn-secondary btn-block"
          onClick={() => dispatch({ type: 'SET_STEP', payload: 7 })}
        >
          Ver comparativa →
        </button>
      </div>
    </aside>
  )
}
