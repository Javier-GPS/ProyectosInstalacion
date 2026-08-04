import { useApp } from '../../context/AppContext'

export default function Step8Detalle() {
  const { state, dispatch } = useApp()
  const { simulation, selectedProductId } = state

  const candidate = simulation?.candidates?.find(c => c.product_id === selectedProductId)

  return (
    <div className="step-form active">
      <h3 className="step-header">Detalle Solución</h3>
      {candidate && (
        <div className="mb-8">
          <strong>{candidate.product_name || candidate.product_id}</strong>
        </div>
      )}
      <div className="result-note">Consulta el detalle en el área central →</div>
      {selectedProductId && (
        <button
          className="btn-secondary btn-sm"
          style={{ marginTop: '8px' }}
          onClick={() => dispatch({ type: 'SET_STEP', payload: 7 })}
        >
          ← Volver a comparativa
        </button>
      )}
    </div>
  )
}
