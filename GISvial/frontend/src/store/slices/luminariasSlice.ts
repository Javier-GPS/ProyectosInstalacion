import type { StateCreator } from 'zustand';
import type { GisLuminaire } from '../../types';

export interface LuminariasSlice {
  zoneLuminaires: Record<string, GisLuminaire[]>;
  inventoryLuminaires: Record<string, GisLuminaire[]>;
  selectedLumIds: Set<string>;

  setZoneLuminaires: (zoneId: string, luminaires: GisLuminaire[]) => void;
  addZoneLuminaire: (zoneId: string, lum: GisLuminaire) => void;
  updateZoneLuminaire: (zoneId: string, lumId: number, updates: Partial<GisLuminaire>) => void;
  removeZoneLuminaire: (zoneId: string, lumId: number) => void;
  setSelectedLumIds: (ids: Set<string>) => void;
  toggleLumSelection: (id: string) => void;
  clearSelection: () => void;
}

export const createLuminariasSlice: StateCreator<LuminariasSlice, [], [], LuminariasSlice> = (set) => ({
  zoneLuminaires: {},
  inventoryLuminaires: {},
  selectedLumIds: new Set(),

  setZoneLuminaires: (zoneId, luminaires) => set((s) => ({
    zoneLuminaires: { ...s.zoneLuminaires, [zoneId]: luminaires },
  })),
  addZoneLuminaire: (zoneId, lum) => set((s) => ({
    zoneLuminaires: { ...s.zoneLuminaires, [zoneId]: [...(s.zoneLuminaires[zoneId] || []), lum] },
  })),
  updateZoneLuminaire: (zoneId, lumId, updates) => set((s) => ({
    zoneLuminaires: {
      ...s.zoneLuminaires,
      [zoneId]: (s.zoneLuminaires[zoneId] || []).map((l) => l.id === lumId ? { ...l, ...updates } : l),
    },
  })),
  removeZoneLuminaire: (zoneId, lumId) => set((s) => ({
    zoneLuminaires: {
      ...s.zoneLuminaires,
      [zoneId]: (s.zoneLuminaires[zoneId] || []).filter((l) => l.id !== lumId),
    },
  })),
  setSelectedLumIds: (ids) => set({ selectedLumIds: ids }),
  toggleLumSelection: (id) => set((s) => {
    const next = new Set(s.selectedLumIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    return { selectedLumIds: next };
  }),
  clearSelection: () => set({ selectedLumIds: new Set() }),
});
