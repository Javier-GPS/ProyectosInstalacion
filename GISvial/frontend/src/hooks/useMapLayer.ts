import { useCallback, useRef } from 'react';
import type maplibregl from 'maplibre-gl';

export interface LayerDef {
  id: string;
  type: 'fill' | 'line' | 'circle' | 'symbol' | 'raster';
  source: string;
  paint?: Record<string, unknown>;
  layout?: Record<string, unknown>;
  filter?: unknown[];
  beforeId?: string;
}

export interface SourceDef {
  id: string;
  type: 'geojson' | 'raster' | 'vector';
  data?: GeoJSON.FeatureCollection | GeoJSON.Feature;
  tiles?: string[];
  tileSize?: number;
  maxzoom?: number;
  attribution?: string;
}

interface RegisteredLayer {
  component: string;
  layerId: string;
}

/** Hook that manages map layers with component-prefixed IDs to prevent collisions. */
export function useMapLayer(componentName: string) {
  const registeredLayers = useRef<RegisteredLayer[]>([]);

  const prefixId = useCallback((name: string) => `${componentName}::${name}`, [componentName]);

  const addSource = useCallback((map: maplibregl.Map, def: SourceDef) => {
    const srcId = prefixId(def.id);
    if (map.getSource(srcId)) return;
    try {
      const { id: _id, ...source } = def;
      map.addSource(srcId, source as any);
    } catch (e) {
      console.warn(`[useMapLayer] Failed to add source ${srcId}:`, e);
    }
  }, [prefixId]);

  const addLayer = useCallback((map: maplibregl.Map, def: LayerDef) => {
    const layerId = prefixId(def.id);
    const srcId = prefixId(def.source);

    // Check collision: warn if same component registers same layer twice
    const existing = registeredLayers.current.find(l => l.layerId === layerId);
    if (existing) {
      console.warn(`[useMapLayer] Layer ${layerId} already registered by ${existing.component}, skipping`);
      return;
    }

    if (map.getLayer(layerId)) {
      console.warn(`[useMapLayer] Layer ${layerId} already exists on map, skipping`);
      return;
    }

    try {
      const { id: _id, source: _source, beforeId, ...layer } = def;
      map.addLayer({ ...layer, id: layerId, source: srcId } as any, beforeId);
      registeredLayers.current.push({ component: componentName, layerId });
    } catch (e) {
      console.warn(`[useMapLayer] Failed to add layer ${layerId}:`, e);
    }
  }, [prefixId, componentName]);

  const removeLayer = useCallback((map: maplibregl.Map, name: string) => {
    const layerId = prefixId(name);
    try {
      if (map.getLayer(layerId)) map.removeLayer(layerId);
      registeredLayers.current = registeredLayers.current.filter(l => l.layerId !== layerId);
    } catch {}
  }, [prefixId]);

  const removeSource = useCallback((map: maplibregl.Map, name: string) => {
    const srcId = prefixId(name);
    try {
      if (map.getSource(srcId)) map.removeSource(srcId);
    } catch {}
  }, [prefixId]);

  const removeAllLayer = useCallback((map: maplibregl.Map) => {
    [...registeredLayers.current].reverse().forEach(l => {
      try { map.removeLayer(l.layerId); } catch {}
    });
    registeredLayers.current = [];
  }, []);

  return { addSource, addLayer, removeLayer, removeSource, removeAllLayer, prefixId };
}
