import { useApp } from '../../context/AppContext'
import { COUNTRY_DATA } from '../../utils'

export default function Step1Proyecto() {
  const { state, dispatch } = useApp()
  const { project, env } = state

  const update = (field, value) => {
    dispatch({ type: 'UPDATE_PROJECT', payload: { [field]: value } })
  }

  const updateEnv = (field, value) => {
    dispatch({ type: 'UPDATE_ENV', payload: { [field]: value } })
  }

  const onCountryChange = (code) => {
    update('country', code)
    const d = COUNTRY_DATA[code]
    if (d) {
      dispatch({ type: 'UPDATE_ENV', payload: {
        country_co2_factor: d.co2,
        electricity_cost: d.electricity_cost,
      }})
    }
  }

  return (
    <div className="step-form active">
      <h3 className="step-header">Proyecto</h3>

      <div className="field-group">
        <label>Nombre del proyecto *</label>
        <input
          type="text"
          placeholder="Ej: Carrer Mallorca, Barcelona"
          value={project.name}
          onChange={e => update('name', e.target.value)}
        />
      </div>

      <div className="field-group">
        <label>País</label>
        <select value={project.country} onChange={e => onCountryChange(e.target.value)}>
          <option value="ES">España</option>
          <option value="FR">Francia</option>
          <option value="DE">Alemania</option>
          <option value="IT">Italia</option>
          <option value="PT">Portugal</option>
          <option value="MA">Marruecos</option>
          <option value="DZ">Argelia</option>
          <option value="TN">Túnez</option>
          <option value="SN">Senegal</option>
          <option value="EG">Egipto</option>
          <option value="NG">Nigeria</option>
          <option value="KE">Kenia</option>
          <option value="ZA">Sudáfrica</option>
          <option value="SA">Arabia Saudí</option>
          <option value="IN">India</option>
          <option value="BR">Brasil</option>
          <option value="MX">México</option>
        </select>
      </div>

      <div className="field-group">
        <label>Ciudad</label>
        <input
          type="text"
          placeholder="Barcelona"
          value={project.city}
          onChange={e => update('city', e.target.value)}
        />
      </div>

      <div className="field-row">
        <div className="field-group half">
          <label>Latitud *</label>
          <input
            type="number"
            step="0.0001"
            min="-90"
            max="90"
            placeholder="41.3851"
            value={project.lat ?? ''}
            onChange={e => update('lat', e.target.value === '' ? null : parseFloat(e.target.value))}
          />
        </div>
        <div className="field-group half">
          <label>Longitud *</label>
          <input
            type="number"
            step="0.0001"
            min="-180"
            max="180"
            placeholder="2.1734"
            value={project.lon ?? ''}
            onChange={e => update('lon', e.target.value === '' ? null : parseFloat(e.target.value))}
          />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
        <button
          className="btn-secondary btn-block"
          style={{ fontSize: '13px' }}
          onClick={() => dispatch({ type: 'SET_MAP_PICKER_OPEN', payload: true })}
        >
          🗺 Abrir mapa
        </button>
        <button
          className="btn-secondary btn-block"
          style={{ fontSize: '13px' }}
          onClick={() => dispatch({ type: 'SET_GIS_IMPORT_OPEN', payload: true })}
        >
          ↗ Importar desde SALVI GIS
        </button>
      </div>

      <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--salvi-line)' }}>
        <div style={{
          fontSize: '11px', fontWeight: '600', letterSpacing: '.06em',
          textTransform: 'uppercase', color: 'var(--salvi-muted)', marginBottom: '10px',
        }}>
          Parámetros de entorno
        </div>

        <div className="field-group">
          <label>Nivel de suciedad</label>
          <select value={env.soiling_env} onChange={e => updateEnv('soiling_env', e.target.value)}>
            <option value="verde_lluviosa">Verde / lluviosa (4%)</option>
            <option value="urbana_normal">Urbana normal (7%)</option>
            <option value="polvo_medio">Polvo medio (10%)</option>
            <option value="desierto_alto">Desierto / polvo alto (20%)</option>
          </select>
        </div>

        <div className="field-row">
          <div className="field-group half">
            <label>Temperatura diseño <span className="unit">°C</span></label>
            <input
              type="number"
              min="-10"
              max="60"
              value={env.ambient_temp_c}
              onChange={e => updateEnv('ambient_temp_c', parseFloat(e.target.value))}
            />
          </div>
          <div className="field-group half">
            <label>Fiabilidad mínima <span className="unit">% fallo máx.</span></label>
            <input
              type="number"
              min="0.1"
              max="20"
              step="0.1"
              value={env.max_failure_rate_pct}
              onChange={e => updateEnv('max_failure_rate_pct', parseFloat(e.target.value))}
            />
          </div>
        </div>

        <div className="field-row">
          <div className="field-group half">
            <label>Coste electricidad <span className="unit">€/kWh</span></label>
            <input
              type="number"
              min="0.01"
              max="1"
              step="0.01"
              value={env.electricity_cost}
              onChange={e => updateEnv('electricity_cost', parseFloat(e.target.value))}
            />
          </div>
          <div className="field-group half">
            <label>Factor CO₂ red <span className="unit">kg/kWh</span></label>
            <input
              type="number"
              min="0.01"
              max="1.5"
              step="0.01"
              value={env.country_co2_factor}
              onChange={e => updateEnv('country_co2_factor', parseFloat(e.target.value))}
            />
          </div>
        </div>
        <div className="field-help">Coste y CO₂ se actualizan al elegir país. Editables.</div>
      </div>
    </div>
  )
}
