import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckSquare, MousePointer, Search, Trash2, PlayCircle, Square, PencilRuler } from 'lucide-react';
import { useI18n } from '../../i18n';
import { useAuth } from '../../auth/AuthContext';
import {
  ApiStatusError, cancelLuxJob, createLuxJob, getBuildingWidths, getLuminaires,
  getLuxJob, getPlanningDraft, getPlanningInventory, getZoneSelection, loadPlanningOsm, putPlanningDraft, putZoneSelection,
} from '../../lib/api';
import { useGisStore, ROAD_CFG } from '../../store/useGisStore';
import type { Etagged, GisLuxJob, GisPlanningDraft, GisPlanningInventory, GisPlanningInventoryTarget, GisPlanningPayload } from '../../types';
import type { RoadSelectionDraft } from '../../store/types';
import { roadSelectionIsCurrent } from '../../lib/roadSelection';
import { targetName } from '../../lib/roadNaming';
import { applyRoadOverrides, effectivePatch, ROAD_CHAR_KEYS } from '../../lib/planningOverrides';

const EMPTY_PAYLOAD = (): GisPlanningPayload => ({ group_defaults: {}, target_overrides: {} });

type Resource =
  | { kind: 'loading' }
  | { kind: 'missing' }
  | { kind: 'absent' }
  | { kind: 'current'; etag: string }
  | { kind: 'stale'; etag: string }
  | { kind: 'conflict' }
  | { kind: 'error' };

const CHAR_FIELDS: { key: (typeof ROAD_CHAR_KEYS)[number]; label: string; step: number; unit: string }[] = [
  { key: 'estWidth', label: 'Calzada', step: 0.5, unit: 'm' },
  { key: 'lanes', label: 'Carriles', step: 1, unit: '' },
  { key: 'sidewalkWidthLeft', label: 'Acera I', step: 0.5, unit: 'm' },
  { key: 'sidewalkWidthRight', label: 'Acera D', step: 0.5, unit: 'm' },
  { key: 'medianWidth', label: 'Mediana', step: 0.5, unit: 'm' },
  { key: 'maxspeed', label: 'Velocidad', step: 5, unit: 'km/h' },
];

