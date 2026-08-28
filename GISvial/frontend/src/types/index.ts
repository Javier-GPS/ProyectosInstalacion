// ── GIS Types ──────────────────────────────────────────────────────────────

export interface GisUser {
  id: number;
  user_id: number;
  username: string;
  name: string;
  email: string;
  role: string;
  company_name: string;
  is_active: boolean;
  must_reset_password: boolean;
}

export interface GisProject {
  id: string;
  name: string;
  created_at: string;
  access_role?: 'admin' | 'owner' | 'editor' | 'viewer';
}

export interface GisZoneGeometry {
  bbox: [number, number, number, number] | null;
  polygon: [number, number][] | null;
  boundary: {
    type: 'Polygon' | 'MultiPolygon';
    coordinates: [number, number][][] | [number, number][][][];
  } | null;
  status: 'valid' | 'bbox_only' | 'missing' | 'ambiguous' | 'invalid';
  source_format: { bbox: string | null; polygon: string | null };
}

export interface GisZone {
  id: string;
  name: string;
  type: string;
  color: string;
  priority: number;
  center_lat: number;
  center_lon: number;
  zoom: number;
  bbox: string;
  description: string;
  corridors: any[];
  bounds_polygon: number[][] | GisZoneGeometry['boundary'];
  geometry: GisZoneGeometry;
  osm_relation: number | null;
  est: Record<string, number>;
  source: string;
  project_id: string;
  created_at: string | null;
  spacing: number;
}

export interface GisZoneConfig {
  zone_id: string;
  spacing: number;
  watt_hps: number;
  watt_led: number;
  efficacy: number;
  hours_night: number;
  updated_at: string;
}

export interface GisOsmWay {
  way_id: number;
  geometry: [number, number][];
  road_type: string;
  name: string;
  length_m: number;
  luxParams?: GisLuxParams;
}

export interface GisLuxParams {
  spacing: number;
  lighting_class: string;
  height: number;
  arm_len: number;
  tilt: number;
  distribution: string;
  watt_hps: number;
  watt_led: number;
  efficacy: number;
}

export interface GisOsmData {
  zone_id: string;
  km_by_type: Record<string, number>;
  ways: GisOsmWay[];
  source: string;
  loaded_at: string;
}

export type GisLightingClass =
  | 'M1' | 'M2' | 'M3' | 'M4' | 'M5' | 'M6'
  | 'C0' | 'C1' | 'C2' | 'C3' | 'C4' | 'C5'
  | 'P1' | 'P2' | 'P3' | 'P4' | 'P5' | 'P6' | 'P7';

export type GisDistribution =
  | 'unilateral_r' | 'unilateral_l' | 'bilateral_pareado'
  | 'bilateral_tresbolillo' | 'centrada_mediana' | 'mediana_compartida';

export interface GisPlanningLuxParams {
  poleH?: number | null;
  armLen?: number | null;
  setback?: number | null;
  tilt?: number | null;
  sidewalkL?: number | null;
  sidewalkR?: number | null;
  medianW?: number | null;
  maintFactor?: number | null;
  brand?: string | null;
  range?: string | null;
  diffuser?: string | null;
  optic?: string | null;
  ledType?: string | null;
  power?: number | null;
  colorTemp?: number | null;
  cri?: number | null;
}

export interface GisPlanningPatch {
  lighting_class?: GisLightingClass | null;
  spacing?: number | null;
  distribution?: GisDistribution | null;
  luxParams?: GisPlanningLuxParams | null;
}

export interface GisPlanningPayload {
  group_defaults: Record<string, GisPlanningPatch>;
  target_overrides: Record<string, GisPlanningPatch>;
}

export interface GisPlanningInventoryGroup {
  group_ref: string;
  road_type: string | null;
  road_role?: string;
  street_count: number;
  target_count: number;
  length_m: number;
  invalid_length_count: number;
}

export interface GisPlanningInventoryTarget {
  target_ref: string;
  group_ref: string;
  source_index: number;
  name: string | null;
  highway?: string | null;
  osmName?: string | null;
  ref?: string | null;
  osmRef?: string | null;
  noname?: string | null;
  officialName?: string | null;
  altName?: string | null;
  locName?: string | null;
  nameState?: 'named' | 'ref_only' | 'explicit_noname' | 'variant_only' | 'unnamed' | 'legacy' | string;
  roadRole?: 'main' | 'auxiliary' | 'link' | 'other' | 'unknown' | string;
  osmWayId?: number | null;
  displayLabel?: string | null;
  lit?: string | null;
  length_m: number | null;
  geometry: [number, number][] | null;
  diagnostics: string[];
  estWidth?: number | null;
  widthSrc?: string | null;
  lanes?: number | null;
  sidewalk?: string | null;
  sidewalkWidthLeft?: number | null;
  sidewalkWidthRight?: number | null;
  median?: boolean | null;
  medianWidth?: number | null;
  dual?: boolean | null;
}

