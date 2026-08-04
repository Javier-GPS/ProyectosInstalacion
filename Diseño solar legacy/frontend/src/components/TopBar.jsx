import { useApp } from '../context/AppContext'
import { showToast } from './Toast'
import { COUNTRY_DATA } from '../utils'

function saveProject(state) {
  const data = {
    version: '1.0.0',
    saved: new Date().toISOString(),
    project: state.project,
    photometry: state.photometry,
    nightProfile: state.nightProfile,
    env: state.env,
    candidates: state.candidates,
  }
  const key = 'salvi_solar_' + (state.project.name || 'default').replace(/\s+/g, '_')
  try {
    localStorage.setItem(key, JSON.stringify(data))
    showToast('Proyecto guardado en navegador', 'success')
  } catch (e) {
    showToast('Error al guardar: ' + e.message, 'error')
  }
}

export default function TopBar() {
  const { state, dispatch } = useApp()

  const handleExport = () => {
    dispatch({ type: 'SET_STEP', payload: 9 })
  }

  return (
    <header id="top-bar">
      <div className="top-bar-brand">
        <svg width="80" height="38" viewBox="0 0 80 38" xmlns="http://www.w3.org/2000/svg"
          style={{ overflow: 'visible', flexShrink: 0 }}>
          <text x="0" y="27" fontFamily="Exposure, Georgia, serif" fontSize="30" fontWeight="300"
            fill="#1E1E1E" letterSpacing="3">Salvi</text>
          <text x="1" y="37" fontFamily="Helvetica Neue, Helvetica, Arial, sans-serif" fontSize="7"
            fontWeight="400" fill="#A09A91" letterSpacing="2">LIGHT INSPIRED BY YOU</text>
        </svg>
        <span className="module-badge">☀ Solar</span>
      </div>

      <div className="top-bar-project">
        <span style={{ color: 'var(--salvi-grey)' }}>
          {state.project.name || 'Sin proyecto'}
        </span>
      </div>

      <div className="top-bar-actions">
        <div className={`api-status ${state.apiStatus === 'ok' ? 'ok' : state.apiStatus === 'err' ? 'err' : ''}`}>
          <span className="api-dot"></span>
          <span>
            {state.apiStatus === 'ok'
              ? `API v${state.apiVersion}`
              : state.apiStatus === 'err'
              ? 'Sin conexión'
              : 'Conectando…'}
          </span>
        </div>
        <button className="btn-header-primary" onClick={() => saveProject(state)}>
          Guardar
        </button>
        <button className="btn-header" onClick={handleExport}>
          Exportar
        </button>
        <span className="version-tag">v1.0.0</span>
      </div>
    </header>
  )
}
