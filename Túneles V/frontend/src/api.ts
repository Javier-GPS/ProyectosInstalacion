import type { ProjectPayload, ProjectRecord, TunnelConfig } from './types';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const details = Array.isArray(data.errors) ? data.errors.map(String).join(' ') : '';
    throw new Error(data.error || details || `Error ${response.status}`);
  }
  return data as T;
}

export const listProjects = () => request<ProjectRecord[]>('/api/tunnel/projects');

export const getProject = (id: number) => request<ProjectRecord>(`/api/tunnel/projects/${id}`);

export const createProject = (payload: ProjectPayload) => request<ProjectRecord>('/api/tunnel/projects', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
});

export const updateProject = (id: number, payload: ProjectPayload) => request<ProjectRecord>(`/api/tunnel/projects/${id}`, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
});

export const deleteProject = (id: number) => request<{ success: boolean }>(`/api/tunnel/projects/${id}`, { method: 'DELETE' });

export const validateTunnel = (config: TunnelConfig) => request<{ valid: boolean; errors: string[]; warnings: string[] }>('/api/tunnel/validate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(config),
});

function configuredValue(explicit: unknown, alias: unknown): unknown {
  return explicit !== undefined && explicit !== null && explicit !== '' ? explicit : alias;
}

function enginePayload(config: TunnelConfig): TunnelConfig {
  return {
    ...config,
    // The modern UI keeps these short names, while the tunnel engine uses
    // the explicit names from the functional model.
    stopping_distance_override_m: configuredValue(config.stopping_distance_override_m, config.dp_override),
    stopping_distance_b_override_m: configuredValue(config.stopping_distance_b_override_m, config.dp_b_override),
  };
}

export const calculateTunnel = (config: TunnelConfig) => request<Record<string, unknown>>('/api/tunnel/calculate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(enginePayload(config)),
});

export const calculateLuminaires = (config: TunnelConfig) => request<Record<string, unknown>>('/api/tunnel/luminaires', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ ...enginePayload(config), luminaire: config.lum_config || {} }),
});

export const calculateControl = (config: TunnelConfig) => request<Record<string, unknown>>('/api/tunnel/control', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ ...enginePayload(config), luminaire: config.lum_config || {}, recalculate: false }),
});
