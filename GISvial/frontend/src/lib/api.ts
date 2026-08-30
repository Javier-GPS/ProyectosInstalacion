/** API helpers for GIS backend requests with AbortSignal support. */
import { errorMessage, requestJson, requestJsonWithSignal } from './http';
import type { Etagged, GisLuxJob, GisPlanningDraft, GisPlanningInventory, GisPlanningPayload, GisRoadScopeAnchor, GisRoadWorkScope, GisProject, GisZoneSelection, GisZoneSummary } from '../types';

let _authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> = fetch;

export const setAuthFetch = (fn: typeof _authFetch) => { _authFetch = fn; };

const api = <T>(url: string, init?: RequestInit, fallback = 'Request failed', signal?: AbortSignal): Promise<T> => {
  const fetcher = _authFetch || fetch;
  if (signal) return requestJsonWithSignal<T>(fetcher, url, init, fallback, signal);
  return requestJson<T>(fetcher, url, init, fallback);
};

const apiBlob = (url: string, init?: RequestInit, fallback = 'Download failed', signal?: AbortSignal): Promise<Blob> => {
  const fetcher = _authFetch || fetch;
  return fetcher(url, { ...init, signal }).then(async r => {
    if (!r.ok) throw new Error(fallback);
    return r.blob();
  });
};

// ── Projects ──────────────────────────────────────────────────────────────
export const getProjects = (signal?: AbortSignal) => api<GisProject[]>('/api/projects', undefined, undefined, signal);
export const createProject = (body: Record<string, unknown>, signal?: AbortSignal) => api<GisProject>('/api/projects', { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }, undefined, signal);
export const updateProject = (id: string, body: Record<string, unknown>, signal?: AbortSignal) => api<GisProject>(`/api/projects/${id}`, { method: 'PUT', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }, undefined, signal);
export const deleteProject = (id: string, signal?: AbortSignal) => api<void>(`/api/projects/${id}`, { method: 'DELETE' }, undefined, signal);

// ── Zones ─────────────────────────────────────────────────────────────────
export const getZones = (projectId?: string, signal?: AbortSignal) => api<any[]>(`/api/zones${projectId ? `?project_id=${projectId}` : ''}`, undefined, undefined, signal);
export const getProjectZonesSummary = (projectId: string, signal?: AbortSignal) => api<GisZoneSummary[]>(`/api/projects/${projectId}/zones-summary`, undefined, undefined, signal);
export const createZone = (data: any, signal?: AbortSignal) => api<any>('/api/zones', { method: 'POST', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }, undefined, signal);
export const updateZone = (id: string, data: any, signal?: AbortSignal) => api<any>(`/api/zones/${id}`, { method: 'PUT', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }, undefined, signal);
export const deleteZone = (id: string, signal?: AbortSignal) => api<void>(`/api/zones/${id}`, { method: 'DELETE' }, undefined, signal);
export const getZoneConfig = (id: string, signal?: AbortSignal) => api<any>(`/api/zones/${id}/config`, undefined, undefined, signal);
export const saveZoneConfig = (id: string, data: any, signal?: AbortSignal) => api<any>(`/api/zones/${id}/config`, { method: 'PUT', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }, undefined, signal);

// ── OSM ───────────────────────────────────────────────────────────────────
export const getZoneOsm = (id: string, signal?: AbortSignal) => api<any>(`/api/zones/${id}/osm`, undefined, undefined, signal);
export const saveZoneOsm = (id: string, data: any, signal?: AbortSignal) => api<any>(`/api/zones/${id}/osm`, { method: 'PUT', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } }, undefined, signal);
export const getZoneTrees = (id: string, signal?: AbortSignal) => api<any>(`/api/zones/${id}/trees`, undefined, undefined, signal);
export const saveZoneTrees = (id: string, trees: any[], signal?: AbortSignal) => api<any>(`/api/zones/${id}/trees`, { method: 'PUT', body: JSON.stringify(trees), headers: { 'Content-Type': 'application/json' } }, undefined, signal);

export class ApiStatusError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const etagged = async <T>(url: string, init?: RequestInit, signal?: AbortSignal): Promise<Etagged<T>> => {
  const response = await _authFetch(url, { ...init, signal });
  if (response.status === 204) return { data: null as T, etag: response.headers.get('ETag') || '' };
  if (response.status === 304) return { data: null as T, etag: response.headers.get('ETag') || '' };
  const text = await response.text();
  let body: unknown = null;
  if (text.trim()) {
    try { body = JSON.parse(text); } catch { body = text; }
  }
  if (!response.ok) throw new ApiStatusError(response.status, errorMessage(body, 'Planning request failed'));
  return { data: body as T, etag: response.headers.get('ETag') || '' };
};

export const getPlanningInventory = (
  zoneId: string,
  ifNoneMatch?: string,
  refresh?: boolean,
  signal?: AbortSignal,
): Promise<Etagged<GisPlanningInventory | null>> => {
  const headers: Record<string, string> = {};
  if (ifNoneMatch) headers['If-None-Match'] = ifNoneMatch;
  const params = refresh ? '?refresh=true' : '';
  const url = `/api/zones/${zoneId}/planning-inventory${params}`;
  return etagged<GisPlanningInventory | null>(url, { headers }, signal).then(result =>
    result.data === null && ifNoneMatch
      ? etagged<GisPlanningInventory | null>(url, undefined, signal)
      : result,
  );
};

