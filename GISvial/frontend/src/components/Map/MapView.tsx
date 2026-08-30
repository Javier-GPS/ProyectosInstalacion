import React, { useEffect, useRef, useCallback, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import { useI18n } from '../../i18n';
import { useMapLayer } from '../../hooks/useMapLayer';
import type { GisPhotometricResult, GisPlanningInventoryTarget, GisPlanningPatch } from '../../types';
import { nearestInventoryHit, pointInsideBoundary, polygonFromPoints, targetsInsidePolygon } from '../../lib/roadSelection';
import { targetName, targetRef, targetDisplayLabel } from '../../lib/roadNaming';
import SegmentContextPopup from './SegmentContextPopup';
import SegmentGeometryInfo from './SegmentGeometryInfo';

const COMPONENT = 'MapView';

const midPoint = (geom: [number, number][]): [number, number] => {
  if (!geom.length) return [0, 0];
  if (geom.length === 1) return geom[0];
  const i = Math.floor((geom.length - 1) / 2);
  const a = geom[i];
  const b = geom[i + 1] ?? a;
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
};

const MapView: React.FC<{ mapContainerId?: string }> = ({ mapContainerId = 'gis-map' }) => {
  const { t } = useI18n();
  const mapRef = useRef<any>(null);
  const initDone = useRef(false);
  const baseLayerRef = useRef<'osm' | 'satellite'>('osm');
  const [styleRevision, setStyleRevision] = useState(0);
  const [contextPopup, setContextPopup] = useState<{ x: number; y: number; target: GisPlanningInventoryTarget; roadType: string | null } | null>(null);
  const [hover, setHover] = useState<{ x: number; y: number; target: GisPlanningInventoryTarget; roadType: string | null } | null>(null);
  const contextOpenRef = useRef(false);
  const lastHoverRef = useRef(0);
  const hoverRef = useRef<string | null>(null);
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
        map.addSource('blink-flash', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
        map.addLayer({ id: 'blink-flash-layer', type: 'line', source: 'blink-flash', paint: { 'line-color': '#FF00C8', 'line-width': 12, 'line-opacity': 0.0, 'line-blur': 6 } } as any);
        map.addSource('blink-flash-ring', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
        map.addLayer({ id: 'blink-flash-ring-layer', type: 'circle', source: 'blink-flash-ring', paint: { 'circle-radius': 8, 'circle-color': '#FF00C8', 'circle-opacity': 0.0, 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } } as any);
        map.addSource('tramo-hover', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
        map.addLayer({ id: 'tramo-hover-layer', type: 'line', source: 'tramo-hover', paint: { 'line-color': '#00E5FF', 'line-width': 11, 'line-opacity': 0.9, 'line-blur': 3 } } as any);
        map.addSource('tramo-hover-ring', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
        map.addLayer({ id: 'tramo-hover-ring-layer', type: 'circle', source: 'tramo-hover-ring', paint: { 'circle-radius': 10, 'circle-color': '#00E5FF', 'circle-opacity': 0.0, 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } } as any);
      } catch (e) { /* terrain may fail silently */ }

      map.on('click', (e: any) => {
        const store = useGisStore.getState();
        const zoneId = store.selectedZoneId;
        const draft = zoneId ? store.roadSelectionByZone[zoneId] : undefined;

        // ── Area drawing ───────────────────────────────────────────────────
        if (zoneId && draft?.status === 'draw_area') {
          const zoneBoundary = store.zones.find(z => z.id === zoneId)?.geometry.boundary;
          const coord: [number, number] = [e.lngLat.lng, e.lngLat.lat];
          // Click near the FIRST vertex → close.
          const first = draft.area_points[0];
          if (first && draft.area_points.length >= 3) {
            const projected = map.project(first);
            const dist = Math.hypot(projected.x - e.point.x, projected.y - e.point.y);
            if (dist <= 14) {
              closeAreaSelection(store, zoneId, draft);
              return;
            }
          }
          if (!zoneBoundary || !pointInsideBoundary(coord, zoneBoundary)) {
            store.setRoadSelection(zoneId, { ...draft, error: 'El área debe quedar dentro del límite real de la zona.' });
            return;
          }
          store.setRoadSelection(zoneId, { ...draft, area_points: [...draft.area_points, coord], error: undefined });
          return;
        }
        // ── Double click anywhere → close ──────────────────────────────────
        if (zoneId && draft?.status === 'draw_area') {
          closeAreaSelection(store, zoneId, draft);
        }
        try {
          const hit = map.queryRenderedFeatures(e.point).find((f: any) => f.properties?.lumId);
          if (hit) toggleLumSelection(hit.properties.lumId);
          const store = useGisStore.getState();
          const inv = store.activePlanningInventory;
          console.log('[MapView click] inv:', inv?.zone_id, 'selectedZone:', store.selectedZoneId, 'targets with geometry:', inv?.targets.filter(t => t.geometry).length);
          if (inv && inv.zone_id === store.selectedZoneId) {
            const targetsWithGeometry = inv.targets.filter(t => t.geometry);
            console.log('[MapView click] calling nearestInventoryHit with', targetsWithGeometry.length, 'targets, point:', e.point);
            const anchor = nearestInventoryHit(map, targetsWithGeometry, e.point, 30);
            console.log('[MapView click] anchor:', anchor);
            if (anchor) {
              // Click sobre tramo ya seleccionado → deselección limpia (sin highlight rojo).
              store.toggleTargetSelection(inv.zone_id, anchor.target_ref);
              store.setSelectedSegment(null, null);
            } else {
              store.setSelectedSegment(null, null);
            }
          }
        } catch (err) { console.error('MapView click error:', err); }
      });

      // Double-click closes the area (ring from last to first vertex).
      map.on('dblclick', (e: any) => {
        void e;
        const store = useGisStore.getState();
        const zoneId = store.selectedZoneId;
        const draft = zoneId ? store.roadSelectionByZone[zoneId] : undefined;
        if (!zoneId || draft?.status !== 'draw_area' || draft.area_points.length < 3) return;
        closeAreaSelection(store, zoneId, draft);
      });

      // Close the drawn area: build the polygon, auto-select streets inside it.
      const closeAreaSelection = (store: ReturnType<typeof useGisStore.getState>, zoneId: string, draft: NonNullable<ReturnType<typeof useGisStore.getState>['roadSelectionByZone'][string]>) => {
        if (draft.area_points.length < 3) return;
        const inventory = store.activePlanningInventory;
        const boundary = polygonFromPoints(draft.area_points);
        const insideRefs = inventory ? targetsInsidePolygon(inventory.targets, boundary) : [];
        store.setRoadSelection(zoneId, {
          ...draft,
          boundary,
          status: 'complete',
          lassoTargetRefs: insideRefs,
          a: undefined,
          b: undefined,
          path: undefined,
          length_m: undefined,
          member_count: undefined,
          error: undefined,
        });
        // Merge (add) the tramos inside the lazo — never replace a pre-existing selection.
        const existing = store.accumulatedSelection[zoneId] || {};
        const merged = { ...existing };
        for (const ref of insideRefs) merged[ref] = true;
        store.setAccumulatedSelection(zoneId, Object.keys(merged));
        console.log(`[MapView] Área cerrada: ${insideRefs.length} tramos dentro.`);
      };

      map.on('mousemove', (e: any) => {
        const state = useGisStore.getState();
        const draft = state.selectedZoneId ? state.roadSelectionByZone[state.selectedZoneId] : undefined;
        if (draft?.status === 'draw_area') {
          map.getCanvas().style.cursor = 'crosshair';
          if (hoverRef.current) { hoverRef.current = null; setHover(null); }
          updateAreaCursor(draft.area_points, [e.lngLat.lng, e.lngLat.lat]);
          return;
        }
        if (draft?.status === 'pick_a' || draft?.status === 'pick_b') {
          map.getCanvas().style.cursor = 'crosshair';
          if (hoverRef.current) { hoverRef.current = null; setHover(null); }
          return;
        }
        if (contextOpenRef.current) {
          map.getCanvas().style.cursor = 'pointer';
          return;
        }
        const inv = state.activePlanningInventory;
        if (!inv || inv.zone_id !== state.selectedZoneId) { setHover(null); hoverRef.current = null; return; }
        const now = performance.now();
        if (now - lastHoverRef.current < 55) return;  // throttle lookups
        lastHoverRef.current = now;

        let target: GisPlanningInventoryTarget | undefined;
        try {
          const feats = map.queryRenderedFeatures(e.point, { layers: [prefixId(`ways-${inv.zone_id}`)] });
          const hit = feats.find((f: any) => f.properties && f.properties.wayId);
          if (hit) {
            target = inv.targets.find(t => t.target_ref === hit.properties.wayId);
          }
        } catch (err) { console.warn('[MapView hover] queryRenderedFeatures:', err); }
        if (!target) {
          try {
            const anchor = nearestInventoryHit(map, inv.targets.filter(t => t.geometry), e.point, 15);
            if (anchor && anchor.target_ref) {
              target = inv.targets.find(t => t.target_ref === anchor.target_ref);
            }
          } catch (err) { console.warn('[MapView hover] nearestInventoryHit:', err); }
        }
        if (!target) {
          if (hoverRef.current) { hoverRef.current = null; setHover(null); }
          map.getCanvas().style.cursor = '';
          return;
        }
        const group = inv.groups.find(g => g.group_ref === target!.group_ref);
        map.getCanvas().style.cursor = 'pointer';
        hoverRef.current = target!.target_ref;
        setHover({ x: e.originalEvent.clientX, y: e.originalEvent.clientY, target: target!, roadType: group?.road_type || null });
      });

      // Live preview of the last area segment: vertices + cursor (no React state).
      const updateAreaCursor = (points: [number, number][], cursor: [number, number]) => {
      const source = map.getSource(prefixId('area-cursor')) as any;
      const line = points.length ? [...points, cursor] : [cursor];
      const data = {
        type: 'FeatureCollection' as const,
        features: [
          { type: 'Feature' as const, properties: { kind: 'area-line' }, geometry: { type: 'LineString' as const, coordinates: line } },
          ...(points.length ? [{ type: 'Feature' as const, properties: { kind: 'area-verts' }, geometry: { type: 'MultiPoint' as const, coordinates: points } }] : []),
          { type: 'Feature' as const, properties: { kind: 'cursor' }, geometry: { type: 'Point' as const, coordinates: cursor } },
        ],
      };
      if (source) source.setData(data);
      };

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
        contextOpenRef.current = true;
        setHover(null);
        hoverRef.current = null;
        setContextPopup({ x: e.originalEvent.clientX, y: e.originalEvent.clientY, target, roadType: group?.road_type || null });
      });
    });

    // Expose for MapControls (store-backed)
    (window as any).__gisMap = map;
    const store = useGisStore.getState();
    store.setMapInstance(map);
    const toggleBaseMap = () => {
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
    const toggle3d = () => {
      if (!map.isStyleLoaded() || typeof map.setTerrain !== 'function') return false;
      const next = map.getPitch() === 0;
      map.easeTo({ pitch: next ? 60 : 0, duration: 300 });
      map.setTerrain(next ? { source: 'terrain-dem', exaggeration: 2.0 } : null);
      return next;
    };
    const focusLocation = (lat: number, lon: number, bbox?: number[]) => {
      const focus = () => {
        if (bbox?.length === 4 && bbox.every(Number.isFinite) && bbox[0] < bbox[1] && bbox[2] < bbox[3]) {
          map.fitBounds([[bbox[2], bbox[0]], [bbox[3], bbox[1]]], { padding: 60, maxZoom: 14, duration: 1000 });
        } else {
          map.flyTo({ center: [lon, lat], zoom: 14, pitch: 0, duration: 1000 });
        }
      };
      if (map.isStyleLoaded()) focus(); else map.once('load', focus);
    };
    store.setToggleBaseMap(toggleBaseMap);
    store.setToggle3dView(toggle3d);
    store.setFocusLocation(focusLocation);
    (window as any).__focusGisLocation = focusLocation;
    (window as any).__toggleBaseMap = toggleBaseMap;

    // Flash + focus a single target so the user knows exactly which tramo it is.
    let blinkToken = 0;
    const blinkTarget = (targetRef: string) => {
      if (!map.isStyleLoaded()) return;
      const state = useGisStore.getState();
      const inv = state.activePlanningInventory;
      const target = inv?.targets.find(t => t.target_ref === targetRef);
      if (!target?.geometry) return;
      const geom = target.geometry;
      const token = ++blinkToken;

      // Fit the tramo in view so it's unmissable.
      const lons = geom.map(p => p[0]);
      const lats = geom.map(p => p[1]);
      const minLon = Math.min(...lons), maxLon = Math.max(...lons);
      const minLat = Math.min(...lats), maxLat = Math.max(...lats);
      if (Number.isFinite(minLon) && maxLon > minLon || maxLat > minLat) {
        map.fitBounds([[minLon, minLat], [maxLon, maxLat]], { padding: 90, maxZoom: 17, duration: 800 });
      } else {
        map.flyTo({ center: [geom[0][0], geom[0][1]], zoom: 16, duration: 700 });
      }

      const mid = midPoint(geom);
      const flash = { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: geom } }] };
      const ring = { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: mid } }] };
      (map.getSource('blink-flash') as any).setData(flash);
      (map.getSource('blink-flash-ring') as any).setData(ring);
      try { map.moveLayer('blink-flash-layer'); } catch {}
      try { map.moveLayer('blink-flash-ring-layer'); } catch {}

      const t0 = performance.now();
      const DURATION = 2200;
      const frame = (now: number) => {
        if (token !== blinkToken) return;
        const k = (now - t0) / DURATION;
        if (k >= 1) {
          try { map.setPaintProperty('blink-flash-layer', 'line-opacity', 0.0); } catch {}
          try { map.setPaintProperty('blink-flash-ring-layer', 'circle-opacity', 0.0); } catch {}
          return;
        }
        // 6 pulses in a decaying ping
        const pulse = (Math.sin(k * Math.PI * 12) + 1) / 2;
        const decay = 1 - k;
        const width = 5 + 18 * pulse * (0.4 + 0.6 * decay);
        const opacity = (0.25 + 0.75 * pulse) * decay;
        try { map.setPaintProperty('blink-flash-layer', 'line-width', width); } catch {}
        try { map.setPaintProperty('blink-flash-layer', 'line-opacity', opacity); } catch {}
        const r = 4 + 16 * pulse * decay;
        try { map.setPaintProperty('blink-flash-ring-layer', 'circle-radius', r); } catch {}
        try { map.setPaintProperty('blink-flash-ring-layer', 'circle-opacity', Math.min(1, opacity * 1.4)); } catch {}
        requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    };
    store.setBlinkTarget(blinkTarget);
    (window as any).__blinkGisTarget = blinkTarget;

    const highlightTarget = (targetRef: string) => {
      if (!map.isStyleLoaded()) return;
      const state = useGisStore.getState();
      const inv = state.activePlanningInventory;
      const target = inv?.targets.find(t => t.target_ref === targetRef);
      if (!target?.geometry) return;
      const geom = target.geometry;
      const mid = midPoint(geom);
      (map.getSource('tramo-hover') as any).setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: geom } }] });
      (map.getSource('tramo-hover-ring') as any).setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: mid } }] });
      try { map.moveLayer('tramo-hover-layer'); } catch {}
      try { map.moveLayer('tramo-hover-ring-layer'); } catch {}
      try { map.setPaintProperty('tramo-hover-ring-layer', 'circle-opacity', 0.9); } catch {}
    };
    const clearHighlightTarget = () => {
      if (!map.isStyleLoaded()) return;
      try {
        (map.getSource('tramo-hover') as any).setData({ type: 'FeatureCollection', features: [] });
        (map.getSource('tramo-hover-ring') as any).setData({ type: 'FeatureCollection', features: [] });
        map.setPaintProperty('tramo-hover-ring-layer', 'circle-opacity', 0.0);
      } catch {}
    };
    store.setHighlightTarget(highlightTarget);
    store.setClearHighlightTarget(clearHighlightTarget);
    (window as any).__highlightGisTarget = highlightTarget;
    (window as any).__clearGisHighlight = clearHighlightTarget;

    mapRef.current = map;
    return () => {
      map.remove();
      initDone.current = false;
      const clean = useGisStore.getState();
      clean.setMapInstance(null);
      clean.setToggleBaseMap(null);
      clean.setToggle3dView(null);
      clean.setFocusLocation(null);
      clean.setBlinkTarget(null);
      clean.setHighlightTarget(null);
      clean.setClearHighlightTarget(null);
      delete (window as any).__gisMap;
      delete (window as any).__focusGisLocation;
      delete (window as any).__toggleBaseMap;
      delete (window as any).__blinkGisTarget;
      delete (window as any).__highlightGisTarget;
      delete (window as any).__clearGisHighlight;
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
          name: targetName(target) || '',
          ref: targetRef(target) || '',
          nameState: target.nameState || '',
          roadRole: target.roadRole || '',
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
    removeLayer(map, 'area-cursor-line');
    removeLayer(map, 'area-cursor-verts');
    removeLayer(map, 'area-cursor-dot');
    removeSource(map, 'road-selection');
    removeSource(map, 'area-cursor');

    const draft = selectedZoneId ? roadSelectionByZone[selectedZoneId] : undefined;
    if (!draft) return;
    const features: any[] = [];
    // El lazo solo se pinta mientras se dibuja; al completar (calles ya seleccionadas) desaparece.
    if (draft.status !== 'complete') {
      if (draft.boundary) features.push({ type: 'Feature', properties: { kind: 'area' }, geometry: draft.boundary });
      else if (draft.area_points.length >= 2) features.push({ type: 'Feature', properties: { kind: 'area-line' }, geometry: { type: 'LineString', coordinates: draft.area_points } });
    }
    const selectedTargetRefs = new Set([draft.a?.target_ref, draft.b?.target_ref].filter(Boolean));
    planningInventory?.targets.forEach(target => {
      if (target.geometry && selectedTargetRefs.has(target.target_ref)) features.push({ type: 'Feature', properties: { kind: 'target' }, geometry: { type: 'LineString', coordinates: target.geometry } });
    });
    if (draft.path?.length && draft.status === 'complete') features.push({ type: 'Feature', properties: { kind: 'path' }, geometry: { type: 'LineString', coordinates: draft.path } });
    if (draft.a) features.push({ type: 'Feature', properties: { kind: 'a' }, geometry: { type: 'Point', coordinates: draft.a.coordinate } });
    if (draft.b) features.push({ type: 'Feature', properties: { kind: 'b' }, geometry: { type: 'Point', coordinates: draft.b.coordinate } });
    if (features.length) {
      addSource(map, { id: 'road-selection', type: 'geojson', data: { type: 'FeatureCollection', features } });
      addLayer(map, { id: 'road-selection-area-fill', type: 'fill', source: 'road-selection', filter: ['==', ['get', 'kind'], 'area'], paint: { 'fill-color': '#2563EB', 'fill-opacity': 0.12 } });
      addLayer(map, { id: 'road-selection-area-outline', type: 'line', source: 'road-selection', filter: ['in', ['get', 'kind'], ['literal', ['area', 'area-line']]], paint: { 'line-color': '#2563EB', 'line-width': 3, 'line-dasharray': [2, 1] } });
      addLayer(map, { id: 'road-selection-target', type: 'line', source: 'road-selection', filter: ['==', ['get', 'kind'], 'target'], paint: { 'line-color': '#F59E0B', 'line-width': 8, 'line-opacity': 0.75 } });
      addLayer(map, { id: 'road-selection-path', type: 'line', source: 'road-selection', filter: ['==', ['get', 'kind'], 'path'], paint: { 'line-color': '#2563EB', 'line-width': 8, 'line-opacity': 0.95 } });
      addLayer(map, {
        id: 'road-selection-points', type: 'circle', source: 'road-selection', filter: ['in', ['get', 'kind'], ['literal', ['a', 'b']]],
        paint: { 'circle-radius': 7, 'circle-color': ['case', ['==', ['get', 'kind'], 'a'], '#16A34A', '#DC2626'], 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' },
      });
    }

    // Live cursor preview while drawing the area.
    if (draft.status === 'draw_area') {
      addSource(map, { id: 'area-cursor', type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      addLayer(map, { id: 'area-cursor-line', type: 'line', source: 'area-cursor', paint: { 'line-color': '#2563EB', 'line-width': 2.5, 'line-dasharray': [1, 2], 'line-opacity': 0.8 } });
      addLayer(map, { id: 'area-cursor-verts', type: 'circle', source: 'area-cursor', paint: { 'circle-radius': 4, 'circle-color': '#2563EB', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff' } });
      addLayer(map, { id: 'area-cursor-dot', type: 'circle', source: 'area-cursor', filter: ['==', ['get', 'kind'], 'cursor'], paint: { 'circle-radius': 5, 'circle-color': '#0EA5E9', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } });
    }
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
          if ((targetName(t) || '') !== selectedStreetName || t.target_ref === selectedTargetRef || !t.geometry) return;
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

  const closeContextPopup = () => { contextOpenRef.current = false; setContextPopup(null); };

  return (
    <>
      <div
        id={mapContainerId}
        className="absolute inset-0 w-full h-full"
        style={{ background: '#0d1520' }}
        onMouseLeave={() => { setHover(null); hoverRef.current = null; }}
      />
      {!contextPopup && hover && (
        <div
          className="pointer-events-none fixed z-50 w-72 rounded-xl bg-white shadow-2xl ring-1 ring-black/10 backdrop-blur"
          style={{ left: Math.min(hover.x + 24, window.innerWidth - 300), top: Math.min(hover.y + 24, window.innerHeight - 260) }}
        >
          <div className="truncate border-b border-salvi-line bg-salvi-surface px-3 py-2 text-xs font-semibold text-salvi-black">
            {targetName(hover.target) || targetDisplayLabel(hover.target) || 'Tramo sin nombre'}
          </div>
          <div className="px-3 py-2">
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-salvi-grey">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: hover.roadType ? ROAD_CFG[hover.roadType]?.color || '#999' : '#999' }} />
              {hover.roadType ? t(`road.${hover.roadType}`) : 'Tipo de vía desconocido'}
            </span>
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-salvi-muted">
              <span>{hover.target.length_m == null ? '—' : `${Math.round(hover.target.length_m)} m`}</span>
              {hover.target.estWidth != null && <span>Calzada {hover.target.estWidth} m</span>}
              {hover.target.highway && <span>highway={hover.target.highway}</span>}
            </div>
          </div>
        </div>
      )}
      {contextPopup && (
        <SegmentContextPopup
          x={contextPopup.x}
          y={contextPopup.y}
          target={contextPopup.target}
          roadType={contextPopup.roadType}
          onClose={closeContextPopup}
          onSelectStreet={(streetName) => {
            const store = useGisStore.getState();
            const inv = store.activePlanningInventory;
            if (!inv || !store.selectedZoneId) return;
            const refs = inv.targets.filter(t => targetName(t) === streetName).map(t => t.target_ref);
            const zoneSel = store.accumulatedSelection[store.selectedZoneId] || {};
            let anyChanged = false;
            for (const r of refs) {
              if (!zoneSel[r]) { store.toggleTargetSelection(store.selectedZoneId, r); anyChanged = true; }
            }
            if (anyChanged) store.setSelectedSegment(null, null);
          }}
        />
      )}
    </>
  );
};

export default MapView;
