import { useEffect } from 'react'
import { useApp } from './context/AppContext'
import { apiGet } from './api'
import { DEMO_PRODUCTS, COUNTRY_DATA } from './utils'
import TopBar from './components/TopBar'
import LeftPanel from './components/LeftPanel'
import MainCanvas from './components/MainCanvas'
import RightPanel from './components/RightPanel'
import BottomBar from './components/BottomBar'
import Toast from './components/Toast'
import MapPickerModal from './components/map/MapPickerModal'
import GISImportModal from './components/map/GISImportModal'
import AskAIWidget from './components/AskAIWidget'

export default function App() {
  const { state, dispatch } = useApp()

  useEffect(() => {
    // Check API health
    apiGet('/health')
      .then(h => {
        dispatch({ type: 'SET_API_STATUS', payload: { status: 'ok', version: h.version || '1.0' } })
      })
      .catch(() => {
        dispatch({ type: 'SET_API_STATUS', payload: { status: 'err' } })
      })

    // Load products
    apiGet('/products')
      .then(r => {
        const products = r.products || r
        if (Array.isArray(products) && products.length > 0) {
          dispatch({ type: 'SET_PRODUCTS', payload: products })
          const silProducts = products.filter(p => (p.id || '').toUpperCase().startsWith('SIL')).slice(0, 4)
          if (silProducts.length > 0) {
            dispatch({ type: 'SET_CANDIDATES', payload: silProducts.map(p => p.id) })
          }
        }
      })
      .catch(() => {
        dispatch({ type: 'SET_PRODUCTS', payload: DEMO_PRODUCTS })
      })
  }, [])

  return (
    <div id="app">
      <TopBar />
      <LeftPanel />
      <MainCanvas />
      <RightPanel />
      <BottomBar />
      <Toast />
      {state.showMapPicker && <MapPickerModal />}
      {state.showGISImport && <GISImportModal />}
      <AskAIWidget />
    </div>
  )
}
