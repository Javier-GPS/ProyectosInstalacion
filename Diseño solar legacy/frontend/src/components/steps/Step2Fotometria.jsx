import { useState, useEffect, useCallback } from 'react'
import { useApp } from '../../context/AppContext'

const API = import.meta.env.VITE_API_URL || 'http://localhost:5001'

const CU_W_H = [0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50]

// OSM highway → EN 13201 class (mirrors via.py)
const HIGHWAY_TO_CLASS = {
  motorway: 'ME1', motorway_link: 'ME2',
  trunk: 'ME1', trunk_link: 'ME2',
  primary: 'ME2', primary_link: 'ME3a',
  secondary: 'ME3a', secondary_link: 'ME4a',
  tertiary: 'ME4a', tertiary_link: 'ME5',
  residential: 'ME5', living_street: 'S2',
  service: 'S3', pedestrian: 'S1',
  footway: 'S2', cycleway: 'S3',
  path: 'S3', unclassified: 'ME5', road: 'ME4a',
}

const CLASS_LUX = {
  ME1: 30, ME2: 15, ME3a: 10, ME3b: 10,
  ME4a: 7.5, ME4b: 7.5, ME5: 5, ME6: 3,
  CE0: 50, CE1: 30, CE2: 20, CE3: 15, CE4: 10, CE5: 7.5,
  S1: 15, S2: 10, S3: 7.5, S4: 5, S5: 3, S6: 2,
}

const HIGHWAY_LABELS = {
  motorway: 'Autopista', motorway_link: 'Acceso autopista',
  trunk: 'Vía rápida', trunk_link: 'Acceso vía rápida',
  primary: 'Vía principal', primary_link: 'Acceso principal',
  secondary: 'Vía secundaria', secondary_link: 'Acceso secundaria',
  tertiary: 'Vía local', tertiary_link: 'Acceso local',
  residential: 'Residencial', living_street: 'Zona de convivencia',
  service: 'Servicio / acceso', pedestrian: 'Peatonal',
  footway: 'Sendero peatonal', cycleway: 'Carril bici',
  path: 'Camino', unclassified: 'Sin clasificar', road: 'Carretera',
}

function interpolateCU(table, wH) {
  if (!table || table.length < 10) return null
  if (wH <= CU_W_H[0]) return table[0] * (wH / CU_W_H[0])
  if (wH >= CU_W_H[9]) return table[9]
  for (let i = 0; i < 9; i++) {
    if (wH <= CU_W_H[i + 1]) {
      const t = (wH - CU_W_H[i]) / (CU_W_H[i + 1] - CU_W_H[i])
      return table[i] + t * (table[i + 1] - table[i])
    }
  }
  return table[9]
}

function calcPotencia(E, wPerLum, spacing, CU, MF, etaLed) {
  const etaEf = CU * MF * etaLed
  return etaEf > 0 ? (E * wPerLum * spacing) / etaEf : 0
}

