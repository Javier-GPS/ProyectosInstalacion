import { useConfigStore } from '../store/useConfigStore';
import { buildCanonicalConfigRequest } from './configRequest';

const sanitizeElement = (el: any) => ({
  ...el,
  lighting_class: el.lighting_class || null,
  pedestrian_class: el.pedestrian_class || null,
  lanes: el.lanes || null,
});

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// ponytail: road_width in CalculationConfig is legacy/derived. The backend
// recomputes W from road_elements when present and revalidates road_width
// against ge=0.5, le=30. Clamp to that range so transient sums (0 or 35)
// from partial road_elements never 422 the calculation.
const sumElementWidths = (els: any[]): number =>
  els.reduce((s, e) => s + (typeof e.width === 'number' ? e.width : 0), 0);

export const buildCalculationRequest = () => {
  const config = useConfigStore.getState();
  const elementsWidth = sumElementWidths(config.roadElements);
  const roadWidth = config.roadElements.length > 0
    ? clamp(elementsWidth, 0.5, 30)
    : config.road_width;
  // ponytail: visualOnlyFields belong to the 3D scene, not the CIE 140
  // calculation. The backend validates them anyway, so a 370-lux
  // auto-scale cap 422s the calc. Omit them here; snapshotConfig keeps
  // persisting them to the tramo so the UI state survives reload.
  return {
    ...buildCanonicalConfigRequest(config),
    road_elements: config.roadElements.map(sanitizeElement),
    road_width: roadWidth,
    sidewalk_left_class: config.sidewalk_left_class || null,
    sidewalk_right_class: config.sidewalk_right_class || null,
    median_class: config.median_class || null,
    t_amb_c: config.t_amb_c,
    margen_lavg: config.margen_lavg,
    i_op_ma: config.i_op_ma ?? undefined,
    lm_w_min: config.lm_w_min ?? undefined,
    language: config.language,
    driver_eficiencia: config.driverEfficiency,
  };
};

export const configHash = (value: unknown) => JSON.stringify(value);

const visualOnlyFields = new Set([
  'illuminance_scale_mode',
  'illuminance_scale_min',
  'illuminance_scale_max',
  'photometric_display_unit',
  'generate_buildings',
  'building_height',
  'buildings_as_obstacles',
  'median_width',
  'language',
]);

export const calculationConfigHash = (value: Record<string, unknown>) => JSON.stringify(
  Object.fromEntries(Object.entries(value).filter(([key]) => !visualOnlyFields.has(key) && key !== '__configHash')),
);

const autoOptimizationIgnoredFields = new Set([
  ...visualOnlyFields,
  'target_flux',
  'power',
]);

export const autoOptimizationConfigHash = (value: Record<string, unknown>) => JSON.stringify(
  Object.fromEntries(Object.entries(value).filter(([key]) => !autoOptimizationIgnoredFields.has(key) && key !== '__configHash')),
);

export const withHash = (value: any, hash: string) => JSON.stringify({ ...value, __configHash: hash });
