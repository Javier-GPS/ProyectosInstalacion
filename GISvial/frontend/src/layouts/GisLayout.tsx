import React from 'react';
import Header from '../components/Header';
import MapView from '../components/Map/MapView';
import ZoneList from '../components/Zones/ZoneList';
import PlanningPanel from '../components/Planning/PlanningPanel';
import DetailPanel from '../components/Detail/DetailPanel';
import { useGisStore } from '../store/useGisStore';

const GisLayout: React.FC = () => {
  const appMode = useGisStore(s => s.appMode);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-salvi-cream">
      <Header />
      <div className="flex-1 relative flex overflow-hidden">
        <div className="absolute inset-0">
          <MapView />
        </div>

        {appMode === 'planning' && (
          <div className="relative z-10 flex gap-2 p-2 pointer-events-none">
            <div className="w-72 pointer-events-auto flex flex-col gap-2 max-h-full overflow-hidden">
              <ZoneList />
            </div>
            {selectedZoneId && (
              <div className="w-80 pointer-events-auto max-h-full overflow-hidden">
                <PlanningPanel />
              </div>
            )}
          </div>
        )}

        {appMode === 'detail' && (
          <div className="relative z-10 flex gap-2 p-2 pointer-events-none w-full">
            <div className="w-72 pointer-events-auto max-h-full overflow-hidden">
              <DetailPanel side="left" />
            </div>
            <div className="flex-1" />
            <div className="w-80 pointer-events-auto max-h-full overflow-hidden">
              <DetailPanel side="right" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default GisLayout;
