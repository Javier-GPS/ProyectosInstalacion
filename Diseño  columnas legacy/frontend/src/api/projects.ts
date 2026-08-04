import { apiClient } from "./client";

export type ProjectStatus =
  | "draft"
  | "in_preparation"
  | "in_review"
  | "observed"
  | "validated"
  | "released"
  | "archived"
  | "cancelled"
  | "blocked";

export type MaturityLevel = "M0" | "M1" | "M2" | "M3" | "M4";

export interface Project {
  id: string;
  project_code: string;
  name: string;
  country: string;
  language: string;
  currency: string;
  timezone: string;
  confidentiality: string;
  status: ProjectStatus;
  maturity: MaturityLevel;
  owner_user_id: string;
  customer_id: string | null;
  opportunity_ref: string | null;
  description: string | null;
  region: string | null;
  cloned_from_id: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface PaginatedProjects {
  items: Project[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ProjectCreateInput {
  name: string;
  country: string;
  language?: string;
  currency?: string;
  timezone?: string;
  confidentiality?: string;
  description?: string;
  region?: string;
}

export interface Revision {
  id: string;
  project_id: string;
  revision_code: string;
  revision_type: string;
  maturity: MaturityLevel;
  description: string | null;
  change_summary: string | null;
  is_frozen: boolean;
}

export interface RevisionCreateInput {
  revision_code: string;
  revision_type?: "draft" | "technical" | "client" | "production" | "as_built";
  description?: string;
  change_summary?: string;
}

export async function listProjects(): Promise<PaginatedProjects> {
  const { data } = await apiClient.get<PaginatedProjects>("/projects");
  return data;
}

export async function getProject(projectId: string): Promise<Project> {
  const { data } = await apiClient.get<Project>(`/projects/${projectId}`);
  return data;
}

export async function createProject(input: ProjectCreateInput): Promise<Project> {
  const { data } = await apiClient.post<Project>("/projects", input);
  return data;
}

export async function transitionProjectStatus(
  projectId: string,
  targetStatus: ProjectStatus,
  reason: string,
): Promise<Project> {
  const { data } = await apiClient.post<Project>(`/projects/${projectId}/status`, {
    target_status: targetStatus,
    reason,
  });
  return data;
}

export async function listRevisions(projectId: string): Promise<{ items: Revision[] }> {
  const { data } = await apiClient.get<{ items: Revision[] }>(`/projects/${projectId}/revisions`);
  return data;
}

export async function createRevision(
  projectId: string,
  input: RevisionCreateInput,
): Promise<Revision> {
  const { data } = await apiClient.post<Revision>(`/projects/${projectId}/revisions`, input);
  return data;
}
