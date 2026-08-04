import { useRef, useEffect, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useApp } from '../../context/AppContext'
import { applyMapLayer, DEFAULT_MAP_LAYER } from '../map/mapLayers'
import LayerSwitcher from '../map/LayerSwitcher'
import MeasureButton from '../map/MeasureButton'
import { useMeasureTool } from '../map/useMeasureTool'

// Fix Leaflet default icon URLs for Vite bundling
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconUrl: new URL('leaflet/dist/images/marker-icon.png', import.meta.url).href,
  iconRetinaUrl: new URL('leaflet/dist/images/marker-icon-2x.png', import.meta.url).href,
  shadowUrl: new URL('leaflet/dist/images/marker-shadow.png', import.meta.url).href,
})

export default function CanvasViaEstimacion() {
  const { state, dispatch } = useApp()
  const { project, viaPickMode, viaPickLatLon, viaMapFlyTo } = state

  const mapRef         = useRef(null)
  const markerRef      = useRef(null)
  const pickMarkerRef  = useRef(null)
  const pickModeRef    = useRef(viaPickMode)
  const layerRefs       = useRef({ base: null, overlay: null })

  const [coordsText,  setCoordsText]  = useState(null)
  const [activeLayer, setActiveLayer] = useState(DEFAULT_MAP_LAYER)
  const measure = useMeasureTool(mapRef)

  // Keep pick-mode ref in sync
  useEffect(() => {
    pickModeRef.current = viaPickMode
    if (mapRef.current) {
      mapRef.current.getContainer().style.cursor = viaPickMode ? 'crosshair' : ''
    }
  }, [viaPickMode])

  // Show coords when a point is picked
  useEffect(() => {
    if (viaPickLatLon) {
      setCoordsText(`${viaPickLatLon.lat.toFixed(5)}, ${viaPickLatLon.lon.toFixed(5)}`)
    }
  }, [viaPickLatLon])

  // Init map
  useEffect(() => {
    const el = document.getElementById('via-map')
    if (!el || mapRef.current) return

    const lat = project.lat || 41.4
    const lon = project.lon || 2.17
    const map = L.map(el, { zoomControl: true }).setView([lat, lon], 16)
    mapRef.current = map

    applyMapLayer(map, DEFAULT_MAP_LAYER, layerRefs.current)

    if (project.lat && project.lon) {
      markerRef.current = L.marker([project.lat, project.lon])
        .addTo(map)
        .bindPopup(`<b>${project.name || 'Proyecto'}</b><br>${project.city || ''}`)
    }

    map.on('click', (e) => {
      if (measure.handleClick(e.latlng)) return
      if (!pickModeRef.current) return
      const { lat: clat, lng: clng } = e.latlng
      if (pickMarkerRef.current) pickMarkerRef.current.remove()
      pickMarkerRef.current = L.circleMarker([clat, clng], {
        radius: 9, color: '#E55', weight: 2.5,
        fillColor: '#E55', fillOpacity: 0.75,
      }).addTo(map).bindPopup('Consultando vía…').openPopup()
      dispatch({ type: 'SET_VIA_PICK_LATLON', payload: { lat: clat, lon: clng } })
    })

    return () => { map.remove(); mapRef.current = null }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Fly to search result
  useEffect(() => {
    if (!mapRef.current || !viaMapFlyTo) return
    mapRef.current.flyTo([viaMapFlyTo.lat, viaMapFlyTo.lon], viaMapFlyTo.zoom ?? 17, {
      animate: true, duration: 1.2,
    })
  }, [viaMapFlyTo])

  // Re-center when project location changes
  useEffect(() => {
    if (!mapRef.current || !project.lat || !project.lon) return
    mapRef.current.setView([project.lat, project.lon], mapRef.current.getZoom())
    if (markerRef.current) {
      markerRef.current.setLatLng([project.lat, project.lon])
    } else {
      markerRef.current = L.marker([project.lat, project.lon])
        .addTo(mapRef.current)
        .bindPopup(`<b>${project.name || 'Proyecto'}</b>`)
    }
  }, [project.lat, project.lon])

  // Switch tile layer
  const switchLayer = (layerId) => {
    if (!mapRef.current || layerId === activeLayer) return
    applyMapLayer(mapRef.current, layerId, layerRefs.current, [markerRef.current, pickMarkerRef.current])
    setActiveLayer(layerId)
  }

  return (
    <div className="canvas-panel canvas-step-view" style={{ display: 'flex', flexDirection: 'column' }}>

      {/* ── Header bar ──────────────────────────────────────────────────────── */}
      <div className="canvas-header" style={{ paddingBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <span className="canvas-title">Selección de vía</span>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {/* Pick button */}
            <button
              onClick={() => dispatch({ type: 'SET_VIA_PICK_MODE', payload: !viaPickMode })}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '5px 13px', borderRadius: 6, border: 'none',
                cursor: 'pointer', fontWeight: 600, fontSize: 12,
                transition: 'background 0.15s, color 0.15s',
                background: viaPickMode ? 'var(--salvi-black, #1E1E1E)' : 'var(--bg-hover, #F0F0F0)',
                color: viaPickMode ? '#fff' : 'var(--salvi-black, #1E1E1E)',
                boxShadow: viaPickMode ? '0 0 0 2px #E5534B' : 'none',
              }}
              title={viaPickMode ? 'Cancelar selección' : 'Haz clic sobre una calle para analizarla'}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
                <line x1="7" y1="1" x2="7" y2="13" stroke="currentColor" strokeWidth="1.5"/>
                <line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" strokeWidth="1.5"/>
              </svg>
              {viaPickMode ? 'Cancelar' : 'Seleccionar vía'}
            </button>

            {viaPickMode && (
              <span style={{
                fontSize: 11, color: '#E5534B', fontWeight: 600,
                padding: '4px 8px', background: 'rgba(229,83,75,0.08)',
                borderRadius: 5, pointerEvents: 'none',
              }}>
                ✦ Haz clic sobre la carretera
              </span>
            )}
          </div>
        </div>

        <span className="canvas-subtitle" style={{ display: 'block', marginTop: 4 }}>
          {project.lat && project.lon
            ? `${project.city || ''}${project.city ? ' · ' : ''}${project.lat.toFixed(4)}, ${(project.lon || 0).toFixed(4)}`
            : 'Sin coordenadas — define la ubicación en el paso 1'}
        </span>
      </div>

      {/* ── Map container ───────────────────────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>

        {/* Pick mode hint */}
        {viaPickMode && (
          <div style={{
            position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
            zIndex: 1000, background: '#1E1E1E', color: '#fff',
            padding: '7px 16px', borderRadius: 8, fontSize: 12, fontWeight: 600,
            boxShadow: '0 2px 12px rgba(0,0,0,0.4)', pointerEvents: 'none',
            whiteSpace: 'nowrap',
          }}>
            🎯 Haz clic sobre la vía que quieres analizar
          </div>
        )}

        <LayerSwitcher activeLayer={activeLayer} onChange={switchLayer} />
        <MeasureButton active={measure.active} hasPoints={measure.hasPoints} onToggle={measure.toggle} onClear={measure.clear} />

        <div id="via-map" style={{ width: '100%', height: '100%' }} />
      </div>

      {/* ── Footer bar ──────────────────────────────────────────────────────── */}
      <div className="canvas-footer-bar">
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--salvi-grey)' }}>
          {coordsText ?? '—'}
        </span>
        <span style={{ fontSize: 11, color: 'var(--salvi-muted)' }}>
          {viaPickMode
            ? 'Modo selección activo — cursor en el mapa'
            : viaPickLatLon
              ? 'Vía seleccionada · ajusta parámetros en el panel izquierdo'
              : 'Activa "Seleccionar vía" y haz clic sobre la carretera'}
        </span>
      </div>

    </div>
  )
}
