/** API helpers for GIS backend requests. */
import { requestJson } from './http';

let _authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> = fetch;

export const setAuthFetch = (fn: typeof _authFetch) => { _authFetch = fn; };

const api = <T>(url: string, init?: RequestInit, fallback = 'Request failed'): Promise<T> => {
  const fetcher = _authFetch || fetch;
  return requestJson<T>(fetcher, url, init, fallback);
};

const apiBlob = (url: string, init?: RequestInit, fallback = 'Download failed'): Promise<Blob> => {
  const fetcher = _authFetch || fetch;
  return fetcher(url, init).then(async r => {
    if (!r.ok) throw new Error(fallback);
    return r.blob();
  });
};

// ── Projects ──────────────────────────────────────────────────────────────
export const getProjects = () => api<any[]>('/api/projects');
export const createProject = (name: string) => api<any>('/api/projects', { method: 'POST', body: JSON.stringify({ name }), headers: { 'Content-Type': 'application/json' } });
export const deleteProject = (id: string) => api<void>(`/api/projects/${id}`, { method: 'DELETE' });

// ── Zones ─────────────────────────────────────────────────────────────────
export const getZones = (projectId?: string) => api<any[]>(`/api/zones${projectId ? `?project_id=${projectId}` : ''}`);
export const createZone = (data: any) => api<any>('/api/zones', { method: 'POST', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } });
export const updateZone = (id: string, data: any) => api<any>(`/api/zones/${id}`, { method: 'PUT', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } });
export const deleteZone = (id: string) => api<void>(`/api/zones/${id}`, { method: 'DELETE' });
export const getZoneConfig = (id: string) => api<any>(`/api/zones/${id}/config`);
export const saveZoneConfig = (id: string, data: any) => api<any>(`/api/zones/${id}/config`, { method: 'PUT', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } });

// ── OSM ───────────────────────────────────────────────────────────────────
export const getZoneOsm = (id: string) => api<any>(`/api/zones/${id}/osm`);
export const saveZoneOsm = (id: string, data: any) => api<any>(`/api/zones/${id}/osm`, { method: 'PUT', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } });
export const getZoneTrees = (id: string) => api<any>(`/api/zones/${id}/trees`);
export const saveZoneTrees = (id: string, trees: any[]) => api<any>(`/api/zones/${id}/trees`, { method: 'PUT', body: JSON.stringify(trees), headers: { 'Content-Type': 'application/json' } });

// ── Nominatim ─────────────────────────────────────────────────────────────
export const nominatimSearch = (q: string, featuretype?: string) => api<any[]>(`/api/nominatim/search?q=${encodeURIComponent(q)}${featuretype ? `&featuretype=${featuretype}` : ''}`);
export const nominatimReverse = (lat: number, lon: number) => api<any>(`/api/nominatim/reverse?lat=${lat}&lon=${lon}`);

// ── Luminaires ────────────────────────────────────────────────────────────
export const getLuminaires = (zoneId?: string) => api<any[]>(`/api/luminaires${zoneId ? `?zone_id=${zoneId}` : ''}`);
export const bulkSaveLuminaires = (luminaires: any[]) => api<any>('/api/luminaires/bulk', { method: 'POST', body: JSON.stringify(luminaires), headers: { 'Content-Type': 'application/json' } });
export const deleteLuminaire = (zoneId: string, lumId: number) => api<void>(`/api/luminaires/${zoneId}/${lumId}`, { method: 'DELETE' });
export const getInventory = (zoneId: string) => api<any[]>(`/api/zones/${zoneId}/inventory`);

// ── Photometric ───────────────────────────────────────────────────────────
export const getPhotometric = (zoneId: string) => api<any[]>(`/api/zones/${zoneId}/photometric`);

// ── Exports ───────────────────────────────────────────────────────────────
export const exportDxf = (zoneId: string) => apiBlob(`/api/export/dxf?zone_id=${zoneId}`);
export const exportPlantilla = (zoneId: string, rows: any[]) => api<any>('/api/export/plantilla_luminotecnica', { method: 'POST', body: JSON.stringify({ zone_id: zoneId, rows }), headers: { 'Content-Type': 'application/json' } });

// ── Import ────────────────────────────────────────────────────────────────
export const importPhotometric = (zoneId: string, file: Blob) => {
  const form = new FormData();
  form.append('file', file, 'results.xlsx');
  return api<any>(`/api/import/photometric?zone_id=${zoneId}`, { method: 'POST', body: form });
};

export const parseInventoryExcel = (file: Blob) => {
  const form = new FormData();
  form.append('file', file, 'inventory.xlsx');
  return api<any>('/api/parse/inventory_excel', { method: 'POST', body: form });
};

export const importInventory = (zoneId: string, rows: any[]) => api<any>('/api/import/inventory', { method: 'POST', body: JSON.stringify({ zone_id: zoneId, rows }), headers: { 'Content-Type': 'application/json' } });

// ── Auth ──────────────────────────────────────────────────────────────────
export const getMe = () => api<any>('/api/auth/me');
