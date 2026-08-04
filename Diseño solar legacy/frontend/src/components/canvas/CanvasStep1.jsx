import { useRef, useEffect, useState, useCallback } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Chart } from 'chart.js/auto'
import { useApp } from '../../context/AppContext'
import { MONTHS } from '../../utils'
import { MAP_LAYERS, TERRAIN_3D_LAYER, applyMapLayer, DEFAULT_MAP_LAYER } from '../map/mapLayers'
import LayerSwitcher from '../map/LayerSwitcher'
import Map3DTerrain from '../map/Map3DTerrain'
import MeasureButton from '../map/MeasureButton'
import { useMeasureTool } from '../map/useMeasureTool'

const LAYERS_WITH_3D = [...MAP_LAYERS, TERRAIN_3D_LAYER]

// Fix Leaflet default icon URLs for Vite bundling
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconUrl: new URL('leaflet/dist/images/marker-icon.png', import.meta.url).href,
  iconRetinaUrl: new URL('leaflet/dist/images/marker-icon-2x.png', import.meta.url).href,
  shadowUrl: new URL('leaflet/dist/images/marker-shadow.png', import.meta.url).href,
})

const MONTHLY_CFG = {
  irradiance: { title: 'Irradiancia mensual (kWh/m²/día) · PVGIS/JRC — año meteorológico típico', unit: 'kWh/m²/día', color: '#F5A623', type: 'bar' },
  precip:     { title: 'Precipitación media mensual (mm/día) · Open-Meteo 2020–2023',              unit: 'mm/día',     color: '#4A90D9', type: 'bar' },
  temp:       { title: 'Temperatura media mensual (°C) · Open-Meteo 2020–2023',                    unit: '°C',         color: '#E8742A', type: 'line' },
  soiling:    { title: 'Índice ambiental de suciedad (% base) · Open-Meteo 2020–2023',             unit: '%',          color: '#8B4513', type: 'bar' },
}

const GHI_COLOR_STOPS = [
  { v: 800,  r: 0,   g: 76,  b: 179 },
  { v: 1200, r: 0,   g: 153, b: 204 },
  { v: 1600, r: 100, g: 200, b: 100 },
  { v: 2000, r: 220, g: 200, b: 0   },
  { v: 2400, r: 240, g: 130, b: 0   },
  { v: 2800, r: 200, g: 0,   b: 0   },
]

function ghiToRGB(ghi) {
  const stops = GHI_COLOR_STOPS
  if (ghi <= stops[0].v) return [stops[0].r, stops[0].g, stops[0].b]
  if (ghi >= stops[stops.length - 1].v) { const s = stops[stops.length - 1]; return [s.r, s.g, s.b] }
  for (let k = 1; k < stops.length; k++) {
    if (ghi <= stops[k].v) {
      const t = (ghi - stops[k-1].v) / (stops[k].v - stops[k-1].v)
      return [
        Math.round(stops[k-1].r + (stops[k].r - stops[k-1].r) * t),
        Math.round(stops[k-1].g + (stops[k].g - stops[k-1].g) * t),
        Math.round(stops[k-1].b + (stops[k].b - stops[k-1].b) * t),
      ]
    }
  }
  return [200, 0, 0]
}

const PRECIP_STOPS  = [[0,255,252,255],[0.15,190,225,250],[0.35,90,170,230],[0.6,30,110,200],[0.8,10,55,160],[1.0,5,20,90]]
const TEMP_STOPS    = [[0,0,40,160],[0.2,30,140,210],[0.4,100,210,120],[0.6,230,225,40],[0.8,240,110,10],[1.0,200,0,0]]
const SOILING_STOPS = [[0,40,180,60],[0.2,150,200,50],[0.4,230,210,30],[0.6,240,130,15],[0.8,200,55,10],[1.0,130,25,10]]
const UNIVERSAL_SCALES = {
  irradiance: { min: 0, max: 8.5 },
  precip:     { min: 0, max: 12 },
  temp:       { min: -10, max: 42 },
  soiling:    { min: 0, max: 20 },
}

