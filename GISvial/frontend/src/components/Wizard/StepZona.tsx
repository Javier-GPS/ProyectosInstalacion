import React, { useState, useCallback } from 'react';
import { useI18n } from '../../i18n';
import { useGisStore } from '../../store/useGisStore';
import { createZone, deleteZone, nominatimSearch, updateZone } from '../../lib/api';
import { useApi } from '../../hooks/useApi';
import type { StatusGranular } from '../../store/types';
import Panel from '../ui/Panel';
import Button from '../ui/Button';
import { TextInput } from '../ui/Field';

const StepZona: React.FC<{ status: StatusGranular; error: string; onRetry: () => void }> = ({ status, error, onRetry }) => {
  const { t } = useI18n();
  const zones = useGisStore(s => s.zones);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const setSelectedZone = useGisStore(s => s.setSelectedZone);
  const addZone = useGisStore(s => s.addZone);
  const removeZone = useGisStore(s => s.removeZone);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const { call: callCreateZone } = useApi<any>();
  const { call: callDeleteZone } = useApi<void>();
  const { call: callUpdateZone } = useApi<any>();

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchCoords, setSearchCoords] = useState<{ lat: number; lon: number; bbox?: string; zoom?: number; boundary?: object; osmRelation?: number } | null>(null);
  const [boundaryZoneId, setBoundaryZoneId] = useState<string | null>(null);
  const [formError, setFormError] = useState('');
  const projectZones = zones.filter(zone => String(zone.project_id) === String(activeProjectId));
  const selectedZone = projectZones.find(zone => zone.id === selectedZoneId);

  const handleCreate = useCallback(async () => {
    if (!newName.trim() || !activeProjectId) return;
    if (!searchCoords?.boundary) {
      setFormError('Selecciona un resultado que tenga límite real.');
      return;
    }
    try {
      setFormError('');
      const payload: any = { name: newName.trim(), project_id: activeProjectId };
      if (searchCoords) {
        payload.center_lat = searchCoords.lat;
        payload.center_lon = searchCoords.lon;
        if (searchCoords.bbox) payload.bbox = searchCoords.bbox;
        if (searchCoords.zoom) payload.zoom = searchCoords.zoom;
        if (searchCoords.boundary) payload.bounds_polygon = searchCoords.boundary;
        if (searchCoords.osmRelation) payload.osm_relation = searchCoords.osmRelation;
      }
      if (boundaryZoneId) {
        await callUpdateZone((signal) => updateZone(boundaryZoneId, {
          center_lat: payload.center_lat, center_lon: payload.center_lon, zoom: payload.zoom,
          bbox: payload.bbox, bounds_polygon: payload.bounds_polygon,
          osm_relation: payload.osm_relation || null, source: 'nominatim',
        }, signal));
        setNewName(''); setSearchCoords(null); setBoundaryZoneId(null); setCreating(false); onRetry();
        return;
      }
      const zone = await callCreateZone((signal) => createZone(payload, signal));
      addZone(zone);
      setNewName('');
      setSearchCoords(null);
      setCreating(false);
      setSelectedZone(zone.id);
    } catch (err) { console.error(err); }
  }, [newName, activeProjectId, searchCoords, boundaryZoneId, callCreateZone, callUpdateZone, addZone, setSelectedZone, onRetry]);

  const handleSearchResult = (r: any) => {
    const boundary = ['Polygon', 'MultiPolygon'].includes(r.geojson?.type) ? r.geojson : undefined;
    if (!boundary) return;
    setNewName(r.display_name?.split(',')[0] || r.display_name || newName);
    setSearchResults([]);
    const lat = parseFloat(r.lat);
    const lon = parseFloat(r.lon);
    if (isNaN(lat) || isNaN(lon)) return;
    const bboxValues = Array.isArray(r.boundingbox) ? r.boundingbox.map(Number) : undefined;
    const bbox = bboxValues?.length === 4 && bboxValues.every(Number.isFinite)
      ? `${bboxValues[0]},${bboxValues[1]},${bboxValues[2]},${bboxValues[3]}`
      : undefined;
    const osmRelation = r.osm_type === 'relation' && Number.isFinite(Number(r.osm_id)) ? Number(r.osm_id) : undefined;
    setSearchCoords({ lat, lon, bbox, zoom: 14, boundary, osmRelation });
    (window as any).__focusGisLocation?.(lat, lon, bboxValues);
  };

  const handleDelete = useCallback(async (id: string, name: string) => {
    if (!confirm(t('zone.deleteConfirm', { name }))) return;
    try {
      await callDeleteZone((signal) => deleteZone(id, signal));
      removeZone(id);
      if (selectedZoneId === id) setSelectedZone(null);
    } catch (err) { console.error(err); }
  }, [selectedZoneId, callDeleteZone, removeZone, setSelectedZone, t]);

  const handleSearch = useCallback(async () => {
    if (!searchQ.trim()) return;
    setSearching(true);
    try {
      const results = await nominatimSearch(searchQ);
      setSearchResults(results || []);
    } catch (err) { console.error(err); }
    finally { setSearching(false); }
  }, [searchQ]);

  return (
    <Panel>
      <div className="flex items-center justify-between border-b border-salvi-line p-4">
        <h2 className="text-base font-semibold text-salvi-black">
          Zonas ({projectZones.length})
        </h2>
        <Button
          variant="primary"
          onClick={() => {
            if (creating && !boundaryZoneId) { setCreating(false); return; }
            setBoundaryZoneId(null); setNewName(''); setSearchQ(''); setSearchResults([]); setSearchCoords(null); setFormError(''); setCreating(true);
          }}
        >
          + {t('zone.create')}
        </Button>
      </div>

      {/* Create zone form */}
      {creating && (
        <div className="space-y-3 border-b border-salvi-line bg-[#FCF9F5]/40 p-4">
          <div className="text-xs font-medium text-salvi-grey">{boundaryZoneId ? 'Actualizar límite real' : 'Nueva zona con límite real'}</div>
          <TextInput
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder={t('zone.name')}
            autoFocus
          />
          <div className="flex gap-1">
            <TextInput
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
              placeholder={t('zone.search')}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
            <Button variant="secondary" onClick={handleSearch} disabled={searching}>🔍</Button>
          </div>
          {searching && <div className="text-xs text-salvi-muted">{t('actions.loading')}</div>}
          {searchResults.length > 0 && (
            <div className="max-h-32 space-y-1 overflow-y-auto">
              {searchResults.map((r, i) => {
                const hasBoundary = ['Polygon', 'MultiPolygon'].includes(r.geojson?.type);
                return (
                <button
                  key={i}
                  disabled={!hasBoundary}
                  className="w-full rounded p-1.5 text-left text-xs hover:bg-salvi-line/50 disabled:cursor-not-allowed disabled:opacity-45"
                  onClick={() => handleSearchResult(r)}
                >
                  {r.display_name} · {hasBoundary ? 'límite disponible' : 'sin límite'}
                </button>
              );})}
            </div>
          )}
          {formError && <p role="alert" className="text-xs text-state-danger">{formError}</p>}
          <div className="flex gap-2 pt-1">
            <Button variant="primary" className="flex-1" onClick={handleCreate}>{boundaryZoneId ? 'Actualizar límite' : t('actions.save')}</Button>
            <Button variant="ghost" onClick={() => { setCreating(false); setBoundaryZoneId(null); setSearchResults([]); setSearchCoords(null); setFormError(''); }}>{t('actions.cancel')}</Button>
          </div>
        </div>
      )}

      {/* Zone list */}
      <div className="flex-1 overflow-y-auto gis-scroll">
        {status === 'loading' && <div className="p-6 text-center text-xs text-salvi-muted">Cargando zonas…</div>}
        {status === 'error' && (
          <div role="alert" className="p-4 text-center text-xs text-state-danger">
            <p>{error || 'No se pudieron cargar las zonas'}</p>
            <Button variant="primary" className="mt-2" onClick={onRetry}>Reintentar</Button>
          </div>
        )}
        {status === 'loaded' && !projectZones.length && <div className="p-6 text-center text-xs text-salvi-muted">Este proyecto no tiene zonas</div>}
        {status === 'loaded' && projectZones.map(zone => (
          <div
            key={zone.id}
            onClick={() => {
              setSelectedZone(zone.id);
            }}
            className={`flex cursor-pointer items-center gap-2 border-b border-salvi-line/50 px-4 py-3 transition-colors ${
              selectedZoneId === zone.id ? 'bg-salvi-black/5' : 'hover:bg-salvi-surface'
            }`}
          >
            <div className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: zone.color }} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-salvi-black">{zone.name}</div>
              <div className="text-xs text-salvi-muted">{zone.type || '—'}</div>
            </div>
            <button
              onClick={e => { e.stopPropagation(); handleDelete(zone.id, zone.name); }}
              className="p-1 text-xs text-salvi-muted hover:text-state-danger"
              title={t('zone.delete')}
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="border-t border-salvi-line p-4">
        {selectedZone && !selectedZone.geometry.boundary && (
          <div role="status" className="mb-2 text-xs text-state-warning">
            <p>Límite real pendiente; el bbox solo se usa para encuadrar el mapa.</p>
            <button
              onClick={() => { setBoundaryZoneId(selectedZone.id); setNewName(selectedZone.name); setSearchQ(selectedZone.name); setSearchCoords(null); setSearchResults([]); setFormError(''); setCreating(true); }}
              className="mt-1 underline"
            >Buscar límite real</button>
          </div>
        )}
        <Button
          variant="primary"
          className="w-full"
          onClick={() => selectedZone && setStepWizard('vias')}
          disabled={!selectedZone || status !== 'loaded'}
        >
          Revisar vías
        </Button>
      </div>
    </Panel>
  );
};

export default StepZona;
