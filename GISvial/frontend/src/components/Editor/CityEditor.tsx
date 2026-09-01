import React, { useCallback, useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { useI18n } from '../../i18n';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import { getEditorFeatures, getBuildingWidths, getZoneTrees, bulkSaveLuminaires, deleteLuminaire, exportDxfObjects, getZoneAlignment, autoAlignZone } from '../../lib/api';
import { shiftLine, shiftRing, shiftLngLat, unshiftLngLat } from '../../lib/alignment';
import { makeEditorObject, type EditorObject } from '../../lib/editorObjects';
import { effectiveInventory } from '../../lib/planningOverrides';
import { targetName, targetDisplayLabel } from '../../lib/roadNaming';
import { nearestInventoryHit, sliceLine } from '../../lib/roadSelection';
import type { RoadSelectionAnchor } from '../../store/types';
import {
  roadPolygon, sidewalkPolygons, rotateFootprint, bboxOfMany, offsetEdge, lineLengthM,
  pointAlongLine, lateralOffsetPoint,
  buildingHeight, parseBuildings, parseTrees, metersToDeg, pointInPolygon,
  connectStreetSegments, joinStreetPath,
  type LngLat, type FarolaPlacement,
} from '../../lib/editorGeometry';
import type { GisPlanningInventoryTarget } from '../../types';
import EditorToolbar, { type EditorBase } from './EditorToolbar';
import EditorRoadInspector from './RoadInspector';
import ObjectsPanel from './ObjectsPanel';
import FarolaPlacementPopup, { type FarolaPlaceResult } from './FarolaPlacementPopup';

const setVis = (map: maplibregl.Map, id: string, vis: 'visible' | 'none') => {
  if (map.getLayer(id)) { try { map.setLayoutProperty(id, 'visibility', vis); } catch { /* ignore */ } }
};

const addExtrusion = (map: maplibregl.Map, id: string, data: any, height: any, base: any, color: any) => {
  if (map.getSource(id)) { (map.getSource(id) as any).setData(data); } else { map.addSource(id, { type: 'geojson', data }); }
  if (!map.getLayer(id)) {
    map.addLayer({
      id, type: 'fill-extrusion', source: id,
      paint: { 'fill-extrusion-color': color, 'fill-extrusion-height': height, 'fill-extrusion-base': base, 'fill-extrusion-opacity': 0.97 },
    } as any);
  }
};

const addFill = (map: maplibregl.Map, id: string, data: any, color: any) => {
  if (map.getSource(id)) { (map.getSource(id) as any).setData(data); } else { map.addSource(id, { type: 'geojson', data }); }
  if (!map.getLayer(id)) map.addLayer({ id, type: 'fill', source: id, paint: { 'fill-color': color, 'fill-opacity': 1 } } as any);
};

const expandBbox = (bb: [number, number, number, number], meters: number): [number, number, number, number] => {
  const lat = (bb[1] + bb[3]) / 2;
  const { dLat, dLng } = metersToDeg(lat);
  return [bb[0] - meters * dLng, bb[1] - meters * dLat, bb[2] + meters * dLng, bb[3] + meters * dLat];
};

const inBbox = (p: LngLat, bb: [number, number, number, number]) =>
  p[0] >= bb[0] && p[0] <= bb[2] && p[1] >= bb[1] && p[1] <= bb[3];

const ringCenter = (ring: LngLat[]): LngLat => {
  let x = 0, y = 0;
  const n = Math.max(1, ring.length - 1);
  for (let i = 0; i < n; i++) { x += ring[i][0]; y += ring[i][1]; }
  return [x / n, y / n];
};

const BUILDING_COLOR = (h: number) => (h < 8 ? '#c2c7cc' : h < 14 ? '#adb3ba' : '#98a0a8');

const fmtDistance = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);

