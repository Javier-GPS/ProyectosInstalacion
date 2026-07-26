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
  bounds_polygon: number[][];
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
