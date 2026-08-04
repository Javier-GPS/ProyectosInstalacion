import { useState, useEffect } from 'react'
import { useApp } from '../../context/AppContext'
import { MONTHS, calcConsumoLive, npNightHours } from '../../utils'

/**
 * Number input with a local text buffer, decoupled from the upstream (parent-derived)
 * numeric value while the user is typing. Without this, clearing the field to type a new
 * value (e.g. backspacing "20" to type "90") produces an intermediate empty string ->
 * parseFloat("") = NaN -> dispatched upstream -> the field silently breaks and stops
 * accepting input. Only valid numbers are committed upstream; on blur, an invalid/empty
 * buffer reverts to the last committed value.
 */
function PctInput({ value, onCommit, min = 0, max = 100, step = 1, style }) {
  const [local, setLocal] = useState(String(value))
  useEffect(() => { setLocal(String(value)) }, [value])

  return (
    <input
      type="number" min={min} max={max} step={step}
      value={local}
      style={style}
      onChange={e => {
        const raw = e.target.value
        setLocal(raw)
        const n = parseFloat(raw)
        if (!Number.isNaN(n)) onCommit(n)
      }}
      onBlur={() => {
        if (Number.isNaN(parseFloat(local))) setLocal(String(value))
      }}
    />
  )
}

