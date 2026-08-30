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

  blinkTarget: ((targetRef: string) => void) | null;
  setBlinkTarget: (fn: ((targetRef: string) => void) | null) => void;

  highlightTarget: ((targetRef: string) => void) | null;
  setHighlightTarget: (fn: ((targetRef: string) => void) | null) => void;

  clearHighlightTarget: (() => void) | null;
  setClearHighlightTarget: (fn: (() => void) | null) => void;
}

export const createMapSlice: StateCreator<MapSlice, [], [], MapSlice> = (set) => ({
  mapInstance: null,
  toggleBaseMap: null,
  toggle3dView: null,
  focusLocation: null,
  blinkTarget: null,
  highlightTarget: null,
  clearHighlightTarget: null,

  setMapInstance: (map) => set({ mapInstance: map }),

  setToggleBaseMap: (fn) => set({ toggleBaseMap: fn }),

  setToggle3dView: (fn) => set({ toggle3dView: fn }),

  setFocusLocation: (fn) => set({ focusLocation: fn }),

  setBlinkTarget: (fn) => set({ blinkTarget: fn }),

  setHighlightTarget: (fn) => set({ highlightTarget: fn }),

  setClearHighlightTarget: (fn) => set({ clearHighlightTarget: fn }),
});
