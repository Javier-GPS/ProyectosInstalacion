import { create } from 'zustand';
import { createMapSlice, type MapSlice } from './slices/mapSlice';
import { createProyectosSlice, type ProyectosSlice } from './slices/proyectosSlice';
import { createZonasSlice, type ZonasSlice } from './slices/zonasSlice';
import { createViasSlice, type ViasSlice } from './slices/viasSlice';
import { createLuminariasSlice, type LuminariasSlice } from './slices/luminariasSlice';
import { createFotometriaSlice, type FotometriaSlice } from './slices/fotometriaSlice';
import { createUiSlice, type UiSlice } from './slices/uiSlice';

export { ROAD_CFG } from './types';
export type { RoadTypeCfg, WizardStep, DetailSelectionMode, StatusGranular } from './types';

export type GisStore = ProyectosSlice & ZonasSlice & ViasSlice & LuminariasSlice & FotometriaSlice & UiSlice & MapSlice;

export const useGisStore = create<GisStore>()((...a) => ({
  ...createMapSlice(...a),
  ...createProyectosSlice(...a),
  ...createZonasSlice(...a),
  ...createViasSlice(...a),
  ...createLuminariasSlice(...a),
  ...createFotometriaSlice(...a),
  ...createUiSlice(...a),
}));
