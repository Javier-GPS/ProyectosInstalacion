import { useState } from 'react'
import { MAP_LAYERS } from './mapLayers'

/** Icon button + dropdown to switch the map base layer. Positioned absolutely by the caller.
 * `layers` defaults to the shared raster catalogue; pass a longer list (e.g. with
 * TERRAIN_3D_LAYER appended) to offer extra, non-raster options handled by the caller. */
export default function LayerSwitcher({ activeLayer, onChange, style, layers = MAP_LAYERS }) {
  const [open, setOpen] = useState(false)
  const current = layers.find(l => l.id === activeLayer) || layers[0]

  return (
    <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 1000, ...style }}>
      <button
        onClick={() => setOpen(o => !o)}
        title="Cambiar capa del mapa"
        style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', gap: 1,
          width: 44, height: 44, borderRadius: 8,
          border: '2px solid rgba(0,0,0,0.18)',
          background: '#fff', cursor: 'pointer',
          boxShadow: '0 2px 8px rgba(0,0,0,0.18)',
          fontSize: 18, lineHeight: 1,
        }}
      >
        <span>{current.icon}</span>
        <span style={{ fontSize: 8, color: '#666', fontWeight: 600 }}>
          {current.label.slice(0, 4)}
        </span>
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 50, right: 0,
          background: '#fff', borderRadius: 10,
          boxShadow: '0 4px 20px rgba(0,0,0,0.22)',
          border: '1px solid rgba(0,0,0,0.10)',
          overflow: 'hidden', minWidth: 150,
        }}>
          {layers.map(layer => (
            <button
              key={layer.id}
              onClick={() => { onChange(layer.id); setOpen(false) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                width: '100%', padding: '9px 14px',
                border: 'none', cursor: 'pointer', textAlign: 'left',
                fontSize: 13, fontWeight: layer.id === activeLayer ? 700 : 400,
                background: layer.id === activeLayer ? 'var(--salvi-black, #1E1E1E)' : 'transparent',
                color: layer.id === activeLayer ? '#fff' : '#333',
                borderBottom: '1px solid rgba(0,0,0,0.06)',
              }}
              onMouseEnter={e => { if (layer.id !== activeLayer) e.currentTarget.style.background = '#F5F5F5' }}
              onMouseLeave={e => { if (layer.id !== activeLayer) e.currentTarget.style.background = 'transparent' }}
            >
              <span style={{ fontSize: 18, lineHeight: 1 }}>{layer.icon}</span>
              <span>{layer.label}</span>
              {layer.id === activeLayer && <span style={{ marginLeft: 'auto', fontSize: 11 }}>✓</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
