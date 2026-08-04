import { useApp } from '../context/AppContext'
import CanvasStep1 from './canvas/CanvasStep1'
import CanvasStep3 from './canvas/CanvasStep3'
import CanvasViaEstimacion from './canvas/CanvasViaEstimacion'
import CanvasSimulacion from './canvas/CanvasSimulacion'
import CanvasResultados from './canvas/CanvasResultados'
import CanvasDetalle from './canvas/CanvasDetalle'
import CanvasWelcome from './canvas/CanvasWelcome'
import CanvasSolarIrradiance from './canvas/CanvasSolarIrradiance'

export default function MainCanvas() {
  const { state } = useApp()
  const { step, simulation, selectedProductId } = state

  // Determine which canvas to show
  let activeCanvas = 'welcome'
  if (step === 1) activeCanvas = 'step1'
  else if (step === 2) activeCanvas = 'via'
  else if (step === 3) activeCanvas = 'step3'
  else if (step === 4) activeCanvas = 'solar'
  else if (step === 6) activeCanvas = simulation ? 'results' : 'welcome'
  else if (step === 7) activeCanvas = simulation ? 'results' : 'welcome'
  else if (step === 8) {
    if (selectedProductId && simulation) activeCanvas = 'detail'
    else if (simulation) activeCanvas = 'results'
    else activeCanvas = 'welcome'
  }
  else if (step === 9) activeCanvas = simulation ? 'results' : 'welcome'
  // step 5 → welcome

  return (
    <main id="main-canvas">
      {activeCanvas === 'step1' && <CanvasStep1 />}
      {activeCanvas === 'via'   && <CanvasViaEstimacion />}
      {activeCanvas === 'step3' && <CanvasStep3 />}
      {activeCanvas === 'solar'  && <CanvasSolarIrradiance />}
      {activeCanvas === 'welcome' && <CanvasWelcome />}
      {activeCanvas === 'results' && <CanvasResultados />}

      {activeCanvas === "detail" && <CanvasDetalle />}
      <CanvasSimulacion />
    </main>
  )
}
