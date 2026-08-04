import { useApp } from '../../context/AppContext'

export default function Step4Entorno() {
  const { state, dispatch } = useApp()
  const { env } = state

  const updateEnv = (field, value) => {
    dispatch({ type: 'UPDATE_ENV', payload: { [field]: value } })
  }

  return (
    <div className="step-form active">
      <h3 className="step-header">Entorno</h3>

      <div className="field-help" style={{ marginBottom: '12px' }}>
        Curvas de irradiancia solar por tipo de panel — ver canvas a la derecha.
      </div>

      <div style={{ marginTop: '4px', paddingTop: '12px', borderTop: '1px solid var(--salvi-line)' }}>
        <div style={{
          fontSize: '11px', fontWeight: '600', letterSpacing: '.06em',
          textTransform: 'uppercase', color: 'var(--salvi-muted)', marginBottom: '10px',
        }}>
          Corrección de sombras locales 3D
        </div>
        <div className="field-help" style={{ marginBottom: '10px' }}>
          PVGIS/JRC sigue siendo la fuente base de irradiancia. Cuando se activa, Shadowmap
          corrige la componente directa según obstáculos 3D locales (edificios, árboles,
          calles estrechas) — la difusa nunca se anula automáticamente.
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', marginBottom: '12px' }}>
          <input
            type="checkbox"
            checked={env.use_local_shading}
            onChange={e => updateEnv('use_local_shading', e.target.checked)}
          />
          <span>Activar corrección Shadowmap</span>
        </label>

        {env.use_local_shading && (
          <>
            <div className="field-group">
              <label>Modo de cálculo</label>
              <select
                value={env.shading_mode}
                onChange={e => updateEnv('shading_mode', e.target.value)}
              >
                <option value="PVGIS_SHADOWMAP_POINT">PVGIS + Shadowmap punto/hora</option>
              </select>
              <div className="field-help">
                Fase 1: solo el modo punto/hora está disponible (un único punto por proyecto).
              </div>
            </div>

            <div className="field-row">
              <div className="field-group half">
                <label>Altura del panel <span className="unit">m</span></label>
                <input
                  type="number"
                  min="0" max="20" step="0.5"
                  value={env.panel_center_height_m}
                  onChange={e => updateEnv('panel_center_height_m', parseFloat(e.target.value) || 0)}
                />
              </div>
              <div className="field-group half">
                <label>Entorno de sombra</label>
                <select
                  value={env.shading_environment_context}
                  onChange={e => updateEnv('shading_environment_context', e.target.value)}
                >
                  <option value="open_area">Zona abierta</option>
                  <option value="urban_street">Calle urbana normal</option>
                  <option value="urban_canyon">Calle estrecha / cañón urbano</option>
                  <option value="dense_trees">Arbolado denso</option>
                </select>
              </div>
            </div>

            <div className="field-group">
              <label>Escenario de prueba (mock)</label>
              <select
                value={env.shadowmap_mock_scenario}
                onChange={e => updateEnv('shadowmap_mock_scenario', e.target.value)}
              >
                <option value="open_area">Zona abierta — siempre sol directo</option>
                <option value="urban_canyon">Cañón urbano — sombra en horas de sol bajo</option>
                <option value="tree_shading">Arbolado — sombra parcial variable</option>
                <option value="morning_shadow">Sombra de mañana</option>
                <option value="afternoon_shadow">Sombra de tarde</option>
                <option value="low_confidence">Baja confianza — no se aplica corrección</option>
                <option value="no_data">Sin datos — no se aplica corrección</option>
              </select>
              <div className="field-help">
                Sin credenciales reales de Shadowmap todavía: se usa un proveedor simulado
                (mock) con estos escenarios para desarrollo y pruebas.
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
