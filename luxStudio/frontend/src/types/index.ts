interface FotometriaInfo {
  id: string;
  filename: string;
  luminaire_name: string;
  manufacturer: string;
  model_family: string;
  cct: number;
  cri: number;
  optic_family: string;
  power: number;
  flux: number;
  efficiency: number;
  LORL: number;
  isym: number;
  gama?: string | null;
  difusor?: string | null;
  lente?: string | null;
  led_type?: string | null;
  fotometria?: string | null;
  mf_origen?: number;
}

// Legacy alias — kept for backward compatibility.
export type LDTInfo = FotometriaInfo;

// --- Catalog dimension types (PR2) ---

export interface DimensionItem {
  id: number;
  name: string;
}

export interface CriterionResult {
  name: string;
  value: number;
  required: number;
  passed: boolean;
  is_compliance_criterion?: boolean;
}

export interface ElementResultItem {
  index: number;
  type: 'carriageway' | 'sidewalk';
  width: number;
  lighting_class?: string | null;
  compliant: boolean;
  Lavg?: number | null;
  Uo?: number | null;
  Ul?: number | null;
  TI?: number | null;
  SR?: number | null;
  EIR?: number | null;
  Eavg?: number | null;
  Emin?: number | null;
  Eavg_ped?: number | null;
  Emin_ped?: number | null;
  pedestrian_class?: string | null;
  criteria_passed?: Record<string, boolean>;
  criteria_required?: Record<string, number>;
}

export interface CalculationResult {
  config: any;
  compliant: boolean;
  mode: string;
  luminaire: LDTInfo;
  criteria: CriterionResult[];
  elements?: ElementResultItem[];
  Lavg?: number;
  Uo?: number;
  Ul?: number;
  TI?: number;
  SR?: number;
  EIR?: number;
  Eavg?: number;
  Emin?: number;
  sidewalk_left_Eavg?: number;
  sidewalk_left_Emin?: number;
  sidewalk_left_class?: string;
  sidewalk_right_Eavg?: number;
  sidewalk_right_Emin?: number;
  sidewalk_right_class?: string;
}

export interface MeasurementGrid {
  title: string;
  unit: string;
  xs: number[];
  ys: number[];
  values: number[][];
  avg: number;
  min: number;
  max: number;
  uniformity_avg: number;
  uniformity_max: number;
}

export interface MeasurementResponse {
  config: any;
  luminaire: LDTInfo;
  primary: string;
  grids: Record<string, MeasurementGrid>;
}

export interface PcbOption {
  pcb_ref?: string | null;
  pcb_descripcion?: string | null;
  pcb_imax_led?: number | null;
  pcb_v_nominal?: number | null;
  n_pcbs?: number | null;
  n_leds_per_pcb?: number | null;
  total_n_leds?: number | null;
  led_ref?: string | null;
}

export interface FluxDetail {
  gama?: string | null;
  difusor?: string | null;
  lente?: string | null;
  led_type?: string | null;
  pcb_ref?: string | null;
  pcb_descripcion?: string | null;
  pcb_v_nominal?: number | null;
  pcb_imax_led?: number | null;
  pcb_no_led?: number | null;
  n_pcbs?: number | null;
  n_leds_per_pcb?: number | null;
  total_n_leds?: number | null;
  led_ref?: string | null;
  flux: number;
  efficiency: number;
  led_efficacy: number;
  thermal_derating: number;
  v_f: number;
  p_led: number;
  p_total: number;
  i_op_ma: number;
  user_i_op_ma?: number | null;
  user_lm_w_min?: number | null;
  lente_eficiencia?: number | null;
  difusor_eficiencia?: number | null;
  driver_eficiencia?: number | null;
  i_op_ok: boolean;
  lm_w_ok: boolean;
  available_pcbs?: PcbOption[];
}

export interface BatchCalculationItem {
  model_id: string;
  row: number;
  config?: any;
  result?: CalculationResult;
  error?: string;
}

export interface BatchCalculationResponse {
  filename: string;
  count: number;
  items: BatchCalculationItem[];
}

export interface OptimizationResponse {
  feasible: boolean;
  message: string;
  objective: string;
  fixed_parameters: string[];
  checked: number;
  config?: any;
  result?: CalculationResult;
}

export interface AdvancedOptimizationVariables {
  power: boolean;
  spacing: boolean;
  height: boolean;
  arm_length: boolean;
  tilt: boolean;
  optic_family: boolean;
}

export interface AdvancedOptimizationLimits {
  power?: number;
  spacing?: number;
  height?: number;
  arm_length?: number;
  tilt?: number;
}

export type AdvancedOptimizationObjective = 'technical_limits' | 'min_power' | 'max_spacing';

interface OptimizationChange {
  label: string;
  before: string;
  after: string;
  delta?: string;
}

export interface OptimizationLensResult {
  model_id: string;
  optic_family: string;
  feasible: boolean;
  message?: string;
  config?: any;
  result?: CalculationResult;
  changes: OptimizationChange[];
}

export type ArrangementType = 'Lineal' | 'Bilateral' | 'Bilateral Alternada' | 'Central Doble' | 'En Isleta';

export type LightingClass = 'M1' | 'M2' | 'M3' | 'M4' | 'M5' | 'M6' | 'P1' | 'P2' | 'P3' | 'P4' | 'P5' | 'P6';

export type PavementType = 'R1' | 'R2' | 'R3' | 'R4';

export type PoleSide = 'left' | 'right';

export type TramoStatus = 'pending' | 'calculation_pending' | 'compliant' | 'non_compliant' | 'dirty' | 'config_error' | 'missing_config' | 'no_pcb_capacity';

interface TramoDocumentRecord {
  id: number;
  filename: string;
  document_type: string;
  created_at: string;
}

interface TramoComplianceSummary {
  compliant?: boolean;
  Lavg?: number;
  Uo?: number;
  Ul?: number;
  TI?: number;
  SR?: number;
  EIR?: number;
  Eavg?: number;
  Emin?: number;
}

export interface TramoRecord {
  id: number;
  project_id: number;
  name: string;
  description?: string | null;
  parent_section_id?: number | null;
  base_name?: string | null;
  variant_name?: string | null;
  sort_order?: number;
  config_json?: string | null;
  result_json?: string | null;
  last_calculated_at?: string | null;
  has_pdf: boolean;
  has_excel: boolean;
  has_result?: boolean;
  document_ids: { pdf?: number; excel?: number };
  documents: TramoDocumentRecord[];
  compliance_summary?: TramoComplianceSummary | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TramoBody {
  name?: string | null;
  parent_section_id?: number | null;
  base_name?: string | null;
  variant_name?: string | null;
  description?: string | null;
  config_json?: string | null;
  result_json?: string | null;
}

// --- Road cross-section elements ---

export interface RoadElement {
  type: 'carriageway' | 'sidewalk';
  width: number;
  /** Carriageway only */
  lanes?: number | null;
  /** Carriageway only — e.g. M3, M1 */
  lighting_class?: string | null;
  /** Sidewalk only — e.g. P4 */
  pedestrian_class?: string | null;
}

export const DEFAULT_ROAD_ELEMENTS: RoadElement[] = [
  { type: 'sidewalk', width: 1.5, pedestrian_class: 'P4' },
  { type: 'carriageway', width: 7.0, lanes: 2, lighting_class: 'M3' },
  { type: 'sidewalk', width: 1.5, pedestrian_class: 'P4' },
];

// --- Power cap (4-tuple -> LED_Pot Max Ajustada) ---
// (the live per-4-tuple cap lives in the pmax_by_combo map served by /api/ldt/dimensions)
