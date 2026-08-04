import L from 'leaflet'

// Shared base-layer catalogue for all Leaflet maps in the app.
// 'satellite_terrain' is a 2D approximation of satellite+3D terrain (Leaflet has no true
// 3D/tilt rendering): Esri World Imagery as base + Esri World Hillshade relief on top.
export const MAP_LAYERS = [
  {
    id: 'streets',
    label: 'Callejero',
    icon: '🗺',
    base: {
      url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>',
      maxZoom: 19,
    },
  },
  {
    id: 'satellite',
    label: 'Satélite',
    icon: '🛰',
    base: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      attribution: '© <a href="https://www.esri.com">Esri</a> World Imagery',
      maxZoom: 19,
    },
  },
  {
    id: 'terrain',
    label: 'Terreno',
    icon: '⛰',
    base: {
      url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
      attribution: '© <a href="https://opentopomap.org">OpenTopoMap</a>',
      maxZoom: 17,
    },
  },
]

export const DEFAULT_MAP_LAYER = 'streets'

// Not a Leaflet raster layer — selecting this swaps to a separate MapLibre GL 3D view
// (see Map3DTerrain.jsx). Kept out of MAP_LAYERS so applyMapLayer() never tries to
// treat it as a tile layer; callers that want it append it explicitly.
export const TERRAIN_3D_LAYER = { id: 'terrain_3d', label: 'Terreno 3D', icon: '🏔' }

/**
 * Creates (or replaces) the base+overlay tile layers for `layerId` on `map`.
 * `refs` is a mutable { base, overlay } object used to track/remove the previous layers.
 * Keeps any marker layers on top by calling bringToFront() on entries in `keepOnTop`.
 */
export function applyMapLayer(map, layerId, refs, keepOnTop = []) {
  const def = MAP_LAYERS.find(l => l.id === layerId) || MAP_LAYERS[0]

  if (refs.base) map.removeLayer(refs.base)
  if (refs.overlay) { map.removeLayer(refs.overlay); refs.overlay = null }

  refs.base = L.tileLayer(def.base.url, {
    attribution: def.base.attribution, maxZoom: def.base.maxZoom,
  }).addTo(map)

  if (def.overlay) {
    refs.overlay = L.tileLayer(def.overlay.url, {
      maxZoom: def.overlay.maxZoom, opacity: def.overlay.opacity ?? 0.5,
    }).addTo(map)
  }

  keepOnTop.forEach(layer => layer?.bringToFront?.())
  return def
}