const CityEditor: React.FC = () => {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const readyRef = useRef(false);
  const draggingRef = useRef<string | null>(null);
  const lassoRef = useRef<LngLat[] | null>(null);
  const dataRef = useRef<{ bbox: [number, number, number, number] | null }>({ bbox: null });

  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [view3d, setView3d] = useState(false);
  const [base, setBase] = useState<EditorBase>('plan');
  const [relief, setRelief] = useState<'none' | 'hillshade' | 'terrain'>('none');
  const [noSel, setNoSel] = useState(false);
  const [layers, setLayers] = useState<Record<string, boolean>>({
    buildings: true, trees: true, luminaries: true, roads: true, sidewalks: true, objects: true,
  });

  const editorOpen = useGisStore(s => s.editorOpen);
  const zoneId = useGisStore(s => s.editorZoneId);
  const editorObjects = useGisStore(s => (zoneId ? s.editorObjects[zoneId] : undefined));
  const selectedIds = useGisStore(s => s.editorSelectedIds);
  const editorRoadRef = useGisStore(s => s.editorRoadRef);
  const editorTool = useGisStore(s => s.editorTool);
  const planningPayload = useGisStore(s => s.planningPayload);

  const targetsRef = useRef<GisPlanningInventoryTarget[]>([]);
  const roadRingsRef = useRef<{ ref: string; ring: LngLat[] }[]>([]);
  const routeRef = useRef<{ a: RoadSelectionAnchor | null; b: RoadSelectionAnchor | null }>({ a: null, b: null });
  const measureRef = useRef<LngLat[]>([]);
  const [placePopup, setPlacePopup] = useState<{ x: number; y: number; path: LngLat[]; roadHalfWidth: number; label: string; obstacleRings: LngLat[][] } | null>(null);
  const [measure, setMeasure] = useState<{ x: number; y: number; text: string } | null>(null);
  const [routeNotice, setRouteNotice] = useState<string | null>(null);
  const routeNoticeTimerRef = useRef<number | undefined>(undefined);
  const [buildingsState, setBuildingsState] = useState<'loading' | 'done' | 'none' | null>(null);

  const showRouteNotice = useCallback((msg: string) => {
    setRouteNotice(msg);
    window.clearTimeout(routeNoticeTimerRef.current);
    routeNoticeTimerRef.current = window.setTimeout(() => setRouteNotice(null), 4500);
  }, []);

  const zoneAlignments = useGisStore(s => s.zoneAlignments);
  const setZoneAlignmentStore = useGisStore(s => s.setZoneAlignment);
  const alignment = zoneId ? zoneAlignments[zoneId] : undefined;
  const [aligning, setAligning] = useState(false);

  // Fetch alignment and auto-trigger if missing
  useEffect(() => {
    if (!zoneId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await getZoneAlignment(zoneId);
        if (cancelled) return;
        setZoneAlignmentStore(zoneId, { dx: res.dx || 0, dy: res.dy || 0, dx_m: res.dx_m || 0, dy_m: res.dy_m || 0, confidence: res.confidence || 0, source: res.source || 'none', updated_at: res.updated_at });
        // Auto-align if never aligned and we have a bbox
        if ((!res.dx && !res.dy) && res.confidence === 0) {
          const zone = useGisStore.getState().zones.find(z => z.id === zoneId);
          if (!zone?.bbox) return;
          setAligning(true);
          try {
            const auto = await autoAlignZone(zoneId);
            if (!cancelled) setZoneAlignmentStore(zoneId, { dx: auto.dx || 0, dy: auto.dy || 0, dx_m: auto.dx_m || 0, dy_m: auto.dy_m || 0, confidence: auto.confidence || 0, source: auto.source || 'auto', updated_at: new Date().toISOString() });
          } catch { /* ignore */ }
          finally { if (!cancelled) setAligning(false); }
        }
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [zoneId, setZoneAlignmentStore]);

  const applyVisibility = useCallback((map: maplibregl.Map) => {
    const plan = base === 'plan';
    // Plan: fondo neutro CAD; satélite/PNOA en sus modos
    setVis(map, 'satellite-layer', base === 'aerial' ? 'visible' : 'none');
    setVis(map, 'pnoa-layer', base === 'pnoa' ? 'visible' : 'none');
    for (const id of ['ed-ground', 'ed-green', 'ed-water']) setVis(map, id, plan ? 'visible' : 'none');
    const rv = plan && layers.roads ? 'visible' : 'none';
    setVis(map, 'ed-roads', rv); setVis(map, 'ed-marks', rv);
    setVis(map, 'ed-sidewalks', plan && layers.sidewalks ? 'visible' : 'none');
    if (map.getLayer('bg')) { try { map.setPaintProperty('bg', 'background-color', plan ? '#e6e1d6' : '#0e1620'); } catch { /* ignore */ } }
    const idsOf = (k: string) => k === 'buildings' ? ['ed-buildings'] : k === 'trees' ? ['ed-trees'] : k === 'luminaries' ? ['ed-lum'] : ['ed-obj-3d', 'ed-obj-circles'];
    for (const k of ['buildings', 'trees', 'luminaries', 'objects'] as const) {
      const vis = layers[k] ? 'visible' : 'none';
      for (const id of idsOf(k)) setVis(map, id, vis);
    }
  }, [base, layers]);

  const buildEditorLayers = useCallback((map: maplibregl.Map, objs: any[]) => {
    const st = useGisStore.getState();
    const align = zoneId ? st.zoneAlignments[zoneId] : undefined;
    const shiftedObjs = (!align || (align.dx === 0 && align.dy === 0)) ? objs : objs.map(o => ({ ...o, lng: o.lng + align.dx, lat: o.lat + align.dy }));
    const objFeats = shiftedObjs.map(o => ({ type: 'Feature', properties: { color: o.color, h: o.height }, geometry: { type: 'Polygon', coordinates: [rotateFootprint(o.lng, o.lat, o.width, o.length, o.rotation)] } }));
    const pts = shiftedObjs.map(o => ({ type: 'Feature', properties: { oid: o.id, color: o.color }, geometry: { type: 'Point', coordinates: [o.lng, o.lat] } }));
    addExtrusion(map, 'ed-obj-3d', { type: 'FeatureCollection', features: objFeats }, ['get', 'h'], 0, ['get', 'color']);
    if (map.getSource('ed-obj-circles')) { (map.getSource('ed-obj-circles') as any).setData({ type: 'FeatureCollection', features: pts }); } else {
      map.addSource('ed-obj-circles', { type: 'geojson', data: { type: 'FeatureCollection', features: pts } as any });
      map.addLayer({ id: 'ed-obj-circles', type: 'circle', source: 'ed-obj-circles', paint: { 'circle-radius': 5, 'circle-color': ['get', 'color'], 'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff', 'circle-pitch-alignment': 'map', 'circle-pitch-scale': 'map' } } as any);
    }
  }, [zoneId]);

  const updateSelection = useCallback((map: maplibregl.Map, ids: string[], objs: any[]) => {
    const st = useGisStore.getState();
    const align = zoneId ? st.zoneAlignments[zoneId] : undefined;
    const shift = (lng: number, lat: number): LngLat => (!align || (align.dx === 0 && align.dy === 0)) ? [lng, lat] : [lng + align.dx, lat + align.dy];
    const sel = ids.filter(id => objs.some(o => o.id === id));
    const feats: any[] = [];
    for (const id of sel) {
      const o = objs.find(x => x.id === id);
      if (!o) continue;
      const [slng, slat] = shift(o.lng, o.lat);
      feats.push({ type: 'Feature', properties: { kind: 'poly' }, geometry: { type: 'Polygon', coordinates: [rotateFootprint(slng, slat, o.width, o.length, o.rotation)] } });
      feats.push({ type: 'Feature', properties: { kind: 'pt' }, geometry: { type: 'Point', coordinates: [slng, slat] } });
    }
    const data = { type: 'FeatureCollection', features: feats } as any;
    if (map.getSource('ed-sel')) { (map.getSource('ed-sel') as any).setData(data); } else {
      map.addSource('ed-sel', { type: 'geojson', data });
      map.addLayer({ id: 'ed-sel', type: 'line', source: 'ed-sel', filter: ['==', ['get', 'kind'], 'poly'], paint: { 'line-color': '#c9a227', 'line-width': 3 } } as any);
      map.addLayer({ id: 'ed-sel-pt', type: 'circle', source: 'ed-sel', filter: ['==', ['get', 'kind'], 'pt'], paint: { 'circle-radius': 16, 'circle-color': '#c9a227', 'circle-opacity': 0.35, 'circle-stroke-width': 2.5, 'circle-stroke-color': '#c9a227' } } as any);
    }
  }, [zoneId]);

  const computeEditorTargets = useCallback((): GisPlanningInventoryTarget[] => {
    if (!zoneId) return [];
    const st = useGisStore.getState();
    const align = st.zoneAlignments[zoneId];
    const inv = st.activePlanningInventory ? effectiveInventory(st.activePlanningInventory, st.planningPayload) : null;
    const acc = st.accumulatedSelection[zoneId] || {};
    const saved = st.savedSelectionByZone[zoneId] || {};
    const hasSel = Object.keys(acc).length > 0;
    const hasSaved = Object.keys(saved).length > 0;
    const want = hasSel ? acc : hasSaved ? saved : null;
    const filtered = inv?.targets.filter(tg => tg.geometry && (want ? want[tg.target_ref] : true)) || [];
    if (!align || (align.dx === 0 && align.dy === 0)) return filtered;
    return filtered.map(tg => ({ ...tg, geometry: tg.geometry ? shiftLine(tg.geometry as LngLat[], align) as any : tg.geometry }));
  }, [zoneId]);

  /** Dibuja calzadas, aceras, marcas de carril y el relleno de suelo. Un bbox de vuelta. */
  const paintScene = useCallback((map: maplibregl.Map, targets: GisPlanningInventoryTarget[]) => {
    const st = useGisStore.getState();
    const align = zoneId ? st.zoneAlignments[zoneId] : undefined;
    const groupTypes = new Map((st.activePlanningInventory?.groups || []).map(g => [g.group_ref, g.road_type]));
    const roads: any[] = [];
    const sidewalks: any[] = [];
    const marks: any[] = [];
    const baseRings: LngLat[][] = [];
    const ringsByRef: { ref: string; ring: LngLat[] }[] = [];
    for (const tg of targets) {
      const geom = shiftLine(tg.geometry as LngLat[], align);
      const type = groupTypes.get(tg.group_ref);
      const w = tg.estWidth ?? ROAD_CFG[type || '']?.width ?? 5;
      const ring = roadPolygon(geom, w);
      if (ring.length >= 4) {
        roads.push({ type: 'Feature', properties: { target_ref: tg.target_ref }, geometry: { type: 'Polygon', coordinates: [ring] } });
        ringsByRef.push({ ref: tg.target_ref, ring });
        baseRings.push(ring);
      }
      for (const r of sidewalkPolygons(geom, w, tg.sidewalkWidthLeft, tg.sidewalkWidthRight)) if (r.length >= 4) { sidewalks.push({ type: 'Feature', properties: { target_ref: tg.target_ref }, geometry: { type: 'Polygon', coordinates: [r] } }); baseRings.push(r); }
      baseRings.push(geom);
      const lanes = Math.max(1, tg.lanes ?? (((tg.lanesForward || 0) + (tg.lanesBackward || 0)) || (tg.dual ? 2 : 1) || 1));
      const center = offsetEdge(geom, 0);
      if (center.length >= 2) marks.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: center } });
      for (let i = 1; i < lanes; i++) {
        const off = -w / 2 + i * (w / lanes);
        if (Math.abs(off) < 0.15) continue;
        const line = offsetEdge(geom, off);
        if (line.length >= 2) marks.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: line } });
      }
    }
    roadRingsRef.current = ringsByRef;
    const bbox = baseRings.length ? bboxOfMany(baseRings) : null;
    if (bbox) {
      const wide = expandBbox(bbox, 120);
      const ring: LngLat[] = [[wide[0], wide[1]], [wide[2], wide[1]], [wide[2], wide[3]], [wide[0], wide[3]], [wide[0], wide[1]]];
      addFill(map, 'ed-ground', { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }] }, '#e0dccf');
    }
    // Aceras primero, luego calzadas encima: los cruces de dos carreteras tapan la acera.
    addExtrusion(map, 'ed-sidewalks', { type: 'FeatureCollection', features: sidewalks }, 0.18, 0, '#c6c1b7');
    addFill(map, 'ed-roads', { type: 'FeatureCollection', features: roads }, '#5d6369');
    if (map.getSource('ed-marks')) { (map.getSource('ed-marks') as any).setData({ type: 'FeatureCollection', features: marks }); } else {
      map.addSource('ed-marks', { type: 'geojson', data: { type: 'FeatureCollection', features: marks } });
      map.addLayer({ id: 'ed-marks', type: 'line', source: 'ed-marks', paint: { 'line-color': '#ffffff', 'line-width': 1.6, 'line-dasharray': [1.6, 1.4] } } as any);
    }
    return bbox;
  }, [zoneId]);

  /** Overlay del recorrido de farolas: puntos A/B + línea. */
  const updateRouteOverlay = useCallback((map: maplibregl.Map, a: RoadSelectionAnchor | null, b: RoadSelectionAnchor | null, path: LngLat[] | null) => {
    if (!map.getSource('ed-route-pts')) {
      map.addSource('ed-route-pts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
      map.addLayer({ id: 'ed-route-a', type: 'circle', source: 'ed-route-pts', filter: ['==', ['get', 'k'], 'a'], paint: { 'circle-radius': 8, 'circle-color': '#16A34A', 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' } } as any);
      map.addLayer({ id: 'ed-route-b', type: 'circle', source: 'ed-route-pts', filter: ['==', ['get', 'k'], 'b'], paint: { 'circle-radius': 8, 'circle-color': '#DC2626', 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' } } as any);
    }
    if (!map.getSource('ed-route-line')) {
      map.addSource('ed-route-line', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
      map.addLayer({ id: 'ed-route-line', type: 'line', source: 'ed-route-line', paint: { 'line-color': '#0EA5E9', 'line-width': 4, 'line-dasharray': [4, 2] } } as any);
    }
    const pts: any[] = [];
    if (a) pts.push({ type: 'Feature', properties: { k: 'a' }, geometry: { type: 'Point', coordinates: a.coordinate } });
    if (b) pts.push({ type: 'Feature', properties: { k: 'b' }, geometry: { type: 'Point', coordinates: b.coordinate } });
    (map.getSource('ed-route-pts') as any).setData({ type: 'FeatureCollection', features: pts });
    const line = path && path.length > 1 ? path : (a && b ? [a.coordinate, b.coordinate] : []);
    (map.getSource('ed-route-line') as any).setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: line } }] });
  }, []);

  const updateMeasureOverlay = useCallback((map: maplibregl.Map, points: LngLat[], cursor: LngLat | null) => {
    if (!map.getSource('ed-measure-line')) {
      map.addSource('ed-measure-line', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
      map.addLayer({ id: 'ed-measure-line', type: 'line', source: 'ed-measure-line', paint: { 'line-color': '#0ea5e9', 'line-width': 3 } } as any);
    }
    if (!map.getSource('ed-measure-pts')) {
      map.addSource('ed-measure-pts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } as any);
      map.addLayer({ id: 'ed-measure-pts', type: 'circle', source: 'ed-measure-pts', paint: { 'circle-radius': 5, 'circle-color': '#0ea5e9', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff' } } as any);
    }
    const line = cursor ? [...points, cursor] : points;
    (map.getSource('ed-measure-line') as any).setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: line } }] });
    (map.getSource('ed-measure-pts') as any).setData({ type: 'FeatureCollection', features: points.map(p => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: p } })) });
  }, []);

  const measureAt = useCallback((map: maplibregl.Map, pts: LngLat[]): { x: number; y: number; text: string } => {
    const last = pts[pts.length - 1];
    const d = lineLengthM(pts);
    const proj = map.project([last[0], last[1]]);
    return { x: proj.x, y: proj.y, text: fmtDistance(d) };
  }, []);

  const makeRouteFarola = useCallback((p: FarolaPlacement, opts: FarolaPlaceResult['opts']): EditorObject => {
    const st = useGisStore.getState();
    const align = zoneId ? st.zoneAlignments[zoneId] : undefined;
    const lng = align ? p.point[0] - align.dx : p.point[0];
    const lat = align ? p.point[1] - align.dy : p.point[1];
    const obj = makeEditorObject('farola', lng, lat);
    obj.rotation = p.rotation;
    obj.height = opts.poleH;
    obj.attrs = { ...obj.attrs, watts: opts.watts, armLength: opts.armLen, tilt: opts.tilt, spacing: opts.spacing, distribution: opts.distribution, setback: opts.setback };
    return obj;
  }, [zoneId]);

  const handlePlaceFarolas = useCallback((result: FarolaPlaceResult) => {
    const z = zoneId;
    if (!z) return;
    const st = useGisStore.getState();
    const ids: string[] = [];
    for (const p of result.items) { const obj = makeRouteFarola(p, result.opts); ids.push(obj.id); st.addEditorObject(z, obj); }
    if (ids.length) st.selectEditorObjects(ids);
    setPlacePopup(null);
    routeRef.current = { a: null, b: null };
    if (mapRef.current) updateRouteOverlay(mapRef.current, null, null, null);
    st.setEditorTool(null);
  }, [zoneId, makeRouteFarola, updateRouteOverlay]);

  const fitSection = useCallback((map: maplibregl.Map) => {
    const b = dataRef.current.bbox;
    if (!b || !b.every(Number.isFinite)) return;
    map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 70, maxZoom: 18, pitch: view3d ? 60 : 0, duration: 0 });
  }, [view3d]);

  useEffect(() => {
    if (!containerRef.current || !editorOpen || !zoneId) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'satellite': { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 19, attribution: 'Tiles © Esri' },
          'pnoa': { type: 'raster', tiles: ['https://www.ign.es/wmts/pnoa-ma?Service=WMTS&Request=GetTile&Version=1.0.0&Format=image/jpeg&Layer=OI.OrthoimageCoverage&Style=default&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileCol={x}&TileRow={y}'], tileSize: 256, maxzoom: 19, attribution: 'Ortofotos PNOA © Instituto Geográfico Nacional de España' },
          'terrain-dem': { type: 'raster-dem', tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 14, encoding: 'terrarium' },
        },
        layers: [
          { id: 'bg', type: 'background', paint: { 'background-color': '#e6e1d6' } },
          { id: 'satellite-layer', type: 'raster', source: 'satellite', layout: { visibility: 'none' } },
          { id: 'pnoa-layer', type: 'raster', source: 'pnoa', layout: { visibility: 'none' } },
          { id: 'hillshade-layer', type: 'hillshade', source: 'terrain-dem', layout: { visibility: 'none' }, paint: { 'hillshade-illumination-direction': 315, 'hillshade-exaggeration': 0.4 } } as any,
        ],
      },
      center: [-3.7038, 40.4168], zoom: 15, pitch: 0, bearing: 0, maxPitch: 85, attributionControl: false,
    } as any);
    mapRef.current = map;
    map.dragRotate.enable();
    map.touchZoomRotate.enableRotation();
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

    const lassoSet = (pts: LngLat[]) => {
      if (map.getSource('ed-lasso')) { (map.getSource('ed-lasso') as any).setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [...pts, pts[0]] } }] }); }
    };

    const handleRouteClick = (e: any) => {
      const st = useGisStore.getState();
      const z = st.editorZoneId;
      if (!z) return;
      const targets = targetsRef.current;
      if (!targets.length) return;
      const anchor = nearestInventoryHit(map, targets, e.point, 30);
      if (!anchor) return;
      const target = targets.find(t => t.target_ref === anchor.target_ref);
      if (!target?.geometry) return;
      const a = routeRef.current.a;
      if (!a) {
        routeRef.current = { a: anchor, b: null };
        updateRouteOverlay(map, anchor, null, null);
        return;
      }
      if (a.target_ref === anchor.target_ref && Math.abs(a.measure - anchor.measure) > 1e-6) {
        const sliced = sliceLine(target.geometry, a, anchor);
        if (sliced && sliced.length_m > 0.5) {
          const w = target.estWidth ?? ROAD_CFG[target.highway || '']?.width ?? 5;
          const obstacleRings = roadRingsRef.current.filter(r => r.ref !== target.target_ref).map(r => r.ring);
          routeRef.current = { a, b: anchor };
          setPlacePopup({
            x: e.originalEvent?.clientX ?? e.point.x,
            y: e.originalEvent?.clientY ?? e.point.y,
            path: sliced.path,
            roadHalfWidth: w / 2,
            label: targetName(target) || targetDisplayLabel(target),
            obstacleRings,
          });
          updateRouteOverlay(map, a, anchor, sliced.path);
          return;
        }
        routeRef.current = { a: anchor, b: null };
        updateRouteOverlay(map, anchor, null, null);
        return;
      }
      if (a.target_ref !== anchor.target_ref) {
        const streetSegs = targets
          .filter(t => t.geometry)
          .map(t => ({ ref: t.target_ref, geom: t.geometry as LngLat[] }));
        const chain = connectStreetSegments(streetSegs, a.target_ref, anchor.target_ref);
        const path = chain && chain.length > 1
          ? joinStreetPath(streetSegs, chain, { measure: a.measure, coordinate: a.coordinate }, { measure: anchor.measure, coordinate: anchor.coordinate })
          : null;
        if (path && lineLengthM(path) > 0.5) {
          const w = target.estWidth ?? ROAD_CFG[target.highway || '']?.width ?? 5;
          const chainSet = new Set(chain);
          const obstacleRings = roadRingsRef.current.filter(r => !chainSet.has(r.ref)).map(r => r.ring);
          const aTarget = targets.find(t => t.target_ref === a.target_ref);
          const aName = aTarget ? targetName(aTarget) : null;
          const bName = targetName(target);
          const label = aName && bName && aName !== bName
            ? `${aName} → ${bName}`
            : (aName || bName || targetDisplayLabel(target));
          routeRef.current = { a, b: anchor };
          setPlacePopup({
            x: e.originalEvent?.clientX ?? e.point.x,
            y: e.originalEvent?.clientY ?? e.point.y,
            path,
            roadHalfWidth: w / 2,
            label,
            obstacleRings,
          });
          updateRouteOverlay(map, a, anchor, path);
          return;
        }
        showRouteNotice('No hay un camino conectado entre los dos puntos.');
        routeRef.current = { a: anchor, b: null };
        updateRouteOverlay(map, anchor, null, null);
        return;
      }
      routeRef.current = { a: anchor, b: null };
      updateRouteOverlay(map, anchor, null, null);
    };
    const onClick = (e: any) => {
      const st = useGisStore.getState();
      const tool = st.editorTool;
      if (tool === 'lasso') return;
      if (tool === 'farolas_route') { handleRouteClick(e); return; }
      if (tool === 'medir') {
        measureRef.current = [...measureRef.current, [e.lngLat.lng, e.lngLat.lat]];
        updateMeasureOverlay(map, measureRef.current, null);
        setMeasure(measureAt(map, measureRef.current));
        return;
      }
      if (!tool && st.editorAlign && st.editorSelectedIds.length === 1 && st.editorZoneId) {
        try {
          const hit = nearestInventoryHit(map, targetsRef.current, e.point, 24);
          if (hit) {
            const target = targetsRef.current.find(t => t.target_ref === hit.target_ref);
            if (target?.geometry && target.geometry.length >= 2) {
              const w = target.estWidth ?? ROAD_CFG[target.highway || '']?.width ?? 5;
              const sample = pointAlongLine(target.geometry, hit.measure * lineLengthM(target.geometry));
              if (sample) {
                const off = st.editorPlaceOffset || 0;
                const v: LngLat = [e.lngLat.lng - sample.point[0], e.lngLat.lat - sample.point[1]];
                const side = (v[0] * sample.lNormal[0] + v[1] * sample.lNormal[1]) >= 0 ? 1 : -1;
                const p = lateralOffsetPoint(sample, (w / 2) + off * side);
                const align = st.zoneAlignments[st.editorZoneId];
                const up = unshiftLngLat(p, align);
                st.updateEditorObject(st.editorZoneId, st.editorSelectedIds[0], { lng: up[0], lat: up[1], rotation: sample.headingDeg });
                return;
              }
            }
          }
        } catch { /* ignore */ }
      }
      if (tool) {
        const z = st.editorZoneId;
        if (!z) return;
        const align = st.zoneAlignments[z];
        const obj = makeEditorObject(tool, e.lngLat.lng, e.lngLat.lat);
        // Store in OSM (unshifted) CRS — unshift the click position
        {
          const up = unshiftLngLat([obj.lng, obj.lat], align);
          obj.lng = up[0]; obj.lat = up[1];
        }
        try {
          const hit = nearestInventoryHit(map, targetsRef.current, e.point, 24);
          if (hit) {
            const target = targetsRef.current.find(t => t.target_ref === hit.target_ref);
            if (target?.geometry && target.geometry.length >= 2) {
              const w = target.estWidth ?? ROAD_CFG[target.highway || '']?.width ?? 5;
              const sample = pointAlongLine(target.geometry, hit.measure * lineLengthM(target.geometry));
              if (sample) {
                obj.rotation = sample.headingDeg;
                const off = (st.editorPlaceOffset || 0);
                if (off > 0) {
                  const v: LngLat = [e.lngLat.lng - sample.point[0], e.lngLat.lat - sample.point[1]];
                  const side = (v[0] * sample.lNormal[0] + v[1] * sample.lNormal[1]) >= 0 ? 1 : -1;
                  const p = lateralOffsetPoint(sample, (w / 2) + off * side);
                  const up = unshiftLngLat(p, align);
                  obj.lng = up[0];
                  obj.lat = up[1];
                }
              }
            }
          }
        } catch { /* ignore */ }
        st.addEditorObject(z, obj);
        return;
      }
      try {
        const hit = map.queryRenderedFeatures(e.point, { layers: ['ed-obj-circles'] }).find((f: any) => f.properties?.oid);
        if (hit) { st.selectEditorObjects([hit.properties.oid]); st.setEditorRoadRef(null); return; }
      } catch { /* ignore */ }
      try {
        const road = map.queryRenderedFeatures(e.point, { layers: ['ed-roads', 'ed-sidewalks'] }).find((f: any) => f.properties?.target_ref);
        if (road) { st.setEditorRoadRef(road.properties.target_ref); st.selectEditorObjects([]); return; }
      } catch { /* ignore */ }
      try {
        const anchor = nearestInventoryHit(map, targetsRef.current, e.point, 20);
        if (anchor) { st.setEditorRoadRef(anchor.target_ref); st.selectEditorObjects([]); return; }
      } catch { /* ignore */ }
      st.selectEditorObjects([]);
      st.setEditorRoadRef(null);
    };
    const onMouseDown = (e: any) => {
      const st = useGisStore.getState();
      if (st.editorTool === 'lasso') {
        lassoRef.current = [[e.lngLat.lng, e.lngLat.lat]];
        map.dragPan.disable();
        map.getCanvas().style.cursor = 'crosshair';
        if (!map.getSource('ed-lasso')) map.addSource('ed-lasso', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        map.addLayer({ id: 'ed-lasso-line', type: 'line', source: 'ed-lasso', paint: { 'line-color': '#0ea5e9', 'line-width': 2, 'line-dasharray': [2, 1.5] } } as any);
        lassoSet(lassoRef.current);
        return;
      }
      if (st.editorTool) return;
      try {
        const hit = map.queryRenderedFeatures(e.point, { layers: ['ed-obj-circles'] }).find((f: any) => f.properties?.oid);
        if (hit) { draggingRef.current = hit.properties.oid; st.selectEditorObjects([hit.properties.oid]); map.dragPan.disable(); }
      } catch { /* ignore */ }
    };
    const onMouseMove = (e: any) => {
      const st = useGisStore.getState();
      if (st.editorTool === 'farolas_route') {
        const a = routeRef.current.a;
        if (a && !routeRef.current.b) {
          const cursor: LngLat = [e.lngLat.lng, e.lngLat.lat];
          updateRouteOverlay(map, a, null, [a.coordinate, cursor]);
        }
        return;
      }
      if (st.editorTool === 'medir') {
        const pts = measureRef.current;
        if (pts.length) {
          const cursor: LngLat = [e.lngLat.lng, e.lngLat.lat];
          updateMeasureOverlay(map, pts, cursor);
          setMeasure(measureAt(map, [...pts, cursor]));
        }
        return;
      }
      if (lassoRef.current) {
        const p: LngLat = [e.lngLat.lng, e.lngLat.lat];
        const last = lassoRef.current[lassoRef.current.length - 1];
        if (Math.hypot(p[0] - last[0], p[1] - last[1]) > 0.00004) { lassoRef.current.push(p); lassoSet(lassoRef.current); }
        return;
      }
      if (!draggingRef.current) return;
      const z = useGisStore.getState().editorZoneId;
      if (z) {
        const st = useGisStore.getState();
        const align = z ? st.zoneAlignments[z] : undefined;
        const up = unshiftLngLat([e.lngLat.lng, e.lngLat.lat], align);
        st.updateEditorObject(z, draggingRef.current, { lng: up[0], lat: up[1] });
      }
    };
    const onMouseUp = () => {
      if (lassoRef.current) {
        const pts = lassoRef.current; lassoRef.current = null;
        map.getCanvas().style.cursor = '';
        map.dragPan.enable();
        if (pts.length >= 3) {
          const st = useGisStore.getState();
          const z = st.editorZoneId;
          const align = z ? st.zoneAlignments[z] : undefined;
          const objs = z ? (st.editorObjects[z] || []) : [];
          st.selectEditorObjects(objs.filter(o => pointInPolygon(shiftLngLat([o.lng, o.lat], align), pts)).map(o => o.id));
          st.setEditorTool(null);
        }
        return;
      }
      if (draggingRef.current) { draggingRef.current = null; map.dragPan.enable(); }
    };
    const onContextMenu = (e: any) => {
      e.originalEvent.preventDefault();
      const st = useGisStore.getState();
      if (st.editorTool === 'medir') {
        measureRef.current = [];
        updateMeasureOverlay(map, [], null);
        setMeasure(null);
        return;
      }
      if (st.editorTool) return;
      try {
        const hit = map.queryRenderedFeatures(e.point, { layers: ['ed-obj-circles'] }).find((f: any) => f.properties?.oid);
        if (hit) st.selectEditorObjects([hit.properties.oid]);
      } catch { /* ignore */ }
    };

    map.on('click', onClick);
    map.on('mousedown', onMouseDown);
    map.on('mousemove', onMouseMove);
    map.on('mouseup', onMouseUp);
    map.on('contextmenu', onContextMenu);
    map.on('error', (e: any) => console.error('[CityEditor]', e?.error?.message || e));

    map.on('load', () => {
      try { buildScene(map); } catch (err) { console.error('[CityEditor] scene', err); setMapError(String((err as Error)?.message || err)); }
      readyRef.current = true;
      setReady(true);
    });

    return () => { map.remove(); mapRef.current = null; readyRef.current = false; setReady(false); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorOpen, zoneId]);

  const buildScene = useCallback((map: maplibregl.Map) => {
    const zid = zoneId as string;
    const stAlign = useGisStore.getState().zoneAlignments[zid];
    const targets = computeEditorTargets();
    targetsRef.current = targets;
    if (!targets.length) { setNoSel(true); return; }
    setNoSel(false);
    const bbox = paintScene(map, targets);
    dataRef.current.bbox = bbox;
    if (bbox) {
      const limited = expandBbox(bbox, 5000);
      try { map.setMaxBounds([[limited[0], limited[1]], [limited[2], limited[3]]] as any); } catch { /* ignore */ }
    }
    const clip = bbox ? expandBbox(bbox, 5000) : null;
    const bboxStr = bbox ? `${bbox[1]},${bbox[3]},${bbox[0]},${bbox[2]}` : '';
    setBuildingsState('loading');
    (async () => {
      let greens: any[] = [];
      let waters: any[] = [];
      let painted = false;
      const paintBuildings = (features: any[]) => {
        if (!features.length) return;
        addExtrusion(map, 'ed-buildings', { type: 'FeatureCollection', features }, ['get', 'h'], ['get', 'base'], ['get', 'color']);
        painted = true;
        setBuildingsState('done');
      };
      // Fuente rápida: edificios del inventario con altura estimada, mientras Overpass responde.
      (async () => {
        try {
          const bw: any = await getBuildingWidths(zid);
          const rings = parseBuildings(bw?.buildings).filter(r => r.length >= 4 && (!clip || inBbox(ringCenter(shiftRing(r, stAlign)), clip)));
          paintBuildings(rings.map(r => { const sr = shiftRing(r, stAlign); const h = buildingHeight(sr); return { type: 'Feature', properties: { h, base: 0, color: BUILDING_COLOR(h) }, geometry: { type: 'Polygon', coordinates: [sr] } }; }));
        } catch { /* ignore */ }
      })();
      try {
        const res: any = await getEditorFeatures(zid, bboxStr);
        const feats = res?.features || [];
        const buildings: any[] = [];
        for (const f of feats) {
          const ring = shiftRing(f.ring as LngLat[], stAlign);
          if (!ring || ring.length < 4) continue;
          if (clip && !inBbox(ringCenter(ring), clip)) continue;
          const geo = { type: 'Polygon', coordinates: [ring] } as any;
          if (f.kind === 'green') greens.push({ type: 'Feature', properties: {}, geometry: geo });
          else if (f.kind === 'water') waters.push({ type: 'Feature', properties: {}, geometry: geo });
          else if (f.kind === 'building') { const h = f.height || buildingHeight(ring); buildings.push({ type: 'Feature', properties: { h, base: f.base || 0, color: BUILDING_COLOR(h) }, geometry: geo }); }
        }
        addFill(map, 'ed-green', { type: 'FeatureCollection', features: greens }, '#a9d3a0');
        addFill(map, 'ed-water', { type: 'FeatureCollection', features: waters }, '#6fb4d9');
        paintBuildings(buildings);
      } catch (err) { console.warn('[CityEditor] features', err); }
      if (!painted) setBuildingsState('none');
      try {
        const tr: any = await getZoneTrees(zid);
        const pts = parseTrees(tr?.trees).filter(p => !clip || inBbox(shiftLngLat(p, stAlign), clip));
        const trees = pts.map(p => { const sp = shiftLngLat(p, stAlign); return { type: 'Feature', properties: { h: 5, color: '#3f7d3f' }, geometry: { type: 'Polygon', coordinates: [rotateFootprint(sp[0], sp[1], 1.2, 1.2, 0)] } }; });
        addExtrusion(map, 'ed-trees', { type: 'FeatureCollection', features: trees }, ['get', 'h'], 0, ['get', 'color']);
      } catch (err) { console.warn('[CityEditor] trees', err); }
      try {
        const lums = useGisStore.getState().zoneLuminaires[zid] || [];
        const lum = lums.map(l => { const sp = shiftLngLat([l.lon, l.lat], stAlign) as LngLat; return { type: 'Feature', properties: { color: '#FACC15' }, geometry: { type: 'Polygon', coordinates: [rotateFootprint(sp[0], sp[1], 0.3, 0.3, 0)] } }; });
        addExtrusion(map, 'ed-lum', { type: 'FeatureCollection', features: lum }, 9, 0, ['get', 'color']);
      } catch (err) { console.warn('[CityEditor] lum', err); }
      applyVisibility(map);
    })();

    buildEditorLayers(map, useGisStore.getState().editorObjects[zid] || []);
    updateSelection(map, useGisStore.getState().editorSelectedIds, useGisStore.getState().editorObjects[zid] || []);
    applyVisibility(map);
    fitSection(map);
  }, [zoneId, computeEditorTargets, paintScene, fitSection, applyVisibility, buildEditorLayers, updateSelection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    buildEditorLayers(map, editorObjects || []);
  }, [editorObjects, ready, buildEditorLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    updateSelection(map, selectedIds, editorObjects || []);
  }, [selectedIds, editorObjects, ready, updateSelection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const target = view3d ? 60 : 0;
    if (Math.abs(map.getPitch() - target) > 0.5) map.easeTo({ pitch: target, duration: 300 });
  }, [view3d, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    try {
      if (relief === 'terrain') map.setTerrain({ source: 'terrain-dem', exaggeration: 1.5 } as any);
      else map.setTerrain(null as any);
    } catch { /* ignore */ }
    setVis(map, 'hillshade-layer', relief === 'hillshade' ? 'visible' : 'none');
  }, [relief, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    applyVisibility(map);
  }, [applyVisibility, ready]);

  const selectedObjects = selectedIds.length && editorObjects ? editorObjects.filter(o => selectedIds.includes(o.id)) : [];

  const handleSave = useCallback(async () => {
    if (!zoneId) return;
    const st = useGisStore.getState();
    const objects = st.editorObjects[zoneId] || [];
    const farolas = objects.filter(o => o.type === 'farola');
    for (const o of farolas) if (o.lumId) { try { await deleteLuminaire(zoneId, o.lumId); } catch { /* ignore */ } }
    if (farolas.length) {
      const payload = farolas.map(o => ({ zone_id: zoneId, lat: o.lat, lon: o.lng, watts: Number(o.attrs?.watts) || 60, arm_len: Number(o.attrs?.armLength) || 1.2, tilt: Number(o.attrs?.tilt) || 15, height_m: o.height }));
      try {
        const created: any[] = await bulkSaveLuminaires(payload);
        farolas.forEach((o, i) => { const c = created?.[i]; if (c) st.updateEditorObject(zoneId, o.id, { lumId: c.id }); });
      } catch (err) { console.error('[CityEditor] sync farolas', err); }
    }
    st.saveEditorObjects(zoneId);
  }, [zoneId]);

  const handleExport = useCallback(async () => {
    if (!zoneId) return;
    const st = useGisStore.getState();
    const inv = st.activePlanningInventory
      ? effectiveInventory(st.activePlanningInventory, st.planningPayload)
      : null;
    const acc = st.accumulatedSelection[zoneId] || {};
    const saved = st.savedSelectionByZone[zoneId] || {};
    const want = Object.keys(acc).length ? acc : Object.keys(saved).length ? saved : null;
    const groupTypes = new Map((inv?.groups || []).map(g => [g.group_ref, g.road_type]));
    const roads = (inv?.targets || [])
      .filter(t => t.geometry && (want ? want[t.target_ref] : true))
      .map(t => ({
        name: targetName(t) ?? `Tramo ${t.source_index + 1}`,
        type: groupTypes.get(t.group_ref) || 'road',
        estWidth: t.estWidth ?? null,
        geom: t.geometry!.map(([lon, lat]) => ({ lon, lat })),
      }));
    const objects = (st.editorObjects[zoneId] || []).map(o => ({
      type: o.type, lng: o.lng, lat: o.lat, width: o.width, length: o.length,
      rotation: o.rotation, label: o.label || o.type,
    }));
    try {
      const blob = await exportDxfObjects(zoneId, roads, objects);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `plano_${zoneId}.dxf`;
      a.click(); URL.revokeObjectURL(url);
    } catch (err) { console.error('[CityEditor] export dxf', err); }
  }, [zoneId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current || !zoneId) return;
    const targets = computeEditorTargets();
    targetsRef.current = targets;
    if (!targets.length) { setNoSel(true); return; }
    paintScene(map, targets);
  }, [planningPayload, zoneId, computeEditorTargets, paintScene, ready]);

  useEffect(() => {
    if (editorTool === 'farolas_route') return;
    routeRef.current = { a: null, b: null };
    setPlacePopup(null);
    setRouteNotice(null);
    if (mapRef.current) updateRouteOverlay(mapRef.current, null, null, null);
  }, [editorTool, updateRouteOverlay]);

  useEffect(() => {
    if (editorTool === 'medir') return;
    measureRef.current = [];
    setMeasure(null);
    if (mapRef.current) updateMeasureOverlay(mapRef.current, [], null);
  }, [editorTool, updateMeasureOverlay]);

  if (!editorOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex bg-[#e6e1d6]">
      <EditorToolbar
        view3d={view3d}
        base={base}
        relief={relief}
        layers={layers}
        onToggleView={() => setView3d(v => !v)}
        onSetBase={setBase}
        onSetRelief={setRelief}
        onReset={() => mapRef.current && fitSection(mapRef.current)}
        onToggleLayer={(k) => setLayers(s => ({ ...s, [k]: !s[k] }))}
        onSave={handleSave}
        onExport={handleExport}
      />
      <div className="relative flex-1">
        <div ref={containerRef} className="absolute inset-0" />
        {measure && editorTool === 'medir' && (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/70 px-2.5 py-1 text-[11px] font-medium text-white"
            style={{ left: measure.x, top: measure.y }}
          >
            📏 {measure.text}
          </div>
        )}
        {noSel && (
          <div className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-black/70 px-3 py-1 text-[11px] text-white">
            {t('editor.noSelection')}
          </div>
        )}
        {routeNotice && (
          <div className="pointer-events-none absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-full bg-black/80 px-3 py-1.5 text-[11px] text-amber-200">
            {routeNotice}
          </div>
        )}
        {buildingsState === 'loading' && (
          <div className="pointer-events-none absolute left-1/2 top-12 z-10 -translate-x-1/2 rounded-full bg-black/70 px-3 py-1 text-[11px] text-white">
            Cargando edificios…
          </div>
        )}
        {buildingsState === 'none' && (
          <div className="pointer-events-none absolute left-1/2 top-12 z-10 -translate-x-1/2 rounded-full bg-black/70 px-3 py-1 text-[11px] text-amber-200">
            Sin datos de edificios en esta zona
          </div>
        )}
        {mapError && (
          <div className="absolute bottom-3 left-1/2 z-10 max-w-md -translate-x-1/2 rounded-lg bg-[#FDECEA] px-3 py-2 text-[11px] text-state-danger">
            {mapError}
          </div>
        )}
        {selectedObjects.length > 0 && (
          <div className="absolute right-2 top-2 z-10 rounded-full bg-black/70 px-2.5 py-1 text-[10px] text-white">
            {selectedObjects.length} {t('editor.selected')}
          </div>
        )}
      </div>
      {(editorRoadRef || (editorObjects && editorObjects.length > 0) || selectedObjects.length > 0) && !placePopup && (
        <div className="h-full w-72 border-l border-salvi-line bg-white">
          {editorRoadRef ? <EditorRoadInspector /> : <ObjectsPanel />}
        </div>
      )}
      {placePopup && (
        <FarolaPlacementPopup
          x={placePopup.x}
          y={placePopup.y}
          path={placePopup.path}
          roadHalfWidth={placePopup.roadHalfWidth}
          label={placePopup.label}
          obstacleRings={placePopup.obstacleRings}
          onClose={() => setPlacePopup(null)}
          onPlace={handlePlaceFarolas}
        />
      )}
    </div>
  );
};

export default CityEditor;
