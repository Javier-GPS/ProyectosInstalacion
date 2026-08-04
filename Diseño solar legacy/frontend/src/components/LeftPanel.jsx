import { useRef, useEffect } from 'react'
import { MapPin, Lightbulb, Moon, Sun, Package, PlayCircle, BarChart2, ZoomIn, FileText, SkipBack, SkipForward } from 'lucide-react'
import { useApp } from '../context/AppContext'
import Step1Proyecto from './steps/Step1Proyecto'
import Step2Fotometria from './steps/Step2Fotometria'
import Step3PerfilNocturno from './steps/Step3PerfilNocturno'
import Step4Entorno from './steps/Step4Entorno'
import Step5Candidatos from './steps/Step5Candidatos'
import Step6Simulacion from './steps/Step6Simulacion'
import Step7Resultados from './steps/Step7Resultados'
import Step8Detalle from './steps/Step8Detalle'
import Step9Informe from './steps/Step9Informe'

const STEP_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9]

const STEPS = [
  { n: 1, label: 'Proyecto',        Icon: MapPin },
  { n: 2, label: 'Fotometría',      Icon: Lightbulb },
  { n: 3, label: 'Perfil Nocturno', Icon: Moon },
  { n: 4, label: 'Entorno',         Icon: Sun },
  { n: 5, label: 'Candidatos',      Icon: Package },
  { n: 6, label: 'Simulación',      Icon: PlayCircle },
  { n: 7, label: 'Resultados',      Icon: BarChart2 },
  { n: 8, label: 'Detalle',         Icon: ZoomIn },
  { n: 9, label: 'Informe',         Icon: FileText },
]

function getStepCompleted(n, state) {
  const { project, photometry, nightProfile, candidates, simulation, selectedProductId } = state
  switch (n) {
    case 1: return !!(project.name && project.lat && project.lon)
    case 2: return photometry.system_power_w > 0
    case 3: return nightProfile.periods.length > 0
    case 4: return true
    case 5: return candidates.length > 0
    case 6: return !!simulation
    case 7: return !!simulation
    case 8: return !!selectedProductId
    case 9: return false
    default: return false
  }
}

export default function LeftPanel() {
  const { state, dispatch } = useApp()
  const panelRef = useRef(null)
  const handleRef = useRef(null)

  const goToStep = (n) => {
    if (!STEP_ORDER.includes(n)) return
    dispatch({ type: 'SET_STEP', payload: n })
  }

  const nextStep = () => {
    const idx = STEP_ORDER.indexOf(state.step)
    if (idx < STEP_ORDER.length - 1) goToStep(STEP_ORDER[idx + 1])
  }

  const prevStep = () => {
    const idx = STEP_ORDER.indexOf(state.step)
    if (idx > 0) goToStep(STEP_ORDER[idx - 1])
  }

  const idx = STEP_ORDER.indexOf(state.step)

  // Panel resize
  useEffect(() => {
    const handle = handleRef.current
    const panel = panelRef.current
    const app = document.getElementById('app')
    if (!handle || !panel || !app) return

    let dragging = false
    let startX = 0
    let startW = 0

    const onMouseDown = (e) => {
      dragging = true
      startX = e.clientX
      startW = panel.offsetWidth
      handle.classList.add('dragging')
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      e.preventDefault()
    }

    const onMouseMove = (e) => {
      if (!dragging) return
      const maxW = Math.floor(window.innerWidth * 0.45)
      const newW = Math.min(maxW, Math.max(220, startW + (e.clientX - startX)))
      app.style.setProperty('--left-w', newW + 'px')
    }

    const onMouseUp = () => {
      if (!dragging) return
      dragging = false
      handle.classList.remove('dragging')
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    handle.addEventListener('mousedown', onMouseDown)
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)

    return () => {
      handle.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  return (
    <aside id="left-panel" ref={panelRef}>
      <div id="panel-resize" ref={handleRef} title="Arrastra para cambiar el ancho"></div>

      <div id="step-nav">
        {STEPS.map(({ n, label, Icon }) => {
          const completed = getStepCompleted(n, state)
          const active = state.step === n
          return (
            <button
              key={n}
              className={`step-icon-btn ${active ? 'active' : ''} ${completed ? 'completed' : ''}`}
              onClick={() => goToStep(n)}
              data-label={label}
            >
              <Icon size={18} strokeWidth={1.75} />
              <span className="step-check"></span>
            </button>
          )
        })}
      </div>

      <div id="step-content">
        {state.step === 1 && <Step1Proyecto />}
        {state.step === 2 && <Step2Fotometria />}
        {state.step === 3 && <Step3PerfilNocturno />}
        {state.step === 4 && <Step4Entorno />}
        {state.step === 5 && <Step5Candidatos />}
        {state.step === 6 && <Step6Simulacion />}
        {state.step === 7 && <Step7Resultados />}
        {state.step === 8 && <Step8Detalle />}
        {state.step === 9 && <Step9Informe />}
      </div>

      <div id="step-nav-buttons">
        <button
          className="btn-secondary btn-icon-only"
          onClick={prevStep}
          disabled={idx <= 0}
          title="Anterior"
          aria-label="Anterior"
        >
          <SkipBack size={18} strokeWidth={1.75} />
        </button>
        <button
          className="btn-primary btn-icon-only"
          onClick={nextStep}
          disabled={idx >= STEP_ORDER.length - 1}
          title="Siguiente"
          aria-label="Siguiente"
        >
          <SkipForward size={18} strokeWidth={1.75} />
        </button>
      </div>
    </aside>
  )
}
