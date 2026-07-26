import React, { useEffect, useRef, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import type { GisOsmWay, GisPhotometricResult } from '../../types';

const MapView: React.FC<{ mapContainerId?: string }> = ({ mapContainerId = 'gis-map' }) => {
  const mapRef = useRef<any>(null);
  const initDone = useRef(false);

  const zones = useGisStore(s => s.zones);
  const zoneOsm = useGisStore(s => s.zoneOsm);
  const zoneLuminaires = useGisStore(s => s.zoneLuminaires);
  const zonePhotometric = useGisStore(s => s.zonePhotometric);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const selectedLumIds = useGisStore(s => s.selectedLumIds);
  const showCompliance = useGisStore(s => s.showCompliance);
  const toggleLumSelection = useGisStore(s => s.toggleLumSelection);

  /* ── Init map ─────────────────────────────────────────────────────────── */
  useEffect(() => {
    if (initDone.current || !document.getElementById(mapContainerId)) return;
    initDone.current = true;

    const map = new maplibregl.Map({
      container: mapContainerId,
      style: 'https://tiles.openfreemap.org/styles/liberty',
      center: [-3.7038, 40.4168],
      zoom: 6,
      pitch: 50,
      attributionControl: false,
    } as any);

    map.on('load', () => {
      try {
        map.addSource('satellite', { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 19 } as any);
        map.addSource('hillshade', { type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade_Dark/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 13 } as any);
        map.addSource('terrain-dem', { type: 'raster-dem', tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 14, encoding: 'terrarium' } as any);
        map.setTerrain({ source: 'terrain-dem', exaggeration: 2.0 });
      } catch (e) {}

      // Click → select luminaire
      map.on('click', (e: any) => {
        const feats = map.queryRenderedFeatures(e.point);
        const sel = feats?.find((f: any) => f.properties?.lumId);
        if (sel) toggleLumSelection(sel.properties.lumId);
      });

      map.on('mousemove', (e: any) => {
        const feats = map.queryRenderedFeatures(e.point);
        map.getCanvas().style.cursor = feats?.length ? 'pointer' : '';
      });
    });

    mapRef.current = map;
    return () => { map.remove(); initDone.current = false; };
  }, [mapContainerId]);

  /* ── Update layers ────────────────────────────────────────────────────── */
  const rebuildLayers = useCallback(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    // Remove all dynamic layers/sources
    const style = map.getStyle();
    const layers = style?.layers || [];
    layers.forEach((l: any) => {
      if (/^(zone-|ways-|lums-|compl-|sel-)/.test(l.id)) {
        try { map.removeLayer(l.id); } catch {}
      }
    });
    ['zone-bounds', ...zones.map(z => `ways-src-${z.id}`), ...zones.map(z => `lums-src-${z.id}`), ...zones.map(z => `compl-src-${z.id}`), 'sel-lums-src'].forEach((id: string) => {
      try { map.removeSource(id); } catch {}
    });

    // Zone bounds
    const boundsFeats: any[] = [];
    zones.forEach(z => {
      if (z.bounds_polygon?.length) {
        boundsFeats.push({ type: 'Feature', properties: { color: z.color }, geometry: { type: 'Polygon', coordinates: [z.bounds_polygon] } });
      }
    });
    if (boundsFeats.length) {
      map.addSource('zone-bounds', { type: 'geojson', data: { type: 'FeatureCollection', features: boundsFeats } });
      map.addLayer({ id: 'zone-fill', type: 'fill', source: 'zone-bounds', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.08 } });
      map.addLayer({ id: 'zone-outline', type: 'line', source: 'zone-bounds', paint: { 'line-color': ['get', 'color'], 'line-width': 2, 'line-opacity': 0.7 } });
    }

    // Ways per zone
    zones.forEach(z => {
      const osm = zoneOsm[z.id];
      if (!osm?.ways?.length) return;
      const feats = osm.ways.map(w => ({
        type: 'Feature',
        properties: { wayId: w.way_id, roadType: w.road_type, zoneId: z.id },
        geometry: { type: 'LineString', coordinates: w.geometry.map(g => [g[0], g[1]]) },
      }));
      const srcId = `ways-src-${z.id}`;
      map.addSource(srcId, { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
      map.addLayer({
        id: `ways-${z.id}`, type: 'line', source: srcId,
        paint: { 'line-color': z.color, 'line-width': z.id === selectedZoneId ? 4 : 2.5, 'line-opacity': z.id === selectedZoneId ? 0.9 : 0.6 },
      });
    });

    // Luminaires
    zones.forEach(z => {
      const lums = zoneLuminaires[z.id];
      if (!lums?.length) return;
      const feats = lums.map(l => ({
        type: 'Feature',
        properties: { lumId: `${z.id}__${l.id}` },
        geometry: { type: 'Point', coordinates: [l.lon, l.lat] },
      }));
      const srcId = `lums-src-${z.id}`;
      map.addSource(srcId, { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
      map.addLayer({
        id: `lums-${z.id}`, type: 'circle', source: srcId,
        paint: { 'circle-radius': 5, 'circle-color': z.color, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff', 'circle-opacity': 0.9 },
      });
    });

    // Compliance
    zones.forEach(z => {
      const pr = zonePhotometric[z.id];
      if (!pr?.length) return;
      const osm = zoneOsm[z.id];
      const feats = osm?.ways?.map(w => {
        const match = pr.find((r: GisPhotometricResult) =>
          Math.abs(r.road_width - ROAD_CFG[w.road_type]?.width) < 1.5 &&
          Math.abs(r.spacing - (w.luxParams?.spacing || 30)) < 5 &&
          r.lighting_class === (w.luxParams?.lighting_class || 'M3')
        );
        return { type: 'Feature', properties: { cumple: match?.cumple || '' }, geometry: { type: 'LineString', coordinates: w.geometry.map(g => [g[0], g[1]]) } };
      }).filter(Boolean);
      if (feats?.length) {
        const srcId = `compl-src-${z.id}`;
        map.addSource(srcId, { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
        map.addLayer({
          id: `compl-${z.id}`, type: 'line', source: srcId,
          layout: { visibility: showCompliance ? 'visible' : 'none' },
          paint: {
            'line-color': ['case', ['==', ['get', 'cumple'], ''], '#A09A91', ['in', ['downcase', ['get', 'cumple']], ['literal', ['no', 'fail', 'false', '0']]], '#B42318', '#1F7A4D'],
            'line-width': 5, 'line-opacity': 0.7,
          },
        });
      }
    });

    // Selected luminaires highlight
    if (selectedLumIds.size > 0) {
      const feats: any[] = [];
      selectedLumIds.forEach(key => {
        const [zId, lumIdStr] = key.split('__');
        const lum = zoneLuminaires[zId]?.find(l => l.id === parseInt(lumIdStr));
        if (lum) feats.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [lum.lon, lum.lat] } });
      });
      if (feats.length) {
        map.addSource('sel-lums-src', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
        map.addLayer({ id: 'sel-lums', type: 'circle', source: 'sel-lums-src', paint: { 'circle-radius': 7, 'circle-color': '#FFD700', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff', 'circle-opacity': 0.9 } });
      }
    }
  }, [zones, zoneOsm, zoneLuminaires, zonePhotometric, selectedZoneId, selectedLumIds, showCompliance]);

  useEffect(() => { rebuildLayers(); }, [rebuildLayers]);

  /* ── Fly to selected zone ─────────────────────────────────────────────── */
  useEffect(() => {
    if (!selectedZoneId) return;
    const zone = zones.find(z => z.id === selectedZoneId);
    if (!zone) return;
    mapRef.current?.flyTo({ center: [zone.center_lon, zone.center_lat], zoom: zone.zoom || 14, duration: 1000 });
  }, [selectedZoneId]);

  return <div id={mapContainerId} className="absolute inset-0 w-full h-full" style={{ background: '#0d1520' }} />;
};

export default MapView;
