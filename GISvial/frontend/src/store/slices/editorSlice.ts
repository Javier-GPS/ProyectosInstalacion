import type { StateCreator } from 'zustand';
import type { EditorObject } from '../../lib/editorObjects';

const STORAGE_PREFIX = 'gis-editor:';

export interface EditorSlice {
  editorOpen: boolean;
  editorZoneId: string | null;
  /** Herramienta activa (catálogo de objeto), o 'lasso', o null = selección. */
  editorTool: string | null;
  editorObjects: Record<string, EditorObject[]>;
  editorSelectedIds: string[];
  /** Tramo (target_ref) seleccionado para editar sus características de vía. */
  editorRoadRef: string | null;
  /** Distancia (m) a la calzada para colocar objetos de forma paralela/snapped. */
  editorPlaceOffset: number;
  /** Alinear el objeto seleccionado a la calzada al hacer clic. */
  editorAlign: boolean;
  /** Por zona: true si coincide con lo persistido. */
  editorSaved: Record<string, boolean>;

  openEditor: (zoneId: string) => void;
  closeEditor: () => void;
  setEditorTool: (tool: string | null) => void;
  addEditorObject: (zoneId: string, obj: EditorObject) => void;
  updateEditorObject: (zoneId: string, id: string, patch: Partial<EditorObject>) => void;
  updateEditorObjects: (zoneId: string, ids: string[], patch: Partial<EditorObject>) => void;
  removeEditorObject: (zoneId: string, id: string) => void;
  removeEditorObjects: (zoneId: string, ids: string[]) => void;
  selectEditorObjects: (ids: string[]) => void;
  setEditorRoadRef: (ref: string | null) => void;
  setEditorPlaceOffset: (offset: number) => void;
  setEditorAlign: (align: boolean) => void;
  saveEditorObjects: (zoneId: string) => void;
}

const loadFromStorage = (zoneId: string): EditorObject[] => {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + zoneId);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as EditorObject[]) : [];
  } catch {
    return [];
  }
};

export const createEditorSlice: StateCreator<EditorSlice, [], [], EditorSlice> = (set, get) => ({
  editorOpen: false,
  editorZoneId: null,
  editorTool: null,
  editorObjects: {},
  editorSelectedIds: [],
  editorRoadRef: null,
  editorPlaceOffset: 0,
  editorAlign: false,
  editorSaved: {},

  openEditor: (zoneId) => set(() => {
    const existing = get().editorObjects[zoneId];
    const loaded = existing && existing.length ? existing : loadFromStorage(zoneId);
    return {
      editorOpen: true,
      editorZoneId: zoneId,
      editorTool: null,
      editorSelectedIds: [],
  editorRoadRef: null,
  editorPlaceOffset: 0,
  editorAlign: false,
  editorObjects: { ...get().editorObjects, [zoneId]: loaded },
  editorSaved: { ...get().editorSaved, [zoneId]: true },
    };
  }),

  closeEditor: () => set({ editorOpen: false, editorTool: null, editorSelectedIds: [], editorRoadRef: null, editorAlign: false }),

  setEditorTool: (tool) => set({ editorTool: tool }),

  addEditorObject: (zoneId, obj) => set((s) => ({
    editorObjects: { ...s.editorObjects, [zoneId]: [...(s.editorObjects[zoneId] || []), obj] },
    editorSelectedIds: [obj.id],
    editorSaved: { ...s.editorSaved, [zoneId]: false },
  })),

  updateEditorObject: (zoneId, id, patch) => set((s) => {
    const list = (s.editorObjects[zoneId] || []).map(o => (o.id === id ? { ...o, ...patch } : o));
    return {
      editorObjects: { ...s.editorObjects, [zoneId]: list },
      editorSaved: { ...s.editorSaved, [zoneId]: false },
    };
  }),

  updateEditorObjects: (zoneId, ids, patch) => set((s) => {
    const idSet = new Set(ids);
    const list = (s.editorObjects[zoneId] || []).map(o => (idSet.has(o.id) ? { ...o, ...patch } : o));
    return {
      editorObjects: { ...s.editorObjects, [zoneId]: list },
      editorSaved: { ...s.editorSaved, [zoneId]: false },
    };
  }),

  removeEditorObject: (zoneId, id) => set((s) => {
    const list = (s.editorObjects[zoneId] || []).filter(o => o.id !== id);
    return {
      editorObjects: { ...s.editorObjects, [zoneId]: list },
      editorSelectedIds: s.editorSelectedIds.filter(x => x !== id),
      editorSaved: { ...s.editorSaved, [zoneId]: false },
    };
  }),

  removeEditorObjects: (zoneId, ids) => set((s) => {
    const idSet = new Set(ids);
    const list = (s.editorObjects[zoneId] || []).filter(o => !idSet.has(o.id));
    return {
      editorObjects: { ...s.editorObjects, [zoneId]: list },
      editorSelectedIds: s.editorSelectedIds.filter(x => !idSet.has(x)),
      editorSaved: { ...s.editorSaved, [zoneId]: false },
    };
  }),

  selectEditorObjects: (ids) => set({ editorSelectedIds: ids }),

  setEditorRoadRef: (ref) => set({ editorRoadRef: ref }),

  setEditorPlaceOffset: (offset) => set({ editorPlaceOffset: offset }),

  setEditorAlign: (align) => set({ editorAlign: align }),

  saveEditorObjects: (zoneId) => set((s) => {
    const list = s.editorObjects[zoneId] || [];
    try {
      window.localStorage.setItem(STORAGE_PREFIX + zoneId, JSON.stringify(list));
    } catch { /* ignore quota */ }
    return { editorSaved: { ...s.editorSaved, [zoneId]: true } };
  }),
});
