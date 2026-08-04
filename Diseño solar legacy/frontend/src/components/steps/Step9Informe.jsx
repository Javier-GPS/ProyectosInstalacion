import { useState } from 'react'
import { useApp } from '../../context/AppContext'
import { downloadFile } from '../../utils'
import { showToast } from '../Toast'

export default function Step9Informe() {
  const { state } = useApp()
  const { simulation, project, photometry, nightProfile, env } = state
  const [generatingDoc, setGeneratingDoc] = useState(false)

  const exportJSON = () => {
    if (!simulation) { showToast('No hay datos de simulación', 'warning'); return }
    const data = {
      meta: { exported: new Date().toISOString(), project },
      params: { photometry, nightProfile, env },
      simulation,
    }
    downloadFile('SALVI_Solar_' + (project.name || 'proyecto').replace(/\s+/g, '_') + '.json',
      JSON.stringify(data, null, 2), 'application/json')
    showToast('JSON exportado', 'success')
  }

  const exportCSV = () => {
    if (!simulation?.candidates) { showToast('No hay datos', 'warning'); return }
    const headers = ['Producto','Panel Wp','Batería Wh','Fiabilidad %','TCO 10a €','CO2 10a kg','Recomendado']
    const rows = simulation.candidates.map(c => [
      c.product_name || c.product_id,
      c.pv_peak_power_wp || '',
      c.battery_nominal_wh || '',
      (100 - (c.annual_failure_rate_pct || 0)).toFixed(1),
      c.tco_10y_sale != null ? c.tco_10y_sale.toFixed(0) : '',
      c.co2_saved_10y_kg != null ? Math.round(c.co2_saved_10y_kg) : '',
      c.recommended ? 'Sí' : 'No',
    ])
    const csv = [headers, ...rows].map(r => r.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(',')).join('\n')
    downloadFile('SALVI_Solar_' + (project.name || 'resultados').replace(/\s+/g, '_') + '.csv', csv, 'text/csv')
    showToast('CSV exportado', 'success')
  }

  const generateReport = async () => {
    if (!simulation) { showToast('Ejecuta la simulación primero', 'warning'); return }
    setGeneratingDoc(true)
    try {
      const resp = await fetch('/api/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project, photometry, nightProfile, env, simulation }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.error || 'Error ' + resp.status)
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `SALVI_Solar_${(project.name || 'informe').replace(/\s+/g, '_')}.docx`
      a.click()
      URL.revokeObjectURL(url)
      showToast('Informe Word generado', 'success')
    } catch (e) {
      showToast('Error al generar informe: ' + e.message, 'error')
    } finally {
      setGeneratingDoc(false)
    }
  }

  const rec = simulation?.candidates?.find(c => c.recommended)

  return (
    <div className="step-form active">
      <h3 className="step-header">Informe y Exportación</h3>

      <div className="export-options">
        <button className="btn-primary btn-block" onClick={generateReport} disabled={generatingDoc || !simulation}>
          {generatingDoc ? '⏳ Generando documento…' : '📄 Generar informe Word (.docx)'}
        </button>
        <button className="btn-secondary btn-block" onClick={exportJSON}>
          {'{ }'} Exportar JSON completo
        </button>
        <button className="btn-secondary btn-block" onClick={exportCSV}>
          📊 Exportar tabla CSV
        </button>
      </div>

      <div className="export-info">
        {!simulation ? (
          'Ejecuta la simulación para habilitar la exportación.'
        ) : (
          <>
            Proyecto: <strong>{project.name || '–'}</strong><br />
            Ubicación: {project.city || ''} ({project.lat}, {project.lon})<br />
            Soluciones: {simulation.candidates?.length || 0}<br />
            Recomendada: <strong>{rec ? (rec.product_name || rec.product_id) : '–'}</strong>
          </>
        )}
      </div>
    </div>
  )
}
