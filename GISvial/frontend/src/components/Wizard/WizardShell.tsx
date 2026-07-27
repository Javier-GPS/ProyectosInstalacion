import React, { useCallback, useEffect, useRef, useState } from 'react';
import Header from '../Header';
import MapView from '../Map/MapView';
import MapControls from '../Map/MapControls';
import WizardNav from './WizardNav';
import StepProyecto from './StepProyecto';
import StepZona from './StepZona';
import StepVias from './StepVias';
import StepLuminarias from './StepLuminarias';
import StepInforme from './StepInforme';
import { useGisStore } from '../../store/useGisStore';
import type { WizardStep } from '../../store/types';

const WizardShell: React.FC = () => {
  const stepWizard = useGisStore(s => s.stepWizard);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const sidebarOpen = useGisStore(s => s.sidebarOpen);
  const setSidebarOpen = useGisStore(s => s.setSidebarOpen);
  const initialized = useGisStore(s => s.initialized);
  const projects = useGisStore(s => s.projects);
  const setProjects = useGisStore(s => s.setProjects);
  const setZones = useGisStore(s => s.setZones);
  const setSelectedZone = useGisStore(s => s.setSelectedZone);
  const setInitialized = useGisStore(s => s.setInitialized);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const setActiveProject = useGisStore(s => s.setActiveProject);
  const confirmPlanningLeave = useGisStore(s => s.confirmPlanningLeave);
  const statusGranular = useGisStore(s => s.statusGranular);
  const setStatusGranular = useGisStore(s => s.setStatusGranular);
  const [zoneLoadError, setZoneLoadError] = useState('');
  const [zoneReloadKey, setZoneReloadKey] = useState(0);
  const zoneRequestRef = useRef(0);
  const prevStepRef = useRef(stepWizard);

  // Auto-open sidebar when entering 'vias' step
  useEffect(() => {
    if (prevStepRef.current !== 'vias' && stepWizard === 'vias') setSidebarOpen(true);
    prevStepRef.current = stepWizard;
  }, [stepWizard, setSidebarOpen]);

  // Load initial data on mount
  useEffect(() => {
    if (initialized) return;
    if (!localStorage.getItem('gis-auth-token')) return;
    const controller = new AbortController();
    (async () => {
      try {
        const { getProjects } = await import('../../lib/api');
        const projects = await getProjects(controller.signal);
        setProjects(projects);
        if (projects.length && !activeProjectId) setActiveProject(projects[0].id);
        setInitialized(true);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        console.error('Failed to load initial data', err);
      }
    })();
    return () => controller.abort();
  }, [initialized, activeProjectId, setActiveProject, setInitialized, setProjects]);

  useEffect(() => {
    const requestedProject = activeProjectId;
    const requestedZone = useGisStore.getState().selectedZoneId;
    const requestId = ++zoneRequestRef.current;
    setZones([]);
    setSelectedZone(null);
    setZoneLoadError('');
    if (!requestedProject) {
      setStatusGranular('zones', 'idle');
      return;
    }
    const controller = new AbortController();
    setStatusGranular('zones', 'loading');
    (async () => {
      try {
        const { getZones } = await import('../../lib/api');
        const result = await getZones(requestedProject, controller.signal);
        if (controller.signal.aborted || requestId !== zoneRequestRef.current || useGisStore.getState().activeProjectId !== requestedProject) return;
        const zones = result.filter(zone => String(zone.project_id) === String(requestedProject));
        setZones(zones);
        if (requestedZone && zones.some(zone => zone.id === requestedZone)) setSelectedZone(requestedZone);
        setStatusGranular('zones', 'loaded');
      } catch (err) {
        if (controller.signal.aborted || requestId !== zoneRequestRef.current || (err as Error).name === 'AbortError') return;
        setZoneLoadError((err as Error).message || 'No se pudieron cargar las zonas');
        setStatusGranular('zones', 'error');
      }
    })();
    return () => controller.abort();
  }, [activeProjectId, zoneReloadKey, setSelectedZone, setStatusGranular, setZones]);

  // If no project selected, default to first
  useEffect(() => {
    if (initialized && !activeProjectId && projects.length > 0) {
      setActiveProject(projects[0].id);
    }
  }, [initialized, activeProjectId, projects]);

  const handleStepChange = useCallback((step: WizardStep) => {
    if (stepWizard === 'vias' && step !== 'vias' && !confirmPlanningLeave()) return;
    setStepWizard(step);
  }, [stepWizard, confirmPlanningLeave, setStepWizard]);

  const renderStep = () => {
    switch (stepWizard) {
      case 'proyecto': return <StepProyecto />;
      case 'zona': return <StepZona status={statusGranular.zones || 'idle'} error={zoneLoadError} onRetry={() => setZoneReloadKey(value => value + 1)} />;
      case 'vias': return <StepVias />;
      case 'luminarias': return <StepLuminarias />;
      case 'informe': return <StepInforme />;
      default: return <StepProyecto />;
    }
  };

  if (!initialized) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-salvi-cream">
        <div className="text-center text-salvi-muted">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-salvi-black border-t-transparent" />
          Cargando SALVI GIS...
        </div>
      </main>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-salvi-cream">
      <Header>
        <WizardNav currentStep={stepWizard} onStepChange={handleStepChange} />
      </Header>

      <div className="flex-1 relative flex overflow-hidden">
        {/* Map background */}
        <div className="absolute inset-0">
          <MapView />
          <MapControls mapId="gis-map" />
        </div>

        {/* Sidebar — collapsible */}
        {sidebarOpen && (
          <div className="relative z-10 flex gap-1.5 p-1.5 pointer-events-none max-w-sm">
            <div className="pointer-events-auto w-96 max-h-full overflow-hidden">
              {renderStep()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default WizardShell;