export const loadPlanningOsm = (zoneId: string, signal?: AbortSignal, force = false) =>
  etagged<GisPlanningInventory>(`/api/zones/${zoneId}/osm/load${force ? '?force=true' : ''}`, { method: 'POST' }, signal).then(result => result.data);

export const getBuildingWidths = (zoneId: string, signal?: AbortSignal) =>
  api<{ zone_id: string; status: string; buildings: any[] | null; enriched_ways: any[] | null; computed_at: string | null }>(
    `/api/zones/${zoneId}/building-widths`, undefined, undefined, signal,
  );

export const getEditorFeatures = (zoneId: string, bbox: string, signal?: AbortSignal) =>
  api<{ features: { kind: string; ring: [number, number][]; height?: number | null }[]; error?: string }>(
    `/api/zones/${zoneId}/editor-features?bbox=${encodeURIComponent(bbox)}`, undefined, undefined, signal,
  );

export const getPlanningDraft = (zoneId: string, signal?: AbortSignal) =>
  etagged<GisPlanningDraft | null>(`/api/zones/${zoneId}/planning-draft`, undefined, signal);

export const putPlanningDraft = (
  zoneId: string,
  mode: 'update' | 'recreate',
  baseInventoryHash: string,
  payload: GisPlanningPayload,
  precondition: { ifMatch?: string; ifNoneMatch?: '*' },
  signal?: AbortSignal,
) => etagged<GisPlanningDraft>(`/api/zones/${zoneId}/planning-draft`, {
  method: 'PUT',
  headers: {
    'Content-Type': 'application/json',
    ...(precondition.ifMatch ? { 'If-Match': precondition.ifMatch } : {}),
    ...(precondition.ifNoneMatch ? { 'If-None-Match': precondition.ifNoneMatch } : {}),
  },
  body: JSON.stringify({
    mode,
    confirm: mode === 'recreate',
    schema_version: 1,
    base_inventory_hash: baseInventoryHash,
    payload,
  }),
}, signal);

export const getRoadScope = (zoneId: string, signal?: AbortSignal) =>
  etagged<GisRoadWorkScope | null>(`/api/zones/${zoneId}/road-scope`, undefined, signal);

export const getZoneSelection = (zoneId: string, signal?: AbortSignal) =>
  etagged<GisZoneSelection | null>(`/api/zones/${zoneId}/selection`, undefined, signal);

export const putZoneSelection = (
  zoneId: string,
  baseInventoryHash: string,
  selectedTargetRefs: string[],
  signal?: AbortSignal,
) => etagged<GisZoneSelection>(`/api/zones/${zoneId}/selection`, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ schema_version: 1, base_inventory_hash: baseInventoryHash, selected_target_refs: selectedTargetRefs }),
}, signal);

export const putRoadScope = (
  zoneId: string,
  baseInventoryHash: string,
  boundary: { type: 'Polygon'; coordinates: [number, number][][] },
  allowedGroupRefs: string[],
  a: GisRoadScopeAnchor,
  b: GisRoadScopeAnchor,
  precondition: { ifMatch?: string; ifNoneMatch?: '*' },
  signal?: AbortSignal,
) => etagged<GisRoadWorkScope>(`/api/zones/${zoneId}/road-scope`, {
  method: 'PUT',
  headers: {
    'Content-Type': 'application/json',
    ...(precondition.ifMatch ? { 'If-Match': precondition.ifMatch } : {}),
    ...(precondition.ifNoneMatch ? { 'If-None-Match': precondition.ifNoneMatch } : {}),
  },
  body: JSON.stringify({ schema_version: 1, base_inventory_hash: baseInventoryHash, boundary, allowed_group_refs: allowedGroupRefs, a, b }),
}, signal);

export const deleteRoadScope = (zoneId: string, etag: string, signal?: AbortSignal) =>
  etagged<null>(`/api/zones/${zoneId}/road-scope`, { method: 'DELETE', headers: { 'If-Match': etag } }, signal);

export const routePreview = (
  zoneId: string,
  baseInventoryHash: string,
  a: GisRoadScopeAnchor,
  b: GisRoadScopeAnchor,
  allowedGroupRefs?: string[],
  signal?: AbortSignal,
) => api<{ path: [number, number][]; length_m: number; members: any[] }>(`/api/zones/${zoneId}/route-preview`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    base_inventory_hash: baseInventoryHash,
    a, b,
    ...(allowedGroupRefs ? { allowed_group_refs: allowedGroupRefs } : {}),
  }),
}, undefined, signal);

