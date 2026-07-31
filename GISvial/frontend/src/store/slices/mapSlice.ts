/** Map instance and control functions — replaces window globals. */
import type { StateCreator } from 'zustand';

export interface MapSlice {
  mapInstance: any | null;
  setMapInstance: (map: any | null) => void;

  toggleBaseMap: (() => void) | null;
  setToggleBaseMap: (fn: (() => void) | null) => void;

  toggle3dView: (() => boolean) | null;
  setToggle3dView: (fn: (() => boolean) | null) => void;

  focusLocation: ((lat: number, lon: number, bbox?: number[]) => void) | null;
  setFocusLocation: (fn: ((lat: number, lon: number, bbox?: number[]) => void) | null) => void;
}

export const createMapSlice: StateCreator<MapSlice, [], [], MapSlice> = (set) => ({
  mapInstance: null,
  toggleBaseMap: null,
  toggle3dView: null,
  focusLocation: null,

  setMapInstance: (map) => set({ mapInstance: map }),

  setToggleBaseMap: (fn) => set({ toggleBaseMap: fn }),

  setToggle3dView: (fn) => set({ toggle3dView: fn }),

  setFocusLocation: (fn) => set({ focusLocation: fn }),
});
