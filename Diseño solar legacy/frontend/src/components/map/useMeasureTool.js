import { useRef, useState, useCallback } from 'react'
import L from 'leaflet'

function haversineMeters(a, b) {
  const R = 6371000
  const toRad = d => (d * Math.PI) / 180
  const dLat = toRad(b.lat - a.lat)
  const dLon = toRad(b.lng - a.lng)
  const lat1 = toRad(a.lat), lat2 = toRad(b.lat)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

function formatDistance(m) {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(2)} km`
}

/**
 * Shared distance-measurement tool for Leaflet maps. Click to add points, shows a running
 * polyline + total distance label. `handleClick(latlng)` returns true if it consumed the
 * click (measure mode active) — callers should skip their own click logic when it does.
 */
export function useMeasureTool(mapRef) {
  const activeRef   = useRef(false)
  const pointsRef    = useRef([])
  const polylineRef  = useRef(null)
  const markersRef   = useRef([])
  const labelRef     = useRef(null)
  const [active, setActive]   = useState(false)
  const [hasPoints, setHasPoints] = useState(false)

  const clearLayers = useCallback(() => {
    const map = mapRef.current
    if (map) {
      if (polylineRef.current) map.removeLayer(polylineRef.current)
      if (labelRef.current) map.removeLayer(labelRef.current)
      markersRef.current.forEach(m => map.removeLayer(m))
    }
    polylineRef.current = null
    labelRef.current = null
    markersRef.current = []
    pointsRef.current = []
    setHasPoints(false)
  }, [mapRef])

  const redraw = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    if (polylineRef.current) { map.removeLayer(polylineRef.current); polylineRef.current = null }
    if (labelRef.current) { map.removeLayer(labelRef.current); labelRef.current = null }

    const pts = pointsRef.current
    if (pts.length >= 2) {
      polylineRef.current = L.polyline(pts, { color: '#E5534B', weight: 3, dashArray: '6,6' }).addTo(map)
    }
    let total = 0
    for (let i = 1; i < pts.length; i++) total += haversineMeters(pts[i - 1], pts[i])
    if (pts.length) {
      labelRef.current = L.marker(pts[pts.length - 1], {
        icon: L.divIcon({
          className: 'measure-label',
          html: `<div style="background:#1E1E1E;color:#fff;padding:3px 8px;border-radius:5px;font-size:11px;font-weight:600;white-space:nowrap;transform:translate(12px,-10px);box-shadow:0 2px 8px rgba(0,0,0,0.3);">📏 ${formatDistance(total)}</div>`,
          iconSize: null,
        }),
        interactive: false,
      }).addTo(map)
    }
  }, [mapRef])

  const handleClick = useCallback((latlng) => {
    if (!activeRef.current) return false
    const map = mapRef.current
    pointsRef.current.push(latlng)
    const marker = L.circleMarker(latlng, {
      radius: 4, color: '#E5534B', weight: 2, fillColor: '#fff', fillOpacity: 1,
    }).addTo(map)
    markersRef.current.push(marker)
    setHasPoints(true)
    redraw()
    return true
  }, [mapRef, redraw])

  const toggle = useCallback(() => {
    setActive(a => {
      const next = !a
      activeRef.current = next
      if (!next) clearLayers()
      if (mapRef.current) mapRef.current.getContainer().style.cursor = next ? 'crosshair' : ''
      return next
    })
  }, [mapRef, clearLayers])

  const clear = useCallback(() => {
    clearLayers()
  }, [clearLayers])

  return { active, hasPoints, toggle, clear, handleClick }
}
