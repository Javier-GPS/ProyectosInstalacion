export type TunnelConfig = Record<string, unknown>;

export interface ProjectRecord {
  id: number;
  project_name: string;
  client?: string | null;
  location?: string | null;
  designer?: string | null;
  study_date?: string | null;
  reference?: string | null;
  calculation_type?: string | null;
  standard?: string | null;
  notes?: string | null;
  status?: string | null;
  config_json?: TunnelConfig | null;
  result_json?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_opened_at?: string | null;
}

export interface ProjectPayload {
  project_name: string;
  client?: string;
  location?: string;
  designer?: string;
  study_date?: string;
  reference?: string;
  calculation_type?: string;
  standard?: string;
  notes?: string;
  status?: string;
  config_json?: TunnelConfig;
  result_json?: Record<string, unknown> | null;
}
