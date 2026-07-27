/** Wizard steps replacing the old appMode planning/detail. */
export type WizardStep = 'proyecto' | 'zona' | 'vias' | 'luminarias' | 'informe';

/** Granular loading status per entity. */
export type StatusGranular = 'idle' | 'loading' | 'loaded' | 'error';

/** Selection mode within the luminarias step. */
export type DetailSelectionMode = 'none' | 'click' | 'marquee' | 'lasso' | 'criteria';

export interface RoadSelectionHit {
  segment_index: number;
  segment_t: number;
  measure: number;
  coordinate: [number, number];
}

export interface RoadSelectionAnchor extends RoadSelectionHit {
  target_ref: string;
}

export interface WalkingAnchor {
  target_ref: string;
  segment_index: number;
  segment_t: number;
  coordinate: [number, number];
}

export interface RoadSelectionDraft {
  zone_id: string;
  inventory_hash: string;
  boundary_signature: string;
  status: 'draw_area' | 'pick_a' | 'pick_b' | 'ready' | 'saving' | 'complete' | 'stale' | 'invalid';
  area_points: [number, number][];
  boundary?: { type: 'Polygon'; coordinates: [number, number][][] };
  allowed_group_refs?: string[];
  a?: RoadSelectionAnchor;
  b?: RoadSelectionAnchor;
  path?: [number, number][];
  length_m?: number;
  member_count?: number;
  etag?: string;
  error?: string;
}

/** Road type configuration (moved from useGisStore). */
export interface RoadTypeCfg {
  labelKey: string;
  color: string;
  width: number;
}

export const ROAD_CFG: Record<string, RoadTypeCfg> = {
  motorway:     { labelKey: 'road.motorway',     color: '#d73027', width: 10 },
  trunk:        { labelKey: 'road.trunk',        color: '#f46d43', width: 9 },
  primary:      { labelKey: 'road.primary',      color: '#4caf82', width: 7 },
  secondary:    { labelKey: 'road.secondary',    color: '#e67e22', width: 6 },
  tertiary:     { labelKey: 'road.tertiary',     color: '#3498db', width: 5 },
  residential:  { labelKey: 'road.residential', color: '#9b59b6', width: 4 },
  unclassified: { labelKey: 'road.unclassified',color: '#e74c3c', width: 3 },
  service:      { labelKey: 'road.service',      color: '#8c8c8c', width: 3 },
  living_street:{ labelKey: 'road.livingStreet', color: '#2a9d8f', width: 3 },
  pedestrian:   { labelKey: 'road.pedestrian',   color: '#6a4c93', width: 2 },
  tunnel:       { labelKey: 'road.tunnel',       color: '#495057', width: 7 },
};