export default function Step2Fotometria() {
  const { state, dispatch } = useApp()
  const { photometry, project, viaPickLatLon, viaPickMode } = state

  const update = (field, value) =>
    dispatch({ type: 'UPDATE_PHOTOMETRY', payload: { [field]: value } })

  // ── State ─────────────────────────────────────────────────────────────────
  const [viaLoading, setViaLoading] = useState(false)
  const [viaError,   setViaError]   = useState(null)
  const [lentes,     setLentes]     = useState(null)

  const [highway,       setHighway]       = useState('secondary')
  const [roadName,      setRoadName]      = useState('')
  const [lightingClass, setLightingClass] = useState('ME3a')
  const [roadWidthM,    setRoadWidthM]    = useState(7.0)
  const [lanes,         setLanes]         = useState(2)
  const [safetyMarginM, setSafetyMarginM] = useState(1.0)

  const [poleHeightM, setPoleHeightM] = useState(photometry.mounting_height_m || 8)
  const [spacingM,    setSpacingM]    = useState(photometry.spacing_m || 30)

  const [opticaId, setOpticaId] = useState('f2md')
  const [MF,       setMF]       = useState(0.75)
  const [etaLed,   setEtaLed]   = useState(130)
  const [cuManual, setCuManual] = useState(null)

  const [disposicion, setDisposicion] = useState(null)
  const [opticas,     setOpticas]     = useState([])

  // Address search
  const [searchText,    setSearchText]    = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchResults, setSearchResults] = useState([])
  const [searchOpen,    setSearchOpen]    = useState(false)

  // ── Derived ───────────────────────────────────────────────────────────────
  const anchoTotal  = roadWidthM + 2 * safetyMarginM
  const isBilateral = disposicion && disposicion.disposicion !== 'unilateral'
  const wPerLum     = isBilateral ? anchoTotal / 2 : anchoTotal
  const wHPerLum    = poleHeightM > 0 ? wPerLum / poleHeightM : 0

  const selectedLente = lentes?.[opticaId]
  const cuFromLdt   = selectedLente ? interpolateCU(selectedLente.cu_table, wHPerLum) : null
  const cuEffective = cuManual !== null ? cuManual : (cuFromLdt ?? 0.48)
  const E_lux       = CLASS_LUX[lightingClass] ?? 7.5
  const potenciaW   = calcPotencia(E_lux, wPerLum, spacingM, cuEffective, MF, etaLed)

  // Auto-sync calculated power to AppContext so downstream panels (dimming chart, TCO) always reflect the live value
  useEffect(() => {
    if (potenciaW > 0) {
      dispatch({ type: 'UPDATE_PHOTOMETRY', payload: {
        system_power_w:    Math.round(potenciaW),
        mounting_height_m: poleHeightM,
        spacing_m:         spacingM,
        lighting_class:    lightingClass,
      }})
    }
  // potenciaW already captures all its dependencies (E_lux, wPerLum, spacingM, cuEffective, MF, etaLed)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [potenciaW, lightingClass, poleHeightM, spacingM])

  // Load lens catalog on mount
  useEffect(() => {
    if (lentes) return
    fetch(`${API}/api/road`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skip_osm: true }),
    }).then(r => r.json()).then(d => {
      setLentes(d.lentes)
      if (d.opticas?.length) setOpticaId(d.opticas[0].id)
    }).catch(() => {})
  }, [lentes])

  // Recalculate disposition when geometry changes
  useEffect(() => {
    const h = poleHeightM
    if (h <= 0) return
    const ratio = anchoTotal / h
    let disp
    if      (ratio < 0.8) disp = { disposicion: 'unilateral',            label: 'Unilateral' }
    else if (ratio < 1.3) disp = { disposicion: 'bilateral_tresbolillo', label: 'Bilateral tresbolillo' }
    else if (ratio < 1.8) disp = { disposicion: 'bilateral_enfrente',    label: 'Bilateral enfrente' }
    else                   disp = { disposicion: 'central_mediana',       label: 'Central mediana' }
    disp.w_H = Math.round(ratio * 1000) / 1000
    setDisposicion(disp)

    if (lentes) {
      const order = ratio < 0.9 ? ['f151','f2md','f2m2']
                  : ratio < 1.5 ? ['f2md','f151','f2m2']
                  :               ['f2m2','f2md','f151']
      setOpticas(order.map((id, i) => ({
        id,
        nombre: lentes[id]?.nombre || id,
        CU: lentes[id] ? Math.round(interpolateCU(lentes[id].cu_table, wHPerLum) * 1000) / 1000 : null,
        recomendada: i === 0,
      })))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchoTotal, poleHeightM, lentes])

  // Auto-link highway → lighting class
  const handleHighwayChange = (hw) => {
    setHighway(hw)
    const cls = HIGHWAY_TO_CLASS[hw]
    if (cls) setLightingClass(cls)
  }

  const queryRoad = useCallback(async (lat, lon) => {
    setViaLoading(true); setViaError(null)
    try {
      const r = await fetch(`${API}/api/road`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon, pole_height_m: poleHeightM, spacing_m: spacingM }),
      })
      const d = await r.json()
      // Always reset all OSM fields so stale values from a previous road don't persist
      const rd = d.road || {}
      const newHighway      = rd.highway      || 'secondary'
      const newLightClass   = rd.lighting_class || HIGHWAY_TO_CLASS[newHighway] || 'ME3a'
      const newWidthM       = rd.width_m      || 7.0
      const newLanes        = rd.lanes        || 2
      setRoadName(rd.name || '')
      setHighway(newHighway)
      setLightingClass(newLightClass)
      setRoadWidthM(newWidthM)
      setLanes(newLanes)

      const newLentes   = d.lentes   || lentes
      const newOpticaId = d.opticas?.[0]?.id || opticaId
      if (d.lentes)      setLentes(d.lentes)
      if (d.opticas?.length) { setOpticas(d.opticas); setOpticaId(newOpticaId) }

      // Auto-apply power to photometry state (compute inline — can't rely on React state timing)
      const newAncho    = newWidthM + 2 * safetyMarginM
      const ratio       = poleHeightM > 0 ? newAncho / poleHeightM : 0
      const bilateral   = ratio >= 0.8
      const newWPerLum  = bilateral ? newAncho / 2 : newAncho
      const newWH       = poleHeightM > 0 ? newWPerLum / poleHeightM : 0
      const lenteDat    = newLentes?.[newOpticaId]
      const newCU       = lenteDat ? interpolateCU(lenteDat.cu_table, newWH) : 0.48
      const newELux     = CLASS_LUX[newLightClass] ?? 7.5
      const newPotencia = calcPotencia(newELux, newWPerLum, spacingM, newCU, MF, etaLed)
      if (newPotencia > 0) {
        dispatch({ type: 'UPDATE_PHOTOMETRY', payload: {
          system_power_w:    Math.round(newPotencia),
          mounting_height_m: poleHeightM,
          spacing_m:         spacingM,
          lighting_class:    newLightClass,
        }})
      }
    } catch (e) { setViaError('Error OSM: ' + e.message) }
    finally { setViaLoading(false) }
  }, [poleHeightM, spacingM])

  useEffect(() => {
    if (!viaPickLatLon) return
    queryRoad(viaPickLatLon.lat, viaPickLatLon.lon)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viaPickLatLon])

  const searchAddress = async () => {
    if (!searchText.trim()) return
    setSearchLoading(true); setSearchResults([]); setSearchOpen(true)
    try {
      const q = encodeURIComponent(searchText.trim())
      const r = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${q}&limit=5&addressdetails=1`,
        { headers: { 'Accept-Language': 'es,en' } }
      )
      const data = await r.json()
      setSearchResults(data)
    } catch { setSearchResults([]) }
    finally { setSearchLoading(false) }
  }

  const selectSearchResult = (item) => {
    const lat = parseFloat(item.lat)
    const lon = parseFloat(item.lon)
    dispatch({ type: 'SET_VIA_MAP_FLY_TO', payload: { lat, lon, zoom: 17 } })
    setSearchOpen(false)
    setSearchText(item.display_name.split(',')[0])
  }

  const applyPotencia = () => {
    update('system_power_w',      Math.round(potenciaW))
    update('mounting_height_m',   poleHeightM)
    update('spacing_m',           spacingM)
    update('lighting_class',      lightingClass)
  }

  return (
    <div className="step-form active">
      <h3 className="step-header">Fotometría</h3>

      {/* ── Address search ────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', marginBottom: 10 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <input
            type="text"
            placeholder="Buscar dirección o lugar…"
            value={searchText}
            onChange={e => { setSearchText(e.target.value); if (searchOpen) setSearchOpen(false) }}
            onKeyDown={e => e.key === 'Enter' && searchAddress()}
            style={{
              flex: 1, padding: '7px 10px', borderRadius: 7,
              border: '1.5px solid var(--border-color, #E0E0E0)',
              fontSize: 12, outline: 'none',
            }}
          />
          <button onClick={searchAddress} disabled={searchLoading} style={{
            padding: '7px 12px', borderRadius: 7, border: 'none',
            background: 'var(--salvi-black, #1E1E1E)', color: '#fff',
            fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap',
            opacity: searchLoading ? 0.6 : 1,
          }}>
            {searchLoading ? '…' : '🔍'}
          </button>
        </div>

        {/* Results dropdown */}
        {searchOpen && searchResults.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
            background: '#fff', border: '1px solid var(--border-color, #E0E0E0)',
            borderRadius: 8, marginTop: 4, boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            overflow: 'hidden',
          }}>
            {searchResults.map((item, i) => (
              <div key={i} onClick={() => selectSearchResult(item)} style={{
                padding: '8px 12px', cursor: 'pointer', fontSize: 12,
                borderBottom: i < searchResults.length - 1 ? '1px solid #f0f0f0' : 'none',
                lineHeight: 1.4,
              }}
                onMouseEnter={e => e.currentTarget.style.background = '#F5F5F5'}
                onMouseLeave={e => e.currentTarget.style.background = ''}
              >
                <div style={{ fontWeight: 600, color: 'var(--salvi-black)' }}>
                  {item.display_name.split(',')[0]}
                </div>
                <div style={{ fontSize: 10, color: 'var(--salvi-muted)', marginTop: 1 }}>
                  {item.display_name.split(',').slice(1, 3).join(',')}
                </div>
              </div>
            ))}
          </div>
        )}
        {searchOpen && !searchLoading && searchResults.length === 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 200,
            background: '#fff', border: '1px solid var(--border-color, #E0E0E0)',
            borderRadius: 8, marginTop: 4, padding: '10px 12px',
            fontSize: 12, color: 'var(--salvi-muted)',
          }}>
            Sin resultados
          </div>
        )}
      </div>

      {/* ── Select road button ────────────────────────────────────────────── */}
      <button
        onClick={() => dispatch({ type: 'SET_VIA_PICK_MODE', payload: !viaPickMode })}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 7, padding: '9px 0', marginBottom: 16,
          background: viaPickMode ? 'var(--salvi-black, #1E1E1E)' : 'var(--bg-hover, #F0F0F0)',
          color:      viaPickMode ? '#fff' : 'var(--salvi-black, #1E1E1E)',
          border:     viaPickMode ? '2px solid #E5534B' : '2px solid transparent',
          borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13,
          transition: 'all 0.15s',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
          <line x1="7" y1="1" x2="7" y2="13" stroke="currentColor" strokeWidth="1.5"/>
          <line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" strokeWidth="1.5"/>
        </svg>
        {viaPickMode ? '✦ Haz clic sobre la carretera…' : 'Seleccionar vía en el mapa'}
      </button>

      {viaLoading && (
        <div style={{ textAlign: 'center', fontSize: 11, color: 'var(--salvi-muted)', marginBottom: 10 }}>
          ⏳ Consultando OpenStreetMap…
        </div>
      )}
      {viaError && (
        <div style={{ padding: '6px 10px', background: '#FFF0F0', border: '1px solid #F5C5C5',
          borderRadius: 6, fontSize: 11, color: '#A33', marginBottom: 12 }}>
          {viaError}
        </div>
      )}

      {/* ── Road name (populated from OSM) ───────────────────────────────── */}
      {roadName && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '7px 11px', marginBottom: 12,
          background: 'var(--bg-hover, #F5F5F5)', borderRadius: 7,
          border: '1px solid var(--border-color, #E0E0E0)',
        }}>
          <span style={{ fontSize: 15 }}>🛣</span>
          <span style={{ fontWeight: 700, fontSize: 13, flex: 1 }}>{roadName}</span>
          <button onClick={() => setRoadName('')} style={{
            border: 'none', background: 'none', cursor: 'pointer',
            fontSize: 14, color: 'var(--salvi-muted)', lineHeight: 1,
          }}>×</button>
        </div>
      )}

      {/* ── Highway type + Lighting class ────────────────────────────────── */}
      <div className="field-row">
        <div className="field-group half">
          <label>Tipo de vía</label>
          <select value={highway} onChange={e => handleHighwayChange(e.target.value)}>
            <optgroup label="Interurbana">
              {['motorway','motorway_link','trunk','trunk_link','primary','primary_link'].map(v =>
                <option key={v} value={v}>{HIGHWAY_LABELS[v]}</option>)}
            </optgroup>
            <optgroup label="Urbana">
              {['secondary','secondary_link','tertiary','tertiary_link','residential','living_street'].map(v =>
                <option key={v} value={v}>{HIGHWAY_LABELS[v]}</option>)}
            </optgroup>
            <optgroup label="Otros">
              {['service','pedestrian','footway','cycleway','path','unclassified','road'].map(v =>
                <option key={v} value={v}>{HIGHWAY_LABELS[v]}</option>)}
            </optgroup>
          </select>
        </div>
        <div className="field-group half">
          <label>
            Clase EN 13201
            <span style={{ fontSize: 10, fontWeight: 400, color: 'var(--salvi-muted)', marginLeft: 4 }}>
              (editable)
            </span>
          </label>
          <select value={lightingClass} onChange={e => setLightingClass(e.target.value)}>
            <optgroup label="ME — vial motorizado">
              {['ME1','ME2','ME3a','ME3b','ME4a','ME4b','ME5','ME6'].map(v =>
                <option key={v} value={v}>{v} — {CLASS_LUX[v]} lux</option>)}
            </optgroup>
            <optgroup label="CE — zona de conflicto">
              {['CE0','CE1','CE2','CE3','CE4','CE5'].map(v =>
                <option key={v} value={v}>{v} — {CLASS_LUX[v]} lux</option>)}
            </optgroup>
            <optgroup label="S — peatonal / ciclista">
              {['S1','S2','S3','S4','S5','S6'].map(v =>
                <option key={v} value={v}>{v} — {CLASS_LUX[v]} lux</option>)}
            </optgroup>
          </select>
        </div>
      </div>

      {/* ── Road geometry ─────────────────────────────────────────────────── */}
      <div className="field-row">
        <div className="field-group half">
          <label>Ancho calzada <span className="unit">m</span></label>
          <input type="number" min="2" max="50" step="0.5"
            value={roadWidthM} onChange={e => setRoadWidthM(parseFloat(e.target.value) || 0)} />
          {lanes > 0 && <div className="field-help">{lanes} carril{lanes !== 1 ? 'es' : ''}</div>}
        </div>
        <div className="field-group half">
          <label>Margen seguridad <span className="unit">m</span></label>
          <input type="number" min="0" max="10" step="0.5"
            value={safetyMarginM} onChange={e => setSafetyMarginM(parseFloat(e.target.value) || 0)} />
          <div className="field-help">Total: {anchoTotal.toFixed(1)} m</div>
        </div>
      </div>

      <div className="field-row">
        <div className="field-group half">
          <label>Altura columna <span className="unit">m</span></label>
          <input type="number" min="3" max="20" step="0.5"
            value={poleHeightM} onChange={e => setPoleHeightM(parseFloat(e.target.value) || 0)} />
        </div>
        <div className="field-group half">
          <label>Interdistancia <span className="unit">m</span></label>
          <input type="number" min="5" max="80" step="1"
            value={spacingM} onChange={e => setSpacingM(parseFloat(e.target.value) || 0)} />
        </div>
      </div>

      {/* ── Disposition badge ─────────────────────────────────────────────── */}
      {disposicion && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '5px 10px', borderRadius: 6, marginBottom: 12,
          background: 'var(--bg-hover, #F5F5F5)', fontSize: 12,
        }}>
          <span style={{ fontWeight: 600 }}>{disposicion.label}</span>
          <span style={{ color: 'var(--salvi-muted)', fontFamily: 'var(--font-mono)' }}>
            w/H = {disposicion.w_H}
          </span>
        </div>
      )}

      {/* ── Optic selection ───────────────────────────────────────────────── */}
      {(opticas.length > 0 || lentes) && (
        <div className="field-group">
          <label>Óptica Salvi</label>
          <div style={{ display: 'flex', gap: 6 }}>
            {(opticas.length ? opticas : ['f151','f2md','f2m2'].map(id => ({ id, CU: null, recomendada: false }))).map(op => (
              <label key={op.id} style={{
                flex: '1 1 0', display: 'flex', flexDirection: 'column',
                alignItems: 'center', padding: '7px 6px', borderRadius: 7,
                cursor: 'pointer',
                border: `2px solid ${opticaId === op.id ? 'var(--salvi-black, #1E1E1E)' : 'var(--border-color, #E0E0E0)'}`,
                background: opticaId === op.id ? 'var(--salvi-black, #1E1E1E)' : '#fff',
                color: opticaId === op.id ? '#fff' : 'inherit',
                transition: 'all 0.12s',
              }}>
                <input type="radio" name="optica" value={op.id} checked={opticaId === op.id}
                  onChange={() => { setOpticaId(op.id); setCuManual(null) }}
                  style={{ display: 'none' }} />
                <span style={{ fontWeight: 700, fontSize: 12 }}>{op.id.toUpperCase()}</span>
                {op.CU != null && (
                  <span style={{ fontSize: 10, opacity: 0.75 }}>CU {op.CU}</span>
                )}
                {op.recomendada && (
                  <span style={{
                    fontSize: 9, marginTop: 2,
                    color: opticaId === op.id ? '#aef' : 'var(--state-success, #1F7A4D)',
                  }}>★ rec.</span>
                )}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* ── MF + η_LED ────────────────────────────────────────────────────── */}
      <div className="field-row">
        <div className="field-group half">
          <label>Factor mant. MF</label>
          <input type="number" min="0.5" max="1" step="0.05"
            value={MF} onChange={e => setMF(parseFloat(e.target.value) || 0.75)} />
        </div>
        <div className="field-group half">
          <label>Efic. LED <span className="unit">lm/W</span></label>
          <input type="number" min="80" max="220" step="5"
            value={etaLed} onChange={e => setEtaLed(parseFloat(e.target.value) || 130)} />
        </div>
      </div>

      {/* ── Result ────────────────────────────────────────────────────────── */}
      <div style={{
        background: 'var(--salvi-black, #1E1E1E)', color: '#fff',
        borderRadius: 10, padding: '12px 14px', marginBottom: 14,
      }}>
        <div style={{
          fontSize: 11, color: '#aaa', marginBottom: 6,
          fontFamily: 'var(--font-mono)', lineHeight: 1.7,
        }}>
          E {E_lux} lux · S {(wPerLum * spacingM).toFixed(0)} m²
          · CU {cuEffective.toFixed(3)} · MF {MF} · η {etaLed} lm/W
        </div>
        <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: -1 }}>
          {potenciaW > 0 ? Math.round(potenciaW) : '—'}
          <span style={{ fontSize: 14, fontWeight: 400, opacity: 0.6, marginLeft: 4 }}>W</span>
        </div>
        <div style={{
          marginTop: 10, width: '100%', padding: '7px 0', borderRadius: 6,
          background: potenciaW > 0 ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.05)',
          color: '#ccc', textAlign: 'center',
          fontSize: 11, letterSpacing: 0.3,
        }}>
          {potenciaW > 0 ? `✓ Aplicado al sistema · ${Math.round(potenciaW)} W` : '—'}
        </div>
      </div>

      {/* ── Normative margin (only remaining pure-photometry field) ──────── */}
      <div className="field-group">
        <label>Margen normativo <span className="unit">%</span></label>
        <input type="number" min="0" max="50"
          value={photometry.compliance_margin_pct}
          onChange={e => update('compliance_margin_pct', parseFloat(e.target.value) || 0)} />
      </div>

    </div>
  )
}
