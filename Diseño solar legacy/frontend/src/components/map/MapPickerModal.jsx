import { useRef, useEffect, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useApp } from '../../context/AppContext'
import { showToast } from '../Toast'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconUrl: new URL('leaflet/dist/images/marker-icon.png', import.meta.url).href,
  iconRetinaUrl: new URL('leaflet/dist/images/marker-icon-2x.png', import.meta.url).href,
  shadowUrl: new URL('leaflet/dist/images/marker-shadow.png', import.meta.url).href,
})

export default function MapPickerModal() {
  const { state, dispatch } = useApp()
  const { project } = state

  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)

  const [pendingLat, setPendingLat] = useState(null)
  const [pendingLon, setPendingLon] = useState(null)
  const [pendingCity, setPendingCity] = useState('')
  const [pendingCountry, setPendingCountry] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [coordsDisplay, setCoordsDisplay] = useState('Haz clic en el mapa para colocar el pin')

  const close = () => {
    dispatch({ type: 'SET_MAP_PICKER_OPEN', payload: false })
  }

  const setPin = (lat, lon) => {
    setPendingLat(lat)
    setPendingLon(lon)
    setCoordsDisplay(`Pin: ${lat}, ${lon}`)

    if (markerRef.current) {
      markerRef.current.setLatLng([lat, lon])
    } else if (mapRef.current) {
      markerRef.current = L.marker([lat, lon], { draggable: true }).addTo(mapRef.current)
      markerRef.current.on('dragend', (e) => {
        const pos = e.target.getLatLng()
        const la = Math.round(pos.lat * 10000) / 10000
        const lo = Math.round(pos.lng * 10000) / 10000
        setPin(la, lo)
      })
    }

    // Reverse geocode
    fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`)
      .then(r => r.json())
      .then(data => {
        const city = data.address?.city || data.address?.town || data.address?.village || data.address?.county || ''
        const country = (data.address?.country_code || '').toUpperCase()
        if (city) {
          setCoordsDisplay(`${city} · ${lat}, ${lon}`)
          setPendingCity(city)
        }
        if (country) setPendingCountry(country)
      })
      .catch(() => {})
  }

  const confirm = () => {
    if (pendingLat === null) return
    dispatch({ type: 'UPDATE_PROJECT', payload: {
      lat: pendingLat,
      lon: pendingLon,
      ...(pendingCity ? { city: pendingCity } : {}),
      ...(pendingCountry ? { country: pendingCountry } : {}),
    }})
    showToast(`Ubicación confirmada: ${pendingLat}, ${pendingLon}`, 'success')
    close()
  }

  const searchCity = async () => {
    if (!searchQuery.trim()) return
    try {
      const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(searchQuery)}&format=json&limit=1`
      const r = await fetch(url)
      const results = await r.json()
      if (!results.length) { showToast('No se encontró la ubicación', 'error'); return }
      const res = results[0]
      const lat = Math.round(parseFloat(res.lat) * 10000) / 10000
      const lon = Math.round(parseFloat(res.lon) * 10000) / 10000
      mapRef.current?.setView([lat, lon], 13)
      setPin(lat, lon)
    } catch (e) {
      showToast('Error buscando ubicación: ' + e.message, 'error')
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      if (mapRef.current) { mapRef.current.invalidateSize(); return }

      const defaultLat = project.lat || 41.3851
      const defaultLon = project.lon || 2.1734
      const map = L.map(mapContainerRef.current).setView([defaultLat, defaultLon], project.lat ? 12 : 5)

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors', maxZoom: 19,
      }).addTo(map)

      map.on('click', (e) => {
        const lat = Math.round(e.latlng.lat * 10000) / 10000
        const lon = Math.round(e.latlng.lng * 10000) / 10000
        setPin(lat, lon)
      })

      if (project.lat && project.lon) setPin(project.lat, project.lon)

      mapRef.current = map
    }, 100)

    return () => {
      clearTimeout(timer)
      mapRef.current?.remove()
      mapRef.current = null
      markerRef.current = null
    }
  }, [])

  return (
    <div id="map-modal" className="open">
      <div className="map-modal-box">
        <div className="map-modal-header">
          <span className="map-modal-title">🗺 Seleccionar ubicación del proyecto</span>
          <button className="map-modal-close" onClick={close}>✕</button>
        </div>

        <div className="map-search-bar">
          <input
            type="text"
            placeholder="Buscar ciudad o dirección... (Ej: Barcelona, España)"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && searchCity()}
          />
          <button className="btn-primary btn-sm" onClick={searchCity}>Buscar</button>
        </div>

        <div ref={mapContainerRef} id="map-container" style={{ height: '380px', width: '100%' }}></div>

        <div className="map-modal-footer">
          <span className="map-coords-display">{coordsDisplay}</span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-secondary btn-sm" onClick={close}>Cancelar</button>
            <button
              className="btn-primary btn-sm"
              onClick={confirm}
              disabled={pendingLat === null}
            >
              Confirmar ubicación
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
