import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { useAuth } from '../../auth/AuthContext';
import { ApiStatusError, cancelLuxJob, createLuxJob, deleteRoadScope, getBuildingWidths, getLuminaires, getLuxJob, getPlanningDraft, getPlanningInventory, getRoadScope, loadPlanningOsm, putPlanningDraft, putRoadScope } from '../../lib/api';
import { useGisStore, ROAD_CFG, type RoadTypeCfg } from '../../store/useGisStore';
import type {
  Etagged, GisDistribution, GisLightingClass, GisPlanningDraft,
  GisPlanningInventoryTarget, GisPlanningLuxParams, GisPlanningPatch,
  GisPlanningPayload, GisRoadWorkScope,
  GisLuxJob,
} from '../../types';
import type { RoadSelectionDraft } from '../../store/types';
import { lineInsideBoundary, roadSelectionIsCurrent } from '../../lib/roadSelection';
import { targetDisplayLabel, targetGroupKey, targetGroupLabel, targetName, targetSelectionKey } from '../../lib/roadNaming';

const EMPTY_PAYLOAD = (): GisPlanningPayload => ({ group_defaults: {}, target_overrides: {} });
const scopeToDraft = (scope: GisRoadWorkScope, etag: string, boundarySignature: string): RoadSelectionDraft => ({
  zone_id: scope.zone_id,
  inventory_hash: scope.base_inventory_hash,
  boundary_signature: boundarySignature,
  status: scope.current ? 'complete' : 'stale',
  area_points: scope.boundary.coordinates[0].slice(0, -1),
  boundary: scope.boundary,
  allowed_group_refs: scope.allowed_group_refs,
  a: { ...scope.a, measure: scope.a.segment_t, coordinate: scope.path[0] },
  b: { ...scope.b, measure: scope.b.segment_t, coordinate: scope.path[scope.path.length - 1] },
  path: scope.path,
  length_m: scope.length_m,
  member_count: scope.members.length,
  etag,
});
const UNE_CLASSES: GisLightingClass[] = [
  'M1', 'M2', 'M3', 'M4', 'M5', 'M6',
  'C0', 'C1', 'C2', 'C3', 'C4', 'C5',
  'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7',
];
const DISTRIBUTIONS: { value: GisDistribution; label: string }[] = [
  { value: 'unilateral_r', label: 'Unilateral derecha' },
  { value: 'unilateral_l', label: 'Unilateral izquierda' },
  { value: 'bilateral_pareado', label: 'Bilateral' },
  { value: 'bilateral_tresbolillo', label: 'Bilateral tresbolillo' },
  { value: 'centrada_mediana', label: 'Centrada en mediana' },
  { value: 'mediana_compartida', label: 'Sin luminarias (mediana compartida)' },
];
const LUX_FIELDS: { key: keyof GisPlanningLuxParams; label: string; type: 'number' | 'text' }[] = [
  { key: 'poleH', label: 'Altura poste (m)', type: 'number' },
  { key: 'armLen', label: 'Longitud brazo (m)', type: 'number' },
  { key: 'setback', label: 'Retranqueo (m)', type: 'number' },
  { key: 'tilt', label: 'Inclinación (°)', type: 'number' },
  { key: 'sidewalkL', label: 'Acera izquierda (m)', type: 'number' },
  { key: 'sidewalkR', label: 'Acera derecha (m)', type: 'number' },
  { key: 'medianW', label: 'Mediana (m)', type: 'number' },
  { key: 'maintFactor', label: 'Factor mantenimiento', type: 'number' },
  { key: 'brand', label: 'Fabricante', type: 'text' },
  { key: 'range', label: 'Gama', type: 'text' },
  { key: 'diffuser', label: 'Difusor', type: 'text' },
  { key: 'optic', label: 'Óptica', type: 'text' },
  { key: 'ledType', label: 'Tipo LED', type: 'text' },
  { key: 'power', label: 'Potencia (W)', type: 'number' },
  { key: 'colorTemp', label: 'Temperatura color (K)', type: 'number' },
  { key: 'cri', label: 'CRI', type: 'number' },
];

type Resource =
  | { kind: 'loading' }
  | { kind: 'missing' }
  | { kind: 'absent' }
  | { kind: 'current'; etag: string }
  | { kind: 'stale'; etag: string }
  | { kind: 'conflict' }
  | { kind: 'error' };

const has = (value: object | null | undefined, key: PropertyKey) => !!value && Object.prototype.hasOwnProperty.call(value, key);

