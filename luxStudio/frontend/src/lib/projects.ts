import type { AuthFetch } from '../auth/AuthContext';
import { requestJson } from './http';

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
  config_json?: string | null;
  result_json?: string | null;
  owner_user_id?: number | null;
  owner_name?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_opened_at?: string | null;
  t_amb_c?: number | null;
  margen_lavg?: number | null;
  i_op_ma?: number | null;
  lm_w_min?: number | null;
}

export interface ProjectBody {
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
  config_json?: string | null;
  result_json?: string | null;
  t_amb_c?: number | null;
  margen_lavg?: number | null;
  i_op_ma?: number | null;
  lm_w_min?: number | null;
}

export const listProjects = async (authFetch: AuthFetch): Promise<ProjectRecord[]> => {
  return requestJson(authFetch, '/api/projects', undefined, 'No se pudo cargar la lista de proyectos');
};

export const getProject = async (authFetch: AuthFetch, id: number): Promise<ProjectRecord> => {
  return requestJson(authFetch, `/api/projects/${id}`, undefined, 'No se pudo cargar el proyecto');
};

export const createProject = async (authFetch: AuthFetch, body: ProjectBody): Promise<ProjectRecord> => {
  return requestJson(authFetch, '/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, 'No se pudo crear el proyecto');
};

export const updateProject = async (
  authFetch: AuthFetch,
  id: number,
  body: ProjectBody,
): Promise<ProjectRecord> => {
  return requestJson(authFetch, `/api/projects/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, 'No se pudo actualizar el proyecto');
};

export const deleteProject = async (authFetch: AuthFetch, id: number): Promise<void> => {
  await requestJson(authFetch, `/api/projects/${id}`, { method: 'DELETE' }, 'No se pudo eliminar el proyecto');
};
