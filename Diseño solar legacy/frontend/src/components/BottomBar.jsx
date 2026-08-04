import { useApp } from '../context/AppContext'

export default function BottomBar() {
  const { state } = useApp()
  const { lat, lon } = state.project

  let pvgisDb = ''
  if (lat != null && lon != null) {
    pvgisDb = (lat >= -65 && lat <= 65 && lon >= -25 && lon <= 75)
      ? 'Base solar: PVGIS-SARAH3'
      : 'Base solar: ERA5'
  }

  return (
    <footer id="bottom-bar">
      <span>SALVI Solar v1.0.0 · Motor v1.0 · Biblioteca Salvi Solar 2026.1</span>
      {lat != null && lon != null && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--salvi-grey)' }}>
          {lat.toFixed(4)}, {lon.toFixed(4)}
        </span>
      )}
      {pvgisDb && (
        <span style={{ fontSize: '11px', color: 'var(--salvi-muted)' }}>{pvgisDb}</span>
      )}
    </footer>
  )
}
