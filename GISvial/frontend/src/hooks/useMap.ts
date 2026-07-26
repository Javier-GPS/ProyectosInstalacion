import { useCallback, useRef, useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

export function useMap(containerId: string) {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const initializedRef = useRef(false);

  const initMap = useCallback(() => {
    if (initializedRef.current || !document.getElementById(containerId)) return;
    initializedRef.current = true;

    const map = new maplibregl.Map({
      container: containerId,
      style: 'https://tiles.openfreemap.org/styles/liberty',
      center: [-3.7038, 40.4168], // Madrid default
      zoom: 6,
      pitch: 50,
      attributionControl: false,
    } as any);

    map.on('load', () => {
      // Satelite source
      map.addSource('satellite' as any, {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© Esri',
      } as any);

      // Hillshade
      map.addSource('hillshade' as any, {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade_Dark/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 13,
        attribution: '© Esri',
      } as any);

      // DEM for 3D terrain
      map.addSource('terrain-dem' as any, {
        type: 'raster-dem',
        tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
        tileSize: 256,
        maxzoom: 14,
        encoding: 'terrarium',
        attribution: '© Mapzen/AWS',
      } as any);

      (map as any).setTerrain({ source: 'terrain-dem', exaggeration: 2.0 });
    });

    map.on('style.load', () => {
      // Re-apply terrain after style changes
      const src = map.getSource('terrain-dem' as any);
      if (src) (map as any).setTerrain({ source: 'terrain-dem', exaggeration: 2.0 });
    });

    mapRef.current = map;
  }, [containerId]);

  const switchBaseMap = useCallback((layer: 'osm' | 'satellite') => {
    const map = mapRef.current;
    if (!map) return;
    const style = map.getStyle();
    const visOsm = style?.layers?.filter(l => l.id.startsWith('openfreemap')).map(l => l.id) || [];

    if (layer === 'satellite') {
      visOsm.forEach(id => map.setLayoutProperty(id, 'visibility', 'none'));
      if (!map.getLayer('satellite-layer' as any)) {
        map.addLayer({ id: 'satellite-layer', type: 'raster', source: 'satellite', layout: { visibility: 'visible' } } as any);
        map.addLayer({ id: 'hillshade-layer', type: 'raster', source: 'hillshade', layout: { visibility: 'visible' } } as any, 'satellite-layer' as any);
      }
    } else {
      visOsm.forEach(id => map.setLayoutProperty(id, 'visibility', 'visible'));
      if (map.getLayer('satellite-layer' as any)) map.removeLayer('satellite-layer' as any);
      if (map.getLayer('hillshade-layer' as any)) map.removeLayer('hillshade-layer' as any);
    }
  }, []);

  useEffect(() => {
    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
      initializedRef.current = false;
    };
  }, []);

  return { mapRef, initMap, switchBaseMap };
}
