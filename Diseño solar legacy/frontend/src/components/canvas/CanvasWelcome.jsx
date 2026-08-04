import { useApp } from '../../context/AppContext'
import { calcConsumoLive } from '../../utils'

export default function CanvasWelcome() {
  const { state, dispatch } = useApp()
  const { project, photometry, nightProfile, candidates } = state

  const consumption = calcConsumoLive(photometry, nightProfile, project.lat || 41.4, 5)

  const locStr = project.lat && project.lon
    ? (project.city ? project.city + ' · ' : '') + project.lat.toFixed(4) + ', ' + project.lon.toFixed(4)
    : project.city || '–'

  return (
    <div className="canvas-panel">
      <div className="welcome-content">
        <div className="welcome-icon">☀</div>
        <h2 className="welcome-title">SALVI Solar</h2>
        <p className="welcome-subtitle">Dimensionamiento solar inteligente para alumbrado público</p>
        <div className="welcome-summary">
          <div className="welcome-summary-row">
            <span className="label">Proyecto</span>
            <span className="val">{project.name || '–'}</span>
          </div>
          <div className="welcome-summary-row">
            <span className="label">Ubicación</span>
            <span className="val">{locStr}</span>
          </div>
          <div className="welcome-summary-row">
            <span className="label">Potencia</span>
            <span className="val">{photometry.system_power_w} W</span>
          </div>
          <div className="welcome-summary-row">
            <span className="label">Consumo estimado</span>
            <span className="val">{consumption} Wh/noche</span>
          </div>
          <div className="welcome-summary-row">
            <span className="label">Candidatos</span>
            <span className="val">{candidates.length} soluciones</span>
          </div>
        </div>
        <button
          className="btn-primary"
          onClick={() => dispatch({ type: 'SET_STEP', payload: 6 })}
        >
          Ir a Simulación →
        </button>
      </div>
    </div>
  )
}