const PlanningFields: React.FC<{
  patch: GisPlanningPatch;
  inherited?: GisPlanningPatch;
  onChange: (patch: GisPlanningPatch) => void;
}> = ({ patch, inherited, onChange }) => {
  const override = inherited !== undefined;
  const effective = <K extends keyof GisPlanningPatch>(key: K) => has(patch, key) ? patch[key] : inherited?.[key];
  const setField = <K extends keyof GisPlanningPatch>(key: K, value: GisPlanningPatch[K] | undefined) => {
    const next = { ...patch };
    if (value === undefined) delete next[key];
    else (next as any)[key] = value;
    onChange(next);
  };
  const patchLux = patch.luxParams && typeof patch.luxParams === 'object' ? patch.luxParams : {};
  const inheritedLux = inherited?.luxParams && typeof inherited.luxParams === 'object' ? inherited.luxParams : {};
  const setLux = (key: keyof GisPlanningLuxParams, value: string | number | null | undefined) => {
    const nextLux = { ...patchLux };
    if (value === undefined) delete nextLux[key];
    else (nextLux as any)[key] = value;
    const next = { ...patch };
    if (Object.keys(nextLux).length) next.luxParams = nextLux;
    else delete next.luxParams;
    onChange(next);
  };

  return (
    <div className="space-y-2">
      <label className="block text-[11px] text-salvi-muted">
        Clase UNE-EN 13201
        <select
          value={(effective('lighting_class') as string | null | undefined) ?? ''}
          onChange={e => setField('lighting_class', e.target.value ? e.target.value as GisLightingClass : override ? null : undefined)}
          className="mt-0.5 w-full rounded border border-salvi-line bg-white px-2 py-1 text-xs"
        >
          <option value="">Sin asignar</option>
          {UNE_CLASSES.map(value => <option key={value} value={value}>{value}</option>)}
        </select>
        {override && has(patch, 'lighting_class') && <button onClick={() => setField('lighting_class', undefined)} className="mt-1 text-[10px] text-state-info">Usar valor del tipo</button>}
      </label>
      <label className="block text-[11px] text-salvi-muted">
        Interdistancia (m)
        <input
          type="number" min="0" step="0.1"
          value={(effective('spacing') as number | null | undefined) ?? ''}
          onChange={e => setField('spacing', e.target.value === '' ? override ? null : undefined : Number(e.target.value))}
          className="mt-0.5 w-full rounded border border-salvi-line px-2 py-1 text-xs"
        />
        {override && has(patch, 'spacing') && <button onClick={() => setField('spacing', undefined)} className="mt-1 text-[10px] text-state-info">Usar valor del tipo</button>}
      </label>
      <label className="block text-[11px] text-salvi-muted">
        Distribución
        <select
          value={(effective('distribution') as string | null | undefined) ?? ''}
          onChange={e => setField('distribution', e.target.value ? e.target.value as GisDistribution : override ? null : undefined)}
          className="mt-0.5 w-full rounded border border-salvi-line bg-white px-2 py-1 text-xs"
        >
          <option value="">Sin asignar</option>
          {DISTRIBUTIONS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        {override && has(patch, 'distribution') && <button onClick={() => setField('distribution', undefined)} className="mt-1 text-[10px] text-state-info">Usar valor del tipo</button>}
      </label>
      <details>
        <summary className="cursor-pointer text-[11px] font-medium text-salvi-grey">Parámetros Lux Studio</summary>
        <div className="mt-2 grid grid-cols-2 gap-2">
          {LUX_FIELDS.map(field => {
            const own = has(patchLux, field.key);
            const value = own ? patchLux[field.key] : inheritedLux[field.key];
            return (
              <label key={field.key} className="text-[10px] text-salvi-muted">
                {field.label}
                <input
                  type={field.type}
                  min={field.type === 'number' && field.key !== 'tilt' ? 0 : undefined}
                  max={field.key === 'cri' ? 100 : undefined}
                  value={(value as string | number | null | undefined) ?? ''}
                  onChange={e => setLux(field.key, e.target.value === '' ? override ? null : undefined : field.type === 'number' ? Number(e.target.value) : e.target.value)}
                  className="mt-0.5 w-full rounded border border-salvi-line px-1.5 py-1 text-[11px]"
                />
                {override && own && <button onClick={() => setLux(field.key, undefined)} className="text-[9px] text-state-info">Heredar</button>}
              </label>
            );
          })}
        </div>
      </details>
    </div>
  );
};

const StepVias: React.FC = () => {
  const { t } = useI18n();
  const { user } = useAuth();
  const zones = useGisStore(s => s.zones);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const activeProject = useGisStore(s => s.projects.find(project => project.id === s.activeProjectId));
  const inventory = useGisStore(s => s.activePlanningInventory);
  const visibility = useGisStore(s => s.roadTypeVisibility);
  const setInventory = useGisStore(s => s.setActivePlanningInventory);
  const setStorePayload = useGisStore(s => s.setPlanningPayload);
  const storePlanningPayload = useGisStore(s => s.planningPayload);
  const setStoreBasePayload = useGisStore(s => s.setPlanningBasePayload);
  const setPlanningDirty = useGisStore(s => s.setPlanningDirty);
  const confirmPlanningLeave = useGisStore(s => s.confirmPlanningLeave);
  const savedStorePayload = useGisStore(s => s.planningSavedPayload);
  const discardVersion = useGisStore(s => s.planningDiscardVersion);
  const setVisibility = useGisStore(s => s.setRoadTypeVisibility);
  const roadSelectionByZone = useGisStore(s => s.roadSelectionByZone);
  const setRoadSelection = useGisStore(s => s.setRoadSelection);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const selectedTargetRef = useGisStore(s => s.selectedTargetRef);
  const selectedStreetName = useGisStore(s => s.selectedStreetName);
  const setSelectedSegment = useGisStore(s => s.setSelectedSegment);
  const setZoneLuminaires = useGisStore(s => s.setZoneLuminaires);
  const accumulatedSelection = useGisStore(s => s.accumulatedSelection);
  const toggleTargetSelection = useGisStore(s => s.toggleTargetSelection);
  const toggleStreetSelection = useGisStore(s => s.toggleStreetSelection);
  const clearAccumulatedSelection = useGisStore(s => s.clearAccumulatedSelection);
  const setAccumulatedSelection = useGisStore(s => s.setAccumulatedSelection);
  const [resource, setResource] = useState<Resource>({ kind: 'loading' });
  const [payload, setPayload] = useState<GisPlanningPayload>(EMPTY_PAYLOAD);
  const [basePayload, setBasePayload] = useState<GisPlanningPayload>(EMPTY_PAYLOAD);
  const [message, setMessage] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [expandedStreet, setExpandedStreet] = useState<string | null>(null);
  const [selectedTarget, setSelectedTarget] = useState<GisPlanningInventoryTarget | null>(null);
  const [query, setQuery] = useState('');
  const [staleReady, setStaleReady] = useState(false);
  const [loadingOsm, setLoadingOsm] = useState(false);
  const [scopeBusy, setScopeBusy] = useState(false);
  const [selectionExpandedStreet, setSelectionExpandedStreet] = useState<string | null>(null);
  const [buildingStatus, setBuildingStatus] = useState<string | null>(null);
  const [luxJob, setLuxJob] = useState<GisLuxJob | null>(null);
  const luxJobEtagRef = useRef<string | undefined>();
  const [luxJobError, setLuxJobError] = useState('');
  const [luxStarting, setLuxStarting] = useState(false);
  const [luxMode, setLuxMode] = useState<'calculate' | 'optimize'>('optimize');
  const luxIntentIdRef = useRef<string>();
  const osmLoadRef = useRef<AbortController | null>(null);
  const inventoryEtagRef = useRef<string | null>(null);
  const legacyRefreshAttemptedRef = useRef(new Set<string>());

  const zone = zones.find(z => z.id === selectedZoneId);
  const roadSelection = selectedZoneId ? roadSelectionByZone[selectedZoneId] : undefined;
  const dirty = JSON.stringify(payload) !== JSON.stringify(basePayload);
  const zoneSelection = selectedZoneId ? (accumulatedSelection[selectedZoneId] || {}) : {};
  const selectedCount = Object.keys(zoneSelection).length;
  const calculableTargetRefs = inventory?.targets
    .filter(target => zoneSelection[target.target_ref] && target.geometry)
    .map(target => target.target_ref) || [];
  const nonCalculableSelectedCount = selectedCount - calculableTargetRefs.length;
  const totalTargetCount = inventory?.targets.length ?? 0;
  const projectEditable = activeProject?.access_role !== 'viewer' && user?.role !== 'VIEWER';

  useEffect(() => {
    setPlanningDirty(dirty);
    return () => setPlanningDirty(false);
  }, [dirty, setPlanningDirty]);

  useEffect(() => {
    if (!discardVersion) return;
    setPayload(savedStorePayload);
    setBasePayload(savedStorePayload);
    setSelectedTarget(null);
  }, [discardVersion, savedStorePayload]);

  // The map popup edits the shared store directly; keep the form payload in sync.
  useEffect(() => {
    if (JSON.stringify(storePlanningPayload) !== JSON.stringify(payload)) setPayload(storePlanningPayload);
  }, [storePlanningPayload]);

  useEffect(() => {
    osmLoadRef.current?.abort();
    if (!selectedZoneId) {
      setInventory(null);
      setStoreBasePayload(EMPTY_PAYLOAD());
      setBuildingStatus(null);
      return;
    }
    const controller = new AbortController();
    let live = true;
    const previousInventory = useGisStore.getState().activePlanningInventory;
    setResource({ kind: 'loading' });
    setStaleReady(false);
    setBuildingStatus(null);
    setMessage('');
    setSelectedTarget(null);
    setInventory(null);
    setStoreBasePayload(EMPTY_PAYLOAD());

    (async () => {
      try {
        // ── Step 1: Load inventory (with ETag for 304 caching) ─────
        const inventoryResult = await getPlanningInventory(selectedZoneId, inventoryEtagRef.current || undefined, undefined, controller.signal);
        let nextInventory = inventoryResult.data;
        const newEtag = inventoryResult.etag;
        if (newEtag) inventoryEtagRef.current = newEtag;

        if (!nextInventory) {
          if (live) setResource({ kind: 'missing' });
          return;
        }

        // Cached ways from before the naming contract are refreshed in the
        // background by a separate effect; the panel renders legacy data first.

        // ── Step 2: Draft + RoadScope en PARALELO ──────────────────
        let draftResult: Etagged<GisPlanningDraft | null> | null = null;
        let scopeResult: Etagged<GisRoadWorkScope | null> | null = null;
        try {
          const [dr, sr] = await Promise.all([
            getPlanningDraft(selectedZoneId, controller.signal)
              .catch(e => { if (e instanceof ApiStatusError && e.status === 404) return { data: null, etag: '' }; throw e; }),
            getRoadScope(selectedZoneId, controller.signal)
              .catch(e => { if (e instanceof ApiStatusError && e.status === 204) return { data: null, etag: '' }; throw e; }),
          ]);
          draftResult = dr as Etagged<GisPlanningDraft | null>;
          scopeResult = sr as Etagged<GisRoadWorkScope | null>;
        } catch (error) {
          if (!(error instanceof ApiStatusError) || error.status !== 404) throw error;
        }

        // ── Step 3: Check building widths status ────────────────────
        try {
          const bw = await getBuildingWidths(selectedZoneId, controller.signal);
          if (live) setBuildingStatus(bw.status);
          // If computing, poll every 5s until available, then refresh inventory
          if (bw.status === 'computing' && live) {
            const poll = async () => {
              while (live) {
                await new Promise(r => setTimeout(r, 5000));
                if (!live) return;
                try {
                  const res = await getBuildingWidths(selectedZoneId, controller.signal);
                  if (!live) return;
                  setBuildingStatus(res.status);
                  if (res.status === 'available') {
                    // Force-refresh inventory to get Catastro-enriched widths
                    const refreshed = await getPlanningInventory(selectedZoneId, undefined, true, controller.signal);
                    if (refreshed.data && live) {
                      setInventory(refreshed.data);
                       setMessage('🏛 Anchos de vía actualizados con datos del Catastro');
                    }
                    return;
                  }
                  if (res.status === 'unavailable' || res.status === 'error') return;
                } catch {
                  return;
                }
              }
            };
            poll();
          }
        } catch {
          // Building widths check failed, non-fatal
        }

        if (!live) return;
        if (previousInventory && previousInventory.base_inventory_hash !== nextInventory.base_inventory_hash) {
          clearAccumulatedSelection(selectedZoneId);
        }
        setInventory(nextInventory);

        // ── Log data source summary ─────────────────────────────────
        const srcCounts: Record<string, number> = {};
        for (const t of nextInventory.targets) {
          const src = t.widthSrc || 'unknown';
          srcCounts[src] = (srcCounts[src] || 0) + 1;
        }
        const srcLabels: Record<string, string> = { osm_width: '📏 OSM', lanes: '🔢 carriles', catastro: '🏛 Catastro', default: '⚠ default', unknown: '❓' };
        console.log('┌── SALVI GIS: Inventario cargado ────────────────');
        console.log(`│ Zona:       ${nextInventory.zone_id}`);
        console.log(`│ Total vías: ${nextInventory.targets.length}`);
        for (const [src, n] of Object.entries(srcCounts)) {
          const pct = (n / nextInventory.targets.length * 100).toFixed(0);
          console.log(`│   ${srcLabels[src] || src}: ${n} (${pct}%)`);
        }
        console.log('└──────────────────────────────────────────────────');

        const localScope = useGisStore.getState().roadSelectionByZone[selectedZoneId];
        const zoneBoundary = useGisStore.getState().zones.find(item => item.id === selectedZoneId)?.geometry.boundary;
        if (scopeResult?.data && (!localScope || ['complete', 'stale', 'invalid'].includes(localScope.status))) {
          setRoadSelection(selectedZoneId, scopeToDraft(scopeResult.data, scopeResult.etag, JSON.stringify(zoneBoundary)));
        }
        if (!draftResult || !draftResult.data) {
          const empty = EMPTY_PAYLOAD();
          setPayload(empty); setBasePayload(empty); setStoreBasePayload(empty);
          setResource({ kind: 'absent' });
        } else if (draftResult.data.base_inventory_hash !== nextInventory.base_inventory_hash) {
          setPayload(EMPTY_PAYLOAD()); setBasePayload(EMPTY_PAYLOAD()); setStoreBasePayload(EMPTY_PAYLOAD());
          setStaleReady(true);
          setResource({ kind: 'stale', etag: draftResult.etag });
        } else {
          setPayload(draftResult.data.payload); setBasePayload(draftResult.data.payload); setStoreBasePayload(draftResult.data.payload);
          setResource({ kind: 'current', etag: draftResult.etag });
        }
      } catch (error) {
        if (!live || (error as Error).name === 'AbortError') return;
        const status = error instanceof ApiStatusError ? ` (HTTP ${error.status})` : '';
        setMessage(`${(error as Error).message || 'No se pudo cargar la planificación'}${status}`);
        setResource({ kind: 'error' });
      }
    })();
    return () => { live = false; controller.abort(); };
  }, [selectedZoneId, reloadKey, setInventory, setRoadSelection, setStoreBasePayload, clearAccumulatedSelection]);

  useEffect(() => () => osmLoadRef.current?.abort(), []);

  // Cached ways from before the naming contract need one forced refresh.
  // Runs in the background so the panel never blocks on Overpass and a
  // failure can never take the whole planning panel to the error state.
  useEffect(() => {
    if (!selectedZoneId || !inventory?.source_needs_refresh) return;
    if (legacyRefreshAttemptedRef.current.has(selectedZoneId)) return;
    legacyRefreshAttemptedRef.current.add(selectedZoneId);
    const previousHash = inventory.base_inventory_hash;
    let alive = true;
    const controller = new AbortController();
    setMessage('Actualizando etiquetado OSM…');
    (async () => {
      try {
        await loadPlanningOsm(selectedZoneId, controller.signal, true);
        const refreshed = await getPlanningInventory(selectedZoneId, undefined, true, controller.signal);
        if (!alive) return;
        if (refreshed.data) {
          if (refreshed.data.base_inventory_hash !== previousHash) clearAccumulatedSelection(selectedZoneId);
          setInventory(refreshed.data);
          inventoryEtagRef.current = refreshed.etag || '';
          if (alive) setMessage('');
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') legacyRefreshAttemptedRef.current.delete(selectedZoneId);
        console.warn('Could not refresh legacy OSM naming data', error);
        if (alive) setMessage('No se pudo actualizar el etiquetado OSM antiguo; se muestran los datos anteriores.');
      }
    })();
    return () => { alive = false; controller.abort(); };
  }, [selectedZoneId, inventory?.source_needs_refresh, setInventory, clearAccumulatedSelection]);

  useEffect(() => {
    if (!selectedZoneId) return;
    const controller = new AbortController();
    getLuminaires(selectedZoneId, controller.signal)
      .then(luminaires => { if (!controller.signal.aborted) setZoneLuminaires(selectedZoneId, luminaires); })
      .catch(() => { /* Existing map data is allowed to remain empty. */ });
    return () => controller.abort();
  }, [selectedZoneId, setZoneLuminaires]);

  useEffect(() => {
    setLuxJob(null);
    luxJobEtagRef.current = undefined;
    setLuxJobError('');
    luxIntentIdRef.current = undefined;
    if (!activeProjectId || !selectedZoneId) return;
    const storageKey = `gis-lux-job:${activeProjectId}:${selectedZoneId}`;
    const savedJobId = window.localStorage.getItem(storageKey);
    if (!savedJobId) return;
    let alive = true;
    getLuxJob(String(activeProjectId), savedJobId)
      .then(result => {
        if (alive && result.data) {
          luxJobEtagRef.current = result.etag;
          setLuxJob(result.data);
        }
      })
      .catch(error => {
        if (error instanceof ApiStatusError && error.status === 404) window.localStorage.removeItem(storageKey);
      });
    return () => { alive = false; };
  }, [activeProjectId, selectedZoneId]);

  useEffect(() => {
    if (!luxJob || !activeProjectId) return;
    let alive = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const result = await getLuxJob(String(activeProjectId), luxJob.id, luxJobEtagRef.current);
        if (!alive) return;
        if (result.etag) {
          luxJobEtagRef.current = result.etag;
        }
        if (result.data) {
          setLuxJob(result.data);
          if (['succeeded', 'partial', 'failed', 'cancelled', 'unknown'].includes(result.data.state)) {
            if (selectedZoneId && result.data.succeeded > 0) {
              const lums = await getLuminaires(selectedZoneId);
              if (alive) setZoneLuminaires(selectedZoneId, lums);
            }
            return;
          }
        }
      } catch (error) {
        if (alive) setLuxJobError((error as Error).message || 'No se pudo consultar el progreso');
      }
      if (alive) timer = window.setTimeout(poll, 1800);
    };
    poll();
    return () => { alive = false; if (timer) window.clearTimeout(timer); };
  }, [luxJob?.id, activeProjectId, selectedZoneId, setZoneLuminaires]);

  useEffect(() => {
    if (!selectedZoneId || !inventory || !roadSelection || ['draw_area', 'invalid', 'stale'].includes(roadSelection.status)) return;
    if (!roadSelectionIsCurrent(roadSelection, inventory, zone?.geometry.boundary)) {
      setRoadSelection(selectedZoneId, { ...roadSelection, status: 'stale', error: undefined });
    }
  }, [selectedZoneId, inventory, roadSelection, zone?.geometry.boundary, setRoadSelection]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const updatePayload = (next: GisPlanningPayload) => { setPayload(next); setStorePayload(next); setMessage(''); };
  const setGroupPatch = (groupRef: string, patch: GisPlanningPatch) => {
    const groups = { ...payload.group_defaults };
    if (Object.keys(patch).length) groups[groupRef] = patch; else delete groups[groupRef];
    updatePayload({ ...payload, group_defaults: groups });
  };
  const setTargetPatch = (targetRef: string, patch: GisPlanningPatch) => {
    const targets = { ...payload.target_overrides };
    if (Object.keys(patch).length) targets[targetRef] = patch; else delete targets[targetRef];
    updatePayload({ ...payload, target_overrides: targets });
  };

  const save = async () => {
    if (!selectedZoneId || !inventory || saving || !dirty || (resource.kind !== 'absent' && resource.kind !== 'current')) return;
    setSaving(true); setMessage('');
    try {
      const result = await putPlanningDraft(
        selectedZoneId, 'update', inventory.base_inventory_hash, payload,
        resource.kind === 'absent' ? { ifNoneMatch: '*' } : { ifMatch: resource.etag },
      );
      setPayload(result.data.payload); setBasePayload(result.data.payload); setStoreBasePayload(result.data.payload);
      setResource({ kind: 'current', etag: result.etag });
      setMessage('Planificación guardada');
    } catch (error) {
      if (error instanceof ApiStatusError && error.status === 409 && resource.kind === 'current') {
        setStaleReady(false);
        setResource({ kind: 'stale', etag: resource.etag });
      }
      else if (error instanceof ApiStatusError && error.status === 412) setResource({ kind: 'conflict' });
      setMessage((error as Error).message || 'No se pudo guardar');
    } finally { setSaving(false); }
  };

  const recreate = async () => {
    if (!selectedZoneId || !inventory || resource.kind !== 'stale' || !staleReady || !window.confirm('La red viaria ha cambiado. ¿Descartar la planificación anterior y empezar vacía?')) return;
    setSaving(true); setMessage('');
    try {
      const empty = EMPTY_PAYLOAD();
      const result = await putPlanningDraft(selectedZoneId, 'recreate', inventory.base_inventory_hash, empty, { ifMatch: resource.etag });
      setPayload(empty); setBasePayload(empty); setStoreBasePayload(empty);
      setResource({ kind: 'current', etag: result.etag });
      setMessage('Planificación recreada');
    } catch (error) { setMessage((error as Error).message || 'No se pudo recrear'); }
    finally { setSaving(false); }
  };
  const navigate = (step: 'zona' | 'luminarias') => {
    if (!confirmPlanningLeave()) return;
    setStepWizard(step);
  };
  const reload = () => {
    if (!confirmPlanningLeave()) return;
    if (selectedZoneId) legacyRefreshAttemptedRef.current.delete(selectedZoneId);
    setReloadKey(v => v + 1);
  };
  const loadOsm = async () => {
    if (!selectedZoneId || loadingOsm) return;
    const controller = new AbortController();
    osmLoadRef.current = controller;
    setLoadingOsm(true); setMessage('');
    try {
      await loadPlanningOsm(selectedZoneId, controller.signal);
      setReloadKey(value => value + 1);
    } catch (error) {
      if ((error as Error).name === 'AbortError') return;
      setMessage((error as Error).message || 'No se pudieron cargar las vías OSM');
    } finally {
      if (osmLoadRef.current === controller) {
        osmLoadRef.current = null;
        setLoadingOsm(false);
      }
    }
  };
  const startArea = () => {
    if (!selectedZoneId || !inventory || !zone?.geometry.boundary) return;
    setRoadSelection(selectedZoneId, {
      zone_id: selectedZoneId,
      inventory_hash: inventory.base_inventory_hash,
      boundary_signature: JSON.stringify(zone.geometry.boundary),
      status: 'draw_area',
      area_points: [],
      allowed_group_refs: inventory.groups.filter(group => visibility[group.group_ref] !== false).map(group => group.group_ref),
      etag: roadSelection?.etag,
    });
  };
  const closeArea = () => {
    if (!selectedZoneId || !zone?.geometry.boundary || !roadSelection || roadSelection.area_points.length < 3) return;
    const ring = [...roadSelection.area_points, roadSelection.area_points[0]];
    if (!lineInsideBoundary(ring, zone.geometry.boundary)) {
      setRoadSelection(selectedZoneId, { ...roadSelection, error: 'El área completa debe quedar dentro del límite real de la zona.' });
      return;
    }
    setRoadSelection(selectedZoneId, {
      ...roadSelection,
      boundary: { type: 'Polygon', coordinates: [ring] },
      status: 'pick_a',
      a: undefined,
      b: undefined,
      path: undefined,
      length_m: undefined,
      error: undefined,
    });
  };
  const cancelArea = () => {
    if (!selectedZoneId || !roadSelection) return;
    if (roadSelection.etag) {
      setRoadSelection(selectedZoneId, { ...roadSelection, status: 'invalid' });
      setReloadKey(value => value + 1);
    } else setRoadSelection(selectedZoneId, null);
  };
  const saveScope = async () => {
    if (!selectedZoneId || !inventory || !zone?.geometry.boundary || !roadSelection?.boundary || !roadSelection.a || !roadSelection.b || scopeBusy) return;
    setScopeBusy(true);
    setRoadSelection(selectedZoneId, { ...roadSelection, status: 'saving', error: undefined });
    try {
      const anchor = (value: NonNullable<RoadSelectionDraft['a']>) => ({ target_ref: value.target_ref, segment_index: value.segment_index, segment_t: value.segment_t });
      const result = await putRoadScope(
        selectedZoneId,
        inventory.base_inventory_hash,
        roadSelection.boundary,
        roadSelection.allowed_group_refs || [],
        anchor(roadSelection.a),
        anchor(roadSelection.b),
        roadSelection.etag ? { ifMatch: roadSelection.etag } : { ifNoneMatch: '*' },
      );
      setRoadSelection(selectedZoneId, scopeToDraft(result.data, result.etag, JSON.stringify(zone.geometry.boundary)));
      setMessage('Ámbito y recorrido guardados');
    } catch (error) {
      const conflict = error instanceof ApiStatusError && error.status === 412;
      setRoadSelection(selectedZoneId, { ...roadSelection, status: conflict ? 'invalid' : 'ready', error: conflict ? 'Otro usuario modificó el ámbito. Recarga antes de guardar.' : (error as Error).message });
    } finally { setScopeBusy(false); }
  };
  const removeScope = async () => {
    if (!selectedZoneId || !roadSelection?.etag || scopeBusy || !window.confirm('¿Eliminar el área y el recorrido guardados?')) return;
    setScopeBusy(true);
    try {
      await deleteRoadScope(selectedZoneId, roadSelection.etag);
      setRoadSelection(selectedZoneId, null);
      setMessage('Ámbito eliminado');
    } catch (error) {
      setRoadSelection(selectedZoneId, { ...roadSelection, error: (error as Error).message || 'No se pudo eliminar' });
    } finally { setScopeBusy(false); }
  };
  const recalculateScope = () => {
    if (!selectedZoneId || !inventory || !zone?.geometry.boundary || !roadSelection?.boundary) return;
    setRoadSelection(selectedZoneId, {
      ...roadSelection,
      inventory_hash: inventory.base_inventory_hash,
      boundary_signature: JSON.stringify(zone.geometry.boundary),
      status: 'pick_a',
      allowed_group_refs: inventory.groups.filter(group => visibility[group.group_ref] !== false).map(group => group.group_ref),
      a: undefined,
      b: undefined,
      path: undefined,
      length_m: undefined,
      error: undefined,
    });
  };

  const startLuxJob = async () => {
    if (!activeProjectId || !selectedZoneId || !inventory || !calculableTargetRefs.length || luxStarting || dirty || !projectEditable) return;
    if (!['absent', 'current'].includes(resource.kind)) return;
    setLuxStarting(true); setLuxJobError('');
    const intentId = luxIntentIdRef.current || (typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
    luxIntentIdRef.current = intentId;
    try {
      const result = await createLuxJob(
        String(activeProjectId), selectedZoneId, calculableTargetRefs,
        inventory.base_inventory_hash, intentId, luxMode,
      );
      luxJobEtagRef.current = undefined;
      setLuxJob(result);
      window.localStorage.setItem(`gis-lux-job:${activeProjectId}:${selectedZoneId}`, result.id);
      luxIntentIdRef.current = undefined;
    } catch (error) {
      setLuxJobError((error as Error).message || 'No se pudo iniciar el cálculo Lux');
      if (error instanceof ApiStatusError) {
        luxIntentIdRef.current = undefined;
        if (error.status === 409 && /STALE|stale|INVENTORY/.test(error.message)) {
          setResource({ kind: 'stale', etag: 'etag' in resource ? resource.etag : '' });
          clearAccumulatedSelection(selectedZoneId);
          setLuxJobError('El inventario o la configuración cambió. Recarga y vuelve a seleccionar los tramos.');
        }
      }
    } finally { setLuxStarting(false); }
  };

  const cancelCurrentLuxJob = async () => {
    if (!luxJob || !activeProjectId) return;
    try {
      const result = await cancelLuxJob(String(activeProjectId), luxJob.id);
      setLuxJob(result);
    } catch (error) { setLuxJobError((error as Error).message || 'No se pudo cancelar'); }
  };

  const streetSelState = (targets: GisPlanningInventoryTarget[]): { all: boolean; some: boolean; none: boolean } => {
    const selectable = targets.filter(target => target.geometry);
    const all = selectable.length > 0 && selectable.every(t => zoneSelection[t.target_ref]);
    return { all, some: selectable.some(t => zoneSelection[t.target_ref]), none: !selectable.some(t => zoneSelection[t.target_ref]) };
  };

  const streetsByGroup = useMemo(() => {
    const result = new Map<string, Map<string, GisPlanningInventoryTarget[]>>();
    inventory?.targets.forEach(target => {
      const streets = result.get(target.group_ref) || new Map<string, GisPlanningInventoryTarget[]>();
      const key = targetGroupKey(target);
      const targets = streets.get(key);
      if (targets) targets.push(target); else streets.set(key, [target]);
      result.set(target.group_ref, streets);
    });
    return result;
  }, [inventory]);

  const flyToStreet = useCallback((streetName: string, targets: GisPlanningInventoryTarget[]) => {
    const t = targets.find(t => t.geometry && t.geometry.length > 0);
    if (!t?.geometry) return;
    const coords = t.geometry;
    const lat = coords.reduce((s, c) => s + c[1], 0) / coords.length;
    const lon = coords.reduce((s, c) => s + c[0], 0) / coords.length;
    (window as any).__focusGisLocation?.(lat, lon);
  }, []);

  if (!zone) return <div className="gis-panel rounded-xl p-6 text-center text-sm text-salvi-muted">Selecciona una zona primero</div>;
  if (resource.kind === 'loading') return <div className="gis-panel rounded-xl p-6 text-center text-sm text-salvi-muted">Cargando vías y planificación…</div>;
  if (resource.kind === 'missing') return (
    <div className="gis-panel rounded-xl p-5 text-center text-sm text-salvi-grey">
      <p>Esta zona todavía no tiene vías OSM.</p>
      {message && <p role="alert" className="mt-2 text-xs text-state-danger">{message}</p>}
      <button onClick={loadOsm} disabled={loadingOsm} className="mt-3 rounded bg-salvi-black px-3 py-1.5 text-xs text-white disabled:opacity-50">
        {loadingOsm ? 'Consultando OpenStreetMap…' : 'Cargar vías OSM'}
      </button>
    </div>
  );
  if (resource.kind === 'error' || !inventory) return (
    <div className="gis-panel rounded-xl p-5 text-center text-sm text-state-danger">
      <p>{message || 'No se pudo cargar la planificación'}</p>
      <button onClick={() => setReloadKey(v => v + 1)} className="mt-3 rounded bg-salvi-black px-3 py-1 text-xs text-white">Reintentar</button>
    </div>
  );

  const editable = resource.kind === 'absent' || resource.kind === 'current';
  const normalizedQuery = query.trim().toLowerCase();
  const groups = inventory.groups.filter(group => {
    if (!normalizedQuery || (group.road_type || 'sin tipo').toLowerCase().includes(normalizedQuery)) return true;
    return [...(streetsByGroup.get(group.group_ref)?.entries() || [])].some(([key, targets]) =>
      key.toLowerCase().includes(normalizedQuery) || targetGroupLabel(targets[0]).toLowerCase().includes(normalizedQuery),
    );
  });

  return (
    <div className="gis-panel flex max-h-full flex-col overflow-hidden rounded-xl">
      <div className="border-b border-salvi-line p-3">
        <h2 className="truncate text-sm font-semibold text-salvi-black">{zone.name}</h2>
        <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-salvi-muted">
          <span>{inventory.counts.distinct_name_count ?? inventory.counts.named_street_count} nombres OSM</span>
          <span>{inventory.counts.segment_count} tramos OSM</span>
          <span>{inventory.counts.without_osm_name_count ?? inventory.counts.unnamed_segment_count} sin `name` OSM</span>
          {!!inventory.counts.ref_only_count && <span>{inventory.counts.ref_only_count} solo referencia</span>}
          {!!inventory.counts.explicit_noname_count && <span>{inventory.counts.explicit_noname_count} declarados sin nombre</span>}
          <span>{inventory.counts.geometry_unavailable} sin geometría</span>
          {!!nonCalculableSelectedCount && <span className="text-state-warning">{nonCalculableSelectedCount} no calculables</span>}
          {buildingStatus === 'computing' && <span className="text-state-info">🏛 Computando anchos catastro…</span>}
          {buildingStatus === 'unavailable' && <span className="text-state-warning">🏛 Anchos no disponibles</span>}
        </div>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-3 gis-scroll">
        {(resource.kind === 'stale' || resource.kind === 'conflict') && (
          <div role="alert" className="rounded border border-state-danger/30 bg-state-danger/10 p-2 text-xs text-state-danger">
            {resource.kind === 'stale' ? 'La red viaria cambió. La planificación anterior no se aplicará.' : 'Otro usuario modificó esta planificación.'}
            <div className="mt-2 flex gap-2">
              <button onClick={reload} className="underline">Recargar</button>
              {resource.kind === 'stale' && staleReady && <button onClick={recreate} disabled={saving} className="underline">Recrear vacía</button>}
              {resource.kind === 'stale' && !staleReady && <span>Recarga primero la red actual.</span>}
            </div>
          </div>
        )}
        {message && <div role="status" className="rounded bg-salvi-surface p-2 text-xs text-salvi-grey">{message}</div>}
        <details className="rounded border border-state-info/30 bg-white text-xs text-salvi-grey [&>summary]:open:font-bold">
          <summary className="cursor-pointer px-2 py-1.5 text-[11px] font-semibold text-salvi-black">Área y recorrido de actuación</summary>
          <div className="space-y-1.5 px-2 pb-2">
            {!zone.geometry.boundary && <div className="text-state-warning">La zona necesita un límite real.</div>}
            {!roadSelection && (
              <><div className="text-[10px]">El recorrido usará los tipos de vía marcados como visibles.</div><button onClick={startArea} disabled={!zone.geometry.boundary} className="mt-1 w-full rounded bg-state-info px-2 py-1 text-white disabled:opacity-40">Dibujar área límite</button></>
            )}
            {roadSelection?.status === 'draw_area' && (
              <div className="space-y-2">
                <div>Haz clic en el mapa para añadir vértices ({roadSelection.area_points.length}).</div>
                <div className="flex gap-2">
                  <button onClick={closeArea} disabled={roadSelection.area_points.length < 3} className="flex-1 rounded bg-state-info px-2 py-1 text-white disabled:opacity-40">Cerrar área</button>
                  <button onClick={cancelArea} className="rounded border px-2 py-1">Cancelar</button>
                </div>
              </div>
            )}
            {roadSelection?.status === 'pick_a' && <div>Área cerrada. Haz clic cerca de una vía para marcar A.</div>}
            {roadSelection?.status === 'pick_b' && <div>Ahora marca B. Puede estar en otro tramo conectado.</div>}
            {roadSelection?.status === 'ready' && (
              <div className="space-y-2">
                <div>A y B preparados. El servidor calculará la ruta más corta dentro del área.</div>
                <button onClick={saveScope} disabled={scopeBusy || !roadSelection.allowed_group_refs?.length} className="w-full rounded bg-state-info px-2 py-1 text-white disabled:opacity-40">Calcular y guardar</button>
              </div>
            )}
            {roadSelection?.status === 'saving' && <div>Calculando y guardando recorrido…</div>}
            {roadSelection?.status === 'complete' && (
              <div className="space-y-2">
                <div>Recorrido vigente: {Math.round(roadSelection.length_m || 0)} m · {roadSelection.member_count || 0} partes</div>
                <div className="flex gap-2"><button onClick={startArea} className="flex-1 rounded border px-2 py-1">Redibujar</button><button onClick={removeScope} disabled={scopeBusy} className="rounded border border-state-danger px-2 py-1 text-state-danger">Eliminar</button></div>
              </div>
            )}
            {roadSelection?.status === 'stale' && (
              <div className="space-y-2 text-state-warning">
                <div>La red o el límite cambió. El área se conserva, pero debes volver a marcar A y B.</div>
                <button onClick={recalculateScope} className="w-full rounded border border-state-warning px-2 py-1">Recalcular recorrido</button>
              </div>
            )}
            {roadSelection?.status === 'invalid' && <div className="text-state-danger">{roadSelection.error || 'El ámbito ya no es válido.'} <button onClick={reload} className="underline">Recargar</button></div>}
            {roadSelection?.error && roadSelection.status !== 'invalid' && <div role="alert" className="mt-1 text-state-danger">{roadSelection.error}</div>}
          </div>
        </details>

        {/* ── Accumulated selection summary ── */}
        <section className="rounded border border-salvi-line bg-white text-xs">
          <div className="flex items-center justify-between gap-2 p-2">
            <span className="font-semibold text-salvi-black">
              Selección de estudio {selectedCount > 0 && <span className="ml-1 rounded bg-state-info px-1.5 py-0.5 text-[10px] text-white">{selectedCount}/{totalTargetCount}</span>}
            </span>
            <div className="flex gap-1">
              {selectedCount > 0 && (
                <button onClick={() => { if (selectedZoneId) clearAccumulatedSelection(selectedZoneId); }} className="rounded border border-salvi-line px-1.5 py-0.5 text-[10px] text-salvi-muted hover:bg-salvi-surface">
                  Limpiar
                </button>
              )}
              {inventory && selectedCount < totalTargetCount && (
                <button onClick={() => { if (selectedZoneId) setAccumulatedSelection(selectedZoneId, inventory.targets.filter(t => t.geometry).map(t => t.target_ref)); }} className="rounded border border-salvi-line px-1.5 py-0.5 text-[10px] text-salvi-muted hover:bg-salvi-surface">
                  Todo visible
                </button>
              )}
            </div>
          </div>
          {selectedCount > 0 && (() => {
            const byStreet: Record<string, { targets: typeof inventory.targets; selected: typeof inventory.targets; cfg: RoadTypeCfg | undefined }> = {};
            for (const t of inventory?.targets || []) {
              const key = targetSelectionKey(t);
              if (!byStreet[key]) {
                const grp = inventory!.groups.find(g => g.group_ref === t.group_ref);
                const rcfg = grp?.road_type ? ROAD_CFG[grp.road_type] : undefined;
                byStreet[key] = { targets: [], selected: [], cfg: rcfg };
              }
              byStreet[key].targets.push(t);
              if (zoneSelection[t.target_ref]) byStreet[key].selected.push(t);
            }
            return (
              <div className="border-t border-salvi-line/50 max-h-48 overflow-y-auto gis-scroll">
                {Object.entries(byStreet).filter(([, v]) => v.selected.length).map(([key, { targets, selected, cfg: scfg }]) => {
                  const selectableTargets = targets.filter(target => target.geometry);
                  const all = selectableTargets.length > 0 && selected.length === selectableTargets.length;
                  const open = selectionExpandedStreet === key;
                  const label = targetDisplayLabel(selected[0]);
                  return (
                    <div key={key}>
                      <div className="flex items-center gap-1.5 border-b border-salvi-line/30 px-2 py-1.5 last:border-0">
                        <button onClick={() => setSelectionExpandedStreet(open ? null : key)} className="shrink-0 text-[8px] text-salvi-muted transition-transform hover:text-salvi-black">
                          ▶
                        </button>
                        <input type="checkbox" checked={all} ref={el => { if (el) el.indeterminate = !all && selected.length > 0; }}
                          onChange={() => { if (selectedZoneId) { const refs = selectableTargets.map(t => t.target_ref); if (all) refs.forEach(r => toggleTargetSelection(selectedZoneId, r)); else refs.forEach(r => { if (!zoneSelection[r]) toggleTargetSelection(selectedZoneId, r); }); } }}
                          className="shrink-0 cursor-pointer"
                        />
                        <span className="flex-1 truncate text-[10px] font-semibold text-salvi-black">{label}</span>
                        <span className="text-[9px] text-salvi-muted">{selected.length}/{targets.length}</span>
                      </div>
                      {open && (() => {
                        const groups: { w: number | null; segs: typeof selected }[] = [];
                        for (const t of selected) {
                          const w = t.estWidth ?? scfg?.width ?? null;
                          const last = groups[groups.length - 1];
                          if (last && last.w === w) last.segs.push(t);
                          else groups.push({ w, segs: [t] });
                        }
                        return (
                          <div className="border-b border-salvi-line/20 bg-salvi-surface/30">
                            {groups.map((g, gi) => {
                              const t = g.segs[0];
                              const sw = t.sidewalk;
                              const sl = t.sidewalkWidthLeft ?? (sw === 'both' || sw === 'left' ? 2.0 : null);
                              const sr = t.sidewalkWidthRight ?? (sw === 'both' || sw === 'right' ? 2.0 : null);
                              const est = t.widthSrc !== 'osm_width' ? '⚠' : '';
                              const totalM = g.segs.reduce((s, x) => s + (x.length_m || 0), 0);
                              return (
                                <div key={gi} className="flex items-center gap-2 px-5 py-1 text-[9px] text-salvi-muted">
                                  <span className="w-16 shrink-0">{g.segs.length} tramos</span>
                                  <span className="w-14 shrink-0">{Math.round(totalM)}m</span>
                                  {g.w != null && <span className="w-14 shrink-0">{est}C {g.w}m</span>}
                                  {sl != null && <span className="w-14 shrink-0">AI {sl}m</span>}
                                  {sr != null && <span className="w-14 shrink-0">AD {sr}m</span>}
                                </div>
                              );
                            })}
                          </div>
                        );
                      })()}
                    </div>
                  );
                })}
              </div>
            );
          })()}
        </section>

        {selectedTargetRef && (
          <section className="rounded border border-state-info/30 bg-white p-2 text-xs text-salvi-grey">
            <div className="mb-1 font-semibold text-salvi-black">Tramo seleccionado</div>
            {selectedStreetName && <div className="mb-1">{selectedStreetName}</div>}
            <div className="mb-1">Ref: {selectedTargetRef.slice(0, 20)}…</div>
          </section>
        )}
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar tipo de vía o nombre…" className="w-full rounded border border-salvi-line px-2 py-1 text-xs" />

        {!groups.length && <div className="rounded bg-salvi-surface p-4 text-center text-xs text-salvi-muted">No hay vías que mostrar.</div>}

        {groups.map(group => {
          const cfg = group.road_type ? ROAD_CFG[group.road_type] : undefined;
          const typeMatches = !!normalizedQuery && (group.road_type || 'sin tipo').toLowerCase().includes(normalizedQuery);
          const allStreets = [...(streetsByGroup.get(group.group_ref)?.entries() || [])]
            .filter(([key, targets]) => !normalizedQuery || typeMatches || key.toLowerCase().includes(normalizedQuery) || targetGroupLabel(targets[0]).toLowerCase().includes(normalizedQuery));
          const open = expandedGroup === group.group_ref;
          return (
            <section key={group.group_ref} className="rounded-lg border border-salvi-line bg-white/80">
              {/* Group header */}
              <div className="flex cursor-pointer items-center gap-2 p-2" onClick={() => setExpandedGroup(open ? null : group.group_ref)}>
                <span className={`text-[10px] text-salvi-muted transition-transform ${open ? 'rotate-90' : ''}`}>▶</span>
                <input
                  type="checkbox" checked={visibility[group.group_ref] !== false}
                  onChange={e => { e.stopPropagation(); setVisibility(group.group_ref, e.target.checked); }}
                  aria-label={`Mostrar ${group.road_type || 'sin tipo'} en el mapa`}
                />
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: cfg?.color || '#999' }} />
                <span className="min-w-0 flex-1 text-xs font-semibold text-salvi-black">
                  {cfg ? t(cfg.labelKey) : group.road_type || 'Sin tipo'}
                </span>
                <span className="text-[10px] text-salvi-muted">{group.street_count} nombres · {group.target_count} tramos · {(group.length_m / 1000).toFixed(1)} km</span>
              </div>
              {open && (
                <div className="space-y-3 border-t border-salvi-line p-2">
                  {/* Per-type planning fields */}
                  <div className="rounded bg-salvi-surface p-2">
                    <div className="mb-2 text-[11px] font-semibold text-salvi-grey">Configuración del tipo</div>
                    {editable
                      ? <PlanningFields patch={payload.group_defaults[group.group_ref] || {}} onChange={patch => setGroupPatch(group.group_ref, patch)} />
                      : <div className="text-[11px] text-salvi-muted">Edición bloqueada hasta resolver el estado de la planificación.</div>}
                  </div>
                  {/* Streets */}
                  <div className="space-y-1">
                    {allStreets.map(([streetKeyPart, targets]) => {
                      const streetKey = `${group.group_ref}:${streetKeyPart}`;
                      const street = targetGroupLabel(targets[0]);
                      const selectableStreet = targets.every(target => !!targetName(target));
                      const { all, some } = streetSelState(targets);
                      const streetExpanded = expandedStreet === streetKey;
                      // Get road width from cfg or mark as unknown
                      const roadWidth = cfg?.width;
                      return (
                        <div key={streetKey} className="rounded border border-salvi-line/60">
                          {/* Street row */}
                          <div className="flex items-center gap-1 px-2 py-1">
                            {selectableStreet && <input
                              type="checkbox"
                              checked={all}
                              ref={el => { if (el) el.indeterminate = some && !all; }}
                              onChange={e => { e.stopPropagation(); if (selectedZoneId) toggleStreetSelection(selectedZoneId, targets.filter(target => target.geometry).map(t => t.target_ref)); }}
                              aria-label={`Seleccionar vía ${street}`}
                              className="shrink-0 cursor-pointer"
                            />}
                            <button
                              onClick={() => flyToStreet(street, targets)}
                              className="truncate text-left text-[11px] font-medium text-salvi-black hover:underline"
                              title="Volar a esta vía en el mapa"
                            >
                              {street}
                            </button>
                            <span className="ml-auto text-[10px] text-salvi-muted">{targets.length} tramos</span>
                            <button
                              onClick={() => setExpandedStreet(streetExpanded ? null : streetKey)}
                              className={`shrink-0 text-[8px] text-salvi-muted transition-transform ${streetExpanded ? 'rotate-90' : ''}`}
                            >
                              ▶
                            </button>
                          </div>
                          {/* Segments */}
                          {streetExpanded && (
                            <div className="border-t border-salvi-line/50">
                              {targets.map(target => {
                                const override = payload.target_overrides[target.target_ref]?.luxParams;
                                const groupDefault = payload.group_defaults[target.group_ref]?.luxParams;
                                const lux = override || groupDefault;
                                const tgtWidth = target.estWidth ?? roadWidth;
                                return (
                                  <div key={target.target_ref} className="border-b border-salvi-line/30 last:border-0">
                                    <div className="flex items-center gap-1 px-3 py-1 text-[10px] hover:bg-salvi-surface/50">
                                      <input
                                        type="checkbox"
                                        checked={!!zoneSelection[target.target_ref]}
                                        disabled={!target.geometry && !zoneSelection[target.target_ref]}
                                        onChange={() => { if (selectedZoneId) toggleTargetSelection(selectedZoneId, target.target_ref); }}
                                        aria-label={`Seleccionar tramo ${target.source_index + 1}`}
                                        className="shrink-0 cursor-pointer"
                                      />
                                      <button
                                        onClick={() => { setSelectedTarget(target); setSelectedSegment(target.target_ref, targetName(target)); }}
                                        className="flex flex-1 items-center gap-2 text-left"
                                      >
                                        <span className="font-medium text-salvi-grey">Tramo {target.source_index + 1}</span>
                                        <span className="text-salvi-muted">{target.length_m == null ? '—' : `${Math.round(target.length_m)} m`}</span>
                                        {tgtWidth != null && <span className="text-salvi-muted">calzada {tgtWidth} m{target.widthSrc ? ` (${target.widthSrc})` : ''}</span>}
                                        {target.sidewalk != null && (target.sidewalkWidthLeft != null || target.sidewalkWidthRight != null
                                          ? <span className="text-salvi-muted">acera I {target.sidewalkWidthLeft ?? '—'}m D {target.sidewalkWidthRight ?? '—'}m</span>
                                          : <span className="text-salvi-muted">acera: {target.sidewalk}</span>)}
                                        {lux?.sidewalkL != null && <span className="text-salvi-muted">acera I* {lux.sidewalkL} m</span>}
                                        {lux?.sidewalkR != null && <span className="text-salvi-muted">acera D* {lux.sidewalkR} m</span>}
                                      </button>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </section>
          );
        })}

        {selectedTarget && editable && (
          <div className="rounded-lg border border-state-info/30 bg-white p-2">
            <div className="mb-2 flex justify-between text-[11px] font-semibold">
              <span>{targetDisplayLabel(selectedTarget)} · tramo {selectedTarget.source_index + 1}</span>
              <button onClick={() => setSelectedTarget(null)}>×</button>
            </div>
            <PlanningFields
              patch={payload.target_overrides[selectedTarget.target_ref] || {}}
              inherited={payload.group_defaults[selectedTarget.group_ref] || {}}
              onChange={patch => setTargetPatch(selectedTarget.target_ref, patch)}
            />
          </div>
        )}
      </div>

      <div className="border-t border-salvi-line p-3">
        <section className="mb-3 rounded border border-state-info/30 bg-state-info/5 p-2 text-xs">
          <div className="font-semibold text-salvi-black">Cálculo y pintado automático</div>
          <div className="mt-1 text-[10px] text-salvi-muted">Cada tramo conforme se pinta solo. Los no conformes, stale o no soportados quedan sin pintar.</div>
          <div className="mt-2 flex gap-2">
            <select value={luxMode} onChange={e => setLuxMode(e.target.value as 'calculate' | 'optimize')} disabled={luxStarting || !!luxJob && !['succeeded', 'partial', 'failed', 'cancelled', 'unknown'].includes(luxJob.state)} className="rounded border border-salvi-line bg-white px-1.5 py-1 text-[10px]">
              <option value="optimize">Optimizar</option>
              <option value="calculate">Calcular fijo</option>
            </select>
            <button
              onClick={startLuxJob}
              disabled={!calculableTargetRefs.length || !activeProjectId || !editable || !projectEditable || dirty || !['absent', 'current'].includes(resource.kind) || luxStarting || !!luxJob && !['succeeded', 'partial', 'failed', 'cancelled', 'unknown'].includes(luxJob.state)}
              className="flex-1 rounded bg-state-info px-2 py-1.5 text-[10px] font-medium text-white disabled:opacity-40"
            >
              {luxStarting ? 'Preparando…' : `Calcular y pintar ${calculableTargetRefs.length || ''} tramos válidos`}
            </button>
          </div>
          {dirty && <div className="mt-1 text-[10px] text-state-warning">Guarda la configuración antes de calcular.</div>}
          {resource.kind === 'stale' && <div className="mt-1 text-[10px] text-state-warning">El inventario OSM cambió. Recarga y vuelve a seleccionar los tramos.</div>}
          {!projectEditable && <div className="mt-1 text-[10px] text-state-warning">Tu membresía solo permite consultar este proyecto.</div>}
          {luxJob && (
            <div className="mt-2 space-y-1 border-t border-state-info/20 pt-2">
              <div className="flex items-center justify-between">
                <span>Estado: <strong>{luxJob.state}</strong> · {luxJob.succeeded}/{luxJob.total} pintados</span>
                {!['succeeded', 'partial', 'failed', 'cancelled', 'unknown'].includes(luxJob.state) && <button onClick={cancelCurrentLuxJob} className="text-state-danger underline">Cancelar</button>}
              </div>
              {luxJob.items.map(item => (
                <div key={item.id} className="flex items-center justify-between gap-2 text-[10px]">
                  <span className="truncate">{item.target_ref}</span>
                  <span className={item.state === 'succeeded' ? 'text-state-success' : item.error_message ? 'text-state-danger' : 'text-salvi-muted'}>{item.state}{item.error_message ? `: ${item.error_message}` : ''}</span>
                </div>
              ))}
            </div>
          )}
          {luxJobError && <div role="alert" className="mt-1 text-[10px] text-state-danger">{luxJobError}</div>}
        </section>
        <div className="mb-2 flex gap-2">
          <button onClick={reload} disabled={saving} className="flex-1 rounded border border-salvi-line py-1 text-xs">Recargar</button>
          <button onClick={save} disabled={!editable || !dirty || saving} className="flex-1 rounded bg-salvi-black py-1 text-xs text-white disabled:opacity-40">{saving ? 'Guardando…' : t('actions.save')}</button>
        </div>
        <div className="flex justify-between">
          <button onClick={() => navigate('zona')} className="text-xs text-salvi-grey">{'< '} {t('actions.cancel')}</button>
          <button onClick={() => navigate('luminarias')} className="rounded-md bg-salvi-black px-3 py-1 text-xs text-white">Luminarias {'>'}</button>
        </div>
      </div>
    </div>
  );
};

export default StepVias;
