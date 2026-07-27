import React, { useEffect, useRef, useCallback, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import { useMapLayer } from '../../hooks/useMapLayer';
import type { GisPhotometricResult, GisPlanningInventoryTarget, GisPlanningPatch } from '../../types';
import { nearestInventoryHit, pointInsideBoundary } from '../../lib/roadSelection';
import SegmentContextPopup from './SegmentContextPopup';

const COMPONENT = 'MapView';

const MapView: React.FC<{ mapContainerId?: string }> = ({ mapContainerId = 'gis-map' }) => {
  const mapRef = useRef<any>(null);
  const initDone = useRef(false);
  const baseLayerRef = useRef<'osm' | 'satellite'>('osm');
  const [styleRevision, setStyleRevision] = useState(0);
  const [contextPopup, setContextPopup] = useState<{ x: number; y: number; target: GisPlanningInventoryTarget; roadType: string | null } | null>(null);
  const { addSource, addLayer, removeLayer, removeSource, removeAllLayer, prefixId } = useMapLayer(COMPONENT);

  const zones = useGisStore(s => s.zones);
  const planningInventory = useGisStore(s => s.activePlanningInventory);
  const planningPayload = useGisStore(s => s.planningPayload);
  const roadTypeVisibility = useGisStore(s => s.roadTypeVisibility);
  const roadSelectionByZone = useGisStore(s => s.roadSelectionByZone);
  const zoneLuminaires = useGisStore(s => s.zoneLuminaires);
  const zonePhotometric = useGisStore(s => s.zonePhotometric);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const selectedLumIds = useGisStore(s => s.selectedLumIds);
  const showCompliance = useGisStore(s => s.showCompliance);
  const toggleLumSelection = useGisStore(s => s.toggleLumSelection);
  const selectedTargetRef = useGisStore(s => s.selectedTargetRef);
  const selectedStreetName = useGisStore(s => s.selectedStreetName);
  const accumulatedSelection = useGisStore(s => s.accumulatedSelection);

  /* ── Init map ─────────────────────────────────────────────────────────── */
  useEffect(() => {
    if (initDone.current || !document.getElementById(mapContainerId)) return;
    initDone.current = true;

    const map = new maplibregl.Map({
      container: mapContainerId,
      style: {
        version: 8,
        sources: {
          'osm-base-source': {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            maxzoom: 19,
            attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>',
          },
        },
        layers: [{ id: 'osm-base', type: 'raster', source: 'osm-base-source' }],
      },
      center: [-3.7038, 40.4168],
      zoom: 6,
      pitch: 0,
      attributionControl: true,
    } as any);

    map.on('load', () => {
      setStyleRevision(value => value + 1);
      try {
        map.addSource('satellite', { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 19, attribution: 'Tiles © Esri' } as any);
        map.addSource('hillshade', { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade_Dark/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 13, attribution: 'Elevation © Esri' } as any);
        map.addSource('terrain-dem', { type: 'raster-dem', tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 14, encoding: 'terrarium' } as any);
        map.setTerrain({ source: 'terrain-dem', exaggeration: 2.0 });
        // Add satellite/hillshade layers hidden by default (below overlays since added before update* effects)
        map.addLayer({ id: 'satellite-layer', type: 'raster', source: 'satellite', layout: { visibility: 'none' } } as any);
        map.addLayer({ id: 'hillshade-layer', type: 'raster', source: 'hillshade', layout: { visibility: 'none' } } as any, 'satellite-layer');
      } catch (e) { /* terrain may fail silently */ }

      map.on('click', (e: any) => {
        const store = useGisStore.getState();
        const zoneId = store.selectedZoneId;
        const draft = zoneId ? store.roadSelectionByZone[zoneId] : undefined;

        if (zoneId && draft?.status === 'draw_area') {
          const zoneBoundary = store.zones.find(z => z.id === zoneId)?.geometry.boundary;
          const coord: [number, number] = [e.lngLat.lng, e.lngLat.lat];
          if (!zoneBoundary || !pointInsideBoundary(coord, zoneBoundary)) {
            store.setRoadSelection(zoneId, { ...draft, error: 'El área debe quedar dentro del límite real de la zona.' });
            return;
          }
          store.setRoadSelection(zoneId, { ...draft, area_points: [...draft.area_points, coord], error: undefined });
          return;
        }
        if (zoneId && draft && (draft.status === 'pick_a' || draft.status === 'pick_b')) {
          const inventory = store.activePlanningInventory;
          if (!inventory || !draft.boundary) { store.setRoadSelection(zoneId, { ...draft, status: 'invalid', error: 'Falta la red o el límite del ámbito.' }); return; }
          const zoneBoundary = store.zones.find(z => z.id === zoneId)?.geometry.boundary;
          if (!zoneBoundary) return;
          const targets = inventory.targets.filter(tgt => draft.allowed_group_refs?.includes(tgt.group_ref));
          const anchor = nearestInventoryHit(map, targets, e.point);
          if (!anchor || !pointInsideBoundary(anchor.coordinate, draft.boundary) || !pointInsideBoundary(anchor.coordinate, zoneBoundary)) {
            store.setRoadSelection(zoneId, { ...draft, error: 'Haz clic cerca de una vía permitida dentro del área.' });
            return;
          }
          if (draft.status === 'pick_a') {
            store.setRoadSelection(zoneId, { ...draft, status: 'pick_b', a: anchor, b: undefined, path: undefined, length_m: undefined, error: undefined });
            return;
          }
          store.setRoadSelection(zoneId, { ...draft, status: 'ready', b: anchor, error: undefined });
          return;
        }
        try {
          const hit = map.queryRenderedFeatures(e.point).find((f: any) => f.properties?.lumId);
          if (hit) toggleLumSelection(hit.properties.lumId);
          const store = useGisStore.getState();
          const inv = store.activePlanningInventory;
          if (inv && inv.zone_id === store.selectedZoneId) {
            const anchor = nearestInventoryHit(map, inv.targets.filter(t => t.geometry), e.point, 30);
            if (anchor) {
              store.setSelectedSegment(anchor.target_ref, inv.targets.find(t => t.target_ref === anchor.target_ref)?.name || null);
              store.toggleTargetSelection(inv.zone_id, anchor.target_ref);
            } else {
              store.setSelectedSegment(null, null);
            }
          }
        } catch (err) { console.error('MapView click error:', err); }
      });

      map.on('mousemove', (e: any) => {
        const state = useGisStore.getState();
        const draft = state.selectedZoneId ? state.roadSelectionByZone[state.selectedZoneId] : undefined;
        if (draft?.status === 'draw_area' || draft?.status === 'pick_a' || draft?.status === 'pick_b') {
          map.getCanvas().style.cursor = 'crosshair';
          return;
        }
        const feats = map.queryRenderedFeatures(e.point);
        map.getCanvas().style.cursor = feats?.length ? 'pointer' : '';
      });

      // Right-click → context popup with segment info & editing
      map.on('contextmenu', (e: any) => {
        e.originalEvent.preventDefault();
        const store = useGisStore.getState();
        const inv = store.activePlanningInventory;
        const zoneId = store.selectedZoneId;
        if (!inv || inv.zone_id !== zoneId) return;
        // Exclude if in draw/pick mode
        const draft = zoneId ? store.roadSelectionByZone[zoneId] : undefined;
        if (draft && (draft.status === 'draw_area' || draft.status === 'pick_a' || draft.status === 'pick_b')) return;

        const anchor = nearestInventoryHit(map, inv.targets.filter(t => t.geometry), e.point, 30);
        if (!anchor) return;
        const target = inv.targets.find(t => t.target_ref === anchor.target_ref);
        if (!target) return;
        const group = inv.groups.find(g => g.group_ref === target.group_ref);
        setContextPopup({ x: e.originalEvent.clientX, y: e.originalEvent.clientY, target, roadType: group?.road_type || null });
      });
    });

    // Expose for MapControls
    (window as any).__gisMap = map;
    (window as any).__focusGisLocation = (lat: number, lon: number, bbox?: number[]) => {
      const focus = () => {
        if (bbox?.length === 4 && bbox.every(Number.isFinite) && bbox[0] < bbox[1] && bbox[2] < bbox[3]) {
          map.fitBounds([[bbox[2], bbox[0]], [bbox[3], bbox[1]]], { padding: 60, maxZoom: 14, duration: 1000 });
        } else {
          map.flyTo({ center: [lon, lat], zoom: 14, pitch: 0, duration: 1000 });
        }
      };
      if (map.isStyleLoaded()) focus(); else map.once('load', focus);
    };
    (window as any).__toggleBaseMap = () => {
      if (!map.isStyleLoaded()) return;
      if (baseLayerRef.current === 'osm') {
        map.setLayoutProperty('osm-base', 'visibility', 'none');
        map.setLayoutProperty('satellite-layer', 'visibility', 'visible');
        map.setLayoutProperty('hillshade-layer', 'visibility', 'visible');
        baseLayerRef.current = 'satellite';
      } else {
        map.setLayoutProperty('osm-base', 'visibility', 'visible');
        map.setLayoutProperty('satellite-layer', 'visibility', 'none');
        map.setLayoutProperty('hillshade-layer', 'visibility', 'none');
        baseLayerRef.current = 'osm';
      }
    };

    mapRef.current = map;
    return () => {
      map.remove();
      initDone.current = false;
      delete (window as any).__gisMap;
      delete (window as any).__focusGisLocation;
      delete (window as any).__toggleBaseMap;
    };
  }, [mapContainerId]);

  /* ── Update layers (non-destructive, each group is independent) ──────── */
  const updateZoneBounds = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;

    const boundsFeats: any[] = [];
    zones.forEach(z => {
      const boundary = z.geometry?.boundary;
      if (boundary) {
        boundsFeats.push({
          type: 'Feature',
          properties: { color: z.color, selected: z.id === selectedZoneId },
          geometry: boundary,
        });
      }
    });

    // Zone fill
    removeLayer(map, 'bounds-fill');
    removeLayer(map, 'bounds-outline');
    removeSource(map, 'zone-bounds');

    if (boundsFeats.length) {
      addSource(map, { id: 'zone-bounds', type: 'geojson', data: { type: 'FeatureCollection', features: boundsFeats } });
      addLayer(map, { id: 'bounds-fill', type: 'fill', source: 'zone-bounds', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': ['case', ['get', 'selected'], 0.18, 0.05] } });
      addLayer(map, { id: 'bounds-outline', type: 'line', source: 'zone-bounds', paint: { 'line-color': ['get', 'color'], 'line-width': ['case', ['get', 'selected'], 4, 1.5], 'line-opacity': 0.8 } });
    }
  }, [zones, selectedZoneId, addSource, addLayer, removeLayer, removeSource]);

  const updateWays = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;

    zones.forEach(z => {
      const layerId = `ways-${z.id}`;
      removeLayer(map, layerId);
      removeSource(map, `ways-src-${z.id}`);
    });

    if (!planningInventory || planningInventory.zone_id !== selectedZoneId) return;
    const groups = new Map(planningInventory.groups.map(group => [group.group_ref, group]));
    const feats = planningInventory.targets.flatMap(target => {
      const group = groups.get(target.group_ref);
      if (!target.geometry || roadTypeVisibility[target.group_ref] === false) return [];
      return [{
        type: 'Feature' as const,
        properties: {
          wayId: target.target_ref,
          roadType: group?.road_type || '',
          zoneId: planningInventory.zone_id,
          color: group?.road_type ? ROAD_CFG[group.road_type]?.color || '#999' : '#999',
          name: target.name || '',
        },
        geometry: { type: 'LineString' as const, coordinates: target.geometry },
      }];
    });
    if (!feats.length) return;
    const layerId = `ways-${planningInventory.zone_id}`;
    addSource(map, { id: `ways-src-${planningInventory.zone_id}`, type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
    addLayer(map, {
      id: layerId, type: 'line', source: `ways-src-${planningInventory.zone_id}`,
      paint: { 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': 0.9 },
    });
  }, [zones, planningInventory, roadTypeVisibility, selectedZoneId, addSource, addLayer, removeLayer, removeSource]);

  const updateLuminaires = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;

    zones.forEach(z => {
      const lums = zoneLuminaires[z.id];
      const layerId = `lums-${z.id}`;
      removeLayer(map, layerId);
      removeSource(map, `lums-src-${z.id}`);

      if (!lums?.length) return;
      const feats = lums.map(l => ({
        type: 'Feature' as const,
        properties: { lumId: `${z.id}__${l.id}` },
        geometry: { type: 'Point' as const, coordinates: [l.lon, l.lat] },
      }));

      addSource(map, { id: `lums-src-${z.id}`, type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
      addLayer(map, {
        id: layerId, type: 'circle', source: `lums-src-${z.id}`,
        paint: { 'circle-radius': 5, 'circle-color': z.color, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff', 'circle-opacity': 0.9 },
      });
    });
  }, [zones, zoneLuminaires, addSource, addLayer, removeLayer, removeSource]);

  const updateRoadSelection = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    removeLayer(map, 'road-selection-points');
    removeLayer(map, 'road-selection-path');
    removeLayer(map, 'road-selection-target');
    removeLayer(map, 'road-selection-area-outline');
    removeLayer(map, 'road-selection-area-fill');
    removeSource(map, 'road-selection');

    const draft = selectedZoneId ? roadSelectionByZone[selectedZoneId] : undefined;
    if (!draft) return;
    const features: any[] = [];
    if (draft.boundary) features.push({ type: 'Feature', properties: { kind: 'area' }, geometry: draft.boundary });
    else if (draft.area_points.length >= 2) features.push({ type: 'Feature', properties: { kind: 'area-line' }, geometry: { type: 'LineString', coordinates: draft.area_points } });
    const selectedTargetRefs = new Set([draft.a?.target_ref, draft.b?.target_ref].filter(Boolean));
    planningInventory?.targets.forEach(target => {
      if (target.geometry && selectedTargetRefs.has(target.target_ref)) features.push({ type: 'Feature', properties: { kind: 'target' }, geometry: { type: 'LineString', coordinates: target.geometry } });
    });
    if (draft.path?.length && draft.status === 'complete') features.push({ type: 'Feature', properties: { kind: 'path' }, geometry: { type: 'LineString', coordinates: draft.path } });
    if (draft.a) features.push({ type: 'Feature', properties: { kind: 'a' }, geometry: { type: 'Point', coordinates: draft.a.coordinate } });
    if (draft.b) features.push({ type: 'Feature', properties: { kind: 'b' }, geometry: { type: 'Point', coordinates: draft.b.coordinate } });
    if (!features.length) return;
    addSource(map, { id: 'road-selection', type: 'geojson', data: { type: 'FeatureCollection', features } });
    addLayer(map, { id: 'road-selection-area-fill', type: 'fill', source: 'road-selection', filter: ['==', ['get', 'kind'], 'area'], paint: { 'fill-color': '#2563EB', 'fill-opacity': 0.12 } });
    addLayer(map, { id: 'road-selection-area-outline', type: 'line', source: 'road-selection', filter: ['in', ['get', 'kind'], ['literal', ['area', 'area-line']]], paint: { 'line-color': '#2563EB', 'line-width': 3, 'line-dasharray': [2, 1] } });
    addLayer(map, { id: 'road-selection-target', type: 'line', source: 'road-selection', filter: ['==', ['get', 'kind'], 'target'], paint: { 'line-color': '#F59E0B', 'line-width': 8, 'line-opacity': 0.75 } });
    addLayer(map, { id: 'road-selection-path', type: 'line', source: 'road-selection', filter: ['==', ['get', 'kind'], 'path'], paint: { 'line-color': '#2563EB', 'line-width': 8, 'line-opacity': 0.95 } });
    addLayer(map, {
      id: 'road-selection-points', type: 'circle', source: 'road-selection', filter: ['in', ['get', 'kind'], ['literal', ['a', 'b']]],
      paint: { 'circle-radius': 7, 'circle-color': ['case', ['==', ['get', 'kind'], 'a'], '#16A34A', '#DC2626'], 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' },
    });
  }, [selectedZoneId, roadSelectionByZone, planningInventory, addSource, addLayer, removeLayer, removeSource]);

  const updateCompliance = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;

    zones.forEach(z => {
      const pr = zonePhotometric[z.id];
      const layerId = `compl-${z.id}`;
      removeLayer(map, layerId);
      removeSource(map, `compl-src-${z.id}`);

      if (!pr?.length || !planningInventory?.targets.length || planningInventory.zone_id !== z.id) return;
      const groups = new Map(planningInventory.groups.map(group => [group.group_ref, group]));
      const effective = (groupRef: string, targetRef: string): GisPlanningPatch => ({
        ...(() => {
          const group = planningPayload.group_defaults[groupRef] || {};
          const target = planningPayload.target_overrides[targetRef] || {};
          const targetHasLux = Object.prototype.hasOwnProperty.call(target, 'luxParams');
          return {
            ...group,
            ...target,
            luxParams: targetHasLux
              ? target.luxParams == null ? target.luxParams : { ...(group.luxParams || {}), ...target.luxParams }
              : group.luxParams,
          };
        })(),
      });
      const feats = planningInventory.targets.flatMap(target => {
        const group = groups.get(target.group_ref);
        const roadType = group?.road_type;
        const params = effective(target.group_ref, target.target_ref);
        if (!target.geometry || !roadType || params.spacing == null || params.lighting_class == null) return [];
        const match = pr.find((r: GisPhotometricResult) =>
          Math.abs(r.road_width - (ROAD_CFG[roadType]?.width || 0)) < 1.5 &&
          Math.abs(r.spacing - params.spacing!) < 5 &&
          r.lighting_class === params.lighting_class
        );
        return [{
          type: 'Feature' as const,
          properties: { cumple: match?.cumple || '' },
          geometry: { type: 'LineString' as const, coordinates: target.geometry },
        }];
      });

      if (feats.length) {
        addSource(map, { id: `compl-src-${z.id}`, type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
        addLayer(map, {
          id: layerId, type: 'line', source: `compl-src-${z.id}`,
          layout: { visibility: showCompliance ? 'visible' : 'none' },
          paint: {
            'line-color': ['case', ['==', ['get', 'cumple'], ''], '#A09A91', ['in', ['downcase', ['get', 'cumple']], ['literal', ['no', 'fail', 'false', '0']]], '#B42318', '#1F7A4D'],
            'line-width': 5, 'line-opacity': 0.7,
          },
        });
      }
    });
  }, [zones, planningInventory, planningPayload, zonePhotometric, showCompliance, addSource, addLayer, removeLayer, removeSource]);

  const updateSelection = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;

    removeLayer(map, 'sel-lums');
    removeSource(map, 'sel-lums-src');

    if (selectedLumIds.size === 0) return;
    const feats: any[] = [];
    selectedLumIds.forEach(key => {
      const [zId, lumIdStr] = key.split('__');
      const lum = zoneLuminaires[zId]?.find(l => l.id === parseInt(lumIdStr));
      if (lum) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [lum.lon, lum.lat] } });
    });

    if (feats.length) {
      addSource(map, { id: 'sel-lums-src', type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
      addLayer(map, { id: 'sel-lums', type: 'circle', source: 'sel-lums-src', paint: { 'circle-radius': 7, 'circle-color': '#FFD700', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff', 'circle-opacity': 0.9 } });
    }
  }, [selectedLumIds, zoneLuminaires, addSource, addLayer, removeLayer, removeSource]);

  const updateHighlight = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    removeLayer(map, 'highlight-street');
    removeLayer(map, 'highlight-segment');
    removeSource(map, 'highlight');

    const features: any[] = [];
    if (selectedTargetRef && planningInventory?.zone_id === selectedZoneId) {
      const target = planningInventory.targets.find(t => t.target_ref === selectedTargetRef);
      if (target?.geometry) features.push({ type: 'Feature', properties: { kind: 'segment' }, geometry: { type: 'LineString', coordinates: target.geometry } });
      if (selectedStreetName) {
        planningInventory.targets.forEach(t => {
          if ((t.name || '') !== selectedStreetName || t.target_ref === selectedTargetRef || !t.geometry) return;
          features.push({ type: 'Feature', properties: { kind: 'street' }, geometry: { type: 'LineString', coordinates: t.geometry } });
        });
      }
    }
    if (!features.length) return;

    addSource(map, { id: 'highlight', type: 'geojson', data: { type: 'FeatureCollection', features } });
    addLayer(map, { id: 'highlight-street', type: 'line', source: 'highlight', filter: ['==', ['get', 'kind'], 'street'], paint: { 'line-color': '#F59E0B', 'line-width': 5, 'line-opacity': 0.35 } });
    addLayer(map, { id: 'highlight-segment', type: 'line', source: 'highlight', filter: ['==', ['get', 'kind'], 'segment'], paint: { 'line-color': '#DC2626', 'line-width': 8, 'line-opacity': 0.85 } });
  }, [selectedTargetRef, selectedStreetName, selectedZoneId, planningInventory, addSource, addLayer, removeLayer, removeSource]);

  const updateAccumulatedSelection = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    removeLayer(map, 'accum-selection');
    removeSource(map, 'accum-selection-src');

    const zoneSel = selectedZoneId ? (accumulatedSelection[selectedZoneId] || {}) : {};
    const selRefs = new Set(Object.keys(zoneSel));
    if (!selRefs.size || !planningInventory || planningInventory.zone_id !== selectedZoneId) return;

    const feats: any[] = [];
    planningInventory.targets.forEach(target => {
      if (target.geometry && selRefs.has(target.target_ref)) {
        feats.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: target.geometry } });
      }
    });
    if (!feats.length) return;

    addSource(map, { id: 'accum-selection-src', type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
    addLayer(map, {
      id: 'accum-selection', type: 'line', source: 'accum-selection-src',
      paint: { 'line-color': '#22C55E', 'line-width': 9, 'line-opacity': 0.7 },
      beforeId: undefined,
    });
  }, [selectedZoneId, accumulatedSelection, planningInventory, addSource, addLayer, removeLayer, removeSource]);

  // Trigger layer updates reactively
  useEffect(() => { updateZoneBounds(); }, [updateZoneBounds, styleRevision]);
  useEffect(() => { updateWays(); }, [updateWays, styleRevision]);
  useEffect(() => { updateLuminaires(); }, [updateLuminaires, styleRevision]);
  useEffect(() => { updateRoadSelection(); }, [updateRoadSelection, styleRevision]);
  useEffect(() => { updateCompliance(); }, [updateCompliance, styleRevision]);
  useEffect(() => { updateSelection(); }, [updateSelection, styleRevision]);
  useEffect(() => { updateHighlight(); }, [updateHighlight, styleRevision]);
  useEffect(() => { updateAccumulatedSelection(); }, [updateAccumulatedSelection, styleRevision]);

  /* ── Fly to selected zone ─────────────────────────────────────────────── */
  useEffect(() => {
    if (!selectedZoneId) return;
    const zone = zones.find(z => z.id === selectedZoneId);
    if (!zone) return;
    const map = mapRef.current;
    if (!map) return;
    const focus = () => {
      const bbox = zone.geometry?.bbox;
      if (bbox) map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 60, maxZoom: 16, duration: 1000 });
      else if (zone.center_lon != null && zone.center_lat != null) map.flyTo({ center: [zone.center_lon, zone.center_lat], zoom: zone.zoom || 14, duration: 1000 });
    };
    focus();
  }, [selectedZoneId, zones]);

  return (
    <>
      <div id={mapContainerId} className="absolute inset-0 w-full h-full" style={{ background: '#0d1520' }} />
      {contextPopup && (
        <SegmentContextPopup
          x={contextPopup.x}
          y={contextPopup.y}
          target={contextPopup.target}
          roadType={contextPopup.roadType}
          onClose={() => setContextPopup(null)}
        />
      )}
    </>
  );
};

export default MapView;
