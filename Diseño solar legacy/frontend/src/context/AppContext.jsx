import { createContext, useContext, useReducer } from 'react'

const initialState = {
  step: 1,
  project: { name: '', country: 'ES', city: '', lat: null, lon: null },
  photometry: {
    lighting_class: 'M4',
    system_power_w: 90,
    mounting_height_m: 8,
    spacing_m: 30,
    compliance_margin_pct: 10,
  },
  nightProfile: {
    margin_on_min: -15,
    margin_off_min: 15,
    aux_wh: 0,
    periods: [
      { duration_pct: 0.333, presence_ratio: 0.5,  dimming_presence: 1.0, dimming_no_presence: 0.3 },
      { duration_pct: 0.333, presence_ratio: 0.2,  dimming_presence: 0.8, dimming_no_presence: 0.2 },
      { duration_pct: 0.334, presence_ratio: 0.3,  dimming_presence: 0.8, dimming_no_presence: 0.2 },
    ],
  },
  env: {
    soiling_env: 'urbana_normal',
    ambient_temp_c: 35,
    max_failure_rate_pct: 2.0,
    electricity_cost: 0.15,
    country_co2_factor: 0.18,
    use_local_shading: false,
    shading_mode: 'PVGIS_SHADOWMAP_POINT',
    shading_environment_context: 'urban_street',
    panel_center_height_m: 8,
    shadowmap_mock_scenario: 'urban_canyon',
  },
  candidates: ['SIL_M_60', 'SIL_M_90', 'SIL_L_200', 'SIL_L_260'],
  products: [],
  simulation: null,
  simulating: false,
  selectedProductId: null,
  apiStatus: 'connecting',
  apiVersion: '',
  showMapPicker: false,
  showGISImport: false,
  viaPickMode: false,
  viaPickLatLon: null,
  viaMapFlyTo: null,
  npMonth: 5,
  sortField: null,
  sortAsc: true,
}

function reducer(state, action) {
  switch (action.type) {
    case 'SET_STEP':
      return { ...state, step: action.payload }

    case 'SET_PROJECT':
      return { ...state, project: action.payload }

    case 'UPDATE_PROJECT':
      return { ...state, project: { ...state.project, ...action.payload } }

    case 'SET_PHOTOMETRY':
      return { ...state, photometry: action.payload }

    case 'UPDATE_PHOTOMETRY':
      return { ...state, photometry: { ...state.photometry, ...action.payload } }

    case 'SET_NIGHT_PROFILE':
      return { ...state, nightProfile: action.payload }

    case 'UPDATE_NIGHT_PROFILE':
      return { ...state, nightProfile: { ...state.nightProfile, ...action.payload } }

    case 'SET_ENV':
      return { ...state, env: action.payload }

    case 'UPDATE_ENV':
      return { ...state, env: { ...state.env, ...action.payload } }

    case 'SET_CANDIDATES':
      return { ...state, candidates: action.payload }

    case 'TOGGLE_CANDIDATE': {
      const id = action.payload
      const idx = state.candidates.indexOf(id)
      if (idx === -1) return { ...state, candidates: [...state.candidates, id] }
      return { ...state, candidates: state.candidates.filter(c => c !== id) }
    }

    case 'SET_PRODUCTS':
      return { ...state, products: action.payload }

    case 'SET_SIMULATING':
      return { ...state, simulating: action.payload }

    case 'SET_SIMULATION':
      return { ...state, simulation: action.payload, simulating: false }

    case 'SET_SELECTED_PRODUCT':
      return { ...state, selectedProductId: action.payload }

    case 'SET_API_STATUS':
      return { ...state, apiStatus: action.payload.status, apiVersion: action.payload.version || '' }

    case 'SET_MAP_PICKER_OPEN':
      return { ...state, showMapPicker: action.payload }

    case 'SET_GIS_IMPORT_OPEN':
      return { ...state, showGISImport: action.payload }

    case 'SET_VIA_PICK_MODE':
      return { ...state, viaPickMode: action.payload }

    case 'SET_VIA_PICK_LATLON':
      return { ...state, viaPickLatLon: action.payload, viaPickMode: false }

    case 'SET_VIA_MAP_FLY_TO':
      return { ...state, viaMapFlyTo: action.payload }

    case 'SET_NP_MONTH':
      return { ...state, npMonth: action.payload }

    case 'SET_SORT':
      if (state.sortField === action.payload) {
        return { ...state, sortAsc: !state.sortAsc }
      }
      return { ...state, sortField: action.payload, sortAsc: true }

    default:
      return state
  }
}

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}
