import { create } from 'zustand';
import type { GisLanguage } from '../i18n';
import type {
  GisProject, GisZone, GisZoneConfig, GisOsmData,
  GisLuminaire, GisPhotometricResult, GisZoneTrees,
} from '../types';

/* ── Road type configuration (same as legacy ROAD_CFG) ─────────────────── */
export interface RoadTypeCfg {
  labelKey: string;
  color: string;
  width: number;
  defaultSpacing: number;
  defaultLightingClass: string;
}

export const ROAD_CFG: Record<string, RoadTypeCfg> = {
  primary:    { labelKey: 'road.primary',    color: '#4caf82', width: 7, defaultSpacing: 35, defaultLightingClass: 'M1' },
  secondary:  { labelKey: 'road.secondary',  color: '#e67e22', width: 6, defaultSpacing: 30, defaultLightingClass: 'M2' },
  tertiary:   { labelKey: 'road.tertiary',   color: '#3498db', width: 5, defaultSpacing: 30, defaultLightingClass: 'M3' },
  residential:{ labelKey: 'road.residential',color: '#9b59b6', width: 4, defaultSpacing: 25, defaultLightingClass: 'M4' },
  unclassified:{labelKey: 'road.unclassified',color:'#e74c3c', width: 3, defaultSpacing: 25, defaultLightingClass: 'M4' },
};

export type AppMode = 'planning' | 'detail';
export type DetailSelectionMode = 'none' | 'click' | 'marquee' | 'lasso' | 'criteria';

export interface GisState {
  // Auth
  initialized: boolean;

  // Projects
  projects: GisProject[];
  activeProjectId: string | null;

  // Zones
  zones: GisZone[];
  selectedZoneId: string | null;
  zoneConfigs: Record<string, GisZoneConfig>;
  zoneOsm: Record<string, GisOsmData>;
  zoneTrees: Record<string, GisZoneTrees>;
  zoneLuminaires: Record<string, GisLuminaire[]>;
  zonePhotometric: Record<string, GisPhotometricResult[]>;

  // Inventory
  inventoryLuminaires: Record<string, GisLuminaire[]>; // placed luminaires by zone

  // App mode
  appMode: AppMode;
  detailZoneId: string | null;
  detailSelectionMode: DetailSelectionMode;
  selectedLumIds: Set<string>;
  showCompliance: boolean;

  // UI
  language: GisLanguage;
  sidebarOpen: boolean;

  // Actions
  setProjects: (projects: GisProject[]) => void;
  setActiveProject: (id: string | null) => void;
  setZones: (zones: GisZone[]) => void;
  addZone: (zone: GisZone) => void;
  updateZone: (id: string, zone: Partial<GisZone>) => void;
  removeZone: (id: string) => void;
  setSelectedZone: (id: string | null) => void;
  setZoneConfig: (zoneId: string, config: GisZoneConfig) => void;
  setZoneOsm: (zoneId: string, data: GisOsmData) => void;
  setZoneTrees: (zoneId: string, data: GisZoneTrees) => void;
  setZoneLuminaires: (zoneId: string, luminaires: GisLuminaire[]) => void;
  setZonePhotometric: (zoneId: string, data: GisPhotometricResult[]) => void;
  addZoneLuminaire: (zoneId: string, lum: GisLuminaire) => void;
  updateZoneLuminaire: (zoneId: string, lumId: number, updates: Partial<GisLuminaire>) => void;
  removeZoneLuminaire: (zoneId: string, lumId: number) => void;
  setAppMode: (mode: AppMode) => void;
  setDetailZone: (zoneId: string | null) => void;
  setDetailSelectionMode: (mode: DetailSelectionMode) => void;
  setSelectedLumIds: (ids: Set<string>) => void;
  toggleLumSelection: (id: string) => void;
  clearSelection: () => void;
  setShowCompliance: (show: boolean) => void;
  setLanguage: (lang: GisLanguage) => void;
  setSidebarOpen: (open: boolean) => void;
  setInitialized: (v: boolean) => void;
}

export const useGisStore = create<GisState>((set, get) => ({
  initialized: false,
  projects: [],
  activeProjectId: null,
  zones: [],
  selectedZoneId: null,
  zoneConfigs: {},
  zoneOsm: {},
  zoneTrees: {},
  zoneLuminaires: {},
  zonePhotometric: {},
  inventoryLuminaires: {},
  appMode: 'planning',
  detailZoneId: null,
  detailSelectionMode: 'none',
  selectedLumIds: new Set(),
  showCompliance: false,
  language: (typeof localStorage !== 'undefined' ? localStorage.getItem('gis-language') as GisLanguage : null) || 'es',
  sidebarOpen: true,

  setInitialized: (v) => set({ initialized: v }),
  setProjects: (projects) => set({ projects }),
  setActiveProject: (id) => set({ activeProjectId: id }),
  setZones: (zones) => set({ zones }),
  addZone: (zone) => set((s) => ({ zones: [...s.zones, zone] })),
  updateZone: (id, partial) => set((s) => ({ zones: s.zones.map((z) => z.id === id ? { ...z, ...partial } : z) })),
  removeZone: (id) => set((s) => ({ zones: s.zones.filter((z) => z.id !== id) })),
  setSelectedZone: (id) => set({ selectedZoneId: id }),
  setZoneConfig: (zoneId, config) => set((s) => ({ zoneConfigs: { ...s.zoneConfigs, [zoneId]: config } })),
  setZoneOsm: (zoneId, data) => set((s) => ({ zoneOsm: { ...s.zoneOsm, [zoneId]: data } })),
  setZoneTrees: (zoneId, data) => set((s) => ({ zoneTrees: { ...s.zoneTrees, [zoneId]: data } })),
  setZoneLuminaires: (zoneId, luminaires) => set((s) => ({ zoneLuminaires: { ...s.zoneLuminaires, [zoneId]: luminaires } })),
  setZonePhotometric: (zoneId, data) => set((s) => ({ zonePhotometric: { ...s.zonePhotometric, [zoneId]: data } })),
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
  setAppMode: (mode) => set({ appMode: mode }),
  setDetailZone: (zoneId) => set({ detailZoneId: zoneId }),
  setDetailSelectionMode: (mode) => set({ detailSelectionMode: mode }),
  setSelectedLumIds: (ids) => set({ selectedLumIds: ids }),
  toggleLumSelection: (id) => set((s) => {
    const next = new Set(s.selectedLumIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    return { selectedLumIds: next };
  }),
  clearSelection: () => set({ selectedLumIds: new Set() }),
  setShowCompliance: (show) => set({ showCompliance: show }),
  setLanguage: (lang) => { localStorage.setItem('gis-language', lang); set({ language: lang }); },
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
}));
