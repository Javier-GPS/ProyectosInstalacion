import type { StateCreator } from 'zustand';
import type { GisPhotometricResult } from '../../types';

export interface FotometriaSlice {
  zonePhotometric: Record<string, GisPhotometricResult[]>;
  showCompliance: boolean;

  setZonePhotometric: (zoneId: string, data: GisPhotometricResult[]) => void;
  setShowCompliance: (show: boolean) => void;
}

export const createFotometriaSlice: StateCreator<FotometriaSlice, [], [], FotometriaSlice> = (set) => ({
  zonePhotometric: {},
  showCompliance: false,

  setZonePhotometric: (zoneId, data) => set((s) => ({
    zonePhotometric: { ...s.zonePhotometric, [zoneId]: data },
  })),
  setShowCompliance: (show) => set({ showCompliance: show }),
});
