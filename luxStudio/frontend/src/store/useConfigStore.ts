import { create } from 'zustand';
import type { Language } from '../i18n';
import type { CalculationResult, LightingClass, RoadElement } from '../types';
import { DEFAULT_ROAD_ELEMENTS } from '../types';

const LAST_OPENED_STORAGE_KEY = 'lux-studio-last-opened-tramo';

const readPersistedLastOpened = (): { projectId: number; tramoId: number } | null => {
  if (typeof localStorage === 'undefined') return null;
  try {
    const raw = localStorage.getItem(LAST_OPENED_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      parsed && typeof parsed === 'object' &&
      typeof parsed.projectId === 'number' && Number.isFinite(parsed.projectId) &&
      typeof parsed.tramoId === 'number' && Number.isFinite(parsed.tramoId)
    ) {
      return { projectId: parsed.projectId, tramoId: parsed.tramoId };
    }
  } catch {
    // ponytail: ignore corrupt JSON, fall back to no persisted entry
  }
  return null;
};

const writePersistedLastOpened = (projectId: number | null, tramoId: number | null) => {
  if (typeof localStorage === 'undefined') return;
  if (projectId === null || tramoId === null) {
    localStorage.removeItem(LAST_OPENED_STORAGE_KEY);
    return;
  }
  localStorage.setItem(LAST_OPENED_STORAGE_KEY, JSON.stringify({ projectId, tramoId }));
};

const persistedLastOpened = readPersistedLastOpened();

export interface ConfigState {
  // Road geometry (new element-based)
  roadElements: RoadElement[];

  // Road geometry (flat — derived from roadElements for backward compat)
  road_width: number;
  sidewalk_left: number;
  sidewalk_right: number;
  lanes: number;
  median_width: number;

  // Luminaire arrangement
  arrangement: 'Lineal' | 'Bilateral' | 'Bilateral Alternada' | 'Central Doble' | 'En Isleta';
  height: number; // meters
  spacing: number; // meters
  arm_length: number; // meters
  pole_offset: number; // meters from road edge to pole axis
  pole_side: 'left' | 'right'; // side where unilateral poles are installed
  pole_count: number; // number of poles per row (scene length)
  tilt: number; // degrees

  // Luminaire selection
  optic_family: string;
  target_flux: number; // lumens — user input (power is computed from this)
  power: number; // watts — computed from target_flux via PCB selection
  ldt_id: string;
  manufacturer: string;
  model_family: string;
  // Catalog dimension selections (UI-only, not sent to backend)
  gama: string;
  difusor: string;
  lente: string;
  led_type: string;

  // Other parameters
  lighting_class: LightingClass;
  sidewalk_left_class: string;
  sidewalk_right_class: string;
  median_class: string;
  mf: number; // maintenance factor
  pavement: 'R1' | 'R2' | 'R3' | 'R4';
  cct: number; // Kelvin
  cri: 70 | 80 | 90;
  t_amb_c: number;
  margen_lavg: number;
  i_op_ma: number | null;
  lm_w_min: number | null;
  language: Language;
  driverEfficiency: number;

  // 3D visualization settings (persisted with the tramo config)
  illuminance_scale_mode: 'auto' | 'manual';
  illuminance_scale_min: number;
  illuminance_scale_max: number;
  photometric_display_unit: 'lux' | 'candela';
  generate_buildings: boolean;
  building_height: number;
  buildings_as_obstacles: boolean;

  setSidewalkLeftClass: (c: string) => void;
  setSidewalkRightClass: (c: string) => void;
  setMedianClass: (c: string) => void;

  // Road element actions
  setRoadElements: (elements: RoadElement[]) => void;
  addRoadElement: (el: RoadElement, index?: number) => void;
  removeRoadElement: (index: number) => void;
  updateRoadElement: (index: number, el: Partial<RoadElement>) => void;
  moveRoadElement: (fromIdx: number, toIdx: number) => void;

  // Calculated results
  results: CalculationResult | null;
  loading: boolean;
  error: string | null;

  // Dirty tracking for unsaved changes (per tramo)
  dirty: boolean;
  lastSavedSnapshot: SavedSnapshot | null;
  lastEditedTramoId: number | null;

