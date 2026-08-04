import { Ruler, X } from 'lucide-react'

/** Icon button to toggle the distance-measurement tool. Positioned absolutely by the caller —
 * stacked directly below the layer-switcher button (top:10, height:44) by default. */
export default function MeasureButton({ active, hasPoints, onToggle, onClear, style }) {
  return (
    <div style={{ position: 'absolute', top: 62, right: 10, zIndex: 1000, display: 'flex', flexDirection: 'column', gap: 6, ...style }}>
      <button
        onClick={onToggle}
        title={active ? 'Desactivar medición de distancia' : 'Medir distancia'}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 44, height: 44, borderRadius: 8,
          border: active ? '2px solid #E5534B' : '2px solid rgba(0,0,0,0.18)',
          background: active ? '#E5534B' : '#fff',
          color: active ? '#fff' : '#1E1E1E',
          cursor: 'pointer',
          boxShadow: '0 2px 8px rgba(0,0,0,0.18)',
        }}
      >
        <Ruler size={20} strokeWidth={1.75} />
      </button>

      {active && hasPoints && (
        <button
          onClick={onClear}
          title="Borrar medición"
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 44, height: 44, borderRadius: 8,
            border: '2px solid rgba(0,0,0,0.18)',
            background: '#fff', color: '#1E1E1E', cursor: 'pointer',
            boxShadow: '0 2px 8px rgba(0,0,0,0.18)',
          }}
        >
          <X size={20} strokeWidth={1.75} />
        </button>
      )}
    </div>
  )
}