export default function Step3PerfilNocturno() {
  const { state, dispatch } = useApp()
  const { nightProfile, photometry, project, npMonth } = state
  const { periods, margin_on_min, margin_off_min, aux_wh } = nightProfile

  const displayMonth = npMonth ?? 5
  const setDisplayMonth = (m) => dispatch({ type: 'SET_NP_MONTH', payload: m })

  const updateProfile = (field, value) => {
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: { [field]: value } })
  }

  const updatePeriod = (idx, field, value) => {
    const newPeriods = periods.map((p, i) =>
      i === idx ? { ...p, [field]: value } : p
    )
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: { periods: newPeriods } })
  }

  const addPeriod = () => {
    const pr = periods[0]?.presence_ratio ?? 0.5
    const newPeriod = { duration_pct: 0.1, presence_ratio: pr, dimming_presence: 0.8, dimming_no_presence: 0.2 }
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: { periods: [...periods, newPeriod] } })
  }

  const deletePeriod = (idx) => {
    if (periods.length <= 1) return
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: { periods: periods.filter((_, i) => i !== idx) } })
  }

  const resetPeriods = () => {
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: {
      periods: [
        { duration_pct: 0.333, presence_ratio: 0.5,  dimming_presence: 1.0, dimming_no_presence: 0.3 },
        { duration_pct: 0.333, presence_ratio: 0.2,  dimming_presence: 0.8, dimming_no_presence: 0.2 },
        { duration_pct: 0.334, presence_ratio: 0.3,  dimming_presence: 0.8, dimming_no_presence: 0.2 },
      ],
    }})
  }

  const addSegment = () => {
    // Find longest segment and split it
    let longest = 0, li = 0
    for (let i = 0; i < periods.length; i++) {
      if (periods[i].duration_pct > longest) { longest = periods[i].duration_pct; li = i }
    }
    const half = periods[li].duration_pct / 2
    const newPeriods = [
      ...periods.slice(0, li),
      { ...periods[li], duration_pct: half },
      { ...periods[li], duration_pct: half },
      ...periods.slice(li + 1),
    ]
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: { periods: newPeriods } })
  }

  const setPresence = (pct) => {
    const ratio = pct / 100
    const newPeriods = periods.map(p => ({ ...p, presence_ratio: ratio }))
    dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: { periods: newPeriods } })
  }

  const P = photometry.system_power_w || 90
  const nightH = npNightHours(project.lat || 41.4, displayMonth)

  const calcPeriodWh = (p) => {
    const h = (p.duration_pct || 0.333) * nightH
    return Math.round(P * h * (
      (p.presence_ratio || 0) * (p.dimming_presence || 1.0) +
      (1 - (p.presence_ratio || 0)) * (p.dimming_no_presence || 0.2)
    ))
  }

  // "Consumo estimado" muestra la media anual (estable, no cambia al mover el slider de mes,
  // que solo sirve para previsualizar la forma del perfil) — el detalle mes a mes va en la
  // tabla de abajo.
  const monthlyConsumption = MONTHS.map((_, m) =>
    calcConsumoLive(photometry, nightProfile, project.lat || 41.4, m)
  )
  const avgConsumption = Math.round(monthlyConsumption.reduce((a, b) => a + b, 0) / 12)
  const presenceRatio = periods[0]?.presence_ratio ?? 0.5

  return (
    <div className="step-form active">
      <h3 className="step-header">Perfil Nocturno</h3>

      <div className="twilight-config">
        <div className="field-row">
          <div className="field-group half">
            <label>Encendido</label>
            <div className="input-with-badge">
              <input
                type="number"
                min="-30"
                max="30"
                value={margin_on_min}
                onChange={e => updateProfile('margin_on_min', parseInt(e.target.value))}
              />
              <span className="unit" style={{ fontSize: '10px' }}>min antes del ocaso</span>
            </div>
          </div>
          <div className="field-group half">
            <label>Apagado</label>
            <div className="input-with-badge">
              <input
                type="number"
                min="-30"
                max="30"
                value={margin_off_min}
                onChange={e => updateProfile('margin_off_min', parseInt(e.target.value))}
              />
              <span className="unit" style={{ fontSize: '10px' }}>min después del alba</span>
            </div>
          </div>
        </div>
      </div>

      <div className="np-sliders">
        <div className="np-slider-row">
          <span className="np-slider-label">Mes</span>
          <input
            type="range"
            className="np-slider-input"
            min="0"
            max="11"
            value={displayMonth}
            onChange={e => setDisplayMonth(parseInt(e.target.value))}
          />
          <span className="np-slider-val">{MONTHS[displayMonth]}</span>
        </div>
        <div className="np-slider-hint">Previsualiza horas de noche por mes</div>

        <div className="np-slider-row">
          <span className="np-slider-label">Presencia</span>
          <input
            type="range"
            className="np-slider-input"
            min="0"
            max="100"
            value={Math.round(presenceRatio * 100)}
            onChange={e => setPresence(parseInt(e.target.value))}
          />
          <span className="np-slider-val">{Math.round(presenceRatio * 100)}%</span>
        </div>
        <div className="np-slider-hint">100% = sin sensor · 0% = siempre sin presencia</div>

        <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
          <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={addSegment}>
            + Segmento
          </button>
          <button className="btn-link btn-sm" onClick={() => {
            dispatch({ type: 'UPDATE_NIGHT_PROFILE', payload: {
              periods: [
                { duration_pct: 0.333, presence_ratio: 0.5,  dimming_presence: 1.0, dimming_no_presence: 0.3 },
                { duration_pct: 0.333, presence_ratio: 0.2,  dimming_presence: 0.8, dimming_no_presence: 0.2 },
                { duration_pct: 0.334, presence_ratio: 0.3,  dimming_presence: 0.8, dimming_no_presence: 0.2 },
              ],
            }})
          }}>
            ↺ Defecto
          </button>
        </div>
      </div>

      <div className="section-label">Periodos nocturnos</div>
      <table className="periods-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Duración<br /><small>% noche</small></th>
            <th>Presencia<br /><small>%</small></th>
            <th>Dim.pres.<br /><small>%</small></th>
            <th>Dim.s/p.<br /><small>%</small></th>
            <th>Wh</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {periods.map((p, i) => (
            <tr key={i}>
              <td style={{ textAlign: 'center', fontWeight: '600', color: 'var(--salvi-grey)' }}>{i + 1}</td>
              <td>
                <PctInput
                  min="0.01" step="1"
                  value={(p.duration_pct * 100).toFixed(1)}
                  onCommit={n => updatePeriod(i, 'duration_pct', n / 100)}
                />
              </td>
              <td>
                <PctInput
                  value={Math.round(p.presence_ratio * 100)}
                  onCommit={n => updatePeriod(i, 'presence_ratio', n / 100)}
                />
                <input
                  type="range" min="0" max="100" step="1"
                  value={Math.round(p.presence_ratio * 100)}
                  onChange={e => updatePeriod(i, 'presence_ratio', parseFloat(e.target.value) / 100)}
                  style={{ width: '100%', marginTop: '3px', accentColor: 'var(--salvi-black)', cursor: 'pointer' }}
                  title={`Presencia periodo ${i + 1}: ${Math.round(p.presence_ratio * 100)}%`}
                />
              </td>
              <td>
                <PctInput
                  value={Math.round(p.dimming_presence * 100)}
                  onCommit={n => updatePeriod(i, 'dimming_presence', n / 100)}
                />
              </td>
              <td>
                <PctInput
                  value={Math.round(p.dimming_no_presence * 100)}
                  onCommit={n => updatePeriod(i, 'dimming_no_presence', n / 100)}
                />
              </td>
              <td className="col-wh">{calcPeriodWh(p)}</td>
              <td>
                <button className="period-del" onClick={() => deletePeriod(i)} title="Eliminar">✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="table-actions">
        <button className="btn-secondary btn-sm" onClick={addPeriod}>+ Añadir</button>
        <button className="btn-link btn-sm" onClick={resetPeriods}>↺ Defecto</button>
      </div>

      <div className="consumption-summary">
        <span className="consumption-label">Consumo estimado:</span>
        <span className="consumption-value">{avgConsumption} Wh/noche</span>
        <span className="consumption-note">media anual · noche ~{nightH.toFixed(1)}h en {MONTHS[displayMonth]}</span>
      </div>

      <table className="periods-table" style={{ marginBottom: '12px' }}>
        <thead>
          <tr>
            {MONTHS.map((m, i) => (
              <th key={i} style={{ fontWeight: i === displayMonth ? 700 : 600, color: i === displayMonth ? 'var(--salvi-black)' : 'var(--salvi-grey)' }}>
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {monthlyConsumption.map((wh, i) => (
              <td key={i} style={{ textAlign: 'center', fontWeight: i === displayMonth ? 700 : 400 }}>
                {wh}
              </td>
            ))}
          </tr>
        </tbody>
      </table>

      <div className="field-group">
        <label>Consumo auxiliar (nodo, controlador) <span className="unit">Wh/noche</span></label>
        <input
          type="number"
          min="0"
          max="50"
          step="0.5"
          value={aux_wh || 0}
          onChange={e => updateProfile('aux_wh', parseFloat(e.target.value))}
        />
      </div>
    </div>
  )
}