  // Actions
  setRoadWidth: (w: number) => void;
  setSidewalkLeft: (w: number) => void;
  setSidewalkRight: (w: number) => void;
  setLanes: (n: number) => void;
  setMedianWidth: (w: number) => void;
  setArrangement: (a: ConfigState['arrangement']) => void;
  setHeight: (h: number) => void;
  setSpacing: (s: number) => void;
  setArmLength: (a: number) => void;
  setPoleOffset: (o: number) => void;
  setPoleSide: (s: ConfigState['pole_side']) => void;
  setPoleCount: (n: number) => void;
  setTilt: (t: number) => void;
  setOpticFamily: (f: string) => void;
  setPower: (p: number) => void;
  setTargetFlux: (f: number) => void;
  setManufacturer: (m: string) => void;
  setModelFamily: (m: string) => void;
  setGama: (g: string) => void;
  setDifusor: (d: string) => void;
  setLente: (l: string) => void;
  setLedType: (lt: string) => void;
  setSelectedLdt: (ldt: { id: string; manufacturer: string; model_family: string; optic_family: string }) => void;
  setLightingClass: (c: ConfigState['lighting_class']) => void;
  setMf: (m: number) => void;
  setPavement: (p: ConfigState['pavement']) => void;
  setCct: (c: number) => void;
  setTAmbC: (t: number) => void;
  setMargenLavg: (m: number) => void;
  setIOpMa: (m: number | null) => void;
  setLmWMin: (m: number | null) => void;
  setCri: (c: ConfigState['cri']) => void;
  setDriverEfficiency: (v: number) => void;
  setLanguage: (language: Language) => void;
  setIlluminanceScaleMode: (mode: ConfigState['illuminance_scale_mode']) => void;
  setIlluminanceScaleMin: (value: number) => void;
  setIlluminanceScaleMax: (value: number) => void;
  setPhotometricDisplayUnit: (unit: ConfigState['photometric_display_unit']) => void;
  setGenerateBuildings: (enabled: boolean) => void;
  setBuildingHeight: (height: number) => void;
  setBuildingsAsObstacles: (enabled: boolean) => void;
  setResults: (r: CalculationResult | null) => void;
  setLoading: (l: boolean) => void;
  setError: (e: string | null) => void;
  setDirty: (d: boolean) => void;
  markSaved: (snapshot: SavedSnapshot) => void;
  setLastEditedTramo: (id: number | null) => void;
  lastOpenedTramoId: number | null;
  lastOpenedTramoProjectId: number | null;
  setLastOpenedTramo: (projectId: number | null, tramoId: number | null) => void;
  reset: () => void;
  calculate: () => Promise<CalculationResult | null>;
}

export interface SavedSnapshot {
  configJson: string;
  resultJson: string | null;
}

const markDirty = (set: any) => set({ dirty: true });