function normToRGBStops(t, stops) {
  if (t <= 0) return [stops[0][1], stops[0][2], stops[0][3]]
  if (t >= 1) { const s = stops[stops.length-1]; return [s[1], s[2], s[3]] }
  for (let k = 1; k < stops.length; k++) {
    if (t <= stops[k][0]) {
      const lo = stops[k-1], hi = stops[k]
      const f = (t - lo[0]) / (hi[0] - lo[0])
      return [
        Math.round(lo[1] + (hi[1]-lo[1])*f),
        Math.round(lo[2] + (hi[2]-lo[2])*f),
        Math.round(lo[3] + (hi[3]-lo[3])*f),
      ]
    }
  }
  const s = stops[stops.length-1]; return [s[1], s[2], s[3]]
}

function _baseSoilingMonthly(precip_mm_day, wind_kmh) {
  const monthly_mm = (precip_mm_day || 0) * 30
  const wind = wind_kmh || 0
  let base
  if      (monthly_mm >= 100) base = 0.5
  else if (monthly_mm >=  60) base = 1.0
  else if (monthly_mm >=  30) base = 2.2
  else if (monthly_mm >=  10) base = 4.5
  else if (monthly_mm >=   3) base = 9.0
  else if (monthly_mm >= 0.5) base = 16.0
  else                        base = 22.0
  const wf = wind > 50 ? 1.30 : wind > 20 ? 1.15 : 1.0
  return base * wf
}

function computeSoilingPct(precip_mm_day, wind_kmh) {
  return Math.min(30, _baseSoilingMonthly(precip_mm_day, wind_kmh))
}

