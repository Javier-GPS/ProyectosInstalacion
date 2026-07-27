import type { StateCreator } from 'zustand';
import type { GisZone, GisZoneConfig } from '../../types';

export interface ZonasSlice {
  zones: GisZone[];
  selectedZoneId: string | null;
  zoneConfigs: Record<string, GisZoneConfig>;

  setZones: (zones: GisZone[]) => void;
  addZone: (zone: GisZone) => void;
  updateZone: (id: string, zone: Partial<GisZone>) => void;
  removeZone: (id: string) => void;
  setSelectedZone: (id: string | null) => void;
  setZoneConfig: (zoneId: string, config: GisZoneConfig) => void;
}

export const createZonasSlice: StateCreator<ZonasSlice, [], [], ZonasSlice> = (set) => ({
  zones: [],
  selectedZoneId: null,
  zoneConfigs: {},

  setZones: (zones) => set({ zones }),
  addZone: (zone) => set((s) => ({ zones: [...s.zones, zone] })),
  updateZone: (id, partial) => set((s) => ({
    zones: s.zones.map((z) => z.id === id ? { ...z, ...partial } : z),
  })),
  removeZone: (id) => set((s) => ({
    zones: s.zones.filter((z) => z.id !== id),
    selectedZoneId: s.selectedZoneId === id ? null : s.selectedZoneId,
  })),
  setSelectedZone: (id) => set({ selectedZoneId: id }),
  setZoneConfig: (zoneId, config) => set((s) => ({
    zoneConfigs: { ...s.zoneConfigs, [zoneId]: config },
  })),
});
