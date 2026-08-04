import { apiClient } from "./client";

export type GeometryLOD = "G0" | "G1" | "G2" | "G3" | "G4";
export type BaseInterfaceType = "plate" | "embedded";
export type SectionLawType = "constant" | "linear" | "stepped" | "table" | "imported";

export interface GeometryModel {
  id: string;
  project_revision_id: string;
  schema_version: string;
  lod: GeometryLOD;
  quality_state: string;
  coordinate_convention: string;
  canonical_units: string;
  source: string;
  geometry_hash: string | null;
  engine_version: string | null;
  notes: string | null;
}

export interface GeometryModelCreateInput {
  project_revision_id: string;
  lod?: GeometryLOD;
  coordinate_convention?: string;
  source?: string;
  notes?: string;
}

export interface SectionLawInput {
  law_type: SectionLawType;
  interpolation?: string;
  continuity?: string;
  parameter_json: Record<string, unknown>;
  domain?: string;
}

export interface MastSegmentInput {
  segment_order: number;
  piece_id: string;
  z_start_m: number;
  z_end_m: number;
  physical_length_m: number;
  section_law: SectionLawInput;
}

export interface MastCreateInput {
  nominal_height_m: number;
  base_type: BaseInterfaceType;
  segments: MastSegmentInput[];
}

export interface Mast {
  id: string;
  geometry_model_id: string;
  nominal_height_m: number;
  base_type: BaseInterfaceType;
  total_height_m: number | null;
  total_mass_kg: number | null;
  is_segmented: boolean;
  segments: Array<Record<string, unknown>>;
}

export interface ValidationSummary {
  geometry_model_id: string;
  quality_state: string;
  total_checks: number;
  errors: number;
  warnings: number;
  blocked: number;
  passed: number;
  validations: Array<Record<string, unknown>>;
}

export async function createGeometryModel(input: GeometryModelCreateInput): Promise<GeometryModel> {
  const { data } = await apiClient.post<GeometryModel>("/geometry-models", input);
  return data;
}

export async function getGeometryModel(modelId: string): Promise<GeometryModel> {
  const { data } = await apiClient.get<GeometryModel>(`/geometry-models/${modelId}`);
  return data;
}

export async function addMast(modelId: string, input: MastCreateInput): Promise<Mast> {
  const { data } = await apiClient.post<Mast>(`/geometry-models/${modelId}/masts`, input);
  return data;
}

export async function listMasts(modelId: string): Promise<Mast[]> {
  const { data } = await apiClient.get<Mast[]>(`/geometry-models/${modelId}/masts`);
  return data;
}

export async function validateGeometry(modelId: string): Promise<ValidationSummary> {
  const { data } = await apiClient.post<ValidationSummary>(`/geometry-models/${modelId}/validate`);
  return data;
}
