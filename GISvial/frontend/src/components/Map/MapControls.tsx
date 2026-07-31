import React, { useState } from 'react';
import { Cuboid } from 'lucide-react';
import { useGisStore } from '../../store/useGisStore';

interface MapControlsProps {
  mapId: string;
}

const MapControls: React.FC<MapControlsProps> = ({ mapId }) => {
  const [is3d, setIs3d] = useState(false);
  const mapInstance = useGisStore(s => s.mapInstance);
  const toggleBaseMapFn = useGisStore(s => s.toggleBaseMap);
  const toggle3dFn = useGisStore(s => s.toggle3dView);

  const handleZoomIn = () => mapInstance?.zoomIn({ duration: 300 });
  const handleZoomOut = () => mapInstance?.zoomOut({ duration: 300 });
  const toggleBaseMap = () => toggleBaseMapFn?.();
  const toggle3d = () => {
    const next = toggle3dFn?.();
    if (typeof next === 'boolean') setIs3d(next);
  };

  return (
    <div className="absolute top-3 right-3 z-20 flex flex-col gap-1">
      <button
        onClick={handleZoomIn}
        className="bg-white/90 backdrop-blur-sm border border-salvi-line rounded-t-md px-2.5 py-1 text-sm font-bold text-salvi-black hover:bg-salvi-surface transition-colors shadow-sm"
        title="Zoom in"
        aria-label="Zoom in"
      >
        +
      </button>
      <button
        onClick={handleZoomOut}
        className="bg-white/90 backdrop-blur-sm border border-salvi-line rounded-b-md px-2.5 py-1 text-sm font-bold text-salvi-black hover:bg-salvi-surface transition-colors shadow-sm"
        title="Zoom out"
        aria-label="Zoom out"
      >
        −
      </button>
      <button
        onClick={toggleBaseMap}
        className="bg-white/90 backdrop-blur-sm border border-salvi-line rounded-md px-2 py-1 text-xs text-salvi-grey hover:bg-salvi-surface transition-colors shadow-sm mt-1"
        title="Toggle base map"
        aria-label="Toggle base map"
      >
        🗺
      </button>
      <button
        onClick={toggle3d}
        className={`rounded-md border px-2 py-1 text-xs transition-colors shadow-sm ${is3d ? 'border-salvi-black bg-salvi-black text-white' : 'border-salvi-line bg-white/90 text-salvi-grey hover:bg-salvi-surface'} backdrop-blur-sm`}
        title={is3d ? 'Volver al mapa plano' : 'Ver mapa en 3D'}
        aria-label={is3d ? 'Volver al mapa plano' : 'Ver mapa en 3D'}
        aria-pressed={is3d}
      >
        <span className="inline-flex items-center gap-1"><Cuboid className="h-3.5 w-3.5" aria-hidden="true" />3D</span>
      </button>
    </div>
  );
};

export default MapControls;
