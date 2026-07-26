import React, { useEffect, useCallback } from 'react';
import MapView from '../components/Map/MapView';
import Header from '../components/Header';
import { useGisStore } from '../store/useGisStore';
import { getZones, getProjects, getZoneOsm, getZoneConfig, getLuminaires, getPhotometric } from '../lib/api';
import ZoneList from '../components/Zones/ZoneList';
import PlanningPanel from '../components/Planning/PlanningPanel';
import DetailPanel from '../components/Detail/DetailPanel';

const GisMapPage: React.FC = () => {
  const appMode = useGisStore(s => s.appMode);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const setZones = useGisStore(s => s.setZones);
  const setProjects = useGisStore(s => s.setProjects);
  const setActiveProject = useGisStore(s => s.setActiveProject);
  const setZoneOsm = useGisStore(s => s.setZoneOsm);
  const setZoneConfig = useGisStore(s => s.setZoneConfig);
  const setZoneLuminaires = useGisStore(s => s.setZoneLuminaires);
  const setZonePhotometric = useGisStore(s => s.setZonePhotometric);
  const setInitialized = useGisStore(s => s.setInitialized);

  /* ── Load initial data ────────────────────────────────────────────────── */
  useEffect(() => {
    (async () => {
      try {
        const [projects, zones] = await Promise.all([getProjects(), getZones()]);
        setProjects(projects);
        setZones(zones);
        if (projects.length && !activeProjectId) setActiveProject(projects[0].id);
        setInitialized(true);
      } catch (err) {
        console.error('Failed to load initial data', err);
      }
    })();
  }, []);

  /* ── Load zone details when selected ──────────────────────────────────── */
  useEffect(() => {
    if (!selectedZoneId) return;
    (async () => {
      try {
        const [osm, config, luminaires, photometric] = await Promise.all([
          getZoneOsm(selectedZoneId).catch(() => null),
          getZoneConfig(selectedZoneId).catch(() => null),
          getLuminaires(selectedZoneId).catch(() => null),
          getPhotometric(selectedZoneId).catch(() => null),
        ]);
        if (osm) setZoneOsm(selectedZoneId, osm);
        if (config) setZoneConfig(selectedZoneId, config);
        if (luminaires) setZoneLuminaires(selectedZoneId, luminaires);
        if (photometric) setZonePhotometric(selectedZoneId, photometric);
      } catch (err) {
        console.error('Failed to load zone details', err);
      }
    })();
  }, [selectedZoneId]);

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-salvi-cream">
      <Header />

      <div className="flex-1 relative flex overflow-hidden">
        {/* Map (full area, behind panels) */}
        <div className="absolute inset-0">
          <MapView />
        </div>

        {/* Planning sidebar */}
        {appMode === 'planning' && (
          <div className="relative z-10 flex gap-2 p-2 pointer-events-none">
            <div className="w-72 pointer-events-auto flex flex-col gap-2">
              <ZoneList />
            </div>
            {selectedZoneId && (
              <div className="w-80 pointer-events-auto">
                <PlanningPanel />
              </div>
            )}
          </div>
        )}

        {/* Detail panels */}
        {appMode === 'detail' && (
          <div className="relative z-10 flex gap-2 p-2 pointer-events-none w-full">
            <div className="w-72 pointer-events-auto">
              <DetailPanel side="left" />
            </div>
            <div className="flex-1" />
            <div className="w-80 pointer-events-auto">
              <DetailPanel side="right" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default GisMapPage;
