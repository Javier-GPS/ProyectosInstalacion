import React, { Suspense, useEffect, useRef } from 'react';
import { useAuth } from './auth/AuthContext';
import { setAuthFetch } from './lib/api';
import { useHashRouter } from './hooks/useHashRouter';
import { useGisStore } from './store/useGisStore';
import type { WizardStep } from './store/types';

const WizardShell = React.lazy(() => import('./components/Wizard/WizardShell'));

function LoadingScreen() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-salvi-cream">
      <div className="text-center text-salvi-muted">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-salvi-black border-t-transparent" />
        Cargando SALVI GIS...
      </div>
    </main>
  );
}

function App() {
  const { user, loading, authFetch } = useAuth();
  const { params, setHashParams } = useHashRouter();
  const setActiveProject = useGisStore(s => s.setActiveProject);
  const setSelectedZone = useGisStore(s => s.setSelectedZone);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const confirmPlanningLeave = useGisStore(s => s.confirmPlanningLeave);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const stepWizard = useGisStore(s => s.stepWizard);
  const contextRef = useRef({ activeProjectId, selectedZoneId, stepWizard });

  // Expose authFetch to the API layer
  useEffect(() => {
    setAuthFetch(authFetch);
  }, [authFetch]);

  useEffect(() => {
    contextRef.current = { activeProjectId, selectedZoneId, stepWizard };
  }, [activeProjectId, selectedZoneId, stepWizard]);

  // Sync new hash events → store without treating ordinary store updates as hash navigation.
  useEffect(() => {
    const current = contextRef.current;
    const changesPlanningContext =
      (!!params.projectId && params.projectId !== current.activeProjectId)
      || (!!params.zoneId && params.zoneId !== current.selectedZoneId)
      || (!!params.step && params.step !== current.stepWizard);
    if (changesPlanningContext && !confirmPlanningLeave()) {
      setHashParams({
        projectId: current.activeProjectId || undefined,
        zoneId: current.selectedZoneId || undefined,
        step: current.stepWizard,
      });
      return;
    }
    if (params.projectId) setActiveProject(params.projectId);
    if (params.zoneId) setSelectedZone(params.zoneId);
    if (params.step) setStepWizard(params.step as WizardStep);
  }, [params.projectId, params.zoneId, params.step, confirmPlanningLeave, setHashParams, setActiveProject, setSelectedZone, setStepWizard]);

  if (loading) return <LoadingScreen />;
  if (!user) return <LoadingScreen />;

  return (
    <Suspense fallback={<LoadingScreen />}>
      <WizardShell />
    </Suspense>
  );
}

export default App;
