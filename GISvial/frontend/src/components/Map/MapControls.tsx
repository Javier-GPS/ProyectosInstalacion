import React from 'react';

interface MapControlsProps {
  mapId: string;
}

const MapControls: React.FC<MapControlsProps> = ({ mapId }) => {
  // Access the map instance via the existing useMap hook
  // We'll use a simpler inline approach since we can't pass mapRef easily
  const handleZoomIn = () => {
    const map = (window as any).__gisMap;
    if (map) map.zoomIn({ duration: 300 });
  };

  const handleZoomOut = () => {
    const map = (window as any).__gisMap;
    if (map) map.zoomOut({ duration: 300 });
  };

  // Base map toggle: expose on window from MapView
  const toggleBaseMap = () => {
    const fn = (window as any).__toggleBaseMap;
    if (fn) fn();
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
    </div>
  );
};

export default MapControls;
