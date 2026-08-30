import type { StateCreator } from 'zustand';
import type { GisPlanningInventory, GisPlanningPatch, GisPlanningPayload, GisZoneTrees } from '../../types';
import type { RoadSelectionDraft } from '../types';

const EMPTY_PAYLOAD: GisPlanningPayload = { group_defaults: {}, target_overrides: {} };

export interface ViasSlice {
  activePlanningInventory: GisPlanningInventory | null;
  planningPayload: GisPlanningPayload;
  planningSavedPayload: GisPlanningPayload;
  planningDirty: boolean;
  planningDiscardVersion: number;
  roadTypeVisibility: Record<string, boolean>;
  roadTypeVisibilityByZone: Record<string, Record<string, boolean>>;
  roadSelectionByZone: Record<string, RoadSelectionDraft>;
  zoneTrees: Record<string, GisZoneTrees>;
  selectedTargetRef: string | null;
  selectedStreetName: string | null;
  /** Accumulated segment selection per zone — target_ref → true */
  accumulatedSelection: Record<string, Record<string, true>>;
  /** Last user-confirmed selection per zone (Aceptar/Deseleccionar) */
  savedSelectionByZone: Record<string, Record<string, true>>;

  setActivePlanningInventory: (data: GisPlanningInventory | null) => void;
  setPlanningPayload: (payload: GisPlanningPayload) => void;
  setPlanningBasePayload: (payload: GisPlanningPayload) => void;
  setPlanningDirty: (dirty: boolean) => void;
  confirmPlanningLeave: () => boolean;
  setRoadTypeVisibility: (groupRef: string, visible: boolean) => void;
  setRoadSelection: (zoneId: string, selection: RoadSelectionDraft | null) => void;
  setZoneTrees: (zoneId: string, data: GisZoneTrees) => void;
  setSelectedSegment: (targetRef: string | null, streetName: string | null) => void;
  /** Toggle a single target in accumulated selection */
  toggleTargetSelection: (zoneId: string, targetRef: string) => void;
  /** Toggle all targets of a street at once */
  toggleStreetSelection: (zoneId: string, targetRefs: string[]) => void;
  /** Remove all accumulated selection for a zone */
  clearAccumulatedSelection: (zoneId: string) => void;
  /** Replace selection with a set of target refs */
  setAccumulatedSelection: (zoneId: string, targetRefs: string[]) => void;
  /** Confirm current selection as saved baseline */
  commitSelection: (zoneId: string) => void;
  /** Replace selection from server-saved state (Aceptar persisted) */
  restoreSelection: (zoneId: string, targetRefs: string[]) => void;
  /** Set or clear planning patch override for a specific target */
  setTargetPatch: (targetRef: string, patch: GisPlanningPatch) => void;
  /** Set the same patch on multiple targets at once (e.g. entire street) */
  setBatchTargetPatches: (targetRefs: string[], patch: GisPlanningPatch) => void;
  /** Merge a partial char patch into existing overrides of multiple targets (preserves lighting). */
  setMergeTargetPatches: (targetRefs: string[], patch: GisPlanningPatch) => void;
}