export const useConfigStore = create<ConfigState>((set, get) => {
  const dirtyField = <K extends keyof ConfigState>(key: K) => (value: ConfigState[K]) => {
    markDirty(set);
    set({ [key]: value } as Partial<ConfigState>);
  };

  return ({
  // Initial values
  roadElements: DEFAULT_ROAD_ELEMENTS,
  road_width: 7.0,
  sidewalk_left: 1.5,
  sidewalk_right: 1.5,
  lanes: 2,
  median_width: 0,

  arrangement: 'Lineal',
  height: 9.0,
  spacing: 30.0,
  arm_length: 1.5,
  pole_offset: 0.0,
  pole_side: 'left',
  pole_count: 3,
  tilt: 5,

  optic_family: 'F151',
  target_flux: 10000,
  power: 0,
  ldt_id: '',
  manufacturer: '',
  model_family: '',
  gama: '',
  difusor: '',
  lente: '',
  led_type: '',

  lighting_class: 'M3',
  sidewalk_left_class: 'P4',
  sidewalk_right_class: 'P4',
  median_class: 'P4',
  mf: 0.85,
  pavement: 'R3',
  cct: 4000,
  cri: 70,
  t_amb_c: 25.0,
  margen_lavg: 0.0,
  i_op_ma: null,
  lm_w_min: null,
  driverEfficiency: 0.9,
  language: (typeof localStorage !== 'undefined' ? localStorage.getItem('lux-studio-language') as Language : null) || 'es',
  illuminance_scale_mode: 'auto',
  illuminance_scale_min: 0,
  illuminance_scale_max: 50,
  photometric_display_unit: 'lux',
  generate_buildings: false,
  building_height: 12,
  buildings_as_obstacles: false,

  results: null,
  loading: false,
  error: null,

  dirty: false,
  lastSavedSnapshot: null,
  lastEditedTramoId: null,
  lastOpenedTramoId: persistedLastOpened?.tramoId ?? null,
  lastOpenedTramoProjectId: persistedLastOpened?.projectId ?? null,
  // Setters (all mark dirty)
  setRoadWidth: dirtyField('road_width'),
  setSidewalkLeft: dirtyField('sidewalk_left'),
  setSidewalkRight: dirtyField('sidewalk_right'),
  setLanes: dirtyField('lanes'),
  setMedianWidth: dirtyField('median_width'),
  setArrangement: dirtyField('arrangement'),
  setHeight: dirtyField('height'),
  setSpacing: dirtyField('spacing'),
  setArmLength: dirtyField('arm_length'),
  setPoleOffset: dirtyField('pole_offset'),
  setPoleSide: dirtyField('pole_side'),
  setPoleCount: dirtyField('pole_count'),
  setTilt: dirtyField('tilt'),
  setOpticFamily: dirtyField('optic_family'),
  setPower: dirtyField('power'),
  setTargetFlux: dirtyField('target_flux'),
  setManufacturer: dirtyField('manufacturer'),
  setModelFamily: dirtyField('model_family'),
  setGama: dirtyField('gama'),
  setDifusor: dirtyField('difusor'),
  setLente: dirtyField('lente'),
  setLedType: dirtyField('led_type'),
  setSelectedLdt: (ldt) => {
    markDirty(set);
    set({
      ldt_id: ldt.id,
      manufacturer: ldt.manufacturer,
      model_family: ldt.model_family,
      optic_family: ldt.optic_family,
    });
  },
  setLightingClass: dirtyField('lighting_class'),
  setSidewalkLeftClass: dirtyField('sidewalk_left_class'),
  setSidewalkRightClass: dirtyField('sidewalk_right_class'),
  setMedianClass: dirtyField('median_class'),

  // Road element actions
  setRoadElements: (elements) => {
    const normalized: RoadElement[] = [];
    let totalWidth = 0;
    let firstSidewalkWidth: number | undefined;
    let lastSidewalkWidth: number | undefined;
    let carriagewayLanes = 2;
    let hasCarriageway = false;
    for (const el of elements) {
      const normalizedEl = {
        ...el,
        lighting_class: el.lighting_class || null,
        pedestrian_class: el.pedestrian_class || null,
        lanes: el.lanes || null,
      } as RoadElement;
      normalized.push(normalizedEl);
      totalWidth += normalizedEl.width;
      if (normalizedEl.type === 'sidewalk') {
        firstSidewalkWidth ??= normalizedEl.width;
        lastSidewalkWidth = normalizedEl.width;
      } else if (normalizedEl.type === 'carriageway' && !hasCarriageway) {
        carriagewayLanes = normalizedEl.lanes ?? 2;
        hasCarriageway = true;
      }
    }
    markDirty(set);
    set({
      roadElements: normalized,
      road_width: totalWidth,
      sidewalk_left: firstSidewalkWidth ?? 0,
      sidewalk_right: lastSidewalkWidth ?? 0,
      lanes: carriagewayLanes,
      median_width: 0,
    });
  },
  addRoadElement: (el, index) => {
    const elements = [...get().roadElements];
    if (index !== undefined) {
      elements.splice(index, 0, el);
    } else {
      // Default: add before first carriageway, or at end
      const ci = elements.findIndex(e => e.type === 'carriageway');
      if (ci >= 0) elements.splice(ci, 0, el);
      else elements.push(el);
    }
    get().setRoadElements(elements);
  },
  removeRoadElement: (index) => {
    const elements = get().roadElements.filter((_, i) => i !== index);
    if (elements.length === 0) {
      elements.push({ type: 'carriageway', width: 7, lanes: 2, lighting_class: 'M3' });
    }
    get().setRoadElements(elements);
  },
  updateRoadElement: (index, partial) => {
    const elements = get().roadElements.map((el, i) =>
      i === index ? { ...el, ...partial } as RoadElement : el,
    );
    get().setRoadElements(elements);
  },
  moveRoadElement: (fromIdx, toIdx) => {
    const elements = [...get().roadElements];
    const [moved] = elements.splice(fromIdx, 1);
    elements.splice(toIdx, 0, moved);
    get().setRoadElements(elements);
  },
  setMf: dirtyField('mf'),
  setPavement: dirtyField('pavement'),
  setCct: dirtyField('cct'),
  setCri: dirtyField('cri'),
  setTAmbC: dirtyField('t_amb_c'),
  setMargenLavg: dirtyField('margen_lavg'),
  setIOpMa: dirtyField('i_op_ma'),
  setLmWMin: dirtyField('lm_w_min'),
  setDriverEfficiency: dirtyField('driverEfficiency'),
  setLanguage: (language: Language) => {
    localStorage.setItem('lux-studio-language', language);
    set({ language });
  },
  setIlluminanceScaleMode: dirtyField('illuminance_scale_mode'),
  setIlluminanceScaleMin: dirtyField('illuminance_scale_min'),
  setIlluminanceScaleMax: dirtyField('illuminance_scale_max'),
  setPhotometricDisplayUnit: dirtyField('photometric_display_unit'),
  setGenerateBuildings: dirtyField('generate_buildings'),
  setBuildingHeight: dirtyField('building_height'),
  setBuildingsAsObstacles: dirtyField('buildings_as_obstacles'),
  setResults: (r) => set({ results: r }),
  setLoading: (l: boolean) => set({ loading: l }),
  setError: (e: string | null) => set({ error: e }),
  setDirty: (d: boolean) => set({ dirty: d }),
  markSaved: (snapshot) => set({ dirty: false, lastSavedSnapshot: snapshot }),
  setLastEditedTramo: (id) => set({ lastEditedTramoId: id }),
  setLastOpenedTramo: (projectId, tramoId) => {
    set({ lastOpenedTramoId: tramoId, lastOpenedTramoProjectId: projectId });
    writePersistedLastOpened(projectId, tramoId);
  },
  reset: () => set({
    roadElements: DEFAULT_ROAD_ELEMENTS,
    road_width: 7.0,
    sidewalk_left: 1.5,
    sidewalk_right: 1.5,
    lanes: 2,
    median_width: 0,
    arrangement: 'Lineal',
    height: 9.0,
    spacing: 30.0,
  arm_length: 0,
    pole_offset: 0.0,
    pole_side: 'left',
    pole_count: 3,
    tilt: 5,
    optic_family: 'F151',
    target_flux: 10000,
    power: 0,
    ldt_id: '',
    manufacturer: '',
    model_family: '',
    gama: '',
    difusor: '',
    lente: '',
    led_type: '',
    lighting_class: 'M3',
    sidewalk_left_class: 'P4',
    sidewalk_right_class: 'P4',
    median_class: 'P4',
    mf: 0.85,
    pavement: 'R3',
    cct: 4000,
    cri: 70,
    t_amb_c: 25.0,
    margen_lavg: 0.0,
    i_op_ma: null,
    lm_w_min: null,
    driverEfficiency: 0.9,
    language: get().language,
    illuminance_scale_mode: 'auto',
    illuminance_scale_min: 0,
    illuminance_scale_max: 50,
    photometric_display_unit: 'lux',
    generate_buildings: false,
    building_height: 12,
    buildings_as_obstacles: false,
    results: null,
    loading: false,
    error: null,
    dirty: false,
    lastSavedSnapshot: null,
    lastEditedTramoId: null,
  }),

  // Calculate action
  calculate: async () => {
    set({ loading: true, error: null });
    try {
      const config = get();

      let elementsWidth = 0;
      const roadElements = config.roadElements.map((el) => {
        elementsWidth += el.width;
        return {
          ...el,
          lighting_class: el.lighting_class || null,
          pedestrian_class: el.pedestrian_class || null,
          lanes: el.lanes || null,
        };
      });
      const requestBody = {
        road_elements: roadElements,
        road_width: Math.max(0.5, Math.min(30, elementsWidth)),
        sidewalk_left: config.sidewalk_left,
        sidewalk_right: config.sidewalk_right,
        lanes: config.lanes,
        median_width: config.median_width,
        arrangement: config.arrangement,
        height: config.height,
        spacing: config.spacing,
        arm_length: config.arm_length,
        armLength: config.arm_length,
        pole_offset: config.pole_offset,
        pole_side: config.pole_side,
        tilt: config.tilt,
        armTiltAngle: config.tilt,
        optic_family: config.optic_family,
        target_flux: config.target_flux > 0 ? config.target_flux : null,
        power: config.power || 0,
        driver_eficiencia: config.driverEfficiency,
        ldt_id: config.ldt_id,
        manufacturer: config.manufacturer,
        model_family: config.model_family,
        gama: config.gama,
        difusor: config.difusor,
        lente: config.lente,
        led_type: config.led_type,
        lighting_class: config.lighting_class,
        sidewalk_left_class: config.sidewalk_left_class || null,
        sidewalk_right_class: config.sidewalk_right_class || null,
        median_class: config.median_class || null,
        mf: config.mf,
        pavement: config.pavement,
        cct: config.cct,
        cri: config.cri,
        t_amb_c: config.t_amb_c,
        margen_lavg: config.margen_lavg,
        i_op_ma: config.i_op_ma ?? undefined,
        lm_w_min: config.lm_w_min ?? undefined,
        language: config.language,
        illuminance_scale_mode: config.illuminance_scale_mode,
        illuminance_scale_min: config.illuminance_scale_min,
        illuminance_scale_max: config.illuminance_scale_max,
        photometric_display_unit: config.photometric_display_unit,
        generate_buildings: config.generate_buildings,
        building_height: config.building_height,
        buildings_as_obstacles: config.buildings_as_obstacles,
      };

      const response = await fetch('/api/calculate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || `Calculation failed (HTTP ${response.status})`);
      }

      const result = await response.json().catch(() => null);
      if (!result) throw new Error('Calculation failed: invalid response');
      set({ results: result, dirty: true });
      return result;
    } catch (err: any) {
      set({ error: err.message || 'An unknown error occurred' });
      return null;
    } finally {
      set({ loading: false });
    }
  },
  });
});
