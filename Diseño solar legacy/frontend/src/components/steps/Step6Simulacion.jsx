import { useApp } from '../../context/AppContext'
import { showToast } from '../Toast'
import { apiPost } from '../../api'

export default function Step6Simulacion() {
  const { state, dispatch } = useApp()
  const { project, photometry, nightProfile, env, candidates, simulation, simulating } = state

  const handleSimulate = async () => {
    if (!project.lat || !project.lon) {
      showToast('Define latitud y longitud del proyecto', 'error')
      return
    }
    if (candidates.length === 0) {
      showToast('Selecciona al menos una solución candidata', 'error')
      return
    }

    dispatch({ type: 'SET_SIMULATING', payload: true })

    const payload = {
      lat: project.lat,
      lon: project.lon,
      system_power_w: photometry.system_power_w,
      lighting_class: photometry.lighting_class,
      mounting_height_m: photometry.mounting_height_m,
      spacing_m: photometry.spacing_m,
      compliance_margin_pct: photometry.compliance_margin_pct,
      night_profile: nightProfile.periods,
      margin_on_min: nightProfile.margin_on_min,
      margin_off_min: nightProfile.margin_off_min,
      candidates: candidates,
      soiling_env: env.soiling_env,
      electricity_cost: env.electricity_cost,
      country_co2_factor: env.country_co2_factor,
      max_failure_rate_pct: env.max_failure_rate_pct,
      aux_consumption_wh: nightProfile.aux_wh || 0,
      smartec_enabled: true,
      year: 2024,
      use_local_shading: env.use_local_shading,
      shading_mode: env.shading_mode,
      shading_environment_context: env.shading_environment_context,
      panel_center_height_m: env.panel_center_height_m,
      shadowmap_mock_scenario: env.shadowmap_mock_scenario,
    }

    try {
      const result = await apiPost('/simulate', payload)
      dispatch({ type: 'SET_SIMULATION', payload: result })
      showToast('Simulación completada — ' + (result.candidates?.length || 0) + ' soluciones', 'success')
      dispatch({ type: 'SET_STEP', payload: 7 })
    } catch (e) {
      dispatch({ type: 'SET_SIMULATING', payload: false })
      showToast('Error en simulación: ' + e.message, 'error')
    }
  }

  const locStr = project.city
    ? project.city + (project.lat ? ` (${project.lat.toFixed(4)}, ${project.lon.toFixed(4)})` : '')
    : (project.lat ? `${project.lat.toFixed(4)}, ${project.lon.toFixed(4)}` : '–')

  const canRun = project.lat && project.lon && candidates.length > 0 && !simulating

  return (
    <div className="step-form active">
      <h3 className="step-header">Simulación</h3>

      <div className="sim-pre">
        <div className="sim-summary">
          <div className="sim-summary-item">
            <span>Ubicación</span>
            <strong>{locStr || '–'}</strong>
          </div>
          <div className="sim-summary-item">
            <span>Potencia</span>
            <strong>{photometry.system_power_w} W</strong>
          </div>
          <div className="sim-summary-item">
            <span>Candidatos</span>
            <strong>{candidates.length} productos</strong>
          </div>
          <div className="sim-summary-item">
            <span>Períodos nocturnos</span>
            <strong>{nightProfile.periods.length} tramos</strong>
          </div>
        </div>

        <button
          className="btn-primary btn-large btn-block"
          onClick={handleSimulate}
          disabled={!canRun}
          style={{ marginTop: '14px', position: 'relative' }}
        >
          {simulating ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
              <span style={{
                width: '14px', height: '14px', border: '2px solid rgba(255,255,255,0.4)',
                borderTopColor: '#fff', borderRadius: '50%',
                display: 'inline-block', animation: 'spin 0.8s linear infinite',
              }} />
              Calculando…
            </span>
          ) : '▶ Ejecutar Simulación'}
        </button>

        {simulating && (
          <div style={{
            marginTop: '12px', padding: '10px 14px',
            background: 'rgba(0,0,0,0.03)', borderRadius: '6px',
            fontSize: '11px', color: 'var(--salvi-grey)', lineHeight: '1.7',
          }}>
            <div>⏳ Consultando PVGIS/JRC para <strong>{candidates.length}</strong> producto{candidates.length !== 1 ? 's' : ''}…</div>
            <div style={{ color: 'var(--salvi-muted)', marginTop: '4px' }}>
              Puede tardar 30–90 segundos según la carga del servidor.
            </div>
          </div>
        )}

        {!simulating && (
          <div className="sim-note" style={{ marginTop: '12px' }}>
            <strong>Fuente solar:</strong> PVGIS/JRC (Comisión Europea)<br />
            El cálculo puede tardar 30–60 s dependiendo de los candidatos.
          </div>
        )}

        {simulation && !simulating && (
          <div style={{ marginTop: '14px' }}>
            <div className="section-label">Última simulación</div>
            <div style={{ fontSize: '12px', color: 'var(--salvi-grey)', marginTop: '4px' }}>
              {simulation.candidates?.length || 0} soluciones procesadas
            </div>
            <button
              className="btn-secondary btn-sm btn-block"
              style={{ marginTop: '8px' }}
              onClick={() => dispatch({ type: 'SET_STEP', payload: 7 })}
            >
              Ver resultados →
            </button>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