const StepVias: React.FC = () => {
  const { t } = useI18n();
  const { user } = useAuth();
  const zones = useGisStore(s => s.zones);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const activeProject = useGisStore(s => s.projects.find(project => project.id === s.activeProjectId));
  const inventory = useGisStore(s => s.activePlanningInventory);
  const setInventory = useGisStore(s => s.setActivePlanningInventory);
  const storePlanningPayload = useGisStore(s => s.planningPayload);
  const setStoreBasePayload = useGisStore(s => s.setPlanningBasePayload);
  const setPlanningDirty = useGisStore(s => s.setPlanningDirty);
  const confirmPlanningLeave = useGisStore(s => s.confirmPlanningLeave);
  const savedStorePayload = useGisStore(s => s.planningSavedPayload);
  const discardVersion = useGisStore(s => s.planningDiscardVersion);
  const roadSelectionByZone = useGisStore(s => s.roadSelectionByZone);
  const setRoadSelection = useGisStore(s => s.setRoadSelection);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const accumulatedSelection = useGisStore(s => s.accumulatedSelection);
  const savedSelectionByZone = useGisStore(s => s.savedSelectionByZone);
  const toggleTargetSelection = useGisStore(s => s.toggleTargetSelection);
  const clearAccumulatedSelection = useGisStore(s => s.clearAccumulatedSelection);
  const setAccumulatedSelection = useGisStore(s => s.setAccumulatedSelection);
  const commitSelection = useGisStore(s => s.commitSelection);
  const restoreSelection = useGisStore(s => s.restoreSelection);
  const planningDirty = useGisStore(s => s.planningDirty);
  const zoneLuminaires = useGisStore(s => s.zoneLuminaires);
  const selectedLumIds = useGisStore(s => s.selectedLumIds);
  const setZoneLuminaires = useGisStore(s => s.setZoneLuminaires);
  const openEditor = useGisStore(s => s.openEditor);
  const clearSelection = useGisStore(s => s.clearSelection);
  const showCompliance = useGisStore(s => s.showCompliance);
  const setShowCompliance = useGisStore(s => s.setShowCompliance);
  const setMergeTargetPatches = useGisStore(s => s.setMergeTargetPatches);

  const [resource, setResource] = useState<Resource>({ kind: 'loading' });
  const [payload, setPayload] = useState<GisPlanningPayload>(EMPTY_PAYLOAD);
  const [basePayload, setBasePayload] = useState<GisPlanningPayload>(EMPTY_PAYLOAD);
  const [message, setMessage] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState('');
  const [showSelectedTramos, setShowSelectedTramos] = useState(false);
  const [staleReady, setStaleReady] = useState(false);
  const [loadingOsm, setLoadingOsm] = useState(false);
  const [satRefreshing, setSatRefreshing] = useState(false);
  const satRefreshRef = useRef(0);
  const [buildingStatus, setBuildingStatus] = useState<string | null>(null);
  const osmLoadRef = useRef<AbortController | null>(null);
  const inventoryEtagRef = useRef<string | null>(null);
  const legacyRefreshAttemptedRef = useRef(new Set<string>());

  const [luxJob, setLuxJob] = useState<GisLuxJob | null>(null);
  const luxJobEtagRef = useRef<string | undefined>();
  const [luxJobError, setLuxJobError] = useState('');
  const [luxStarting, setLuxStarting] = useState(false);
  const [luxMode, setLuxMode] = useState<'calculate' | 'optimize'>('optimize');
  const luxIntentIdRef = useRef<string>();
  const [selExpandedStreet, setSelExpandedStreet] = useState<string | null>(null);

  const zone = zones.find(z => z.id === selectedZoneId);
  const roadSelection = selectedZoneId ? roadSelectionByZone[selectedZoneId] : undefined;
  const dirty = JSON.stringify(payload) !== JSON.stringify(basePayload);
  const zoneSelection = selectedZoneId ? (accumulatedSelection[selectedZoneId] || {}) : {};
  const selectedCount = Object.keys(zoneSelection).length;
  const totalTargetCount = inventory?.targets.length ?? 0;
  const projectEditable = activeProject?.access_role !== 'viewer' && user?.role !== 'VIEWER';
  const savedSelection = selectedZoneId ? (savedSelectionByZone[selectedZoneId] || {}) : {};
  const hasPendingSelection = JSON.stringify(zoneSelection) !== JSON.stringify(savedSelection);

  const zoneId = selectedZoneId;
  const lums = zoneId ? (zoneLuminaires[zoneId] || []) : [];
  const jobRunning = !!luxJob && !['succeeded', 'partial', 'failed', 'cancelled', 'unknown'].includes(luxJob.state);
  const calculableTargetRefs = inventory?.targets
    .filter(target => zoneSelection[target.target_ref] && target.geometry)
    .map(target => target.target_ref) || [];

  useEffect(() => {
    setPlanningDirty(dirty);
    return () => setPlanningDirty(false);
  }, [dirty, setPlanningDirty]);

  useEffect(() => {
    if (!discardVersion) return;
    setPayload(savedStorePayload);
    setBasePayload(savedStorePayload);
  }, [discardVersion, savedStorePayload]);

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
    setInventory(null);
    setStoreBasePayload(EMPTY_PAYLOAD());

    (async () => {
      try {
        const inventoryResult = await getPlanningInventory(selectedZoneId, inventoryEtagRef.current || undefined, undefined, controller.signal);
        let nextInventory = inventoryResult.data;
        const newEtag = inventoryResult.etag;
        if (newEtag) inventoryEtagRef.current = newEtag;

        if (!nextInventory) {
          if (live) setResource({ kind: 'missing' });
          return;
        }

        let draftResult: Etagged<GisPlanningDraft | null> | null = null;
        try {
          draftResult = await getPlanningDraft(selectedZoneId, controller.signal)
            .catch(e => { if (e instanceof ApiStatusError && e.status === 404) return { data: null, etag: '' }; throw e; }) as Etagged<GisPlanningDraft | null>;
        } catch (error) {
          if (!(error instanceof ApiStatusError) || error.status !== 404) throw error;
        }

        try {
          const bw = await getBuildingWidths(selectedZoneId, controller.signal);
          if (live) setBuildingStatus(bw.status);
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
                    const refreshed = await getPlanningInventory(selectedZoneId, undefined, true, controller.signal);
                    if (refreshed.data && live) {
                      setInventory(refreshed.data);
                      setMessage('Anchos de vía actualizados con datos del Catastro');
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

        // Restore the confirmed street selection (Aceptar) for this zone.
        try {
          const selResult = await getZoneSelection(selectedZoneId, controller.signal);
          if (live && selResult.data && selResult.data.base_inventory_hash === nextInventory.base_inventory_hash) {
            restoreSelection(selectedZoneId, selResult.data.selected_target_refs);
          }
        } catch { /* selection restore is best-effort */ }

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
  }, [selectedZoneId, reloadKey, setInventory, setRoadSelection, setStoreBasePayload, clearAccumulatedSelection, restoreSelection]);

  useEffect(() => () => osmLoadRef.current?.abort(), []);

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

  // ── Lux job: resume from localStorage, poll while running ──
  useEffect(() => {
    setLuxJob(null);
    luxJobEtagRef.current = undefined;
    setLuxJobError('');
    luxIntentIdRef.current = undefined;
    if (!activeProjectId || !zoneId) return;
    const storageKey = `gis-lux-job:${activeProjectId}:${zoneId}`;
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
  }, [activeProjectId, zoneId]);

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
            if (zoneId && result.data.succeeded > 0) {
              const lums = await getLuminaires(zoneId);
              if (alive) setZoneLuminaires(zoneId, lums);
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
  }, [luxJob?.id, activeProjectId, zoneId, setZoneLuminaires]);

  const startLuxJob = useCallback(async () => {
    if (!activeProjectId || !zoneId || !inventory || !calculableTargetRefs.length || luxStarting || jobRunning || planningDirty || !projectEditable) return;
    setLuxStarting(true); setLuxJobError('');
    const intentId = luxIntentIdRef.current || (typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
    luxIntentIdRef.current = intentId;
    try {
      const result = await createLuxJob(
        String(activeProjectId), zoneId, calculableTargetRefs,
        inventory.base_inventory_hash, intentId, luxMode,
      );
      luxJobEtagRef.current = undefined;
      setLuxJob(result);
      window.localStorage.setItem(`gis-lux-job:${activeProjectId}:${zoneId}`, result.id);
      luxIntentIdRef.current = undefined;
    } catch (error) {
      setLuxJobError((error as Error).message || 'No se pudo iniciar el cálculo Lux');
      if (error instanceof ApiStatusError) {
        luxIntentIdRef.current = undefined;
        if (error.status === 409 && /STALE|stale|INVENTORY/.test(error.message)) {
          setLuxJobError('El inventario o la configuración cambió. Recarga la selección.');
        }
      }
    } finally { setLuxStarting(false); }
  }, [activeProjectId, zoneId, inventory, calculableTargetRefs, luxStarting, jobRunning, projectEditable, luxMode]);

  const cancelCurrentLuxJob = useCallback(async () => {
    if (!luxJob || !activeProjectId) return;
    try {
      const result = await cancelLuxJob(String(activeProjectId), luxJob.id);
      setLuxJob(result);
    } catch (error) { setLuxJobError((error as Error).message || 'No se pudo cancelar'); }
  }, [luxJob, activeProjectId]);

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

  const persistSelection = useCallback(async () => {
    if (!selectedZoneId || !inventory) return;
    const sel = useGisStore.getState().accumulatedSelection[selectedZoneId] || {};
    try {
      await putZoneSelection(selectedZoneId, inventory.base_inventory_hash, Object.keys(sel));
    } catch (error) {
      setMessage((error as Error).message || 'No se pudo guardar la selección');
    }
  }, [selectedZoneId, inventory]);

  const acceptSelection = useCallback((zoneId: string) => {
    commitSelection(zoneId);
    void persistSelection();
  }, [commitSelection, persistSelection]);

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
  const navigate = (step: 'zona' | 'informe') => {
    if (!confirmPlanningLeave()) return;
    if (step === 'informe' && selectedZoneId && hasPendingSelection && !window.confirm('La selección todavía no se ha confirmado. ¿Aceptar los cambios actuales y continuar?')) return;
    if (step === 'informe' && selectedZoneId) acceptSelection(selectedZoneId);
    setStepWizard(step);
  };
  const reload = () => {
    if (!confirmPlanningLeave()) return;
    if (selectedZoneId) legacyRefreshAttemptedRef.current.delete(selectedZoneId);
    setReloadKey(v => v + 1);
  };
  const loadOsm = async (force = false) => {
    if (!selectedZoneId || loadingOsm) return;
    const controller = new AbortController();
    osmLoadRef.current = controller;
    setLoadingOsm(true); setMessage('');
    try {
      await loadPlanningOsm(selectedZoneId, controller.signal, force);
      setReloadKey(value => value + 1);
      if (force) {
        // Poll inventory ~60s while satellite measures widths in background
        setSatRefreshing(true);
        satRefreshRef.current = 15;
      }
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

  useEffect(() => {
    if (!satRefreshing) return;
    const timer = setInterval(() => {
      if (satRefreshRef.current <= 0) {
        setSatRefreshing(false);
        return;
      }
      satRefreshRef.current -= 1;
      setReloadKey(v => v + 1);
    }, 4000);
    return () => clearInterval(timer);
  }, [satRefreshing]);
  const startArea = () => {
    if (!selectedZoneId || !inventory || !zone) return;
    setRoadSelection(selectedZoneId, {
      zone_id: selectedZoneId,
      inventory_hash: inventory.base_inventory_hash,
      boundary_signature: JSON.stringify(zone.geometry.boundary ?? null),
      status: 'draw_area',
      area_points: [],
      etag: undefined,
    });
  };
  const clearAreaDraft = () => {
    if (!selectedZoneId || !roadSelection) return;
    if ((roadSelection.status === 'draw_area' || roadSelection.status === 'complete') && roadSelection.lassoTargetRefs?.length) {
      // Undo only the last lazo: remove its tramos, keep the previously-selected ones.
      const cur = accumulatedSelection[selectedZoneId] || {};
      const next = { ...cur };
      for (const ref of roadSelection.lassoTargetRefs) delete next[ref];
      setAccumulatedSelection(selectedZoneId, Object.keys(next));
    }
    setRoadSelection(selectedZoneId, null);
  };

  const revealTarget = useCallback((targetRef: string) => {
    (window as any).__blinkGisTarget?.(targetRef);
  }, []);

  const hoverTarget = useCallback((targetRef: string | null) => {
    if (targetRef) (window as any).__highlightGisTarget?.(targetRef);
  }, []);

  const clearHover = useCallback(() => {
    (window as any).__clearGisHighlight?.();
  }, []);

  const normalizedQuery = query.trim().toLowerCase();

  const selectedTramosByStreet = useMemo(() => {
    if (!inventory || !selectedZoneId) return [];
    const zoneSel = accumulatedSelection[selectedZoneId] || {};
    const byStreet = new Map<string, { selected: typeof inventory.targets; all: typeof inventory.targets }>();
    for (const target of inventory.targets) {
      const street = targetName(target) || `Tramo ${target.source_index + 1}`;
      const entry = byStreet.get(street) || { selected: [], all: [] };
      entry.all.push(target);
      if (zoneSel[target.target_ref]) entry.selected.push(target);
      byStreet.set(street, entry);
    }
    return [...byStreet.entries()]
      .filter(([, entry]) => entry.selected.length > 0)
      .map(([street, entry]) => ({ key: street, street, targets: entry.selected, allTargets: entry.all }));
  }, [inventory, selectedZoneId, accumulatedSelection]);

  const searchGroups = useMemo(() => {
    if (!inventory || !normalizedQuery) return [];
    const groups: { street: string | null; targets: GisPlanningInventoryTarget[] }[] = [];
    const byStreet = new Map<string, GisPlanningInventoryTarget[]>();
    const singles: GisPlanningInventoryTarget[] = [];
    for (const target of inventory.targets) {
      const name = targetName(target);
      const label = name || `Tramo ${target.source_index + 1}`;
      if (!label.toLowerCase().includes(normalizedQuery)) continue;
      if (name) {
        const arr = byStreet.get(name) || [];
        arr.push(target);
        byStreet.set(name, arr);
      } else {
        singles.push(target);
      }
    }
    for (const [street, targets] of byStreet) groups.push({ street, targets });
    for (const t of singles) groups.push({ street: null, targets: [t] });
    return groups;
  }, [inventory, normalizedQuery]);

  const toggleAllRefs = useCallback((targets: GisPlanningInventoryTarget[]) => {
    if (!selectedZoneId || !targets.length) return;
    const refs = targets.filter(t => t.geometry).map(t => t.target_ref);
    const all = refs.length > 0 && refs.every(r => zoneSelection[r]);
    if (all) refs.forEach(r => toggleTargetSelection(selectedZoneId, r));
    else refs.forEach(r => { if (!zoneSelection[r]) toggleTargetSelection(selectedZoneId, r); });
  }, [selectedZoneId, zoneSelection, toggleTargetSelection]);

  const selectedTargetsFlat = useMemo(() => {
    if (!inventory || !selectedZoneId) return [];
    const zoneSel = accumulatedSelection[selectedZoneId] || {};
    return inventory.targets.filter(t => zoneSel[t.target_ref]);
  }, [inventory, selectedZoneId, accumulatedSelection]);

  // ── Batch characteristic editor ──
  const [charBatch, setCharBatch] = useState<Record<string, true>>({});
  const charInitRef = useRef<string | null>(null);
  const charRefs = Object.keys(charBatch);

  useEffect(() => {
    if (!selectedZoneId) { setCharBatch({}); charInitRef.current = null; return; }
    const sel = accumulatedSelection[selectedZoneId] || {};
    const sig = JSON.stringify(sel);
    if (charInitRef.current !== sig) {
      charInitRef.current = sig;
      setCharBatch({ ...sel });
    }
  }, [selectedZoneId, accumulatedSelection]);

  const charFieldState = useCallback((key: (typeof ROAD_CHAR_KEYS)[number]) => {
    if (!charRefs.length) return { value: '', mixed: false };
    const values = charRefs.map(ref => {
      const t = inventory?.targets.find(x => x.target_ref === ref);
      if (!t) return null;
      return (applyRoadOverrides(t, effectivePatch(storePlanningPayload, t)) as any)[key] ?? null;
    });
    const nonNull = values.filter(v => v != null);
    if (!nonNull.length) return { value: '', mixed: false };
    const distinct = new Set(nonNull.map(String));
    if (distinct.size === 1) return { value: nonNull[0], mixed: false };
    return { value: '', mixed: true };
  }, [charRefs, inventory, storePlanningPayload]);

  const setBatchChar = useCallback((key: (typeof ROAD_CHAR_KEYS)[number], value: number | string | null) => {
    if (!charRefs.length) return;
    setMergeTargetPatches(charRefs, { [key]: value } as any);
  }, [charRefs, setMergeTargetPatches]);

  const resetBatchChar = useCallback(() => {
    if (!charRefs.length) return;
    const patch: Record<string, null> = {};
    for (const key of ROAD_CHAR_KEYS) patch[key] = null;
    setMergeTargetPatches(charRefs, patch as any);
  }, [charRefs, setMergeTargetPatches]);

  if (!zone) return <div className="gis-panel rounded-xl p-6 text-center text-sm text-salvi-muted">Selecciona una zona primero</div>;
  if (resource.kind === 'loading') return <div className="gis-panel rounded-xl p-6 text-center text-sm text-salvi-muted">Cargando vías y planificación…</div>;
  if (resource.kind === 'missing') return (
    <div className="gis-panel rounded-xl p-5 text-center text-sm text-salvi-grey">
      <p>Esta zona todavía no tiene vías OSM.</p>
      {message && <p role="alert" className="mt-2 text-xs text-state-danger">{message}</p>}
      <button onClick={() => loadOsm()} disabled={loadingOsm} className="mt-3 rounded bg-salvi-black px-3 py-1.5 text-xs text-white disabled:opacity-50">
        {loadingOsm ? 'Cargando calles y aceras…' : 'Cargar calles y aceras'}
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

  const searchResult = searchGroups.map(group => {
    const { street, targets } = group;
    if (!street) {
      const target = targets[0];
      const selected = !!zoneSelection[target.target_ref];
      return (
        <div
          key={target.target_ref}
          className={`flex items-center gap-2 px-3 py-1.5 border-t border-salvi-line/60 ${selected ? 'bg-[#1F7A4D]/5' : ''}`}
          onMouseEnter={() => hoverTarget(target.target_ref)}
          onMouseLeave={clearHover}
        >
          <input
            type="checkbox"
            checked={selected}
            disabled={!target.geometry && !selected}
            onChange={() => { if (selectedZoneId) toggleTargetSelection(selectedZoneId, target.target_ref); }}
            className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-[#1F7A4D]"
            aria-label={`Seleccionar tramo ${target.source_index + 1}`}
          />
          <button
            onClick={() => revealTarget(target.target_ref)}
            className="min-w-0 flex-1 truncate text-left text-xs font-medium text-salvi-black hover:underline"
            title="Ver este tramo en el mapa"
          >
            Tramo {target.source_index + 1}
          </button>
          <span className="shrink-0 text-[10px] text-salvi-muted">{target.length_m != null ? `${Math.round(target.length_m)} m` : '—'}</span>
        </div>
      );
    }
    const all = targets.filter(t => t.geometry).length > 0 && targets.every(t => !t.geometry || zoneSelection[t.target_ref]);
    return (
      <div key={`street:${street}`} className="overflow-hidden border-t border-salvi-line/60">
        <div className="flex items-center gap-2 bg-salvi-surface/50 px-3 py-1.5">
          <input
            type="checkbox"
            checked={all}
            disabled={!targets.some(t => t.geometry)}
            onChange={() => toggleAllRefs(targets)}
            className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-[#1F7A4D]"
            aria-label={`Seleccionar calle ${street}`}
          />
          <button
            onClick={() => toggleAllRefs(targets)}
            className="min-w-0 flex-1 truncate text-left text-xs font-semibold text-salvi-black hover:underline"
            title={all ? 'Deseleccionar toda la calle' : 'Seleccionar toda la calle'}
          >
            {street}
          </button>
          <span className="shrink-0 rounded bg-salvi-surface px-1.5 py-0.5 text-[9px] text-salvi-muted">{targets.length} tramos</span>
        </div>
        {targets.map(target => {
          const selected = !!zoneSelection[target.target_ref];
          return (
            <div
              key={target.target_ref}
              className={`flex items-center gap-2 py-1.5 pl-8 pr-3 border-t border-salvi-line/40 ${selected ? 'bg-[#1F7A4D]/5' : ''}`}
              onMouseEnter={() => hoverTarget(target.target_ref)}
              onMouseLeave={clearHover}
            >
              <input
                type="checkbox"
                checked={selected}
                disabled={!target.geometry && !selected}
                onChange={() => { if (selectedZoneId) toggleTargetSelection(selectedZoneId, target.target_ref); }}
                className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-[#1F7A4D]"
                aria-label={`Seleccionar tramo ${target.source_index + 1}`}
              />
              <button
                onClick={() => revealTarget(target.target_ref)}
                className="min-w-0 flex-1 truncate text-left text-[11px] font-medium text-salvi-black hover:underline"
                title="Ver este tramo en el mapa"
              >
                Tramo {target.source_index + 1}
                {target.length_m != null && <span className="ml-1 font-normal text-salvi-muted">· {Math.round(target.length_m)} m</span>}
              </button>
              <span className="shrink-0 text-[9px] text-salvi-muted">{target.nameState === 'legacy' ? 'legacy' : ''}</span>
            </div>
          );
        })}
      </div>
    );
  });

  return (
    <div className="gis-panel flex max-h-full flex-col overflow-hidden rounded-xl">
      {/* Header — zone + totals + elements */}
      <div className="border-b border-salvi-line px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="truncate text-sm font-semibold text-salvi-black">{zone.name}</h2>
          <span className="shrink-0 rounded bg-salvi-surface px-2 py-0.5 text-[10px] text-salvi-muted">{t('detail.elements', { n: lums.length })}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-salvi-muted">
          <span className="rounded bg-salvi-surface px-1.5 py-0.5">{inventory.counts.distinct_name_count ?? inventory.counts.named_street_count} calles</span>
          <span className="rounded bg-salvi-surface px-1.5 py-0.5">{inventory.counts.segment_count} tramos</span>
          <span className="rounded bg-salvi-surface px-1.5 py-0.5">{inventory.counts.geometry_available} con geometría</span>
          {(() => {
            const satCount = inventory.targets.filter(t => t.widthSrc === 'satellite').length;
            const totalCount = inventory.targets.length;
            const pct = totalCount ? Math.round((satCount / totalCount) * 100) : 0;
            if (satRefreshing) {
              return <span className="rounded bg-state-info/10 px-1.5 py-0.5 text-state-info">🛰 Midiendo anchos…</span>;
            }
            if (satCount === 0) {
              return <span className="rounded bg-salvi-surface px-1.5 py-0.5 text-salvi-muted">🛰 0 tramos medidos</span>;
            }
            return <span className="rounded bg-state-success/10 px-1.5 py-0.5 text-state-success">🛰 {satCount}/{totalCount} tramos medidos ({pct}%)</span>;
          })()}
          {buildingStatus === 'computing' && <span className="rounded bg-salvi-surface px-1.5 py-0.5 text-state-info">🏛 Computando anchos…</span>}
          {buildingStatus === 'unavailable' && <span className="rounded bg-salvi-surface px-1.5 py-0.5 text-state-warning">🏛 Anchos no disponibles</span>}
        </div>
        <button
          onClick={() => loadOsm(true)}
          disabled={loadingOsm}
          className="mt-2 w-full rounded border border-salvi-line bg-white px-2 py-1 text-[11px] font-medium text-salvi-black hover:bg-salvi-surface disabled:opacity-40"
          title="Vuelve a consultar calles y aceras y mide los anchos con más precisión (satélite)."
        >
          {loadingOsm ? 'Calculando calles y aceras…' : '🛰 Recalcular calles y aceras con precisión'}
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3 gis-scroll">
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

        {/* ── Cálculo y pintado ── */}
        <section className="rounded-lg border border-salvi-line bg-[#FCF9F5]/60">
          <div className="mb-2 flex items-center gap-1.5 px-3 pt-2 text-xs font-semibold text-salvi-black">
            <PlayCircle className="h-3.5 w-3.5 text-salvi-muted" aria-hidden="true" />
            Cálculo y pintado
          </div>
          <div className="flex gap-2 px-3 pb-2">
            <select value={luxMode} onChange={e => setLuxMode(e.target.value as 'calculate' | 'optimize')} disabled={luxStarting || jobRunning} className="rounded border border-salvi-line bg-white px-1.5 py-1.5 text-xs">
              <option value="optimize">Optimizar</option>
              <option value="calculate">Calcular fijo</option>
            </select>
            <button
              onClick={startLuxJob}
              disabled={!calculableTargetRefs.length || !activeProjectId || !projectEditable || planningDirty || luxStarting || jobRunning}
              className="flex-1 rounded bg-salvi-black px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-40"
              title={!calculableTargetRefs.length ? 'Selecciona tramos primero' : planningDirty ? 'Guarda la configuración antes de calcular' : ''}
            >
              {luxStarting ? 'Preparando…' : `Pintar ${calculableTargetRefs.length || ''} tramos`}
            </button>
          </div>
          {planningDirty && <p className="px-3 pb-2 text-[10px] text-state-warning">Hay configuración pendiente de guardar. Guárdala antes de calcular.</p>}
          {!projectEditable && <p className="px-3 pb-2 text-[10px] text-state-warning">Tu membresía solo permite consultar este proyecto.</p>}
          {luxJobError && <p role="alert" className="px-3 pb-2 text-[10px] text-state-danger">{luxJobError}</p>}
          {luxJob && (
            <div className="mx-3 mb-2 mt-1 space-y-1 border-t border-salvi-line/60 pt-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-salvi-grey">{luxJob.succeeded}/{luxJob.total} pintados</span>
                {jobRunning ? (
                  <button onClick={cancelCurrentLuxJob} className="inline-flex items-center gap-1 text-[10px] text-state-danger">
                    <Square className="h-3 w-3" aria-hidden="true" /> Cancelar
                  </button>
                ) : (
                  <span className="rounded bg-[#1F7A4D]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#1F7A4D]">{luxJob.state === 'succeeded' ? 'Completado' : luxJob.state}</span>
                )}
              </div>
            </div>
          )}
        </section>

        {/* ── Área de trabajo ── */}
        <section className="rounded-lg border border-salvi-line bg-white">
          <div className="flex items-center justify-between gap-2 px-3 py-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-salvi-black">
              <MousePointer className="h-3.5 w-3.5 text-salvi-muted" aria-hidden="true" />
              Área de trabajo
            </div>
            {roadSelection?.status === 'complete' ? (
              <div className="flex items-center gap-1">
                <button onClick={startArea} className="rounded border border-salvi-line px-1.5 py-0.5 text-[10px] text-salvi-grey hover:bg-salvi-surface">Redibujar</button>
                <button onClick={clearAreaDraft} className="rounded border border-state-danger px-1.5 py-0.5 text-[10px] text-state-danger hover:bg-[#FDECEA]">Eliminar</button>
              </div>
            ) : (
              <button
                onClick={startArea}
                disabled={!editable}
                className="rounded bg-salvi-black px-2.5 py-1 text-[11px] font-medium text-white disabled:opacity-40"
              >
                {roadSelection?.status === 'draw_area' ? 'Area en curso…' : 'Dibujar área'}
              </button>
            )}
          </div>
          {roadSelection?.status === 'draw_area' && (
            <div className="space-y-1.5 border-t border-salvi-line px-3 py-2 text-[11px] text-salvi-grey">
              <div>Haz clic para añadir vértices ({roadSelection.area_points.length}).</div>
              <div>Doble clic o clic sobre el primer punto para cerrar.</div>
              <div className="flex gap-1.5">
                <button onClick={clearAreaDraft} className="flex-1 rounded border border-salvi-line px-2 py-1 text-[11px] text-salvi-grey">Cancelar</button>
              </div>
            </div>
          )}
          {roadSelection?.status === 'complete' && (
            <div className="space-y-1.5 border-t border-salvi-line px-3 py-2 text-[11px] text-state-success">
              <div>Área cerrada: {selectedCount > 0 ? `${selectedCount} tramos seleccionados automáticamente.` : 'ningún tramo dentro del área.'}</div>
              <div className="flex gap-1.5">
                <button onClick={startArea} className="flex-1 rounded border border-salvi-line px-2 py-1 text-[11px] text-salvi-grey">Redibujar</button>
                <button onClick={clearAreaDraft} className="flex-1 rounded border border-state-danger px-2 py-1 text-[11px] text-state-danger">Eliminar</button>
              </div>
            </div>
          )}
        </section>

        {/* ── Selección ── */}
        <section className="rounded-lg border border-salvi-line bg-white">
          <div className="flex items-center justify-between gap-2 px-3 py-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-salvi-black">
              <CheckSquare className="h-3.5 w-3.5 text-salvi-muted" aria-hidden="true" />
              {selectedCount === 0 ? 'Selección' : `Selección: ${selectedCount} de ${totalTargetCount}`}
            </div>
            <div className="flex items-center gap-1">
              {selectedCount > 0 && (
                <button onClick={() => { if (selectedZoneId) clearAccumulatedSelection(selectedZoneId); }} className="rounded border border-salvi-line px-1.5 py-0.5 text-[10px] text-salvi-grey hover:bg-salvi-surface" title={t('actions.cancel')}>
                  <Trash2 className="h-3 w-3" aria-hidden="true" />
                </button>
              )}
              <button
                onClick={() => { if (selectedZoneId) setAccumulatedSelection(selectedZoneId, inventory.targets.filter(t => t.geometry).map(t => t.target_ref)); }}
                disabled={!inventory.targets.some(t => t.geometry) || selectedCount >= totalTargetCount}
                className="rounded bg-salvi-black px-2.5 py-1 text-[11px] font-medium text-white disabled:opacity-40"
              >
                Seleccionar todo
              </button>
            </div>
          </div>
          <div className="border-t border-salvi-line px-3 py-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-salvi-muted" aria-hidden="true" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Buscar calle…"
                className="w-full rounded border border-salvi-line bg-white py-1.5 pl-7 pr-2 text-xs outline-none focus:border-salvi-black/40"
              />
            </div>
            <p className="mt-1.5 text-[10px] text-salvi-muted">También puedes hacer clic en los tramos del mapa para seleccionarlos.</p>
          </div>
          {selectedCount > 0 && (
            <div className="border-t border-salvi-line px-3 py-2">
              {hasPendingSelection && (
                <div role="status" className="mb-2 flex items-center gap-2 rounded border border-state-warning/40 bg-amber-50 px-2 py-1.5">
                  <span className="flex-1 text-[10px] font-medium text-state-warning">Cambios sin confirmar en la selección</span>
                  <button
                    onClick={() => setAccumulatedSelection(selectedZoneId!, Object.keys(savedSelection))}
                    className="rounded border border-state-warning/40 px-1.5 py-0.5 text-[10px] text-state-warning hover:bg-amber-100"
                  >
                    Deshacer
                  </button>
                  <button
                    onClick={() => selectedZoneId && acceptSelection(selectedZoneId)}
                    className="rounded bg-salvi-black px-1.5 py-0.5 text-[10px] font-medium text-white"
                  >
                    Aceptar
                  </button>
                </div>
              )}
              {showSelectedTramos
                ? (
                  <div className="space-y-2">
                    <button
                      onClick={() => setShowSelectedTramos(false)}
                      className="w-full rounded border border-salvi-line px-2 py-1 text-[11px] font-medium text-salvi-grey hover:bg-salvi-surface"
                    >
                      Ocultar tramos seleccionados
                    </button>
                    {selectedTramosByStreet.map(({ key, street, targets, allTargets }) => {
                      const all = allTargets.length > 0 && targets.length === allTargets.length;
                      const missing = allTargets.filter(t => !zoneSelection[t.target_ref]);
                      return (
                        <div key={key} className="overflow-hidden rounded border border-salvi-line/60">
                          <div className="flex items-center gap-2 bg-salvi-surface/50 px-2.5 py-1.5">
                            <button
                              onClick={() => { if (selectedZoneId && allTargets.length) { const refs = allTargets.map(t => t.target_ref); if (all) refs.forEach(r => toggleTargetSelection(selectedZoneId, r)); else refs.forEach(r => { if (!zoneSelection[r]) toggleTargetSelection(selectedZoneId, r); }); } }}
                              className="min-w-0 flex-1 truncate text-left text-[11px] font-semibold text-salvi-black hover:underline"
                              title={all ? 'Deseleccionar toda la calle' : 'Seleccionar toda la calle'}
                            >
                              {street}
                            </button>
                            {all
                              ? <span className="shrink-0 rounded bg-[#1F7A4D]/10 px-1.5 py-0.5 text-[9px] font-semibold text-[#1F7A4D]">Calle completa</span>
                              : <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800">{targets.length}/{allTargets.length} tramos</span>}
                          </div>
                          {targets.map((target, idx) => (
                            <div key={target.target_ref} className={`flex items-center gap-2 border-t border-salvi-line/40 py-1.5 pl-6 pr-2.5 ${idx > 0 ? '' : ''}`}
                              onMouseEnter={() => hoverTarget(target.target_ref)}
                              onMouseLeave={clearHover}
                            >
                              <input
                                type="checkbox"
                                checked={!!zoneSelection[target.target_ref]}
                                onChange={() => { if (selectedZoneId) toggleTargetSelection(selectedZoneId, target.target_ref); }}
                                className="h-3.5 w-3.5 shrink-0 cursor-pointer accent-[#1F7A4D]"
                                aria-label={`Seleccionar tramo ${target.source_index + 1}`}
                              />
                              <button
                                onClick={() => revealTarget(target.target_ref)}
                                className="min-w-0 flex-1 truncate text-left text-[11px] font-medium text-salvi-black hover:underline"
                                title="Ver en el mapa"
                              >
                                Tramo {target.source_index + 1}
                                {target.length_m != null && <span className="ml-1 font-normal text-salvi-muted">· {Math.round(target.length_m)} m</span>}
                              </button>
                              <span className="shrink-0 text-[9px] text-salvi-muted">{target.nameState === 'legacy' ? 'legacy' : ''}</span>
                              <button
                                onClick={() => { if (selectedZoneId) toggleTargetSelection(selectedZoneId, target.target_ref); }}
                                className="shrink-0 rounded border border-state-danger/30 px-1.5 py-0.5 text-[10px] text-state-danger hover:bg-[#FDECEA]"
                                title="Deseleccionar"
                              >
                                ✕
                              </button>
                            </div>
                          ))}
                          {missing.length > 0 && (
                            <div className="border-t border-salvi-line/30 bg-salvi-surface/20 py-1.5 pl-8 pr-2.5">
                              <div className="text-[9px] font-semibold uppercase tracking-wide text-salvi-muted">Faltan {missing.length} tramos</div>
                              <div className="mt-1 flex flex-wrap gap-1">
                                {missing.map(t => (
                                  <button
                                    key={t.target_ref}
                                    onClick={() => { if (selectedZoneId) toggleTargetSelection(selectedZoneId, t.target_ref); }}
                                    className="rounded border border-salvi-line bg-white px-1.5 py-0.5 text-[10px] text-salvi-grey hover:bg-[#1F7A4D]/10 hover:text-[#1F7A4D]"
                                    title={`Tramo ${t.source_index + 1} · ${t.length_m != null ? Math.round(t.length_m) + ' m' : '—'}`}
                                  >
                                    + Tramo {t.source_index + 1}{t.length_m != null ? ` (${Math.round(t.length_m)} m)` : ''}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )
                : (
                  <button
                    onClick={() => setShowSelectedTramos(true)}
                    className="w-full rounded bg-salvi-black px-2 py-1 text-[11px] font-medium text-white"
                  >
                    Ver tramos seleccionados ({selectedCount})
                  </button>
                )}
            </div>
          )}
        </section>

        {/* ── Resultados de búsqueda (solo con texto) ── */}
        {normalizedQuery && (
          <>
            {!searchGroups.length
              ? <div className="rounded bg-salvi-surface p-4 text-center text-xs text-salvi-muted">No hay tramos con ese nombre.</div>
              : <section className="rounded-lg border border-salvi-line bg-white">{searchResult}</section>}
          </>
        )}

        {/* ── Características de los tramos ── */}
        {selectedTargetsFlat.length > 0 && (
          <section className="rounded-lg border border-salvi-line bg-white">
            <div className="flex items-center justify-between gap-2 px-3 py-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-salvi-black">
                <PencilRuler className="h-3.5 w-3.5 text-salvi-muted" aria-hidden="true" />
                Características
              </div>
              <span className="shrink-0 rounded bg-[#1F7A4D]/10 px-1.5 py-0.5 text-[10px] font-semibold text-[#1F7A4D]">
                {charRefs.length ? `Editando ${charRefs.length} tramos` : 'Sin tramos'}
              </span>
            </div>
            <p className="border-t border-salvi-line/50 px-3 py-1.5 text-[10px] text-salvi-muted">
              Selecciona los tramos a corregir y edita los campos. Se aplica en bloque y se guarda con la planificación.
            </p>

            {/* Tramo selector (batch) */}
            <div className="border-t border-salvi-line/50 space-y-1 px-3 py-2">
              {selectedTramosByStreet.map(({ key, street, targets, allTargets }) => (
                <details key={key} className="overflow-hidden rounded border border-salvi-line/60">
                  <summary className="flex cursor-pointer items-center justify-between bg-salvi-surface/50 px-2.5 py-1.5 text-[11px] font-semibold text-salvi-black">
                    <span className="min-w-0 truncate">{street}</span>
                    <span className="shrink-0 text-[9px] font-normal text-salvi-muted">{targets.length}/{allTargets.length} tramos</span>
                  </summary>
                  <div className="flex flex-wrap gap-1 border-t border-salvi-line/40 px-2.5 py-2">
                    {targets.map(target => {
                      const inBatch = !!charBatch[target.target_ref];
                      return (
                        <button
                          key={target.target_ref}
                          onClick={() => setCharBatch(cur => {
                            const next = { ...cur };
                            if (next[target.target_ref]) delete next[target.target_ref];
                            else next[target.target_ref] = true;
                            return next;
                          })}
                          className={`rounded px-1.5 py-0.5 text-[10px] transition-colors ${inBatch ? 'bg-[#1F7A4D] text-white' : 'border border-salvi-line text-salvi-grey hover:bg-salvi-surface'}`}
                          title={`Tramo ${target.source_index + 1} · ${target.length_m != null ? Math.round(target.length_m) + ' m' : '—'}`}
                        >
                          T{target.source_index + 1}
                          {target.length_m != null ? ` · ${Math.round(target.length_m)}m` : ''}
                        </button>
                      );
                    })}
                  </div>
                </details>
              ))}
            </div>

            {/* Batch fields */}
            {charRefs.length > 0 && (
              <div className="border-t border-salvi-line/50 px-3 py-2">
                <div className="grid grid-cols-3 gap-1.5">
                  {CHAR_FIELDS.map(field => {
                    const { value, mixed } = charFieldState(field.key);
                    const isOverride = charRefs.some(ref => {
                      const t = inventory.targets.find(x => x.target_ref === ref);
                      return t && (effectivePatch(storePlanningPayload, t) as any)[field.key] !== undefined;
                    });
                    return (
                      <label key={field.key} className={`text-[9px] ${isOverride ? 'font-medium text-[#1F7A4D]' : 'text-salvi-muted'}`}>
                        <span className="flex items-baseline justify-between">
                          <span className="truncate">{field.label}{field.unit ? ` (${field.unit})` : ''}</span>
                          {mixed && <span className="rounded bg-amber-100 px-1 text-[8px] font-semibold text-amber-800">varios</span>}
                        </span>
                        <input
                          type="number" step={field.step} min={0}
                          value={value}
                          placeholder={mixed ? 'varios' : ''}
                          onChange={e => setBatchChar(field.key, e.target.value === '' ? null : Number(e.target.value))}
                          className={`mt-0.5 w-full rounded border px-1.5 py-1 text-[11px] ${isOverride ? 'border-[#1F7A4D]/50 bg-[#1F7A4D]/5' : 'border-salvi-line'}`}
                        />
                      </label>
                    );
                  })}
                </div>
                <button
                  onClick={resetBatchChar}
                  className="mt-2 w-full rounded border border-salvi-line px-2 py-1 text-[10px] text-salvi-grey hover:bg-salvi-surface"
                >
                  Restablecer estos tramos
                </button>
              </div>
            )}
          </section>
        )}

        {/* ── Luminarias existentes ── */}
        <section className="rounded-lg border border-salvi-line bg-white">
          <div className="px-3 py-2 text-xs font-semibold text-salvi-black">Luminarias ({lums.length})</div>
          <div className="max-h-40 overflow-y-auto gis-scroll border-t border-salvi-line/50">
            {lums.map(lum => {
              const isSelected = selectedLumIds.has(`${zoneId}__${lum.id}`);
              return (
                <div
                  key={lum.id}
                  className={`px-3 py-2 border-b border-salvi-line/30 text-xs cursor-pointer transition-colors ${
                    isSelected ? 'bg-yellow-50 border-l-2 border-l-yellow-400' : 'hover:bg-salvi-surface'
                  }`}
                >
                  <div className="font-medium text-salvi-black">{lum.street_name || '—'}</div>
                  <div className="text-salvi-muted">{lum.road_type} · {lum.watts}W · {lum.lighting_class}</div>
                </div>
              );
            })}
            {!lums.length && (
              <div className="p-4 text-center text-xs text-salvi-muted">
                {calculableTargetRefs.length ? 'Pulsa "Pintar tramos" para colocar luminarias.' : 'Selecciona tramos para pintar luminarias.'}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Footer */}
      <div className="border-t border-salvi-line p-3">
        {dirty && (
          <div className="mb-2 flex items-center gap-2">
            <span className="flex-1 text-[11px] text-state-warning">Hay cambios sin guardar</span>
            <button onClick={reload} disabled={saving} className="rounded border border-salvi-line px-2 py-1 text-[11px] text-salvi-grey hover:bg-salvi-surface">Recargar</button>
          </div>
        )}
        <button
          onClick={() => zoneId && openEditor(zoneId)}
          disabled={selectedCount === 0}
          className="w-full rounded border border-salvi-line px-2 py-1.5 text-[11px] font-medium text-salvi-black hover:bg-salvi-surface disabled:opacity-40"
          title={selectedCount === 0 ? 'Selecciona al menos un tramo' : t('editor.open')}
        >
          🏙 {t('editor.open')}
        </button>
        <button
          onClick={() => setShowCompliance(!showCompliance)}
          className={`mt-2 w-full rounded-md py-1.5 text-[11px] border transition-colors ${
            showCompliance
              ? 'bg-state-success/10 border-state-success text-state-success'
              : 'border-salvi-line text-salvi-grey hover:bg-salvi-surface'
          }`}
        >
          {showCompliance ? t('detail.compliance.hide') : t('detail.compliance.show')}
        </button>
        <div className="mt-2 flex gap-2">
          <button
            onClick={() => navigate('zona')}
            className="rounded-lg border border-salvi-line px-3 py-2 text-xs text-salvi-grey hover:bg-salvi-surface"
          >
            {'< '}{t('actions.cancel')}
          </button>
          {dirty && (
            <button
              onClick={save}
              disabled={!editable || saving}
              className="flex-1 rounded-lg bg-salvi-black px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
            >
              {saving ? 'Guardando…' : t('actions.save')}
            </button>
          )}
          <button
            onClick={() => navigate('informe')}
            disabled={selectedCount === 0}
            className="flex-1 rounded-lg bg-salvi-black px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
            title={selectedCount === 0 ? 'Selecciona al menos un tramo' : ''}
          >
            Informe {'>'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default StepVias;