export default function CanvasStep1() {
  const { state, dispatch } = useApp()
  const { project } = state

  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const gridLayerRef = useRef(null)
  const gridDataRef = useRef(null)
  const gridDebounceRef = useRef(null)
  const climateDebounceRef = useRef(null)
  const monthlyChartRef = useRef(null)
  const chartCanvasRef = useRef(null)
  const layerRefs = useRef({ base: null, overlay: null })

  const [activeLayer, setActiveLayer] = useState(DEFAULT_MAP_LAYER)
  const measure = useMeasureTool(mapRef)
  const [activeTab, setActiveTab] = useState('irradiance')
  const [monthlyData, setMonthlyData] = useState({ irradiance: null, precip: null, temp: null, wind: null, soiling: null })
  const [heatmapMonth, setHeatmapMonth] = useState(null)
  const [loading, setLoading] = useState(false)
  const [monthlyTitle, setMonthlyTitle] = useState(MONTHLY_CFG.irradiance.title)
  const [showChart, setShowChart] = useState(false)
  const [emptyMsg, setEmptyMsg] = useState('Haz clic en el mapa para ver el perfil climático mensual')
  const [coordsText, setCoordsText] = useState('–')
  const [pvgisDb, setPvgisDb] = useState('')
  const [annualGHI, setAnnualGHI] = useState('')
  const [showHint, setShowHint] = useState(true)
  const [opacityVal, setOpacityVal] = useState(70)

  const fetchGHIGrid = useCallback(async () => {
    if (!mapRef.current) return
    setLoading(true)
    try {
      const n = 5
      const b = mapRef.current.getBounds()
      const c = mapRef.current.getCenter()
      const dlat = (b.getNorth() - b.getSouth()) / (n - 1)
      const dlon = (b.getEast()  - b.getWest())  / (n - 1)
      const url = `/api/climate/grid?lat=${c.lat.toFixed(4)}&lon=${c.lng.toFixed(4)}&n=${n}&dlat=${dlat.toFixed(4)}&dlon=${dlon.toFixed(4)}`
      const r = await fetch(url)
      if (!r.ok) throw new Error('HTTP ' + r.status)
      const d = await r.json()
      if (d.grid) renderGHICanvas(d, activeTab, heatmapMonth, opacityVal)
    } catch (e) {
      console.warn('[grid] error:', e.message)
    } finally {
      setLoading(false)
    }
  }, [activeTab, heatmapMonth, opacityVal])

  const renderGHICanvas = (data, tab, mo, opacity) => {
    if (!mapRef.current) return
    const n = data.n
    const dlat = data.dlat
    const dlon = data.dlon
    const center = data.center
    const pts = data.grid
    const half = (n - 1) / 2

    const sc = UNIVERSAL_SCALES[tab] || { min: 0, max: 10 }
    const scaleMin = sc.min
    const scaleMax = sc.max

    const matrix = []
    for (let i = 0; i < n; i++) {
      matrix[i] = []
      for (let j = 0; j < n; j++) {
        const elat = center.lat + (i - half) * dlat
        const elon = center.lon + (j - half) * dlon
        const pt = pts.find(p => Math.abs(p.lat - elat) < 0.5 && Math.abs(p.lon - elon) < 0.5)
        let val = null
        if (pt) {
          if (tab === 'irradiance') {
            val = (mo !== null && pt.monthly?.[mo] != null) ? pt.monthly[mo] : (pt.annual ? pt.annual / 365.0 : null)
          } else if (tab === 'precip') {
            const arr = pt.precip
            if (arr) val = mo !== null ? arr[mo] : arr.reduce((s, v) => s + v, 0) / 12
          } else if (tab === 'temp') {
            const arr = pt.temp
            if (arr) val = mo !== null ? arr[mo] : arr.reduce((s, v) => s + v, 0) / 12
          } else if (tab === 'soiling') {
            const pa = pt.precip, wa = pt.wind
            if (pa && wa) {
              if (mo !== null) {
                val = computeSoilingPct(pa[mo], wa[mo])
              } else {
                val = pa.map((p, i) => computeSoilingPct(p, wa[i])).reduce((s, v) => s + v, 0) / 12
              }
            }
          }
        }
        matrix[i][j] = val
      }
    }

    const allValid = []
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) if (matrix[i][j] != null) allValid.push(matrix[i][j])
    allValid.sort((a, b) => a - b)
    if (!allValid.length) return
    const median = allValid[Math.floor(allValid.length / 2)]
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) if (matrix[i][j] == null) matrix[i][j] = median

    const colorStops = tab === 'precip' ? PRECIP_STOPS : tab === 'temp' ? TEMP_STOPS : tab === 'soiling' ? SOILING_STOPS : null
    function normToRGB(t) {
      if (colorStops) return normToRGBStops(t, colorStops)
      const stops = [[0,0,76,179],[0.2,0,153,204],[0.4,100,200,100],[0.6,220,200,0],[0.8,240,130,0],[1.0,200,0,0]]
      return normToRGBStops(t, stops)
    }

    const SZ = 512
    const canvas = document.createElement('canvas')
    canvas.width = SZ; canvas.height = SZ
    const ctx = canvas.getContext('2d')
    const imgData = ctx.createImageData(SZ, SZ)
    const px = imgData.data
    const alpha = Math.round(opacity * 2.55)

    for (let py = 0; py < SZ; py++) {
      for (let pxx = 0; pxx < SZ; pxx++) {
        const gi = ((SZ - 1 - py) / (SZ - 1)) * (n - 1)
        const gj = (pxx / (SZ - 1)) * (n - 1)
        const i0 = Math.min(Math.floor(gi), n - 2), i1 = i0 + 1
        const j0 = Math.min(Math.floor(gj), n - 2), j1 = j0 + 1
        const ti = gi - i0, tj = gj - j0
        const val = matrix[i0][j0]*(1-ti)*(1-tj) + matrix[i1][j0]*ti*(1-tj) +
                    matrix[i0][j1]*(1-ti)*tj      + matrix[i1][j1]*ti*tj
        const t = Math.max(0, Math.min(1, (val - scaleMin) / (scaleMax - scaleMin)))
        const [r, g, b] = normToRGB(t)
        const idx = (py * SZ + pxx) * 4
        px[idx] = r; px[idx+1] = g; px[idx+2] = b; px[idx+3] = alpha
      }
    }
    ctx.putImageData(imgData, 0, 0)

    const mb = mapRef.current.getBounds()
    const overlayBounds = [[mb.getSouth(), mb.getWest()], [mb.getNorth(), mb.getEast()]]
    if (gridLayerRef.current) mapRef.current.removeLayer(gridLayerRef.current)
    gridLayerRef.current = L.imageOverlay(canvas.toDataURL('image/png'), overlayBounds, {
      opacity: 1.0, interactive: false, zIndex: 200
    }).addTo(mapRef.current)

    gridDataRef.current = { matrix, n, center, dlat, dlon, scaleMin, scaleMax, half, _raw: data }
  }

  const fetchClimateData = useCallback(async (lat, lon) => {
    setEmptyMsg('Cargando datos climáticos…')
    setShowChart(false)
    try {
      const r = await fetch(`/api/climate?lat=${lat}&lon=${lon}`)
      if (!r.ok) throw new Error('HTTP ' + r.status)
      const d = await r.json()
      const days = [31,28,31,30,31,30,31,31,30,31,30,31]
      const irr = d.irradiance?.length === 12 ? d.irradiance : null
      const prec = d.precip?.length === 12 ? d.precip : null
      const temp = d.temp?.length === 12 ? d.temp : null
      const wind = d.wind?.length === 12 ? d.wind : null
      let soiling = null
      if (prec) {
        soiling = prec.map((p, i) => computeSoilingPct(p, wind ? wind[i] : 0))
      }
      setMonthlyData({ irradiance: irr, precip: prec, temp, wind, soiling })

      if (irr) {
        const annual = irr.reduce((s, v, i) => s + v * days[i], 0)
        setAnnualGHI('GHI anual: ' + Math.round(annual) + ' kWh/m²')
        // Trigger grid fetch
        clearTimeout(gridDebounceRef.current)
        gridDebounceRef.current = setTimeout(fetchGHIGrid, 200)
      }

      if (temp) {
        // Auto-fill design temperature
        const avg = Math.round(temp.reduce((a, b) => a + b, 0) / temp.length)
        dispatch({ type: 'UPDATE_ENV', payload: { ambient_temp_c: avg } })
      }

      setShowChart(true)
    } catch (e) {
      setEmptyMsg('Error al cargar datos climáticos: ' + e.message)
      setShowChart(false)
      setMonthlyData({ irradiance: null, precip: null, temp: null, wind: null, soiling: null })
    }
  }, [dispatch, fetchGHIGrid])

  // Render monthly chart
  useEffect(() => {
    if (!chartCanvasRef.current || !showChart) return
    const data = monthlyData[activeTab]
    if (!data) return
    const cfg = MONTHLY_CFG[activeTab] || MONTHLY_CFG.irradiance
    const maxV = Math.max(...data) || 1
    const isLine = cfg.type === 'line'

    if (monthlyChartRef.current) {
      monthlyChartRef.current.destroy()
      monthlyChartRef.current = null
    }

    const hexToRgba = (hex, a) => {
      const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16)
      return `rgba(${r},${g},${b},${a})`
    }

    monthlyChartRef.current = new Chart(chartCanvasRef.current, {
      type: isLine ? 'line' : 'bar',
      data: {
        labels: MONTHS,
        datasets: [{
          data,
          backgroundColor: isLine
            ? hexToRgba(cfg.color, 0.15)
            : data.map(v => hexToRgba(cfg.color, 0.38 + 0.58 * (v / maxV))),
          borderColor: cfg.color,
          borderWidth: isLine ? 2 : 1,
          borderRadius: isLine ? 0 : 3,
          fill: isLine, tension: 0.35,
          pointRadius: isLine ? 3 : 0, pointBackgroundColor: cfg.color,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => c.raw + ' ' + cfg.unit } } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#9A9A9A' } },
          y: {
            grid: { color: 'rgba(0,0,0,0.04)' },
            ticks: { font: { size: 10 }, color: '#9A9A9A' },
            beginAtZero: true,
            max: activeTab === 'soiling' ? 25 : undefined,
          }
        }
      }
    })

    return () => { monthlyChartRef.current?.destroy(); monthlyChartRef.current = null }
  }, [monthlyData, activeTab, showChart])

  // Re-render heatmap when tab or month changes
  useEffect(() => {
    if (gridDataRef.current?._raw) {
      renderGHICanvas(gridDataRef.current._raw, activeTab, heatmapMonth, opacityVal)
    }
  }, [activeTab, heatmapMonth, opacityVal])

  // Init Leaflet map
  useEffect(() => {
    if (mapRef.current) return
    const lat = project.lat || 20.0
    const lon = project.lon || 10.0
    const zoom = project.lat ? 8 : 3

    const map = L.map(mapContainerRef.current, { zoomControl: true, attributionControl: true })
      .setView([lat, lon], zoom)

    applyMapLayer(map, DEFAULT_MAP_LAYER, layerRefs.current)

    setTimeout(() => map.invalidateSize(), 50)

    map.on('moveend', () => {
      if (!gridDataRef.current) return
      clearTimeout(gridDebounceRef.current)
      gridDebounceRef.current = setTimeout(fetchGHIGrid, 800)
    })

    map.on('click', (e) => {
      if (measure.handleClick(e.latlng)) return
      const lat = parseFloat(e.latlng.lat.toFixed(5))
      const lon = parseFloat(e.latlng.lng.toFixed(5))
      dispatch({ type: 'UPDATE_PROJECT', payload: { lat, lon } })
      setShowHint(false)

      // Place marker
      if (markerRef.current) {
        markerRef.current.setLatLng([lat, lon])
      } else {
        markerRef.current = L.marker([lat, lon]).addTo(map)
      }
      map.setView([lat, lon], Math.max(map.getZoom(), 8))

      const db = (lat >= -65 && lat <= 65 && lon >= -25 && lon <= 75) ? 'PVGIS-SARAH3' : 'ERA5'
      setCoordsText(lat.toFixed(4) + ', ' + lon.toFixed(4))
      setPvgisDb('Base solar: ' + db)

      // Reverse geocode
      fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lon}&zoom=10&addressdetails=1`, {
        headers: { 'Accept-Language': 'es,en' }
      })
        .then(r => r.json())
        .then(d => {
          if (d.address) {
            const city = d.address.city || d.address.town || d.address.village || d.address.municipality || d.address.county || ''
            const cc = (d.address.country_code || '').toUpperCase()
            dispatch({ type: 'UPDATE_PROJECT', payload: {
              ...(city ? { city } : {}),
              ...(cc ? { country: cc } : {}),
            }})
          }
        }).catch(() => {})

      // Fetch climate data
      clearTimeout(climateDebounceRef.current)
      climateDebounceRef.current = setTimeout(() => fetchClimateData(lat, lon), 700)

      // Pre-warm PVGIS cache in background so simulation in step 6 is instant
      const candidatesToPrefetch = state.candidates?.length ? state.candidates : ['SIL_M_60','SIL_M_90','SIL_L_200','SIL_L_260']
      fetch('/api/prefetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon, candidates: candidatesToPrefetch }),
      }).catch(() => {}) // silent — non-critical
    })

    mapRef.current = map

    // If already has coords, place marker
    if (project.lat && project.lon) {
      markerRef.current = L.marker([project.lat, project.lon]).addTo(map)
      setCoordsText(project.lat.toFixed(4) + ', ' + project.lon.toFixed(4))
      clearTimeout(climateDebounceRef.current)
      climateDebounceRef.current = setTimeout(() => fetchClimateData(project.lat, project.lon), 300)
    }

    return () => {
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
        markerRef.current = null
        gridLayerRef.current = null
        gridDataRef.current = null
      }
    }
  }, [])

  // Invalidate size when shown
  useEffect(() => {
    setTimeout(() => mapRef.current?.invalidateSize(), 100)
  }, [])

  const switchLayer = (layerId) => {
    if (layerId === activeLayer) return
    if (layerId === TERRAIN_3D_LAYER.id) { setActiveLayer(layerId); return }
    setActiveLayer(layerId)
    if (mapRef.current) {
      applyMapLayer(mapRef.current, layerId, layerRefs.current, [markerRef.current])
    }
  }
  const is3D = activeLayer === TERRAIN_3D_LAYER.id

  const GRADIENTS = {
    irradiance: 'linear-gradient(to top,#004CB3,#0099CC,#64C864,#DCE800,#F08200,#C80000)',
    precip:     'linear-gradient(to top,#FFFCFF,#BEE1FA,#5AAAE6,#1E6EC8,#0A37A0,#05145A)',
    temp:       'linear-gradient(to top,#00289F,#1E8CD2,#64D278,#E6E128,#F06E0A,#C80000)',
    soiling:    'linear-gradient(to top,#28B43C,#96C832,#E6D21E,#F0820F,#C8370A,#821919)',
  }

  const LEGEND_UNITS = {
    irradiance: 'kWh/m²/d',
    precip:     'mm/día',
    temp:       '°C',
    soiling:    '%',
  }
  const sc = UNIVERSAL_SCALES[activeTab] || { min: 0, max: 10 }
  const legendLabels = Array.from({ length: 6 }, (_, k) => {
    const step = (sc.max - sc.min) / 5
    const val = sc.min + k * step
    return Number.isInteger(val) ? val.toFixed(1) : val.toFixed(1)
  }).reverse()

  const tabs = [
    { key: 'irradiance', label: '☀ Irradiancia' },
    { key: 'precip',     label: '🌧 Lluvia' },
    { key: 'temp',       label: '🌡 Temperatura' },
    { key: 'soiling',    label: '🌫 Soiling' },
  ]

  const handleTabChange = (tab) => {
    setActiveTab(tab)
    setMonthlyTitle(MONTHLY_CFG[tab].title)
    const data = monthlyData[tab]
    if (data) {
      setShowChart(true)
    } else if (project.lat) {
      setShowChart(false)
      setEmptyMsg('Datos no disponibles para esta variable.')
    }
  }

  return (
    <div className="canvas-panel canvas-step-view" style={{ display: 'flex' }}>
      <div className="canvas-header" style={{ paddingBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '6px' }}>
          <span className="canvas-title">Clima Solar</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: '5px' }}>
              {tabs.map(t => (
                <button
                  key={t.key}
                  className={`c1-tab ${activeTab === t.key ? 'active' : ''}`}
                  onClick={() => handleTabChange(t.key)}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {gridDataRef.current && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <button
                  className={`c1-tab ${heatmapMonth === null ? 'active' : ''}`}
                  style={{ fontSize: '10px', padding: '2px 9px' }}
                  onClick={() => setHeatmapMonth(null)}
                >
                  Media anual
                </button>
                <input
                  type="range" min="0" max="11" step="1"
                  value={heatmapMonth ?? 0}
                  style={{ width: '120px', accentColor: 'var(--salvi-black)', cursor: 'pointer' }}
                  onChange={e => setHeatmapMonth(parseInt(e.target.value))}
                />
                <span style={{ fontSize: '11px', fontWeight: '600', minWidth: '28px' }}>
                  {heatmapMonth !== null ? MONTHS[heatmapMonth] : ''}
                </span>
                <span style={{ fontSize: '10px', color: 'var(--salvi-grey)', marginLeft: '4px' }}>opac.</span>
                <input
                  type="range" min="0" max="100" step="5"
                  value={opacityVal}
                  style={{ width: '55px', height: '3px', accentColor: 'var(--salvi-black)', cursor: 'pointer' }}
                  onChange={e => setOpacityVal(parseInt(e.target.value))}
                />
              </div>
            )}
          </div>
        </div>
        <span className="canvas-subtitle" style={{ display: 'block', marginTop: '4px' }}>
          {project.lat && project.lon
            ? (project.city || '') + (project.city ? ' · ' : '') + project.lat.toFixed(4) + ', ' + (project.lon || 0).toFixed(4)
            : 'Sin coordenadas — haz clic en el mapa para situar el proyecto'}
        </span>
      </div>

      {showHint && !project.lat && (
        <div style={{
          background: '#FFFBF0', borderBottom: '1px solid #E8D5A0',
          padding: '7px 16px', display: 'flex', alignItems: 'center',
          gap: '8px', fontSize: '12px', color: '#7A5C00', flexShrink: 0,
        }}>
          <span style={{ fontSize: '15px' }}>☝️</span>
          <span>Haz clic en el mapa para situar el proyecto y cargar los datos climáticos</span>
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        <LayerSwitcher activeLayer={activeLayer} onChange={switchLayer} layers={LAYERS_WITH_3D} />
        {!is3D && (
          <MeasureButton active={measure.active} hasPoints={measure.hasPoints} onToggle={measure.toggle} onClear={measure.clear} />
        )}

        {is3D && (
          <div style={{ position: 'absolute', inset: 0 }}>
            <Map3DTerrain lat={project.lat} lon={project.lon} />
          </div>
        )}

      <div ref={mapContainerRef} style={{ width: '100%', height: '100%', display: is3D ? 'none' : 'block' }}>
        {loading && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
            background: 'rgba(255,255,255,0.85)', borderRadius: '8px',
            padding: '8px 14px', fontSize: '12px', color: 'var(--salvi-grey)',
            zIndex: 600, pointerEvents: 'none',
          }}>
            ⏳ Calculando mapa solar…
          </div>
        )}
        {gridDataRef.current && (
          <div style={{
            position: 'absolute', bottom: '10px', right: '10px', zIndex: 500,
            background: 'rgba(255,255,255,0.92)', borderRadius: '6px',
            padding: '7px 8px', fontSize: '9px', lineHeight: '1.4',
            border: '1px solid rgba(30,30,30,0.15)',
            display: 'flex', flexDirection: 'row', alignItems: 'stretch', gap: '5px',
          }}>
            <div style={{
              width: '14px', borderRadius: '3px', height: '110px',
              background: GRADIENTS[activeTab],
            }} />
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', color: 'var(--salvi-grey)' }}>
              {legendLabels.map((l, i) => <span key={i}>{l}</span>)}
              <span style={{ marginTop: '4px', color: 'var(--salvi-muted)', fontSize: '8px', whiteSpace: 'nowrap' }}>
                {LEGEND_UNITS[activeTab]}
              </span>
            </div>
          </div>
        )}
      </div>
      </div>

      <div id="c1-monthly-panel">
        <span style={{
          fontSize: '11px', fontWeight: '600', color: 'var(--salvi-grey)',
          padding: '6px 14px 3px', display: 'block',
        }}>
          {monthlyTitle}
        </span>
        {showChart ? (
          <div style={{ padding: '2px 14px 8px', height: '90px', position: 'relative' }}>
            <canvas ref={chartCanvasRef}></canvas>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '14px 0 12px', fontSize: '12px', color: 'var(--salvi-muted)' }}>
            {emptyMsg}
          </div>
        )}
      </div>

      <div className="canvas-footer-bar">
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--salvi-grey)' }}>
          {coordsText}
        </span>
        <span style={{ fontSize: '11px', color: 'var(--salvi-muted)' }}>{pvgisDb}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--salvi-grey)' }}>
          {annualGHI}
        </span>
      </div>
    </div>
  )
}
