import { useRef, useEffect } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

/**
 * Real 3D terrain view (MapLibre GL + AWS terrain-tiles DEM), view-only — no click-to-pick.
 * The project marker is synced from lat/lon already fixed in the 2D map; to move the
 * project, switch back to a 2D layer. All sources below are free/open, no API key required.
 */
export default function Map3DTerrain({ lat, lon }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: 'https://tiles.openfreemap.org/styles/liberty',
      center: [lon ?? 2.17, lat ?? 41.4],
      zoom: lat ? 13 : 3,
      pitch: 50,
      maxZoom: 21,
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-left')

    map.on('load', () => {
      map.addSource('dem', {
        type: 'raster-dem',
        tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
        tileSize: 256, encoding: 'terrarium', maxzoom: 14,
      })
      map.setTerrain({ source: 'dem', exaggeration: 2.0 })

      map.addSource('sat', {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
      })
      map.addLayer({ id: 'sat', type: 'raster', source: 'sat' })
      // No hillshade overlay: Esri's World_Hillshade tiles render as a semi-transparent
      // grey wash across the ENTIRE image (not just relief edges), which reads as fog/haze
      // over flat or low-relief terrain. The DEM-driven 3D terrain geometry above already
      // gives the relief a visual sense of depth without needing this overlay.

      map.getCanvas().style.background = '#0d1520'
      // MapLibre (unlike Mapbox GL) has no setFog() — atmospheric haze is controlled via
      // setSky(). Zero out all blending so no sky/horizon haze renders at all.
      map.setSky({
        'fog-ground-blend': 0,
        'horizon-fog-blend': 0,
        'sky-horizon-blend': 0,
        'atmosphere-blend': 0,
      })

      if (lat && lon) {
        markerRef.current = new maplibregl.Marker({ color: '#E5534B' }).setLngLat([lon, lat]).addTo(map)
      }
    })

    return () => { map.remove(); mapRef.current = null; markerRef.current = null }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Re-center + move marker when the project location changes while this view is open
  useEffect(() => {
    if (!mapRef.current || !lat || !lon) return
    mapRef.current.easeTo({ center: [lon, lat], zoom: Math.max(mapRef.current.getZoom(), 13) })
    if (markerRef.current) {
      markerRef.current.setLngLat([lon, lat])
    } else if (mapRef.current.isStyleLoaded()) {
      markerRef.current = new maplibregl.Marker({ color: '#E5534B' }).setLngLat([lon, lat]).addTo(mapRef.current)
    }
  }, [lat, lon])

  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
}
