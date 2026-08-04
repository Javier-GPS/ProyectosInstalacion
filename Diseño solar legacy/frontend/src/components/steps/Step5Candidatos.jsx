import { useApp } from '../../context/AppContext'

export default function Step5Candidatos() {
  const { state, dispatch } = useApp()
  const { products, candidates } = state

  const toggleCandidate = (id) => {
    dispatch({ type: 'TOGGLE_CANDIDATE', payload: id })
  }

  const selectAll = () => {
    dispatch({ type: 'SET_CANDIDATES', payload: products.map(p => p.id) })
  }

  const selectSILOnly = () => {
    dispatch({ type: 'SET_CANDIDATES', payload: products.filter(p => (p.id || '').toLowerCase().startsWith('sil')).map(p => p.id) })
  }

  const clearAll = () => {
    dispatch({ type: 'SET_CANDIDATES', payload: [] })
  }

  return (
    <div className="step-form active">
      <h3 className="step-header">Soluciones Candidatas</h3>

      <div className="candidates-actions">
        <button className="btn-secondary btn-sm" onClick={selectAll}>Todas</button>
        <button className="btn-secondary btn-sm" onClick={selectSILOnly}>Solo SIL</button>
        <button className="btn-secondary btn-sm" onClick={clearAll}>Ninguna</button>
      </div>

      {products.length === 0 ? (
        <div className="candidates-loading">Cargando productos...</div>
      ) : (
        <div className="candidates-grid">
          {products.map(p => {
            const selected = candidates.includes(p.id)
            return (
              <div
                key={p.id}
                className={`candidate-card ${selected ? 'selected' : ''}`}
                onClick={() => toggleCandidate(p.id)}
              >
                <span className="card-check">{selected ? '☑' : '☐'}</span>
                <div className="card-name">{p.name || p.id}</div>
                <div className="card-spec">
                  {p.pv_peak_power_wp ? p.pv_peak_power_wp + ' Wp' : ''}
                  {p.battery_nominal_wh ? ' · ' + p.battery_nominal_wh + ' Wh' : ''}
                  {p.weight_kg ? ' · ' + p.weight_kg + ' kg' : ''}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
