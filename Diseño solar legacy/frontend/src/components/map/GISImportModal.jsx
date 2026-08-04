import { useEffect, useState } from 'react'
import { useApp } from '../../context/AppContext'
import { showToast } from '../Toast'

export default function GISImportModal() {
  const { state, dispatch } = useApp()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const close = () => {
    dispatch({ type: 'SET_GIS_IMPORT_OPEN', payload: false })
  }

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch('http://localhost:8733/api/projects')
      .then(r => r.json())
      .then(data => {
        setProjects(data.projects || data || [])
        setLoading(false)
      })
      .catch(() => {
        setError('SALVI GIS no está disponible')
        setLoading(false)
      })
  }, [])

  const importProject = (p) => {
    const lat = parseFloat(p.latitude || p.lat)
    const lon = parseFloat(p.longitude || p.lon)
    if (isNaN(lat) || isNaN(lon)) return

    dispatch({ type: 'UPDATE_PROJECT', payload: {
      lat,
      lon,
      ...(p.name || p.project_name ? { name: state.project.name || p.name || p.project_name } : {}),
      ...(p.city ? { city: p.city } : {}),
    }})
    showToast(`Importado desde GIS: ${lat}, ${lon}`, 'success')
    close()
  }

  return (
    <div id="gis-modal" className="open">
      <div className="gis-modal-box">
        <div className="map-modal-header">
          <span className="map-modal-title">↗ Importar proyecto desde SALVI GIS</span>
          <button className="map-modal-close" onClick={close}>✕</button>
        </div>

        <div className="gis-project-list">
          {loading ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--salvi-muted)' }}>
              Conectando con SALVI GIS (puerto 8733)...
            </div>
          ) : error ? (
            <div style={{ padding: '20px', textAlign: 'center' }}>
              <div style={{ color: 'var(--state-danger)', fontWeight: '600', marginBottom: '8px' }}>
                {error}
              </div>
              <div style={{ color: 'var(--salvi-muted)', fontSize: '12px' }}>
                Abre SALVI GIS primero y vuelve a intentarlo.
              </div>
            </div>
          ) : projects.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--salvi-muted)' }}>
              No hay proyectos en SALVI GIS.
            </div>
          ) : (
            projects.map((p, i) => {
              const lat = p.latitude || p.lat
              const lon = p.longitude || p.lon
              const hasCoords = lat != null && lon != null && lat !== '–' && lon !== '–'
              return (
                <div
                  key={i}
                  className="gis-project-item"
                  style={!hasCoords ? { opacity: 0.5, cursor: 'default' } : {}}
                  onClick={hasCoords ? () => importProject(p) : undefined}
                >
                  <div>
                    <div className="gis-project-name">
                      {p.name || p.project_name || 'Proyecto sin nombre'}
                    </div>
                    <div className="gis-project-coords">
                      {hasCoords ? `${lat}, ${lon}` : 'Sin coordenadas'}
                    </div>
                  </div>
                  {hasCoords && (
                    <span style={{ fontSize: '11px', color: 'var(--state-success)' }}>Importar →</span>
                  )}
                </div>
              )
            })
          )}
        </div>

        <div className="map-modal-footer">
          <span style={{ fontSize: '12px', color: 'var(--salvi-muted)' }}>SALVI GIS · puerto 8733</span>
          <button className="btn-secondary btn-sm" onClick={close}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}