export interface GisMergedStreet {
  street: string;
  road_type: string;
  geometry: {
    type: 'MultiLineString';
    coordinates: [number, number][][];
  };
  target_count: number;
  total_length_m: number;
  target_refs: string[];
}

export interface GisPlanningInventory {
  schema_version: 1;
  adapter_version: number;
  zone_id: string;
  base_inventory_hash: string;
  counts: {
    segment_count: number;
    named_street_count: number;
    distinct_name_count?: number;
    named_way_count?: number;
    unnamed_segment_count: number;
    without_osm_name_count?: number;
    explicit_noname_count?: number;
    ref_only_count?: number;
    variant_only_count?: number;
    legacy_name_count?: number;
    geometry_available: number;
    geometry_unavailable: number;
    invalid_length_count: number;
  };
  name_state_counts?: Record<string, number>;
  road_role_counts?: Record<string, number>;
  source_needs_refresh?: boolean;
  groups: GisPlanningInventoryGroup[];
  targets: GisPlanningInventoryTarget[];
  streets?: GisMergedStreet[];  // merged street geometries for efficient rendering
}

export interface GisPlanningDraft {
  zone_id: string;
  revision: number;
  schema_version: 1;
  base_inventory_hash: string;
  payload: GisPlanningPayload;
  updated_at: string | null;
  updated_by: number | null;
}

export interface GisRoadScopeAnchor {
  target_ref: string;
  segment_index: number;
  segment_t: number;
}

export interface GisRoadScopeMember {
  target_ref: string;
  segment_index: number;
  from_t: number;
  to_t: number;
  geometry: [number, number][];
  length_m: number;
}

export interface GisRoadWorkScope {
  zone_id: string;
  revision: number;
  schema_version: 1;
  base_inventory_hash: string;
  current: boolean;
  boundary: { type: 'Polygon'; coordinates: [number, number][][] };
  allowed_group_refs: string[];
  a: GisRoadScopeAnchor;
  b: GisRoadScopeAnchor;
  path: [number, number][];
  length_m: number;
  members: GisRoadScopeMember[];
  topology_basis: 'exact-coordinate';
  topology_limitations: string[];
  updated_at: string | null;
  updated_by: number | null;
}

export interface Etagged<T> {
  data: T;
  etag: string;
}

export interface GisLuxJobItem {
  id: string;
  target_ref: string;
  state: string;
  calculation_status: string;
  materialization_status: string;
  error_code: string | null;
  error_message: string | null;
  result_hash: string | null;
}

export interface GisLuxJob {
  id: string;
  project_id: number;
  zone_id: string;
  intent_id: string;
  state: string;
  state_version: number;
  total: number;
  succeeded: number;
  failed: number;
  blocked: number;
  unknown: number;
  materialize_valid: boolean;
  partial_policy: string;
  mode: 'calculate' | 'optimize';
  created_at: string;
  updated_at: string;
  items: GisLuxJobItem[];
}

export interface GisLuminaire {
  id: number;
  project_id: string;
  zone_id: string;
  road_type: string;
  lighting_class: string;
  street_name: string;
  lat: number;
  lon: number;
  watts: number;
  spacing: number;
  placed_at: string;
  tilt: number | null;
  height_m: number | null;
  arm_len: number | null;
  distribution: string | null;
}

export interface GisInventoryLuminaire {
  id: number;
  zone_id: string;
  point_id: string;
  lat: number;
  lon: number;
  power_w: number;
  height_m: number;
  brand: string;
  model: string;
  lamp_type: string;
  support_type: string;
  circuit_id: string;
  line_id: string;
  extra: any;
  way_key: string;
  road_type: string;
  imported_at: string;
}

export interface GisPhotometricResult {
  id: number;
  zone_id: string;
  segment_name: string;
  match_key: string;
  road_width: number;
  spacing: number;
  lighting_class: string;
  power_w: number;
  lm_em: number;
  uo: number;
  ui: number;
  ti: number;
  sr: number;
  model: string;
  lente: string;
  tilt: number;
  phi_lm: number;
  cumple: string;
  notes: string;
  imported_at: string | null;
}

export interface GisZoneTrees {
  zone_id: string;
  trees: any[];
  loaded_at: string;
}

export interface GisPlantillaRow {
  wayKey: string;
  streetName: string;
  roadType: string;
  lightingClass: string;
  roadWidth: number;
  spacing: number;
  height: number;
  armLen: number;
  tilt: number;
  distribution: string;
  power: number;
  lm: number;
  model: string;
  lente: string;
}

export interface LoginResponse {
  token: string;
  access_token: string;
  token_type: string;
  user: GisUser;
}