export const createViasSlice: StateCreator<ViasSlice, [], [], ViasSlice> = (set, get) => ({
  activePlanningInventory: null,
  planningPayload: EMPTY_PAYLOAD,
  planningSavedPayload: EMPTY_PAYLOAD,
  planningDirty: false,
  planningDiscardVersion: 0,
  roadTypeVisibility: {},
  roadTypeVisibilityByZone: {},
  roadSelectionByZone: {},
  selectedTargetRef: null,
  selectedStreetName: null,
  accumulatedSelection: {},
  savedSelectionByZone: {},
  zoneTrees: {},

  setActivePlanningInventory: (data) => set((state) => {
    if (!data) return { activePlanningInventory: null };
    const saved = state.roadTypeVisibilityByZone[data.zone_id] || {};
    const visibility = Object.fromEntries(data.groups.map(group => [group.group_ref, saved[group.group_ref] ?? true]));
    return {
      activePlanningInventory: data,
      roadTypeVisibility: visibility,
      roadTypeVisibilityByZone: { ...state.roadTypeVisibilityByZone, [data.zone_id]: visibility },
    };
  }),
  setPlanningPayload: (planningPayload) => set({ planningPayload }),
  setPlanningBasePayload: (planningPayload) => set({ planningPayload, planningSavedPayload: planningPayload, planningDirty: false }),
  setPlanningDirty: (planningDirty) => set({ planningDirty }),
  confirmPlanningLeave: () => {
    const state = get();
    if (!state.planningDirty) return true;
    if (!window.confirm('Hay cambios de planificación sin guardar. ¿Salir y descartarlos?')) return false;
    set({
      planningPayload: state.planningSavedPayload,
      planningDirty: false,
      planningDiscardVersion: state.planningDiscardVersion + 1,
    });
    return true;
  },
  setRoadTypeVisibility: (groupRef, visible) => set((s) => ({
    roadTypeVisibility: { ...s.roadTypeVisibility, [groupRef]: visible },
    roadTypeVisibilityByZone: s.activePlanningInventory ? {
      ...s.roadTypeVisibilityByZone,
      [s.activePlanningInventory.zone_id]: {
        ...(s.roadTypeVisibilityByZone[s.activePlanningInventory.zone_id] || {}),
        [groupRef]: visible,
      },
    } : s.roadTypeVisibilityByZone,
  })),
  setRoadSelection: (zoneId, selection) => set((state) => {
    const roadSelectionByZone = { ...state.roadSelectionByZone };
    if (selection) roadSelectionByZone[zoneId] = selection;
    else delete roadSelectionByZone[zoneId];
    return { roadSelectionByZone };
  }),
  setZoneTrees: (zoneId, data) => set((s) => ({ zoneTrees: { ...s.zoneTrees, [zoneId]: data } })),
  setSelectedSegment: (targetRef, streetName) => set({ selectedTargetRef: targetRef, selectedStreetName: streetName }),
  toggleTargetSelection: (zoneId, targetRef) => set((state) => {
    const current = { ...(state.accumulatedSelection[zoneId] || {}) };
    if (current[targetRef]) delete current[targetRef];
    else current[targetRef] = true;
    return { accumulatedSelection: { ...state.accumulatedSelection, [zoneId]: current } };
  }),
  toggleStreetSelection: (zoneId, targetRefs) => set((state) => {
    const current = { ...(state.accumulatedSelection[zoneId] || {}) };
    const allSelected = targetRefs.every(ref => current[ref]);
    for (const ref of targetRefs) {
      if (allSelected) delete current[ref];
      else current[ref] = true;
    }
    return { accumulatedSelection: { ...state.accumulatedSelection, [zoneId]: current } };
  }),
  clearAccumulatedSelection: (zoneId) => set((state) => {
    const next = { ...state.accumulatedSelection };
    delete next[zoneId];
    return { accumulatedSelection: next };
  }),
  setAccumulatedSelection: (zoneId, targetRefs) => set((state) => {
    const sel: Record<string, true> = {};
    for (const ref of targetRefs) sel[ref] = true;
    return { accumulatedSelection: { ...state.accumulatedSelection, [zoneId]: sel } };
  }),
  commitSelection: (zoneId) => set((state) => ({
    savedSelectionByZone: { ...state.savedSelectionByZone, [zoneId]: { ...(state.accumulatedSelection[zoneId] || {}) } },
  })),
  restoreSelection: (zoneId, targetRefs) => set((state) => {
    const sel: Record<string, true> = {};
    for (const ref of targetRefs) sel[ref] = true;
    return {
      accumulatedSelection: { ...state.accumulatedSelection, [zoneId]: sel },
      savedSelectionByZone: { ...state.savedSelectionByZone, [zoneId]: { ...sel } },
    };
  }),
  setTargetPatch: (targetRef, patch) => set((state) => {
    const targets = { ...(state.planningPayload.target_overrides || {}) };
    if (Object.keys(patch).length) targets[targetRef] = patch;
    else delete targets[targetRef];
    return { planningPayload: { ...state.planningPayload, target_overrides: targets } };
  }),
  setBatchTargetPatches: (targetRefs, patch) => set((state) => {
    const targets = { ...(state.planningPayload.target_overrides || {}) };
    for (const ref of targetRefs) {
      if (Object.keys(patch).length) targets[ref] = { ...patch };
      else delete targets[ref];
    }
    return { planningPayload: { ...state.planningPayload, target_overrides: targets } };
  }),
  setMergeTargetPatches: (targetRefs, patch) => set((state) => {
    const targets = { ...(state.planningPayload.target_overrides || {}) };
    for (const ref of targetRefs) {
      const merged = { ...(targets[ref] || {}) };
      for (const [key, value] of Object.entries(patch)) {
        const k = key as keyof GisPlanningPatch;
        if (value === undefined || value === null) delete merged[k];
        else (merged as any)[k] = value;
      }
      if (Object.keys(merged).length) targets[ref] = merged;
      else delete targets[ref];
    }
    return { planningPayload: { ...state.planningPayload, target_overrides: targets } };
  }),
});
