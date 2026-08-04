import type { ComplianceState } from "../layout/DecisionPanelContext";
import type { ProjectStatus } from "../api/projects";

export const COMPLIANCE_LABEL: Record<ComplianceState, string> = {
  ok: "Cumple",
  warning: "Revisar",
  danger: "No cumple",
  pending: "Pendiente",
};

export const COMPLIANCE_ICON: Record<ComplianceState, string> = {
  ok: "✓",
  warning: "!",
  danger: "✕",
  pending: "…",
};

/**
 * Traduce el estado de un proyecto (ciclo de vida) al lenguaje funcional de
 * cumplimiento común a toda la suite (sección 9 del Design System).
 */
export function complianceForProjectStatus(status: ProjectStatus): ComplianceState {
  if (status === "validated" || status === "released") return "ok";
  if (status === "blocked" || status === "cancelled") return "danger";
  if (status === "in_review" || status === "observed") return "warning";
  return "pending";
}
