import type { AuthFetch } from '../auth/AuthContext';
import type { TramoBody, TramoRecord } from '../types';
import { requestBlob, requestJson } from './http';



export const getTramo = async (
  authFetch: AuthFetch,
  projectId: number,
  tramoId: number,
): Promise<TramoRecord> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos/${tramoId}`, undefined, 'No se pudo cargar el tramo');
};

export const createTramo = async (
  authFetch: AuthFetch,
  projectId: number,
  body: TramoBody,
): Promise<TramoRecord> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, 'No se pudo crear el tramo');
};

export const updateTramo = async (
  authFetch: AuthFetch,
  projectId: number,
  tramoId: number,
  body: TramoBody,
): Promise<TramoRecord> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos/${tramoId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, 'No se pudo actualizar el tramo');
};

export const deleteTramo = async (
  authFetch: AuthFetch,
  projectId: number,
  tramoId: number,
): Promise<void> => {
  await requestJson(authFetch, `/api/projects/${projectId}/tramos/${tramoId}`, {
    method: 'DELETE',
  }, 'No se pudo eliminar el tramo');
};

export const duplicateTramo = async (
  authFetch: AuthFetch,
  projectId: number,
  tramoId: number,
): Promise<TramoRecord> => {
  return requestJson(authFetch,
    `/api/projects/${projectId}/tramos/${tramoId}/duplicate`,
    { method: 'POST' }, 'No se pudo duplicar el tramo');
};

/** Lightweight tramo returned by the list endpoint (no config_json / result_json). */
export interface TramoSummary {
  id: number;
  project_id: number;
  name: string;
  parent_section_id?: number | null;
  base_name?: string | null;
  variant_name?: string | null;
  sort_order?: number;
  description?: string | null;
  last_calculated_at?: string | null;
  has_pdf: boolean;
  has_excel: boolean;
  document_ids: { pdf?: number; excel?: number };
  compliance_summary?: { compliant?: boolean; Lavg?: number; Uo?: number; Ul?: number; TI?: number; SR?: number; EIR?: number; Eavg?: number; Emin?: number; criteria_passed?: Record<string, boolean> } | null;
  status: string;
  has_result: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BulkCalculateFailure {
  id: number;
  name: string;
  error: string;
}

export interface BulkCalculateProgressItem {
  id: number;
  name: string;
  status: string;
  error?: string | null;
  compliant?: boolean | null;
}

export interface BulkCalculateStatus {
  batch_id: string;
  total: number;
  completed: number;
  failed: number;
  cancelled: boolean;
  items: BulkCalculateProgressItem[];
}

export const listTramos = async (
  authFetch: AuthFetch,
  projectId: number,
): Promise<TramoSummary[]> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos`, undefined, 'No se pudieron cargar los tramos');
};

export const startBulkCalculate = async (
  authFetch: AuthFetch,
  projectId: number,
  ids: number[],
  margenLavg = 0,
): Promise<BulkCalculateStatus> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos/bulk-calculate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, margen_lavg: margenLavg }),
  }, 'No se pudo iniciar el cálculo');
};

export const pollBulkProgress = async (
  authFetch: AuthFetch,
  projectId: number,
  batchId: string,
): Promise<BulkCalculateStatus> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos/bulk-calculate/${batchId}/progress`, undefined, 'Error al consultar progreso');
};

export const cancelBulkCalculate = async (
  authFetch: AuthFetch,
  projectId: number,
  batchId: string,
): Promise<BulkCalculateStatus> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos/bulk-calculate/${batchId}/cancel`, {
    method: 'POST',
  }, 'No se pudo parar el cálculo');
};

export const bulkDeleteTramos = async (
  authFetch: AuthFetch,
  projectId: number,
  ids: number[],
): Promise<{ deleted: number }> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  }, 'No se pudieron eliminar los tramos');
};

export const downloadTramoDocument = async (
  authFetch: AuthFetch,
  projectId: number,
  tramoId: number,
  documentId: number,
): Promise<Blob> => {
  return requestBlob(authFetch,
    `/api/projects/${projectId}/tramos/${tramoId}/documents/${documentId}/download`,
    undefined, 'No se pudo descargar el documento');
};

export const downloadBatchPdf = async (
  authFetch: AuthFetch,
  tramoIds: number[],
): Promise<Blob> => {
  return requestBlob(authFetch, '/api/report/pdf-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tramo_ids: tramoIds }),
  }, 'No se pudo generar el PDF batch');
};

export const downloadBatchExcel = async (
  authFetch: AuthFetch,
  tramoIds: number[],
): Promise<Blob> => {
  return requestBlob(authFetch, '/api/report/excel-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tramo_ids: tramoIds }),
  }, 'No se pudo generar el Excel batch');
};

export interface TramoBulkImportPayload {
  name?: string | null;
  description?: string | null;
  config: Record<string, unknown>;
}

export interface TramoBulkImportResultItem {
  row: number;
  name: string;
  status: 'created' | 'error';
  tramo?: TramoRecord;
  error?: string;
}

export interface TramoBulkImportResponse {
  created: number;
  failed: number;
  items: TramoBulkImportResultItem[];
}

export const bulkImportTramos = async (
  authFetch: AuthFetch,
  projectId: number,
  items: TramoBulkImportPayload[],
): Promise<TramoBulkImportResponse> => {
  return requestJson(authFetch, `/api/projects/${projectId}/tramos/bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  }, 'No se pudo importar los tramos');
};


