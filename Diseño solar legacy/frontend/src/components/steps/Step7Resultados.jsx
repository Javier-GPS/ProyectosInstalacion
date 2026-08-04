import { useApp } from '../../context/AppContext'
import { downloadFile } from '../../utils'
import { showToast } from '../Toast'

export default function Step7Resultados() {
  const { state, dispatch } = useApp()
  const { simulation, project } = state

  const exportCSV = () => {
    if (!simulation?.candidates) {
      showToast('No hay datos de simulación para exportar', 'warning')
      return
    }
    const headers = ['Producto','Panel Wp','Batería Wh','Peso kg','Fiabilidad %','TCO 10a €','CO2 10a kg','Fiab. año 10 %','Recomendado']
    const rows = simulation.candidates.map(c => [
      c.product_name || c.product_id,
      c.pv_peak_power_wp || '',
      c.battery_nominal_wh || '',
      c.weight_kg || '',
      (100 - (c.annual_failure_rate_pct || 0)).toFixed(1),
      c.tco_10y_sale != null ? c.tco_10y_sale.toFixed(0) : '',
      c.co2_saved_10y_kg != null ? Math.round(c.co2_saved_10y_kg) : '',
      c.annual_failure_rate_pct_y10 != null ? (100 - c.annual_failure_rate_pct_y10).toFixed(1) : '',
      c.recommended ? 'Sí' : 'No',
    ])
    const csv = [headers, ...rows].map(r => r.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(',')).join('\n')
    downloadFile('SALVI_Solar_' + (project.name || 'resultados').replace(/\s+/g, '_') + '.csv', csv, 'text/csv')
    showToast('CSV exportado', 'success')
  }

  const exportJSON = () => {
    if (!simulation) { showToast('No hay datos de simulación', 'warning'); return }
    const data = {
      meta: { exported: new Date().toISOString(), project: state.project },
      params: { photometry: state.photometry, nightProfile: state.nightProfile, env: state.env },
      simulation,
    }
    downloadFile('SALVI_Solar_' + (project.name || 'proyecto').replace(/\s+/g, '_') + '.json',
      JSON.stringify(data, null, 2), 'application/json')
    showToast('JSON exportado', 'success')
  }

  const count = simulation?.candidates?.length || 0

  return (
    <div className="step-form active">
      <h3 className="step-header">Resultados</h3>
      <div className="results-info">
        <span>Comparativa de <strong>{count}</strong> soluciones</span>
      </div>
      <div className="result-note">Consulta la tabla comparativa en el área central →</div>
      <div className="gap-btn mt-8">
        <button className="btn-secondary btn-sm" onClick={exportCSV}>📊 Exportar CSV</button>
        <button className="btn-secondary btn-sm" onClick={exportJSON}>{'{ }'} JSON</button>
      </div>
    </div>
  )
}