// ── Nominatim ─────────────────────────────────────────────────────────────
export const nominatimSearch = (q: string, featuretype?: string, signal?: AbortSignal) => api<any[]>(`/api/nominatim/search?q=${encodeURIComponent(q)}${featuretype ? `&featuretype=${featuretype}` : ''}`, undefined, undefined, signal);
export const nominatimReverse = (lat: number, lon: number, signal?: AbortSignal) => api<any>(`/api/nominatim/reverse?lat=${lat}&lon=${lon}`, undefined, undefined, signal);

// ── Luminaires ────────────────────────────────────────────────────────────
export const getLuminaires = (zoneId?: string, signal?: AbortSignal) => api<any[]>(`/api/luminaires${zoneId ? `?zone_id=${zoneId}` : ''}`, undefined, undefined, signal);
export const bulkSaveLuminaires = (luminaires: any[], signal?: AbortSignal) => api<any>('/api/luminaires/bulk', { method: 'POST', body: JSON.stringify(luminaires), headers: { 'Content-Type': 'application/json' } }, undefined, signal);
export const deleteLuminaire = (zoneId: string, lumId: number, signal?: AbortSignal) => api<void>(`/api/luminaires/${zoneId}/${lumId}`, { method: 'DELETE' }, undefined, signal);
export const getInventory = (zoneId: string, signal?: AbortSignal) => api<any[]>(`/api/zones/${zoneId}/inventory`, undefined, undefined, signal);

// ── Photometric ───────────────────────────────────────────────────────────
export const getPhotometric = (zoneId: string, signal?: AbortSignal) => api<any[]>(`/api/zones/${zoneId}/photometric`, undefined, undefined, signal);

// ── Durable Lux jobs ───────────────────────────────────────────────────────
export const createLuxJob = (
  projectId: string,
  zoneId: string,
  targetRefs: string[],
  baseInventoryHash: string,
  intentId: string,
  mode: 'calculate' | 'optimize' = 'optimize',
  signal?: AbortSignal,
) => api<GisLuxJob>(`/api/projects/${projectId}/lux/jobs`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Idempotency-Key': intentId },
  body: JSON.stringify({
    zone_id: zoneId,
    target_refs: targetRefs,
    base_inventory_hash: baseInventoryHash,
    materialize_valid: true,
    mode,
  }),
}, 'No se pudo iniciar el cálculo Lux', signal);

export const getLuxJob = async (
  projectId: string,
  jobId: string,
  etag?: string,
  signal?: AbortSignal,
): Promise<Etagged<GisLuxJob | null>> => {
  const headers: Record<string, string> = {};
  if (etag) headers['If-None-Match'] = etag;
  const response = await _authFetch(`/api/projects/${projectId}/lux/jobs/${jobId}`, { headers, signal });
  if (response.status === 304) return { data: null, etag: response.headers.get('ETag') || etag || '' };
  const text = await response.text();
  let body: unknown = null;
  if (text.trim()) {
    try { body = JSON.parse(text); } catch { body = text; }
  }
  if (!response.ok) throw new ApiStatusError(response.status, errorMessage(body, 'No se pudo consultar el cálculo Lux'));
  return { data: body as GisLuxJob, etag: response.headers.get('ETag') || '' };
};

export const cancelLuxJob = (projectId: string, jobId: string, signal?: AbortSignal) =>
  api<GisLuxJob>(`/api/projects/${projectId}/lux/jobs/${jobId}/cancel`, { method: 'POST' }, 'No se pudo cancelar el cálculo', signal);

// ── Exports ───────────────────────────────────────────────────────────────
export const exportDxf = (zoneId: string, signal?: AbortSignal) => apiBlob(`/api/export/dxf?zone_id=${zoneId}`, undefined, undefined, signal);
export const exportDxfObjects = (zoneId: string, roads: unknown[], objects: unknown[], signal?: AbortSignal) =>
  apiBlob('/api/export/dxf', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ zone_id: zoneId, roads, objects }) }, undefined, signal);
export const exportPlantilla = (zoneId: string, rows: any[], signal?: AbortSignal) => api<any>('/api/export/plantilla_luminotecnica', { method: 'POST', body: JSON.stringify({ zone_id: zoneId, rows }), headers: { 'Content-Type': 'application/json' } }, undefined, signal);

// ── Import ────────────────────────────────────────────────────────────────
export const importPhotometric = (zoneId: string, file: Blob, signal?: AbortSignal) => {
  const form = new FormData();
  form.append('file', file, 'results.xlsx');
  return api<any>(`/api/import/photometric?zone_id=${zoneId}`, { method: 'POST', body: form }, undefined, signal);
};

export const parseInventoryExcel = (file: Blob, signal?: AbortSignal) => {
  const form = new FormData();
  form.append('file', file, 'inventory.xlsx');
  return api<any>('/api/parse/inventory_excel', { method: 'POST', body: form }, undefined, signal);
};

export const importInventory = (zoneId: string, rows: any[], signal?: AbortSignal) => api<any>('/api/import/inventory', { method: 'POST', body: JSON.stringify({ zone_id: zoneId, rows }), headers: { 'Content-Type': 'application/json' } }, undefined, signal);

// ── Auth ──────────────────────────────────────────────────────────────────
export const getMe = (signal?: AbortSignal) => api<any>('/api/auth/me', undefined, undefined, signal);
